#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
ACTIVE="$ROOT/dist/backend-active"
ARCHIVE="$ROOT/dist/backend-archive"
STAGING="$ROOT/dist/backend-staging"

usage() { echo "usage: $0 install VERSION | local /path/to/wheel | rollback [VERSION] | remove" >&2; exit 2; }
restart_lab() {
  docker compose -f "$ROOT/deployment/independent/compose.yaml" restart web
}
set_backend_enabled() {
  value=$1 python3 - "$ROOT/deployment/independent/.state/lab.env" <<'PY'
import os, pathlib, sys
path=pathlib.Path(sys.argv[1])
lines=path.read_text().splitlines()
lines=[line for line in lines if not line.startswith('JALALI_BACKEND_ENABLED=')]
lines.append('JALALI_BACKEND_ENABLED='+os.environ['value'])
path.write_text('\n'.join(lines)+'\n')
path.chmod(0o600)
PY
}
checked_wheel() {
  WHEEL_PATH=$1 EXPECTED=$2 python3 - <<'PY'
import email, os, sys, zipfile
path, expected = os.environ['WHEEL_PATH'], os.environ['EXPECTED']
with zipfile.ZipFile(path) as wheel:
    names=[n for n in wheel.namelist() if n.endswith('.dist-info/METADATA')]
    if len(names)!=1: raise SystemExit('wheel must contain exactly one metadata file')
    metadata=email.message_from_bytes(wheel.read(names[0]))
    if metadata['Name']!='superset-jalali-backend' or metadata['Version']!=expected:
        raise SystemExit(f"artifact metadata mismatch: {metadata['Name']} {metadata['Version']}")
PY
}
archive_active() {
  set -- "$ACTIVE"/*.whl
  [ -e "$1" ] || return 0
  [ "$#" -eq 1 ] || { echo 'Expected exactly one active backend wheel' >&2; exit 1; }
  archived_version=${1##*superset_jalali_backend-}
  archived_version=${archived_version%%-*}
  mkdir -p "$ARCHIVE/$archived_version"
  archived_file="$ARCHIVE/$archived_version/${1##*/}"
  if [ -e "$archived_file" ]; then
    cmp -s -- "$1" "$archived_file" || {
      echo "Refusing to overwrite different artifact for version $archived_version" >&2
      exit 1
    }
    rm -- "$1"
  else
    mv -- "$1" "$archived_file"
  fi
}
install_file() {
  file=$1 version=$2
  checked_wheel "$file" "$version"
  mkdir -p "$ACTIVE" "$ARCHIVE" "$STAGING"
  archive_active
  temp="$ACTIVE/.new-wheel"
  cp -- "$file" "$temp"
  mv -- "$temp" "$ACTIVE/superset_jalali_backend-$version-py3-none-any.whl"
  set_backend_enabled 1
  restart_lab
  printf 'Installed %s; previous wheel is under %s\n' "$version" "$ARCHIVE"
}

case ${1:-} in
  install)
    [ "$#" -eq 2 ] || usage
    version=$2
    case $version in *[!0-9.]*|.*|*.) usage;; esac
    [ -n "${GITHUB_REPOSITORY:-}" ] || { echo 'Set GITHUB_REPOSITORY (owner/repository)' >&2; exit 2; }
    [ -n "${GH_TOKEN:-}" ] || { echo 'Set GH_TOKEN with private release read access' >&2; exit 2; }
    command -v gh >/dev/null && command -v sha256sum >/dev/null || { echo 'Install GitHub CLI and sha256sum' >&2; exit 2; }
    release="jalali-backend-v$version"
    mkdir -p "$STAGING/$version"
    GH_TOKEN=$GH_TOKEN gh release download "$release" --repo "$GITHUB_REPOSITORY" \
      --dir "$STAGING/$version" --pattern "superset_jalali_backend-$version-*.whl" \
      --pattern SHASUMS256.txt
    (cd "$STAGING/$version" && sha256sum -c SHASUMS256.txt)
    set -- "$STAGING/$version"/superset_jalali_backend-"$version"-*.whl
    [ -f "$1" ] && [ "$#" -eq 1 ] || { echo 'Release must contain exactly one compatible wheel' >&2; exit 1; }
    install_file "$1" "$version"
    ;;
  local)
    [ "$#" -eq 2 ] || usage
    file=$(CDPATH= cd -- "$(dirname "$2")" && pwd)/$(basename "$2")
    version=$(python3 - "$file" <<'PY'
import email,sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
 p=next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))
 print(email.message_from_bytes(z.read(p))['Version'])
PY
)
    case ${file##*/} in
      "superset_jalali_backend-$version-"*.whl) ;;
      *) echo 'Wheel filename must agree with its embedded version metadata' >&2; exit 1;;
    esac
    install_file "$file" "$version"
    ;;
  rollback)
    [ "$#" -le 2 ] || usage
    if [ "$#" -eq 2 ]; then
      version=$2
      case $version in *[!0-9.]*|.*|*.) usage;; esac
      set -- "$ARCHIVE/$version"/*.whl
    else
      set -- "$ARCHIVE"/*/*.whl
    fi
    [ -e "$1" ] && [ "$#" -eq 1 ] || {
      echo 'Specify a rollback version when the archive contains zero or multiple candidates' >&2
      exit 1
    }
    version=${1##*superset_jalali_backend-}; version=${version%%-*}
    file=$1; checked_wheel "$file" "$version"; mkdir -p "$ACTIVE"
    set -- "$ACTIVE"/*.whl
    if [ -e "$1" ]; then
      [ "$#" -eq 1 ] || { echo 'Expected exactly one active backend wheel' >&2; exit 1; }
      current_version=${1##*superset_jalali_backend-}; current_version=${current_version%%-*}
      [ "$current_version" != "$version" ] || { echo "Version $version is already active" >&2; exit 1; }
    fi
    archive_active; cp -- "$file" "$ACTIVE/.rollback-wheel"
    mv -- "$ACTIVE/.rollback-wheel" "$ACTIVE/superset_jalali_backend-$version-py3-none-any.whl"
    set_backend_enabled 1
    restart_lab; printf 'Rolled back to %s\n' "$version"
    ;;
  remove)
    [ "$#" -eq 1 ] || usage
    archive_active; set_backend_enabled 0; restart_lab
    echo 'Backend wheel removed from the extension mount and disabled.'
    ;;
  *) usage;;
esac
