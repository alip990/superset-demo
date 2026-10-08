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
 * A Jalali replacement for the antd DatePicker used by Superset's date-filter
 * popover, with the same props, so patches/02-custom-frame-picker.sh can swap
 * it in with a two-line edit and nothing else in CustomFrame changes.
 *
 * The user can type (1403/12/20, ۱۴۰۳/۱۲/۲۰, 1403-12-20 14:30) or pick from the
 * month grid; either way the value leaves as the same `Dayjs` upstream expects
 * and is stored as the same ISO Gregorian string, so a chart saved with this
 * picker is readable by a stock Superset.
 *
 * Wall clock vs UTC: dayjs values here are wall-clock - upstream formats them
 * with DAYJS_FORMAT and never converts a zone - while the calendar core works
 * in UTC. The two bridges below move between them by parts, which is what keeps
 * a date from sliding a day in a browser east or west of UTC.
 */
import { useEffect, useMemo, useState } from 'react';
import type { Dayjs } from 'dayjs';
import { t } from '@apache-superset/core/translation';
import { DatePicker, Input, Popover } from '@superset-ui/core/components';
import { extendedDayjs } from '@superset-ui/core/utils/dates';
import { formatJalali } from '../core/jalali';
import { parsePickerText } from '../core/picker';
import { storageToBusiness, businessToStorage } from '../core/timezone';
import { getJalaliOptions, isJalaliEnabled } from '../options';
import JalaliCalendarPanel from './JalaliCalendarPanel';

export interface JalaliDatePickerProps {
  showTime?: boolean;
  value?: Dayjs;
  defaultValue?: Dayjs;
  onChange?: (value: Dayjs) => void;
  /** accepted for API compatibility with antd; this control always has a value */
  allowClear?: boolean;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
  getPopupContainer?: (trigger: HTMLElement) => HTMLElement;
}

const DATE_PATTERN = 'YYYY/MM/DD';
const DATETIME_PATTERN = 'YYYY/MM/DD HH:mm:ss';

/** wall-clock Dayjs -> the same wall clock as a UTC instant */
const toUtc = (value: Dayjs): Date =>
  new Date(Date.UTC(value.year(), value.month(), value.date(),
    value.hour(), value.minute(), value.second()));

/** UTC instant -> a Dayjs with the same wall clock in the browser's zone */
const fromUtc = (value: Date): Dayjs =>
  extendedDayjs(new Date(value.getUTCFullYear(), value.getUTCMonth(),
    value.getUTCDate(), value.getUTCHours(), value.getUTCMinutes(),
    value.getUTCSeconds()));

export default function JalaliDatePicker(props: JalaliDatePickerProps) {
  const { showTime, value, defaultValue, onChange, className, disabled,
    placeholder, getPopupContainer } = props;
  const clock = getJalaliOptions();
  const { digits } = clock;
  const persianDigits = digits === 'persian';
  const pattern = showTime ? DATETIME_PATTERN : DATE_PATTERN;

  const [current, setCurrent] = useState<Dayjs | undefined>(value ?? defaultValue);
  const [text, setText] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);

  // follow the value the frame hands back after each change
  const incoming = value ?? defaultValue;
  const incomingKey = incoming ? incoming.valueOf() : 0;
  useEffect(() => {
    if (incoming && (!current || !incoming.isSame(current))) {
      setCurrent(incoming);
      setText(null);
      setInvalid(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incomingKey]);

  const display = useMemo(() => {
    if (text !== null) return text;
    if (!current) return '';
    try {
      return formatJalali(storageToBusiness(toUtc(current), clock), pattern, { persianDigits });
    } catch {
      return current.format(pattern);
    }
  }, [current, pattern, persianDigits, text, clock]);

  function commit(utcDate: Date) {
    let next: Dayjs;
    try {
      next = fromUtc(businessToStorage(utcDate, clock));
    } catch {
      setInvalid(true);
      return;
    }
    setCurrent(next);
    setText(null);
    setInvalid(false);
    onChange?.(next);
  }

  function confirmText() {
    if (text === null) return;
    const parsed = parsePickerText(text);
    if (parsed) commit(parsed);
    else setInvalid(true);
  }

  // Gregorian mode: behave exactly like the control this replaces
  if (!isJalaliEnabled()) {
    return <DatePicker {...props} />;
  }

  return (
    <Popover
      trigger="click"
      placement="bottomRight"
      destroyTooltipOnHide
      getPopupContainer={getPopupContainer}
      content={
        <JalaliCalendarPanel
          value={current ? storageToBusiness(toUtc(current), clock) : undefined}
          onChange={commit}
          showTime={showTime}
          persianDigits={persianDigits}
          thursdayIsWeekend={getJalaliOptions().thursdayIsWeekend}
          clock={clock}
        />
      }
    >
      <Input
        className={className}
        disabled={disabled}
        value={display}
        aria-label={t('Jalali date')}
        aria-invalid={invalid}
        placeholder={placeholder ?? (showTime ? DATETIME_PATTERN : DATE_PATTERN)}
        onChange={event => {
          const next = event.target.value;
          setText(next);
          setInvalid(false);
        }}
        onBlur={confirmText}
        onKeyDown={event => {
          if (event.key === 'Enter') confirmText();
          if (event.key === 'Escape') { setText(null); setInvalid(false); }
        }}
      />
    </Popover>
  );
}
