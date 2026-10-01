# plugins/

- `superset-jalali/`: the **browser half** of the Jalali (Persian) calendar - time formats, the Jalali shortcuts
  of the date-filter popover, and the Jalali month-grid date picker. Built into the Superset image by
  `superset/Dockerfile`; the server half is `superset/jalali_calendar/` and needs no custom image. See
  [../JALALI_CALENDAR.md](../JALALI_CALENDAR.md).

All charts are built-in Superset chart types. See the "Plugins" section of the top-level README for how to add a
chart plugin.
