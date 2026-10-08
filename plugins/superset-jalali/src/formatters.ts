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
 * Jalali entries in Superset's time-format registry.
 *
 * Superset formats every temporal value in the browser through
 * getTimeFormatterRegistry(); its default entry, smart_date ("Adaptive
 * formatting"), is what axes and tooltips use unless a chart picks a format.
 * This module
 *   - registers named Jalali formats, which show up in every chart's
 *     "Time format" / "X axis time format" dropdown, and
 *   - replaces smart_date and its tooltip variants when
 *     JALALI_CALENDAR_OPTIONS.overrideSmartDate is on, so charts that were
 *     built before the plugin become Jalali without being edited.
 */
import {
  getTimeFormatterRegistry,
  PREVIEW_TIME,
  SMART_DATE_DETAILED_ID,
  SMART_DATE_ID,
  SMART_DATE_VERBOSE_ID,
  TimeFormatter,
} from '@superset-ui/core';
import { D3_TIME_FORMAT_OPTIONS } from '@superset-ui/chart-controls';
import {
  FormatOptions,
  NAMED_FORMATS,
  formatJalali,
  formatSmart,
} from './core/jalali';
import { getJalaliOptions } from './options';
import { storageToBusiness } from './core/timezone';

export const JALALI_SMART_ID = 'jalali_smart';

/** Titles for the dropdown; the sample value is appended from the formatter. */
const TITLES: Record<string, string> = {
  jalali_smart: 'شمسی - هوشمند',
  jalali_date: 'شمسی - تاریخ',
  jalali_datetime: 'شمسی - تاریخ و زمان',
  jalali_minute: 'شمسی - تا دقیقه',
  jalali_month: 'شمسی - ماه',
  jalali_month_short: 'شمسی - ماه (عددی)',
  jalali_quarter: 'شمسی - فصل',
  jalali_year: 'شمسی - سال',
  jalali_week: 'شمسی - هفته',
  jalali_verbose: 'شمسی - کامل',
  jalali_day_month: 'شمسی - روز و ماه',
};

/** Formats that always use Persian digits, whatever the global digits option
 * is, so one dashboard can mix both. */
const PERSIAN_DIGIT_VARIANTS = ['jalali_date', 'jalali_datetime', 'jalali_month',
  'jalali_verbose', 'jalali_smart'];

type FormatFunc = (value: Date) => string;

function formatterFor(id: string, options: FormatOptions): FormatFunc {
  const pattern = NAMED_FORMATS[id];
  const clock = getJalaliOptions();
  return pattern === undefined
    ? (value: Date) => formatSmart(storageToBusiness(value, clock), options)
    : (value: Date) => formatJalali(storageToBusiness(value, clock), pattern, options);
}

function register(id: string, title: string, formatFunc: FormatFunc,
                  addToDropdown = true): void {
  let sample = '';
  try {
    sample = formatFunc(PREVIEW_TIME);
  } catch {
    sample = '';
  }
  const label = sample ? `${title} | ${sample}` : title;
  getTimeFormatterRegistry().registerValue(
    id,
    new TimeFormatter({ id, label, formatFunc, useLocalTime: false }),
  );
  // the array is shared by every control panel, so pushing adds the format to
  // every chart's time-format dropdown
  if (addToDropdown && !D3_TIME_FORMAT_OPTIONS.some(([value]) => value === id)) {
    D3_TIME_FORMAT_OPTIONS.push([id, label]);
  }
}

/** Register every Jalali time format. Returns the ids registered. */
export default function registerJalaliFormatters(): string[] {
  const { digits, enabled, overrideSmartDate } = getJalaliOptions();
  const base: FormatOptions = {
    persianDigits: digits === 'persian',
  };
  const persian: FormatOptions = { persianDigits: true };
  const registered: string[] = [];

  [JALALI_SMART_ID, ...Object.keys(NAMED_FORMATS)].forEach(id => {
    register(id, TITLES[id] ?? id, formatterFor(id, base));
    registered.push(id);
  });
  PERSIAN_DIGIT_VARIANTS.forEach(id => {
    const variant = `${id}_fa`;
    register(variant, `${TITLES[id] ?? id} (ارقام فارسی)`,
      formatterFor(id, persian));
    registered.push(variant);
  });

  if (enabled && overrideSmartDate) {
    // Superset's own ids, so charts that never chose a format follow along
    register(SMART_DATE_ID, 'Adaptive formatting (شمسی)',
      formatterFor(JALALI_SMART_ID, base), false);
    register(SMART_DATE_VERBOSE_ID, 'شمسی - کامل',
      formatterFor('jalali_verbose', base), false);
    register(SMART_DATE_DETAILED_ID, 'شمسی - تاریخ و زمان',
      formatterFor('jalali_datetime', base), false);
    registered.push(SMART_DATE_ID, SMART_DATE_VERBOSE_ID, SMART_DATE_DETAILED_ID);
  }
  return registered;
}
