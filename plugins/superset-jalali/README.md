# superset-jalali

The browser half of the Jalali (Persian) calendar: time formatters, the Jalali
shortcuts of the date picker, and the picker itself. The server half -
time grains, the time-range vocabulary, the dataset macros - is
`superset/jalali_calendar/` and needs no custom image. Both halves and how they
fit together are described in [../../JALALI_CALENDAR.md](../../JALALI_CALENDAR.md).

## What it does

| File | Adds |
|---|---|
| `src/core/jalali.ts` | the calendar itself: conversion, leap years, period starts, formatting, parsing. No imports, no dependencies, unit-tested on its own |
| `src/formatters.ts` | Jalali entries in Superset's time-format registry, so every chart's *Time format* dropdown offers them - and, with `override_smart_date`, so existing charts turn Jalali without being edited |
| `src/ranges.ts` | the Jalali shortcuts ("ماه جاری (شمسی)", "از ابتدای سال تا امروز") in the date-filter popover of every chart and native filter |
| `src/components/JalaliDatePicker.tsx` | a Jalali month grid (Saturday first, Persian month names, optional Persian digits) that replaces the antd date picker in the popover's *Custom* frame; typing `1403/12/20` works too |
| `src/fetchTimeRange.ts` | the resolved range shown in Jalali in the control's pill, its tooltip and "Actual time range" |
| `src/options.ts` | reads `JALALI_CALENDAR_OPTIONS` from the bootstrap payload, so all of the above is configured in `superset_config.py` |

Nothing runs unless the backend published `JALALI_CALENDAR_OPTIONS` with
`enabled: true` (or `FEATURE_FLAGS["JALALI_CALENDAR"]` is set), so the same
bundle serves a Gregorian installation unchanged.

## How it reaches Superset

Superset has no runtime hook for time formatters or for the date-picker
component, so the frontend is rebuilt. `superset/Dockerfile` copies `src/` to
`superset-frontend/src/jalali/` and runs `patches/apply.sh`, three idempotent
edits of upstream files:

| Patch | File | Edit |
|---|---|---|
| `01-setup-formatters.sh` | `src/setup/setupFormatters.ts` | calls `setupJalali()` at the end |
| `02-custom-frame-picker.sh` | `.../DateFilterControl/components/CustomFrame.tsx` | imports `DatePicker` from `src/jalali` instead of the component library |
| `03-date-filter-label.sh` | `.../DateFilterControl/DateFilterLabel.tsx` | imports `fetchTimeRange` from `src/jalali` |

Each patch verifies its own result and exits non-zero otherwise, so a Superset
upgrade that moved the code **fails the image build** instead of quietly
producing a Gregorian bundle. `src/` is never installed as an npm package:
Superset's `package.json` and `package-lock.json` stay untouched, which is why
`npm ci` in the build still works. That is also why the picker is built on
Superset's own components instead of `antd-jalali`.

```bash
docker compose --profile build build superset-frontend-build   # ~8 GB RAM, 20-40 min
SUPERSET_IMAGE=superset-demo:6.1.0-jalali docker compose up -d
```

## Tests and type-check

```bash
cd plugins/superset-jalali
npm install        # typescript, @types/*, dayjs - nothing else
npm run check      # type-check + calendar tests
```

* `npm test` compiles the calendar core and runs `tests/jalali.test.ts` under
  plain Node. It asserts `../../tests/fixtures/jalali_cases.json`, which is
  generated from the Python core, so the two implementations cannot drift apart;
  it also compares every day of 1900-2200 against the browser's own Persian
  calendar (`Intl`, ICU).
* `npm run typecheck` checks the whole plugin against `types/superset.d.ts`,
  hand-written declarations of the Superset modules copied from the 6.1.0
  sources, plus `types/upstreamUsage.tsx`, which reproduces how upstream calls
  the two exports the patches redirect. This catches wrong imports, props and
  signatures without a 20-minute frontend install - it is not a substitute for
  the real build, which type-checks against the real packages.
