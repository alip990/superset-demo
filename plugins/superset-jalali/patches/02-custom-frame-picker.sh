#!/bin/sh
# Put the Jalali date picker in the "Custom" frame of the date-filter popover.
#
# The frame uses <DatePicker> three times (start, end, anchor) and keeps the
# value as the ISO Gregorian string Superset stores, so swapping the import is
# all it takes - the component is a drop-in with the same props, and in a
# Gregorian installation it renders the antd picker it replaced.
set -e
f=src/explore/components/controls/DateFilterControl/components/CustomFrame.tsx
test -f "$f" || { echo "jalali: $f not found (run from superset-frontend/)"; exit 1; }
if grep -q "from 'src/jalali'" "$f"; then
  exit 0
fi
grep -q '^  DatePicker,$' "$f" || {
  echo "jalali: $f no longer imports DatePicker on its own line"; exit 1; }
# drop it from the component-library import, then shadow the name with ours
perl -0pi -e 's/^  DatePicker,\n//m' "$f"
echo "import { JalaliDatePicker as DatePicker } from 'src/jalali';" >> "$f"
grep -q 'JalaliDatePicker as DatePicker' "$f" || {
  echo "jalali: could not swap the date picker in $f"; exit 1; }
! grep -q '^  DatePicker,$' "$f" || {
  echo "jalali: DatePicker is still imported from the component library"; exit 1; }
