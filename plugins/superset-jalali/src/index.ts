/**
 * Jalali (Persian / Solar Hijri) date formatters for the Superset frontend.
 *
 * Copied into superset-frontend/src/jalali/ by superset/Dockerfile and called at the
 * end of src/setup/setupFormatters.ts. It
 *  - registers named time formats (jalali_date, jalali_datetime, jalali_month, ...)
 *    that can be picked in any chart's "Time format" / "X axis time format" control;
 *  - when the feature flag JALALI_CALENDAR is on, replaces Superset's adaptive
 *    formatters (smart_date, its tooltip and detailed variants) so every chart that
 *    uses the default time format shows Jalali dates.
 *
 * Conversion uses the browser's built-in calendar (Intl, "fa-IR-u-ca-persian"), so
 * it works for data from any database. Dates are formatted in UTC, like Superset's
 * own formatters: timestamps from the database are naive, e.g. Tehran local time.
 */
import {
  getTimeFormatterRegistry,
  SMART_DATE_DETAILED_ID,
  SMART_DATE_ID,
  SMART_DATE_VERBOSE_ID,
  TimeFormatter,
} from '@superset-ui/core';
import { D3_TIME_FORMAT_OPTIONS } from '@superset-ui/chart-controls';
import getBootstrapData from 'src/utils/getBootstrapData';

export const JALALI_DATE_ID = 'jalali_date';
export const JALALI_DATETIME_ID = 'jalali_datetime';
export const JALALI_MONTH_ID = 'jalali_month';
export const JALALI_YEAR_ID = 'jalali_year';
export const JALALI_SMART_ID = 'jalali_smart';
export const JALALI_VERBOSE_ID = 'jalali_verbose';

// Persian month and weekday names, Latin digits (so they match Superset's number formats)
const LOCALE = 'fa-IR-u-ca-persian-nu-latn';
const numericParts = new Intl.DateTimeFormat(LOCALE, {
  timeZone: 'UTC',
  year: 'numeric',
  month: 'numeric',
  day: 'numeric',
});
const nameParts = new Intl.DateTimeFormat(LOCALE, {
  timeZone: 'UTC',
  month: 'long',
  weekday: 'long',
});

export interface JalaliParts {
  year: number;
  month: number; // 1..12
  day: number; // 1..31
  monthName: string; // فروردین ... اسفند
  weekday: string; // شنبه ... جمعه
  hours: number;
  minutes: number;
  seconds: number;
}

export function jalaliParts(date: Date): JalaliParts {
  const n: Record<string, string> = {};
  numericParts.formatToParts(date).forEach(p => {
    n[p.type] = p.value;
  });
  const t: Record<string, string> = {};
  nameParts.formatToParts(date).forEach(p => {
    t[p.type] = p.value;
  });
  return {
    year: parseInt(n.year, 10),
    month: parseInt(n.month, 10),
    day: parseInt(n.day, 10),
    monthName: t.month,
    weekday: t.weekday,
    hours: date.getUTCHours(),
    minutes: date.getUTCMinutes(),
    seconds: date.getUTCSeconds(),
  };
}

const pad = (v: number) => String(v).padStart(2, '0');
const ymd = (p: JalaliParts) => `${p.year}-${pad(p.month)}-${pad(p.day)}`;
const hm = (p: JalaliParts) => `${pad(p.hours)}:${pad(p.minutes)}`;
const hasTime = (p: JalaliParts) => p.hours || p.minutes || p.seconds;

/** 1403-12-20 */
export const formatJalaliDate = (d: Date) => ymd(jalaliParts(d));
/** 1403-12-20 14:32:05 */
export const formatJalaliDateTime = (d: Date) => {
  const p = jalaliParts(d);
  return `${ymd(p)} ${hm(p)}:${pad(p.seconds)}`;
};
/** اسفند 1403 */
export const formatJalaliMonth = (d: Date) => {
  const p = jalaliParts(d);
  return `${p.monthName} ${p.year}`;
};
/** 1403 */
export const formatJalaliYear = (d: Date) => String(jalaliParts(d).year);

/**
 * Axis labels, like smart_date but on Jalali boundaries: a time of day if there is
 * one, the year on 1 Farvardin, the month name on the 1st of a Jalali month,
 * otherwise day + month ("20 اسفند"). Axis ticks fall on Gregorian boundaries
 * (ECharts picks them), so a label only shows a month alone when the tick really
 * is the 1st of that Jalali month.
 */
export const formatJalaliSmart = (d: Date) => {
  const p = jalaliParts(d);
  if (d.getUTCMilliseconds() || p.seconds) return `${hm(p)}:${pad(p.seconds)}`;
  if (p.hours || p.minutes) return hm(p);
  if (p.day === 1 && p.month === 1) return String(p.year);
  if (p.day === 1) return p.monthName;
  return `${p.day} ${p.monthName}`;
};

/** Tooltips: "دوشنبه 20 اسفند 1403" (+ " 14:32" if there is a time of day) */
export const formatJalaliVerbose = (d: Date) => {
  const p = jalaliParts(d);
  const date = `${p.weekday} ${p.day} ${p.monthName} ${p.year}`;
  return hasTime(p) ? `${date} ${hm(p)}` : date;
};

const FORMATS: [string, string, (d: Date) => string][] = [
  [JALALI_SMART_ID, 'Jalali adaptive | 20 اسفند', formatJalaliSmart],
  [JALALI_DATE_ID, 'Jalali date | 1403-12-20', formatJalaliDate],
  [JALALI_DATETIME_ID, 'Jalali date time | 1403-12-20 14:32:05', formatJalaliDateTime],
  [JALALI_MONTH_ID, 'Jalali month | اسفند 1403', formatJalaliMonth],
  [JALALI_YEAR_ID, 'Jalali year | 1403', formatJalaliYear],
  [JALALI_VERBOSE_ID, 'Jalali verbose | دوشنبه 20 اسفند 1403', formatJalaliVerbose],
];

const formatter = (id: string, label: string, formatFunc: (d: Date) => string) =>
  new TimeFormatter({ id, label, formatFunc, useLocalTime: false });

export default function registerJalaliFormatters() {
  const registry = getTimeFormatterRegistry();
  FORMATS.forEach(([id, label, func]) => {
    registry.registerValue(id, formatter(id, label, func));
    // offered in every chart's time format dropdown (the array is shared by all control panels)
    if (!D3_TIME_FORMAT_OPTIONS.some(([value]) => value === id)) {
      D3_TIME_FORMAT_OPTIONS.push([id, label]);
    }
  });

  // FEATURE_FLAGS = {"JALALI_CALENDAR": True} in superset_config.py: Jalali by default
  const flags = getBootstrapData().common?.feature_flags as unknown as
    | Record<string, boolean>
    | undefined;
  if (flags?.JALALI_CALENDAR) {
    registry
      .registerValue(SMART_DATE_ID, formatter(SMART_DATE_ID, 'Adaptive formatting (Jalali)', formatJalaliSmart))
      .registerValue(SMART_DATE_VERBOSE_ID, formatter(SMART_DATE_VERBOSE_ID, 'Jalali verbose', formatJalaliVerbose))
      .registerValue(SMART_DATE_DETAILED_ID, formatter(SMART_DATE_DETAILED_ID, 'Jalali detailed', formatJalaliDateTime));
  }
}
