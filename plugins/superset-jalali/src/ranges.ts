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
 * Jalali shortcuts in Superset's date-filter popover, and Jalali text for the
 * ranges it displays.
 *
 * The popover's three shortcut frames ("Last", "Previous", "Current") render
 * from arrays and validate against sets that upstream exports as module
 * constants. Extending those objects adds Jalali options to the real control -
 * for every chart, every native dashboard filter and every adhoc temporal
 * filter - without touching upstream's components. The strings are resolved on
 * the server by superset/jalali_calendar/ranges.py.
 */
import {
  CALENDAR_RANGE_OPTIONS,
  CALENDAR_RANGE_SET,
  CALENDAR_RANGE_VALUES_SET,
  COMMON_RANGE_OPTIONS,
  COMMON_RANGE_SET,
  COMMON_RANGE_VALUES_SET,
  CURRENT_CALENDAR_RANGE_SET,
  CURRENT_RANGE_OPTIONS,
  CURRENT_RANGE_VALUES_SET,
} from 'src/explore/components/controls/DateFilterControl/utils';
import { formatJalali, parseLiteral } from './core/jalali';
import { getJalaliOptions } from './options';
import { RangeOption, allRangeOptions, rangeLabel } from './rangeVocabulary';

interface FrameTarget {
  options: { value: string; label: string }[];
  // the frame renders from `options` but decides what is valid with these two
  sets: Set<string>[];
}

/** Add the Jalali shortcuts to the popover's frames. Idempotent. */
export function registerJalaliRanges(): number {
  const { ranges } = getJalaliOptions();
  const targets: [RangeOption[], FrameTarget][] = [
    [ranges.common, {
      options: COMMON_RANGE_OPTIONS as { value: string; label: string }[],
      sets: [COMMON_RANGE_VALUES_SET as Set<string>,
        COMMON_RANGE_SET as unknown as Set<string>],
    }],
    [ranges.calendar, {
      options: CALENDAR_RANGE_OPTIONS as { value: string; label: string }[],
      sets: [CALENDAR_RANGE_VALUES_SET as Set<string>,
        CALENDAR_RANGE_SET as unknown as Set<string>],
    }],
    [ranges.current, {
      options: CURRENT_RANGE_OPTIONS as { value: string; label: string }[],
      sets: [CURRENT_RANGE_VALUES_SET as Set<string>,
        CURRENT_CALENDAR_RANGE_SET as unknown as Set<string>],
    }],
  ];
  let added = 0;
  targets.forEach(([options, target]) => {
    options.forEach(([value, label]) => {
      if (!target.options.some(option => option.value === value)) {
        target.options.push({ value, label });
        added += 1;
      }
      // guessFrame() uses the first set to route a saved value to its frame;
      // the frame itself uses the second one to decide the value is valid
      target.sets.forEach(set => set.add(value));
    });
  });
  return added;
}

/** The Persian label of a shortcut, or the value unchanged. */
export function jalaliRangeLabel(value: string): string {
  return rangeLabel(getJalaliOptions().ranges, value);
}

export function isJalaliRange(value: string): boolean {
  return allRangeOptions(getJalaliOptions().ranges)
    .some(([option]) => option === value);
}

// 2025-03-21, 2025-03-21T00:00:00, 2025-03-21 00:00:00
const ISO_RE = /(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/g;

/**
 * Rewrite the Gregorian dates in a rendered range into Jalali ones, keeping
 * everything around them: "2025-03-21 ≤ col < 2025-04-21" becomes
 * "1404-01-01 ≤ col < 1404-02-01". Used for the "Actual time range" line, the
 * control's pill and its tooltip.
 */
export function jalaliseTimeRangeText(text: string): string {
  const { digits, shiftMinutes } = getJalaliOptions();
  const options = { persianDigits: digits === 'persian', shiftMinutes };
  return text.replace(ISO_RE, (match, year, month, day, hour, minute, second) => {
    const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day),
      Number(hour ?? 0), Number(minute ?? 0), Number(second ?? 0)));
    if (Number.isNaN(date.getTime())) return match;
    const pattern = hour === undefined
      ? 'YYYY-MM-DD'
      : `YYYY-MM-DD HH:mm${second === undefined ? '' : ':ss'}`;
    try {
      return formatJalali(date, pattern, options);
    } catch {
      return match; // outside the calendar's range: leave it Gregorian
    }
  });
}

/** Does this free-text value contain a Jalali literal? Used by the picker to
 * decide whether the Advanced frame needs a Jalali hint. */
export function containsJalaliLiteral(value: string): boolean {
  return value.split(' : ').some(part =>
    parseLiteral(part.replace(/^(?:jalali|shamsi|jalaali|j)\s*[:_-]\s*/i, '')) !== null);
}
