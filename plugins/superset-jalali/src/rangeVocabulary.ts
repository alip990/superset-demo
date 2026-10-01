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
 * The Jalali time-range shortcuts, as the date-filter popover shows them.
 *
 * These strings are what a saved chart stores in its `time_range`, and
 * superset/jalali_calendar/ranges.py is what resolves them to dates - on the
 * server, so that alerts, reports, CSV exports and embedded dashboards agree
 * with the browser. This file only has to agree about the *vocabulary*, which
 * tests/fixtures/jalali_cases.json pins for both sides.
 *
 * At runtime the list normally arrives from the backend
 * (JALALI_CALENDAR_OPTIONS.ranges); this copy is the fallback.
 */

/** [value stored in the chart, Persian label shown in the popover] */
export type RangeOption = [string, string];

export interface RangeGroups {
  /** the "Last" frame: rolling windows ending now */
  common: RangeOption[];
  /** the "Previous" frame: whole previous calendar periods */
  calendar: RangeOption[];
  /** the "Current" frame: the period we are in, and "to date" ranges */
  current: RangeOption[];
}

export const DEFAULT_RANGES: RangeGroups = {
  common: [
    ['Last jalali week', 'هفته گذشته (شمسی)'],
    ['Last jalali month', 'ماه گذشته (شمسی)'],
    ['Last jalali quarter', 'فصل گذشته (شمسی)'],
    ['Last jalali year', 'سال گذشته (شمسی)'],
  ],
  calendar: [
    ['previous jalali week', 'هفته تقویمی قبل (شمسی)'],
    ['previous jalali month', 'ماه تقویمی قبل (شمسی)'],
    ['previous jalali quarter', 'فصل تقویمی قبل (شمسی)'],
    ['previous jalali year', 'سال تقویمی قبل (شمسی)'],
  ],
  current: [
    ['Current jalali day', 'امروز'],
    ['Current jalali week', 'هفته جاری (شمسی)'],
    ['Current jalali month', 'ماه جاری (شمسی)'],
    ['Current jalali quarter', 'فصل جاری (شمسی)'],
    ['Current jalali year', 'سال جاری (شمسی)'],
    ['jalali month to date', 'از ابتدای ماه تا امروز'],
    ['jalali quarter to date', 'از ابتدای فصل تا امروز'],
    ['jalali year to date', 'از ابتدای سال تا امروز'],
  ],
};

export function allRangeOptions(groups: RangeGroups): RangeOption[] {
  return [...groups.common, ...groups.calendar, ...groups.current];
}

/** The Persian label of a shortcut, or the value itself when it is not one. */
export function rangeLabel(groups: RangeGroups, value: string): string {
  const found = allRangeOptions(groups).find(([option]) => option === value);
  return found ? found[1] : value;
}
