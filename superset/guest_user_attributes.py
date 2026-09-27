# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Guest-token user attributes on Superset 6.1.0 - a backport of apache/superset master.

Upstream master carries arbitrary `user.attributes` on a guest token and exposes them
to dataset SQL / RLS templates through the `get_guest_user_attribute()` Jinja macro.
Neither has shipped in a release yet, so on 6.1.0:

  * `POST /api/v1/security/guest_token/` silently DROPS `user.attributes` -
    `UserSchema` inherits `PermissiveSchema`, whose `Meta.unknown` is `EXCLUDE`; and
  * there is no `get_guest_user_attribute` macro to read them back.

`install()` adds both, patching exactly the places upstream changed:

  superset.security.api.UserSchema                          + attributes field
  superset.jinja_context.ExtraCache                          + get_guest_user_attribute()
  superset.jinja_context.ExtraCache.regex                    + get_guest_user_attribute(...)
  superset.jinja_context.JinjaTemplateProcessor.set_context   exposes the macro

The regex is what makes the feature safe to cache, and is the reason this cannot be
done with `JINJA_CONTEXT_ADDONS` alone. `SqlaTable.has_extra_cache_key_calls()` only
re-renders a dataset's SQL to collect extra cache keys when that regex matches the
SQL; a macro it does not know about never contributes to the cache key, so two
tenants querying the same virtual dataset collide on one cache entry and the second
one is served the first one's rows. Registering the macro as a bound method of the
request's own `ExtraCache` lets it call `cache_key_wrapper()`, which is what keeps
tenants on separate cache entries - with this in place the data cache can stay on.

Wire it up from superset_config.py:

    def FLASK_APP_MUTATOR(app):
        from guest_user_attributes import install
        install()

then mint tokens with attributes:

    {"user": {"username": "u1", "attributes": {"allowed_companies": [3, 4]}}, ...}

and read them in a virtual dataset:

    SELECT * FROM bi.violation WHERE 1=1
    {% set allowed = get_guest_user_attribute('allowed_companies', escape_result=False) %}
    {% if allowed %} AND company_id IN {{ allowed | where_in }}
    {% else %}       AND 1=0  -- failsafe: no attribute, no rows
    {% endif %}

One deliberate deviation from upstream: upstream returns list and dict attributes as
`SQLSafeList` / `SQLSafeDict`, whose whole-container `str()` joins the already-escaped
elements instead of going through Python's `repr()`. This backport returns plain lists and
dicts, because 6.1.0's `safe_proxy()` rejects return types outside `ALLOWED_TYPES` and
round-trips collections through `json`, which would undo the subclass anyway. Escaping of
individual string leaves is identical; what differs is interpolating a *whole* container,
where Python's repr adds quote delimiters that were never escaped for SQL. So interpolate
a list through `| where_in` (as the datasets here do) and index into a dict
(`{{ get_guest_user_attribute('cfg')['theme'] }}`) rather than rendering either wholesale.

Ported from (Apache-2.0):
  https://github.com/apache/superset/blob/master/superset/jinja_context.py
  https://github.com/apache/superset/blob/master/superset/security/api.py
"""

from __future__ import annotations

import json
import logging
import re
from functools import partial
from typing import Any, Union

logger = logging.getLogger(__name__)

# Every type a JSON attribute can hold, matching upstream's JsonValue alias.
JsonValue = Union[None, bool, int, float, str, list, dict]

# The alternative added to ExtraCache.regex, anchored on url_param's so the patch
# fails loudly if a future version rewrites the pattern out from under it.
_ANCHOR = r"url_param\([^)]*\)"
_ADDED = r"url_param\([^)]*\)|get_guest_user_attribute\([^)]*\)"


def _normalize_postgresql_backslash_escapes(dialect: Any) -> None:
    """Stop a connection-less PostgreSQL dialect from doubling backslashes.

    A dialect built without a live connection (which `Database.get_dialect()` does)
    defaults `_backslash_escapes` to True, so rendering `C:\\Users` as a literal
    would produce `C:\\\\Users` and silently stop matching. Every supported
    PostgreSQL treats the backslash as a plain character
    (`standard_conforming_strings` has been on since 9.1). Dialects that really do
    escape backslashes, such as MySQL, are left alone.
    """
    if dialect is not None and dialect.name == "postgresql":
        dialect._backslash_escapes = False  # pylint: disable=protected-access


def _escape_value(self: Any, value: JsonValue) -> JsonValue:
    """Dialect-escape every string leaf, the way 6.1.0's `url_param()` escapes its own.

    Strings nested in lists and dict values are escaped too, since a template can
    interpolate them one at a time. Non-string JSON types pass through untouched.
    """
    # pylint: disable=import-outside-toplevel
    from sqlalchemy.types import String

    if self.dialect is None:
        return value
    if isinstance(value, str):
        _normalize_postgresql_backslash_escapes(self.dialect)
        # literal_processor wraps the value in quotes; keep only the escaped body,
        # because the template supplies its own quoting.
        return String().literal_processor(dialect=self.dialect)(value=value)[1:-1]
    if isinstance(value, list):
        return [_escape_value(self, item) for item in value]
    if isinstance(value, dict):
        return {
            _escape_value(self, key): _escape_value(self, item)
            for key, item in value.items()
        }
    return value


def get_guest_user_attribute(
    self: Any,
    attribute_name: str,
    default: JsonValue = None,
    add_to_cache_keys: bool = True,
    escape_result: bool = True,
) -> JsonValue:
    """Read one attribute off the guest token, for use in dataset SQL and RLS clauses.

    Supports every JSON-native type: string, number, boolean, array, object, null.

    :param attribute_name: name of the attribute to read
    :param default: value to return when the attribute (or the guest token) is absent
    :param add_to_cache_keys: whether the resolved value joins the query's cache key.
        It is keyed on every branch - attribute, default, and null - because a guest
        whose attribute is missing renders different SQL from one whose attribute is
        set, so both have to be distinguishable. Only turn this off for a value that
        cannot change the result set.
    :param escape_result: escape string values (including strings inside lists and
        object values) through the dialect's literal rendering, mirroring `url_param`.
        Pass False when piping a list through the `where_in` filter, which does its
        own dialect-safe quoting - leaving it on would escape each value twice.
    :returns: the attribute value, or `default`

    Examples::

        {{ get_guest_user_attribute('department') }}            # "Engineering"
        {{ get_guest_user_attribute('is_admin') }}              # True
        {{ get_guest_user_attribute('missing', 'fallback') }}    # "fallback"
        company_id IN {{ get_guest_user_attribute('allowed_companies',
                                                  escape_result=False) | where_in }}
    """
    # pylint: disable=import-outside-toplevel
    from flask import g
    from superset import security_manager

    result: JsonValue = default
    # Guest tokens only exist for embedded users; is_guest_user() does the
    # feature-flag and request-context checks itself.
    if security_manager.is_guest_user():
        token = g.user.guest_token or {}
        user_attributes = (token.get("user") or {}).get("attributes") or {}
        result = user_attributes.get(attribute_name, default)

    if add_to_cache_keys:
        # json.dumps gives a stable serialisation across all JSON-native types;
        # default=str keeps an exotic template-supplied default from raising here.
        cache_value = json.dumps(result, sort_keys=True, default=str)
        self.cache_key_wrapper(f"guest_user_attribute:{attribute_name}:{cache_value}")

    if escape_result:
        result = self._escape_value(result)  # pylint: disable=protected-access
    return result


def _patch_user_schema() -> None:
    """Stop the guest-token endpoint from dropping `user.attributes`."""
    # pylint: disable=import-outside-toplevel
    from marshmallow import fields

    from superset.security import api as security_api

    if "attributes" in security_api.UserSchema._declared_fields:  # noqa: SLF001
        return
    security_api.UserSchema._declared_fields["attributes"] = fields.Dict(  # noqa: SLF001
        keys=fields.String(), values=fields.Raw(allow_none=True), allow_none=True
    )
    # The endpoint loads request bodies through a module-level schema instance built
    # at import time, which deep-copied the declared fields as they were then; rebuild
    # it so its nested UserSchema picks the new field up.
    security_api.guest_token_create_schema = security_api.GuestTokenCreateSchema()


def _patch_extra_cache() -> None:
    """Add the macro to ExtraCache and teach the cache-key detector about it."""
    # pylint: disable=import-outside-toplevel
    from superset.jinja_context import ExtraCache

    if not hasattr(ExtraCache, "_escape_value"):
        ExtraCache._escape_value = _escape_value  # noqa: SLF001
    if not hasattr(ExtraCache, "get_guest_user_attribute"):
        ExtraCache.get_guest_user_attribute = get_guest_user_attribute

    pattern = ExtraCache.regex.pattern
    if "get_guest_user_attribute" in pattern:
        return
    patched = pattern.replace(_ANCHOR, _ADDED)
    if patched == pattern:
        # Refuse to run half-patched: without this alternative the macro's value
        # never reaches the cache key, and one tenant can be served another's rows.
        raise RuntimeError(
            "guest_user_attributes: could not extend ExtraCache.regex - "
            "this Superset's pattern no longer contains the url_param anchor. "
            "Re-derive the patch against superset/jinja_context.py before running "
            "with a data cache enabled."
        )
    ExtraCache.regex = re.compile(patched)


def _patch_template_processor() -> None:
    """Expose the macro, bound to each render's own ExtraCache."""
    # pylint: disable=import-outside-toplevel
    from superset import jinja_context

    processor = jinja_context.JinjaTemplateProcessor
    if getattr(processor.set_context, "_guest_attributes_patched", False):
        return
    original_set_context = processor.set_context

    def set_context(self: Any, **kwargs: Any) -> None:
        original_set_context(self, **kwargs)
        # The macro must be the bound method of *this* render's ExtraCache, so its
        # cache_key_wrapper() calls land in this query's extra cache keys. That
        # instance is a local in the original set_context, so recover it from a
        # macro it already bound.
        wrapper = self._context.get("cache_key_wrapper")  # noqa: SLF001
        bound = (getattr(wrapper, "args", None) or (None,))[0]
        extra_cache = getattr(bound, "__self__", None)
        if extra_cache is None:
            logger.warning(
                "guest_user_attributes: no ExtraCache in the template context; "
                "get_guest_user_attribute() is unavailable for this render"
            )
            return
        self._context["get_guest_user_attribute"] = partial(  # noqa: SLF001
            jinja_context.safe_proxy, extra_cache.get_guest_user_attribute
        )

    set_context._guest_attributes_patched = True  # noqa: SLF001
    processor.set_context = set_context


def install() -> None:
    """Idempotently patch the running Superset. Call from FLASK_APP_MUTATOR."""
    _patch_user_schema()
    _patch_extra_cache()
    _patch_template_processor()
    logger.info("guest_user_attributes: guest-token user attributes enabled")
