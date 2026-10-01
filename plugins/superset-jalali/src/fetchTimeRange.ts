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
 * fetchTimeRange() with the resolved range shown in Jalali.
 *
 * Superset asks /api/v1/time_range/ what a time range resolves to and renders
 * the answer in the control's pill, its tooltip and the "Actual time range"
 * line of the popover. The server answers in ISO Gregorian - correctly, since
 * that is what the query will use - so the translation to Jalali belongs here.
 *
 * patches/03-date-filter-label.sh points DateFilterLabel at this wrapper
 * instead of the one in @superset-ui/core; everything else keeps using the
 * original.
 */
import { fetchTimeRange as original } from '@superset-ui/core';
import { isJalaliEnabled } from './options';
import { jalaliRangeLabel, jalaliseTimeRangeText } from './ranges';

type FetchTimeRange = typeof original;

export const fetchTimeRange: FetchTimeRange = async (
  timeRange: string,
  columnPlaceholder?: string,
  shifts?: string[],
) => {
  const result = await original(timeRange, columnPlaceholder, shifts);
  if (!isJalaliEnabled() || !result || 'error' in result) return result;
  const { value } = result as { value: string | string[] };
  if (Array.isArray(value)) {
    return { value: value.map(jalaliseTimeRangeText) };
  }
  if (typeof value === 'string') {
    return { value: jalaliseTimeRangeText(value) };
  }
  return result;
};

/** A Persian name for a stored range, for tooltips: the shortcut's label when
 * it is one of ours, the Jalali-ised text otherwise. */
export function describeTimeRange(value: string): string {
  const label = jalaliRangeLabel(value);
  return label === value ? jalaliseTimeRangeText(value) : label;
}

export default fetchTimeRange;
