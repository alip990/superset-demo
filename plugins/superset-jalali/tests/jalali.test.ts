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
 * Tests for the calendar core. Runs under plain Node (npm test) - the Superset
 * frontend's Jest setup is not needed, and deliberately not used, so this can
 * be checked without a 20-minute frontend install.
 *
 * Three independent oracles:
 *  1. tests/fixtures/jalali_cases.json, generated from the Python core, so the
 *     backend and the browser can never disagree about a date;
 *  2. the browser's own Persian calendar (Intl / ICU), for every day of 300 years;
 *  3. hand-checked dates from an Iranian calendar.
 */

import assert from 'assert';
import fs from 'fs';
import path from 'path';
import * as jalali from '../src/core/jalali';
import { DEFAULT_RANGES } from '../src/rangeVocabulary';

// Walk up to the repository root, so the path works whether this file runs from
// source or from dist-test/.
function findFixtures(): string {
  let dir = __dirname;
  for (let depth = 0; depth < 6; depth += 1) {
    const candidate = path.join(dir, 'tests', 'fixtures', 'jalali_cases.json');
    if (fs.existsSync(candidate)) return candidate;
    dir = path.dirname(dir);
  }
  throw new Error('tests/fixtures/jalali_cases.json not found: regenerate it with '
    + 'python3 tests/test_jalali_core.py --write-fixtures');
}
const FIXTURES = findFixtures();

let passed = 0;
const failures: string[] = [];

function test(name: string, body: () => void): void {
  try {
    body();
    passed += 1;
  } catch (error) {
    failures.push(`${name}\n    ${(error as Error).message.split('\n').join('\n    ')}`);
  }
}

const utc = (iso: string): Date => new Date(`${iso}T00:00:00Z`);
const isoDate = (date: Date): string => date.toISOString().slice(0, 10);

// ------------------------------------------------------------- known dates ---
const KNOWN: [string, number, number, number][] = [
  ['2025-03-20', 1403, 12, 30],
  ['2025-03-21', 1404, 1, 1],
  ['2024-03-20', 1403, 1, 1],
  ['2021-03-20', 1399, 12, 30],
  ['2026-03-21', 1405, 1, 1],
  ['1979-02-11', 1357, 11, 22],
  ['2016-03-20', 1395, 1, 1],
  ['2000-01-01', 1378, 10, 11],
];

test('known dates convert both ways', () => {
  KNOWN.forEach(([iso, jy, jm, jd]) => {
    assert.deepStrictEqual(jalali.toJalali(utc(iso)), { jy, jm, jd }, iso);
    assert.strictEqual(isoDate(jalali.fromJalali(jy, jm, jd)), iso, iso);
  });
});

test('round trip for every day between 1900 and 2200', () => {
  let count = 0;
  for (let time = Date.UTC(1900, 0, 1); time <= Date.UTC(2200, 11, 31);
    time += 86400000) {
    const date = new Date(time);
    const { jy, jm, jd } = jalali.toJalali(date);
    assert.strictEqual(jalali.fromJalali(jy, jm, jd).getTime(), time,
      date.toISOString());
    count += 1;
  }
  assert.strictEqual(count, 109938);
});

test('leap years match the official calendar', () => {
  const known = [1362, 1366, 1370, 1375, 1379, 1383, 1387, 1391, 1395, 1399,
    1403, 1408, 1412, 1416, 1420, 1424, 1428, 1432, 1436, 1441];
  const found: number[] = [];
  for (let jy = 1360; jy <= 1444; jy += 1) if (jalali.isLeapYear(jy)) found.push(jy);
  assert.deepStrictEqual(found, known.filter(jy => jy <= 1444));
  assert.strictEqual(jalali.daysInMonth(1403, 12), 30);
  assert.strictEqual(jalali.daysInMonth(1404, 12), 29);
  assert.strictEqual(jalali.daysInYear(1403), 366);
});

test('a non-existent day is refused', () => {
  assert.throws(() => jalali.fromJalali(1404, 12, 30), RangeError);
  assert.throws(() => jalali.fromJalali(1403, 7, 31), RangeError);
  assert.throws(() => jalali.fromJalali(jalali.DOMAIN_MIN_YEAR - 1, 1, 1), RangeError);
});

// ------------------------------------------------------------ period starts --
test('period starts', () => {
  const day = utc('2025-03-10'); // دوشنبه 20 اسفند 1403
  assert.strictEqual(isoDate(jalali.dayStart(day)), '2025-03-10');
  assert.strictEqual(isoDate(jalali.weekStart(day)), '2025-03-08'); // Saturday
  assert.strictEqual(isoDate(jalali.monthStart(day)), '2025-02-19');
  assert.strictEqual(isoDate(jalali.quarterStart(day)), '2024-12-21');
  assert.strictEqual(isoDate(jalali.halfYearStart(day)), '2024-09-22');
  assert.strictEqual(isoDate(jalali.yearStart(day)), '2024-03-20');
});

test('period starts are idempotent and inside the period', () => {
  for (let time = Date.UTC(2020, 0, 1); time <= Date.UTC(2030, 11, 31);
    time += 86400000) {
    const date = new Date(time);
    (Object.keys(jalali.PERIOD_STARTS) as jalali.PeriodUnit[]).forEach(unit => {
      const start = jalali.PERIOD_STARTS[unit](date);
      assert.ok(start.getTime() <= time, `${unit} ${date.toISOString()}`);
      assert.strictEqual(jalali.PERIOD_STARTS[unit](start).getTime(), start.getTime(),
        `${unit} ${date.toISOString()}`);
    });
    assert.strictEqual(jalali.toJalali(jalali.monthStart(date)).jd, 1);
    assert.strictEqual(jalali.dayOfWeek(jalali.weekStart(date)), 0);
    assert.ok([1, 4, 7, 10].includes(jalali.toJalali(jalali.quarterStart(date)).jm));
  }
});

test('day of week is Saturday-first', () => {
  assert.strictEqual(jalali.dayOfWeek(utc('2025-03-08')), 0);
  assert.strictEqual(jalali.dayOfWeek(utc('2025-03-14')), 6);
  assert.strictEqual(jalali.WEEKDAY_NAMES[jalali.dayOfWeek(utc('2025-03-10'))], 'دوشنبه');
  assert.ok(jalali.isWeekend(utc('2025-03-14')));
  assert.ok(!jalali.isWeekend(utc('2025-03-13')));
  assert.ok(jalali.isWeekend(utc('2025-03-13'), true));
});

test('adding Jalali months clamps the day', () => {
  // 31 Farvardin 1404 minus a month is 30 Esfand 1403 (a leap year)
  assert.strictEqual(isoDate(jalali.addPeriod(utc('2025-04-20'), -1, 'month')),
    '2025-03-20');
  // ... and 29 Esfand 1402, which is not
  assert.deepStrictEqual(jalali.toJalali(jalali.addPeriod(utc('2024-04-19'), -1, 'month')),
    { jy: 1402, jm: 12, jd: 29 });
  assert.strictEqual(isoDate(jalali.addPeriod(utc('2025-03-10'), 1, 'month')),
    '2025-04-09');
  assert.strictEqual(isoDate(jalali.addPeriod(utc('2025-03-10'), 1, 'week')),
    '2025-03-17');
  assert.deepStrictEqual(jalali.toJalali(jalali.addPeriod(utc('2025-03-10'), 1, 'year')),
    { jy: 1404, jm: 12, jd: 20 });
});

// --------------------------------------------------------------- formatting --
test('format tokens', () => {
  const value = new Date('2025-03-10T14:32:05Z');
  assert.strictEqual(jalali.formatJalali(value, 'YYYY-MM-DD'), '1403-12-20');
  assert.strictEqual(jalali.formatJalali(value, 'YYYY/M/D HH:mm:ss'), '1403/12/20 14:32:05');
  assert.strictEqual(jalali.formatJalali(value, 'dddd D MMMM YYYY'), 'دوشنبه 20 اسفند 1403');
  assert.strictEqual(jalali.formatJalali(value, 'QQQQ YYYY'), 'زمستان 1403');
  assert.strictEqual(jalali.formatJalali(value, 'YY A'), '03 ب.ظ');
  assert.strictEqual(jalali.formatJalali(value, '[ساعت] HH'), 'ساعت 14');
  assert.strictEqual(jalali.formatJalali(value, 'DDD'), '356');
  assert.strictEqual(jalali.formatJalali(value, 'YYYY-MM-DD', { persianDigits: true }),
    '۱۴۰۳-۱۲-۲۰');
});

test('smart format', () => {
  assert.strictEqual(jalali.formatSmart(utc('2025-03-21')), '1404');
  assert.strictEqual(jalali.formatSmart(utc('2025-02-19')), 'اسفند');
  assert.strictEqual(jalali.formatSmart(utc('2025-03-10')), '20 اسفند');
  assert.strictEqual(jalali.formatSmart(new Date('2025-03-10T14:30:00Z')), '14:30');
  assert.strictEqual(jalali.formatSmart(new Date('2025-03-10T14:30:09Z')), '14:30:09');
});

test('digits convert both ways', () => {
  assert.strictEqual(jalali.toLatinDigits('۱۴۰۳/۱۲/۲۰'), '1403/12/20');
  assert.strictEqual(jalali.toLatinDigits('١٤٠٣'), '1403');
  assert.strictEqual(jalali.toPersianDigits('1403'), '۱۴۰۳');
});

// ------------------------------------------------------------------ parsing --
test('literals and their precision', () => {
  const cases: [string, string, jalali.LiteralPrecision][] = [
    ['1403', '2024-03-20', 'year'],
    ['1403-12', '2025-02-19', 'month'],
    ['1403-q4', '2024-12-21', 'quarter'],
    ['1403-12-20', '2025-03-10', 'day'],
    ['1403/12/20', '2025-03-10', 'day'],
    ['۱۴۰۳/۱۲/۲۰', '2025-03-10', 'day'],
    ['1403-12-20 14:30', '2025-03-10', 'minute'],
    ['1403-12-20T14:30:05', '2025-03-10', 'second'],
  ];
  cases.forEach(([text, iso, precision]) => {
    const parsed = jalali.parseLiteral(text);
    assert.ok(parsed, text);
    assert.strictEqual(isoDate(parsed.date), iso, text);
    assert.strictEqual(parsed.precision, precision, text);
  });
  assert.strictEqual(isoDate(jalali.literalEnd(jalali.parseLiteral('1403-12')!)),
    '2025-03-21');
  assert.strictEqual(isoDate(jalali.literalEnd(jalali.parseLiteral('1403')!)),
    '2025-03-21');
});

test('Gregorian dates are not read as Jalali', () => {
  ['2025-03-10', '1999-01-01', '2020', '', 'hello', '1403-13-01', '1404-12-30',
    '1403-12-20 25:00'].forEach(text => {
    assert.strictEqual(jalali.parseLiteral(text), null, text);
  });
});

// ------------------------------------------------------------------- shift ----
test('shiftMinutes moves the day boundary', () => {
  // 21:00 UTC is already half past midnight of the next day in Tehran (+3:30),
  // so UTC-stored data of an Asia/Tehran business needs shiftMinutes: 210
  const late = new Date('2025-03-10T21:00:00Z');
  assert.deepStrictEqual(jalali.toJalali(late), { jy: 1403, jm: 12, jd: 20 });
  assert.deepStrictEqual(jalali.toJalali(late, 210), { jy: 1403, jm: 12, jd: 21 });
  assert.strictEqual(jalali.formatJalali(late, 'YYYY-MM-DD HH:mm', { shiftMinutes: 210 }),
    '1403-12-21 00:30');
  // a period start is the instant the period begins in the shifted zone, so it
  // reads back as the 1st of the month there
  const start = jalali.monthStart(late, 210);
  assert.strictEqual(jalali.formatJalali(start, 'YYYY-MM-DD HH:mm', { shiftMinutes: 210 }),
    '1403-12-01 00:00');
  assert.strictEqual(start.toISOString(), '2025-02-18T20:30:00.000Z');
  // without a shift the day boundary is UTC midnight, unchanged
  assert.strictEqual(jalali.monthStart(late).toISOString(), '2025-02-19T00:00:00.000Z');
});

// ---------------------------------------------------------------- fixtures ----
test('shared fixtures from the Python core', () => {
  const cases = JSON.parse(fs.readFileSync(FIXTURES, 'utf8'));
  cases.conversions.forEach((item: { gregorian: string; jalali: number[] }) => {
    const { jy, jm, jd } = jalali.toJalali(utc(item.gregorian));
    assert.deepStrictEqual([jy, jm, jd], item.jalali, item.gregorian);
  });
  cases.formats.forEach((item: {
    gregorian: string; pattern: string; expected: string; persianDigits?: boolean;
  }) => {
    const date = new Date(`${item.gregorian}Z`);
    const options = { persianDigits: item.persianDigits || false };
    const actual = item.pattern === '@smart'
      ? jalali.formatSmart(date, options)
      : jalali.formatJalali(date, item.pattern, options);
    assert.strictEqual(actual, item.expected, `${item.gregorian} ${item.pattern}`);
  });
  cases.periodStarts.forEach((item: {
    gregorian: string; starts: Record<string, string>;
  }) => {
    Object.entries(item.starts).forEach(([unit, expected]) => {
      assert.strictEqual(
        isoDate(jalali.PERIOD_STARTS[unit as jalali.PeriodUnit](utc(item.gregorian))),
        expected, `${item.gregorian} ${unit}`);
    });
  });
  cases.literals.forEach((item: {
    text: string; date: string | null; precision: string | null;
  }) => {
    const parsed = jalali.parseLiteral(item.text);
    if (item.date === null) {
      assert.strictEqual(parsed, null, item.text);
    } else {
      assert.ok(parsed, item.text);
      assert.strictEqual(isoDate(parsed.date), item.date, item.text);
      assert.strictEqual(parsed.precision, item.precision, item.text);
    }
  });
});

test('the range vocabulary matches the backend', () => {
  const cases = JSON.parse(fs.readFileSync(FIXTURES, 'utf8'));
  assert.deepStrictEqual(DEFAULT_RANGES, cases.ranges,
    'src/rangeVocabulary.ts and superset/jalali_calendar/ranges.py disagree');
});

// --------------------------------------------------------------------- ICU ----
test('every day of 1900..2200 matches the ICU Persian calendar', () => {
  let formatter: Intl.DateTimeFormat;
  try {
    formatter = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', {
      timeZone: 'UTC', year: 'numeric', month: 'numeric', day: 'numeric',
    });
    if (!formatter.format(utc('2025-03-20')).includes('1403')) {
      process.stdout.write('  (skipped: this runtime has no Persian calendar)\n');
      return;
    }
  } catch {
    process.stdout.write('  (skipped: Intl has no Persian calendar here)\n');
    return;
  }
  for (let time = Date.UTC(1900, 0, 1); time <= Date.UTC(2200, 11, 31);
    time += 86400000) {
    const date = new Date(time);
    const parts: Record<string, string> = {};
    formatter.formatToParts(date).forEach(part => { parts[part.type] = part.value; });
    assert.deepStrictEqual(jalali.toJalali(date), {
      jy: Number(parts.year), jm: Number(parts.month), jd: Number(parts.day),
    }, date.toISOString());
  }
});

process.stdout.write(`\n${passed} passed, ${failures.length} failed\n`);
if (failures.length) {
  failures.forEach(failure => process.stdout.write(`\nFAIL ${failure}\n`));
  process.exit(1);
}
