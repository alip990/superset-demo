#!/bin/sh
# Hook the Jalali plugin into Superset's frontend. Run from superset-frontend/
# after copying plugins/superset-jalali/src/ to src/jalali/ (superset/Dockerfile
# does both). Idempotent: running it twice changes nothing.
#
# Every patch verifies its own result and exits non-zero if the file did not end
# up as expected, so a Superset upgrade that moved the code fails the image build
# instead of silently producing a Gregorian bundle.
set -e
dir=$(dirname "$0")
for patch in "$dir"/[0-9][0-9]-*.sh; do
  echo "jalali: applying $(basename "$patch")"
  sh "$patch"
done
echo "jalali: frontend patched"
