#!/bin/sh
# Show the resolved time range in Jalali in the control's pill, its tooltip and
# the popover's "Actual time range" line.
#
# The label asks fetchTimeRange() what the range resolves to; the server answers
# in ISO Gregorian (correctly - that is what the query uses), so the wrapper in
# src/jalali rewrites the dates for display only.
set -e
f=src/explore/components/controls/DateFilterControl/DateFilterLabel.tsx
test -f "$f" || { echo "jalali: $f not found (run from superset-frontend/)"; exit 1; }
if grep -q "from 'src/jalali'" "$f"; then
  exit 0
fi
grep -q '^  fetchTimeRange,$' "$f" || {
  echo "jalali: $f no longer imports fetchTimeRange on its own line"; exit 1; }
perl -0pi -e 's/^  fetchTimeRange,\n//m' "$f"
echo "import { fetchTimeRange } from 'src/jalali';" >> "$f"
grep -q "import { fetchTimeRange } from 'src/jalali';" "$f" || {
  echo "jalali: could not swap fetchTimeRange in $f"; exit 1; }
! grep -q '^  fetchTimeRange,$' "$f" || {
  echo "jalali: fetchTimeRange is still imported from @superset-ui/core"; exit 1; }
