"""One clock contract for filtering, macros and PostgreSQL bucketing.

Serialized Superset strings are Gregorian, naive storage-clock timestamps.
UTC storage is explicit; ``wall`` preserves legacy local timestamp columns.
IANA rules are used for UTC storage. shift_minutes is legacy fixed-offset mode,
not a substitute for Asia/Tehran's historical daylight saving rules.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc

@dataclass(frozen=True)
class CalendarClock:
    storage_timezone: str = 'wall'
    business_timezone: str = 'Asia/Tehran'
    shift_minutes: int = 0

    def __post_init__(self):
        if self.storage_timezone not in ('wall', 'UTC'):
            raise ValueError('storage_timezone must be wall or UTC')
        ZoneInfo(self.business_timezone)
        if not isinstance(self.shift_minutes, int) or abs(self.shift_minutes) > 1440:
            raise ValueError('shift_minutes must be an integer within one day')
        if self.storage_timezone == 'UTC' and self.shift_minutes:
            raise ValueError('Use an IANA business_timezone OR legacy shift_minutes, not both')

    @property
    def zone(self):
        return (dt.timezone(dt.timedelta(minutes=self.shift_minutes))
                if self.shift_minutes else ZoneInfo(self.business_timezone))

    def now(self, value: dt.datetime | str | None = None) -> dt.datetime:
        if isinstance(value, str):
            value = dt.datetime.fromisoformat(value)
        if value is None:
            value = dt.datetime.now(UTC)
        # Explicit naive anchors denote business wall time, never the machine zone.
        if value.tzinfo is None:
            return value
        return value.astimezone(self.zone).replace(tzinfo=None)

    def to_storage(self, wall: dt.datetime, *, boundary: bool = False) -> dt.datetime:
        if wall.tzinfo is not None:
            raise ValueError('Expected naive business wall time')
        if self.shift_minutes:
            return wall - dt.timedelta(minutes=self.shift_minutes)
        if self.storage_timezone == 'wall':
            return wall
        # Round-trip each fold: reject nonexistent/ambiguous typed date-times.
        candidates = set()
        for fold in (0, 1):
            instant = wall.replace(tzinfo=self.zone, fold=fold).astimezone(UTC)
            if instant.astimezone(self.zone).replace(tzinfo=None) == wall:
                candidates.add(instant)
        if len(candidates) == 1:
            return candidates.pop().replace(tzinfo=None)
        if boundary:
            if candidates:
                return min(candidates).replace(tzinfo=None)
            # A calendar day can begin after 00:00 during a midnight DST jump.
            for minute in range(1, 181):
                try:
                    return self.to_storage(wall + dt.timedelta(minutes=minute))
                except ValueError:
                    continue
        raise ValueError(f'Ambiguous or nonexistent business time: {wall} {self.business_timezone}')

    def from_storage(self, value: dt.datetime) -> dt.datetime:
        if self.shift_minutes:
            return value + dt.timedelta(minutes=self.shift_minutes)
        if self.storage_timezone == 'wall':
            return value.replace(tzinfo=None)
        instant = value.replace(tzinfo=UTC) if value.tzinfo is None else value
        return instant.astimezone(self.zone).replace(tzinfo=None)

def from_options(options: dict) -> CalendarClock:
    return CalendarClock(**{k: options[k] for k in
        ('storage_timezone', 'business_timezone', 'shift_minutes') if k in options})

def current() -> CalendarClock:
    # Pure calendar tests need neither Flask nor a running Superset.
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            return from_options(current_app.config.get('JALALI_CALENDAR_OPTIONS') or {})
    except ImportError:
        pass
    return CalendarClock()
