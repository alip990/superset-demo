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
 * The plugin's settings, published by the backend.
 *
 * superset/jalali_calendar/install.py puts JALALI_CALENDAR_OPTIONS into the
 * bootstrap payload (it adds the key to FRONTEND_CONF_KEYS), so the Persian
 * labels, the digit style, the timezone shift and the list of range shortcuts
 * all come from superset_config.py instead of being frozen into this bundle.
 *
 * Everything degrades: with no options published, the FEATURE_FLAGS entry
 * JALALI_CALENDAR alone still turns the plugin on with the defaults below.
 */
import getBootstrapData from 'src/utils/getBootstrapData';
import { DEFAULT_RANGES, RangeGroups } from './rangeVocabulary';

export interface JalaliOptions {
  /** master switch; false leaves Superset Gregorian */
  enabled: boolean;
  /** "latin" (1403-12-20) or "persian" (۱۴۰۳-۱۲-۲۰) */
  digits: 'latin' | 'persian';
  /** replace Superset's own adaptive formatters, so existing charts turn Jalali */
  overrideSmartDate: boolean;
  /** minutes added to an instant before deciding which Jalali day it is */
  shiftMinutes: number;
  storageTimezone: 'wall' | 'UTC';
  businessTimezone: string;
  /** some employers count Thursday as weekend; shown greyed in the calendar */
  thursdayIsWeekend: boolean;
  /** the time-range shortcuts, grouped by the frame that shows them */
  ranges: RangeGroups;
}

export const DEFAULT_OPTIONS: JalaliOptions = {
  enabled: false,
  digits: 'latin',
  overrideSmartDate: true,
  shiftMinutes: 0,
  storageTimezone: 'wall',
  businessTimezone: 'Asia/Tehran',
  thursdayIsWeekend: false,
  ranges: DEFAULT_RANGES,
};

let cached: JalaliOptions | null = null;

/** Read the options once; the bootstrap payload cannot change at runtime. */
export function getJalaliOptions(): JalaliOptions {
  if (cached) return cached;
  let published: Partial<JalaliOptions> = {};
  let featureFlag = false;
  try {
    const common = getBootstrapData()?.common;
    published = (common?.conf?.JALALI_CALENDAR_FRONTEND_OPTIONS
      ?? common?.conf?.JALALI_CALENDAR_OPTIONS ?? {}) as Partial<JalaliOptions>;
    featureFlag = Boolean(
      (common?.feature_flags as unknown as Record<string, boolean>)?.JALALI_CALENDAR,
    );
  } catch {
    // no bootstrap data (unit tests, storybook): stay with the defaults
  }
  cached = {
    ...DEFAULT_OPTIONS,
    enabled: published.enabled ?? featureFlag,
    ...published,
    ranges: { ...DEFAULT_RANGES, ...(published.ranges ?? {}) },
  };
  return cached;
}

export function isJalaliEnabled(): boolean {
  return getJalaliOptions().enabled;
}

export function usePersianDigits(): boolean {
  return getJalaliOptions().digits === 'persian';
}

/** Test seam: forget the memoised options. */
export function resetJalaliOptions(): void {
  cached = null;
}
