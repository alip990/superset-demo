#!/bin/sh
# Call setupJalali() at the end of Superset's own formatter setup. This is the
# only entry point the plugin needs: the embedded-dashboard bundle runs the same
# setup, so iframes get the Jalali calendar too.
set -e
f=src/setup/setupFormatters.ts
test -f "$f" || { echo "jalali: $f not found (run from superset-frontend/)"; exit 1; }
if grep -q setupJalali "$f"; then
  exit 0
fi
# ES imports are hoisted, so appending keeps the license header at the top
echo "import setupJalali from 'src/jalali';" >> "$f"
# setupFormatters() ends with ".setDefaultKey(SMART_DATE_ID);\n}": register right
# before the closing brace, after every built-in formatter exists
perl -0pi -e 's/(\.setDefaultKey\(SMART_DATE_ID\);\n)\}/$1\n  setupJalali();\n}/' "$f"
grep -q 'setupJalali();' "$f" || {
  echo "jalali: could not hook setupJalali() into $f"; exit 1; }
