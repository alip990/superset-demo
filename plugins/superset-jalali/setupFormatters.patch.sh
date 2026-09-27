#!/bin/sh
# Hooks the Jalali formatters into Superset's frontend setup (run inside superset-frontend/).
set -e
f=src/setup/setupFormatters.ts
grep -q registerJalaliFormatters "$f" && exit 0
# ES imports are hoisted, so appending it keeps the license header intact
echo "import registerJalaliFormatters from 'src/jalali';" >> "$f"
# setupFormatters() ends with "setDefaultKey(SMART_DATE_ID);\n}" - register right before the closing brace
perl -0pi -e 's/(\.setDefaultKey\(SMART_DATE_ID\);\n)\}/$1\n  registerJalaliFormatters();\n}/' "$f"
grep -q 'registerJalaliFormatters();' "$f"
