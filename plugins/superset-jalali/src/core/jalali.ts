/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

/**
 * Jalali (Solar Hijri / Persian) calendar arithmetic, formatting and parsing.
 *
 * Dependency-free and import-free on purpose: this file is the single source of
 * calendar truth for the whole frontend, it is unit-tested on its own (see
 * tests/), and it is a literal port of superset/jalali_calendar/core.py - both
 * sides assert tests/fixtures/jalali_cases.json, so they cannot drift apart.
 *
 * The conversion is Borkowski's algorithm, which reproduces the official
 * Iranian calendar for Jalali years 1178..1633. The first version of this
 * plugin asked the browser instead, with
 * Intl.DateTimeFormat('fa-IR-u-ca-persian'); arithmetic replaced it because
 * Intl depends on the ICU build behind the runtime (small-icu builds have no
 * Persian calendar at all), it cannot be asked about a timezone offset that is
 * not a real zone, and formatToParts() per cell is slow in a big table.
 *
 * Dates are handled in UTC, like Superset's own time formatters: a timestamp
 * from a database arrives naive and Superset renders it as if it were UTC. Where
 * the data really is UTC but the business day is Tehran's, shiftMinutes moves
 * the instant before the calendar sees it (JALALI_CALENDAR_OPTIONS.shiftMinutes).
 */

export interface JalaliDate {
  jy: number;
  jm: number; // 1..12
  jd: number; // 1..31
}

export interface JalaliTime {
  hours: number;
  minutes: number;
  seconds: number;
  milliseconds: number;
}

export type PeriodUnit = 'day' | 'week' | 'month' | 'quarter' | 'half' | 'year';

export const MONTH_NAMES = [
  'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
  'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
];
/** Index 0 is Saturday: the Iranian week. */
export const WEEKDAY_NAMES = [
  'شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه',
];
/** Short names for the calendar's weekday header. */
export const WEEKDAY_NAMES_SHORT = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];
/** Jalali quarters are the four seasons. */
export const SEASON_NAMES = ['بهار', 'تابستان', 'پاییز', 'زمستان'];

export const PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹';
const ARABIC_DIGITS = '٠١٢٣٤٥٦٧٨٩';

/** Borkowski's table spans these Jalali years. */
export const DOMAIN_MIN_YEAR = -61;
export const DOMAIN_MAX_YEAR = 3177;
/** Inside this window the result is the official Iranian calendar; literals are
 * only accepted here, which is what keeps a Gregorian date from being read as a
 * Jalali one. */
export const MIN_YEAR = 1178;
export const MAX_YEAR = 1633;

const MS_PER_DAY = 86400000;
const DAYS_BEFORE_MONTH = [0, 31, 62, 93, 124, 155, 186, 216, 246, 276, 306, 336];
const QUARTER_START_DOY0 = [0, 93, 186, 276];
const HALF_START_DOY0 = [0, 186];
const BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635,
  2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];

// Integer division and modulo truncating toward zero, as in the reference
// implementation. JS / and % already truncate, but div() must drop the fraction.
const div = (a: number, b: number) => Math.trunc(a / b);
const mod = (a: number, b: number) => a - b * div(a, b);

interface JalCal {
  leap: number; // 0 on a leap year
  gy: number;
  march: number; // 1 Farvardin falls on this day of March in gy
}

function jalCal(jy: number): JalCal {
  if (jy < BREAKS[0] || jy >= BREAKS[BREAKS.length - 1]) {
    throw new RangeError(`Jalali year out of range: ${jy}`);
  }
  const gy = jy + 621;
  let leapJ = -14;
  let jp = BREAKS[0];
  let jump = 0;
  for (let i = 1; i < BREAKS.length; i += 1) {
    const jm = BREAKS[i];
    jump = jm - jp;
    if (jy < jm) break;
    leapJ += div(jump, 33) * 8 + div(mod(jump, 33), 4);
    jp = jm;
  }
  let n = jy - jp;
  leapJ += div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
  if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;
  const leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
  const march = 20 + leapJ - leapG;
  if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
  let leap = mod(mod(n + 1, 33) - 1, 4);
  if (leap === -1) leap = 4;
  return { leap, gy, march };
}

/** Gregorian date parts -> Julian Day Number. */
function g2d(gy: number, gm: number, gd: number): number {
  const d =
    div((gy + div(gm - 8, 6) + 100100) * 1461, 4) +
    div(153 * mod(gm + 9, 12) + 2, 5) +
    gd -
    34840408;
  return d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
}

/** Julian Day Number -> Gregorian date parts. */
function d2g(jdn: number): { gy: number; gm: number; gd: number } {
  let j = 4 * jdn + 139361631;
  j += div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
  const i = div(mod(j, 1461), 4) * 5 + 308;
  const gd = div(mod(i, 153), 5) + 1;
  const gm = mod(div(i, 153), 12) + 1;
  const gy = div(j, 1461) - 100100 + div(8 - gm, 6);
  return { gy, gm, gd };
}

/** The instant shifted into the zone the calendar should be read in. */
export function shifted(date: Date, shiftMinutes = 0): Date {
  return shiftMinutes ? new Date(date.getTime() + shiftMinutes * 60000) : date;
}

export function isLeapYear(jy: number): boolean {
  return jalCal(jy).leap === 0;
}

export function daysInMonth(jy: number, jm: number): number {
  if (jm < 1 || jm > 12) throw new RangeError(`Jalali month out of range: ${jm}`);
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  return isLeapYear(jy) ? 30 : 29;
}

export function daysInYear(jy: number): number {
  return isLeapYear(jy) ? 366 : 365;
}

/** Gregorian Date (read in UTC) -> Jalali date. */
export function toJalali(date: Date, shiftMinutes = 0): JalaliDate {
  const value = shifted(date, shiftMinutes);
  const jdn = g2d(value.getUTCFullYear(), value.getUTCMonth() + 1, value.getUTCDate());
  const { gy } = d2g(jdn);
  let jy = gy - 621;
  const { leap, march } = jalCal(jy);
  let k = jdn - g2d(gy, 3, march);
  if (k >= 0) {
    if (k <= 185) return { jy, jm: 1 + div(k, 31), jd: mod(k, 31) + 1 };
    k -= 186;
  } else {
    jy -= 1;
    k += 179;
    if (leap === 1) k += 1;
  }
  return { jy, jm: 7 + div(k, 30), jd: mod(k, 30) + 1 };
}

/** Jalali date (+ optional time of day) -> Gregorian Date in UTC. */
export function fromJalali(
  jy: number,
  jm: number,
  jd: number,
  time: Partial<JalaliTime> = {},
): Date {
  if (jm < 1 || jm > 12) throw new RangeError(`Jalali month out of range: ${jm}`);
  if (jd < 1 || jd > daysInMonth(jy, jm)) {
    throw new RangeError(`no day ${jd} in ${jy}-${jm}`);
  }
  const { gy, march } = jalCal(jy);
  const jdn = g2d(gy, 3, march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
  const { gy: year, gm, gd } = d2g(jdn);
  return new Date(
    Date.UTC(year, gm - 1, gd, time.hours || 0, time.minutes || 0,
      time.seconds || 0, time.milliseconds || 0),
  );
}

export function timeOf(date: Date, shiftMinutes = 0): JalaliTime {
  const value = shifted(date, shiftMinutes);
  return {
    hours: value.getUTCHours(),
    minutes: value.getUTCMinutes(),
    seconds: value.getUTCSeconds(),
    milliseconds: value.getUTCMilliseconds(),
  };
}

/** 1-based day of the Jalali year. */
export function dayOfYear(date: Date, shiftMinutes = 0): number {
  const { jm, jd } = toJalali(date, shiftMinutes);
  return DAYS_BEFORE_MONTH[jm - 1] + jd;
}

/** 0 = Saturday .. 6 = Friday. */
export function dayOfWeek(date: Date, shiftMinutes = 0): number {
  return (shifted(date, shiftMinutes).getUTCDay() + 1) % 7;
}

/** 1..4 - the Jalali quarter, i.e. the season. */
export function quarter(date: Date, shiftMinutes = 0): number {
  return div(toJalali(date, shiftMinutes).jm - 1, 3) + 1;
}

export function isWeekend(date: Date, thursday = false, shiftMinutes = 0): boolean {
  const dow = dayOfWeek(date, shiftMinutes);
  return dow === 6 || (thursday && dow === 5);
}

/** Midnight of the same day, in the shifted zone, as a UTC Date. */
export function dayStart(date: Date, shiftMinutes = 0): Date {
  const { jy, jm, jd } = toJalali(date, shiftMinutes);
  const midnight = fromJalali(jy, jm, jd);
  return shiftMinutes ? new Date(midnight.getTime() - shiftMinutes * 60000) : midnight;
}

function minusDays(date: Date, days: number): Date {
  return new Date(date.getTime() - days * MS_PER_DAY);
}

export function weekStart(date: Date, shiftMinutes = 0): Date {
  return minusDays(dayStart(date, shiftMinutes), dayOfWeek(date, shiftMinutes));
}

export function monthStart(date: Date, shiftMinutes = 0): Date {
  return minusDays(dayStart(date, shiftMinutes), toJalali(date, shiftMinutes).jd - 1);
}

export function quarterStart(date: Date, shiftMinutes = 0): Date {
  const doy0 = dayOfYear(date, shiftMinutes) - 1;
  const start = QUARTER_START_DOY0.filter(value => doy0 >= value).pop() as number;
  return minusDays(dayStart(date, shiftMinutes), doy0 - start);
}

export function halfYearStart(date: Date, shiftMinutes = 0): Date {
  const doy0 = dayOfYear(date, shiftMinutes) - 1;
  const start = doy0 >= HALF_START_DOY0[1] ? HALF_START_DOY0[1] : 0;
  return minusDays(dayStart(date, shiftMinutes), doy0 - start);
}

export function yearStart(date: Date, shiftMinutes = 0): Date {
  return minusDays(dayStart(date, shiftMinutes), dayOfYear(date, shiftMinutes) - 1);
}

export const PERIOD_STARTS: Record<PeriodUnit, (date: Date, shift?: number) => Date> = {
  day: dayStart,
  week: weekStart,
  month: monthStart,
  quarter: quarterStart,
  half: halfYearStart,
  year: yearStart,
};

/** Shift by whole Jalali months, clamping the day: 31 Farvardin minus a month
 * is 30 Esfand in a leap year and 29 Esfand otherwise. */
export function addMonths(date: Date, months: number, shiftMinutes = 0): Date {
  const { jy, jm, jd } = toJalali(date, shiftMinutes);
  const total = jy * 12 + jm - 1 + months;
  const year = Math.floor(total / 12);
  const month = total - year * 12 + 1;
  const time = timeOf(date, shiftMinutes);
  const value = fromJalali(year, month, Math.min(jd, daysInMonth(year, month)), time);
  return shiftMinutes ? new Date(value.getTime() - shiftMinutes * 60000) : value;
}

export function addPeriod(
  date: Date,
  periods: number,
  unit: PeriodUnit,
  shiftMinutes = 0,
): Date {
  switch (unit) {
    case 'day':
      return new Date(date.getTime() + periods * MS_PER_DAY);
    case 'week':
      return new Date(date.getTime() + 7 * periods * MS_PER_DAY);
    case 'month':
      return addMonths(date, periods, shiftMinutes);
    case 'quarter':
      return addMonths(date, 3 * periods, shiftMinutes);
    case 'half':
      return addMonths(date, 6 * periods, shiftMinutes);
    case 'year':
      return addMonths(date, 12 * periods, shiftMinutes);
    default:
      throw new RangeError(`unknown Jalali period: ${unit}`);
  }
}

// ----------------------------------------------------------------- digits ----
export function toPersianDigits(text: string): string {
  return text.replace(/[0-9]/g, digit => PERSIAN_DIGITS[Number(digit)]);
}

export function toLatinDigits(text: string): string {
  return text.replace(/[۰-۹٠-٩]/g, char => {
    const persian = PERSIAN_DIGITS.indexOf(char);
    return String(persian >= 0 ? persian : ARABIC_DIGITS.indexOf(char));
  });
}

// -------------------------------------------------------------- formatting ---
export interface FormatOptions {
  persianDigits?: boolean;
  shiftMinutes?: number;
}

const pad = (value: number, length = 2) => String(value).padStart(length, '0');

// dayjs-style tokens; [literal text] is copied through. Longest token first.
const TOKEN_RE =
  /\[([^\]]*)\]|YYYY|YY|MMMM|MMM|MM|M|DDDD|DDD|DD|D|dddd|ddd|HH|H|hh|h|mm|m|ss|s|QQQQ|QQ|Q|WW|W|A|a/g;

export function formatJalali(
  date: Date,
  pattern: string,
  options: FormatOptions = {},
): string {
  const shift = options.shiftMinutes || 0;
  const { jy, jm, jd } = toJalali(date, shift);
  const { hours, minutes, seconds } = timeOf(date, shift);
  const doy = DAYS_BEFORE_MONTH[jm - 1] + jd;
  const dow = dayOfWeek(date, shift);
  const qtr = div(jm - 1, 3) + 1;
  const week = div(doy - 1, 7) + 1;
  const out = pattern.replace(TOKEN_RE, (token, literal) => {
    if (literal !== undefined) return literal;
    switch (token) {
      case 'YYYY': return pad(jy, 4);
      case 'YY': return pad(jy % 100);
      case 'MMMM': return MONTH_NAMES[jm - 1];
      case 'MMM': return MONTH_NAMES[jm - 1].slice(0, 3);
      case 'MM': return pad(jm);
      case 'M': return String(jm);
      case 'DDDD': return pad(doy, 3);
      case 'DDD': return String(doy);
      case 'DD': return pad(jd);
      case 'D': return String(jd);
      case 'dddd': return WEEKDAY_NAMES[dow];
      case 'ddd': return WEEKDAY_NAMES[dow].slice(0, 3);
      case 'HH': return pad(hours);
      case 'H': return String(hours);
      case 'hh': return pad(hours % 12 || 12);
      case 'h': return String(hours % 12 || 12);
      case 'mm': return pad(minutes);
      case 'm': return String(minutes);
      case 'ss': return pad(seconds);
      case 's': return String(seconds);
      case 'QQQQ': return SEASON_NAMES[qtr - 1];
      case 'QQ': return pad(qtr);
      case 'Q': return String(qtr);
      case 'WW': return pad(week);
      case 'W': return String(week);
      case 'A': case 'a': return hours < 12 ? 'ق.ظ' : 'ب.ظ';
      default: return token;
    }
  });
  return options.persianDigits ? toPersianDigits(out) : out;
}

/** The named formats registered in Superset's time-format registry. Kept equal
 * to NAMED_FORMATS in superset/jalali_calendar/core.py. */
export const NAMED_FORMATS: Record<string, string> = {
  jalali_date: 'YYYY-MM-DD',
  jalali_datetime: 'YYYY-MM-DD HH:mm:ss',
  jalali_minute: 'YYYY-MM-DD HH:mm',
  jalali_month: 'MMMM YYYY',
  jalali_month_short: 'YYYY-MM',
  jalali_quarter: 'QQQQ YYYY',
  jalali_year: 'YYYY',
  jalali_week: '[هفته] W [-] YYYY',
  jalali_verbose: 'dddd D MMMM YYYY',
  jalali_day_month: 'D MMMM',
};

/** Adaptive axis labels, like Superset's smart_date but on Jalali boundaries:
 * a time of day when there is one, the year on 1 Farvardin, the month name on
 * the 1st of a month, otherwise "20 اسفند". */
export function formatSmart(date: Date, options: FormatOptions = {}): string {
  const shift = options.shiftMinutes || 0;
  const { jy, jm, jd } = toJalali(date, shift);
  const { hours, minutes, seconds, milliseconds } = timeOf(date, shift);
  let out: string;
  if (seconds || milliseconds) out = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  else if (hours || minutes) out = `${pad(hours)}:${pad(minutes)}`;
  else if (jd === 1 && jm === 1) out = pad(jy, 4);
  else if (jd === 1) out = MONTH_NAMES[jm - 1];
  else out = `${jd} ${MONTH_NAMES[jm - 1]}`;
  return options.persianDigits ? toPersianDigits(out) : out;
}

// ----------------------------------------------------------------- parsing ---
export type LiteralPrecision = 'year' | 'quarter' | 'month' | 'day' | 'minute' | 'second';

export interface JalaliLiteral extends JalaliDate, JalaliTime {
  /** How much of the literal was given: "1403-12" means the whole of Esfand. */
  precision: LiteralPrecision;
  /** Midnight (or the given time) of the literal, as a UTC Date. */
  date: Date;
}

const LITERAL_RE =
  /^(\d{3,4})(?:[-/](\d{1,2})(?:[-/](\d{1,2}))?)?(?:[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?$/;
const QUARTER_RE = /^(\d{3,4})[-/]?[qQ]([1-4])$/;

/** Parse a Jalali literal, or null when the text is not one. Persian and
 * Arabic-Indic digits are accepted. */
export function parseLiteral(text: string): JalaliLiteral | null {
  const normalised = toLatinDigits(String(text).trim());
  if (!normalised) return null;
  const quarterMatch = QUARTER_RE.exec(normalised);
  if (quarterMatch) {
    const jy = Number(quarterMatch[1]);
    if (jy < MIN_YEAR || jy > MAX_YEAR) return null;
    const jm = 3 * (Number(quarterMatch[2]) - 1) + 1;
    return {
      jy, jm, jd: 1, precision: 'quarter', hours: 0, minutes: 0, seconds: 0,
      milliseconds: 0, date: fromJalali(jy, jm, 1),
    };
  }
  const match = LITERAL_RE.exec(normalised);
  if (!match) return null;
  const jy = Number(match[1]);
  if (jy < MIN_YEAR || jy > MAX_YEAR) return null;
  const jm = match[2] === undefined ? 1 : Number(match[2]);
  const jd = match[3] === undefined ? 1 : Number(match[3]);
  if (jm < 1 || jm > 12 || jd < 1 || jd > daysInMonth(jy, jm)) return null;
  const hours = match[4] === undefined ? 0 : Number(match[4]);
  const minutes = match[5] === undefined ? 0 : Number(match[5]);
  const seconds = match[6] === undefined ? 0 : Number(match[6]);
  if (hours > 23 || minutes > 59 || seconds > 59) return null;
  let precision: LiteralPrecision;
  if (match[4] !== undefined) precision = match[6] === undefined ? 'minute' : 'second';
  else if (match[3] !== undefined) precision = 'day';
  else if (match[2] !== undefined) precision = 'month';
  else precision = 'year';
  return {
    jy, jm, jd, precision, hours, minutes, seconds, milliseconds: 0,
    date: fromJalali(jy, jm, jd, { hours, minutes, seconds }),
  };
}

/** Exclusive end of the period a literal denotes. */
export function literalEnd(literal: JalaliLiteral): Date {
  switch (literal.precision) {
    case 'year':
      return addPeriod(literal.date, 1, 'year');
    case 'quarter':
      return addPeriod(literal.date, 1, 'quarter');
    case 'month':
      return addPeriod(literal.date, 1, 'month');
    case 'day':
      return new Date(literal.date.getTime() + MS_PER_DAY);
    case 'minute':
      return new Date(literal.date.getTime() + 60000);
    default:
      return new Date(literal.date.getTime() + 1000);
  }
}
