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
 * Jalali (Persian) calendar support for the Superset frontend.
 *
 * superset/Dockerfile copies this directory to superset-frontend/src/jalali/
 * and runs the scripts in ../patches, which call setupJalali() from Superset's
 * own setup and point two upstream components at the exports below. Nothing
 * here runs unless the backend published JALALI_CALENDAR_OPTIONS (see
 * superset/jalali_calendar/install.py) or the JALALI_CALENDAR feature flag is
 * on, so the same bundle serves a Gregorian installation unchanged.
 *
 * What it adds:
 *   formatters   Jalali time formats in every chart, and - when
 *                overrideSmartDate is on - as Superset's default, so existing
 *                charts and tooltips turn Jalali without being edited.
 *   ranges       Jalali shortcuts ("ماه جاری (شمسی)", "از ابتدای سال تا امروز")
 *                in the date-filter popover of every chart and native filter.
 *   picker       a Jalali month grid in the popover's Custom frame, typing
 *                included.
 *   pill/tooltip the resolved range, rendered in Jalali.
 */
import registerJalaliFormatters from './formatters';
import { registerJalaliRanges } from './ranges';
import { isJalaliEnabled } from './options';

export { default as JalaliDatePicker } from './components/JalaliDatePicker';
export { default as JalaliCalendarPanel } from './components/JalaliCalendarPanel';
export { fetchTimeRange, describeTimeRange } from './fetchTimeRange';
export {
  containsJalaliLiteral,
  isJalaliRange,
  jalaliRangeLabel,
  jalaliseTimeRangeText,
} from './ranges';
export { getJalaliOptions, isJalaliEnabled } from './options';
export * from './core/jalali';

/** Called at the end of Superset's setupFormatters(); safe to call twice. */
export default function setupJalali(): void {
  // the named formats are registered even when the calendar is off, so a chart
  // saved with "شمسی - ماه" keeps rendering after someone flips the switch
  registerJalaliFormatters();
  if (!isJalaliEnabled()) return;
  registerJalaliRanges();
}

export { registerJalaliFormatters, registerJalaliRanges };
