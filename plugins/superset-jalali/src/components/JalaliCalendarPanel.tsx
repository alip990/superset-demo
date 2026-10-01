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
 * A Jalali month grid: the popup of JalaliDatePicker.
 *
 * Written from scratch on Superset's own components instead of pulling in
 * antd-jalali / dayjs-jalali, because adding a dependency means changing
 * superset-frontend/package.json and package-lock.json, and the whole point of
 * this plugin is that `npm ci` in the image build stays untouched.
 *
 * Iranian conventions it has to get right: the week starts on Saturday, Friday
 * is the weekend (optionally Thursday too), month lengths are 31/31/31/31/31/31/
 * 30/30/30/30/30/29-or-30, and the digits may be Persian.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { css, styled } from '@apache-superset/core/theme';
import { Button, Input, Select } from '@superset-ui/core/components';
import {
  MONTH_NAMES,
  WEEKDAY_NAMES_SHORT,
  dayOfWeek,
  daysInMonth,
  formatJalali,
  fromJalali,
  toJalali,
  toPersianDigits,
} from '../core/jalali';

export interface JalaliCalendarPanelProps {
  /** the selected instant, read as UTC wall clock */
  value?: Date;
  onChange: (value: Date) => void;
  /** show the time-of-day row */
  showTime?: boolean;
  persianDigits?: boolean;
  thursdayIsWeekend?: boolean;
  /** years offered in the year dropdown, around the selected one */
  yearSpan?: number;
}

const Wrapper = styled.div`
  ${({ theme }) => css`
    direction: rtl;
    width: 268px;
    font-size: ${theme.fontSize}px;

    .jalali-header {
      display: flex;
      align-items: center;
      gap: ${theme.sizeUnit}px;
      margin-bottom: ${2 * theme.sizeUnit}px;
    }

    .jalali-header .ant-select {
      flex: 1;
    }

    .jalali-grid {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 2px;
      outline: none;
    }

    .jalali-weekday {
      text-align: center;
      color: ${theme.colorTextTertiary};
      font-size: ${theme.fontSizeSM}px;
      padding-bottom: ${theme.sizeUnit}px;
    }

    .jalali-day {
      border: none;
      background: none;
      border-radius: ${theme.borderRadius}px;
      padding: ${theme.sizeUnit}px 0;
      cursor: pointer;
      color: ${theme.colorText};
      font-variant-numeric: tabular-nums;
    }

    .jalali-day:hover {
      background: ${theme.colorPrimaryBg};
    }

    .jalali-day.is-weekend {
      color: ${theme.colorError};
    }

    .jalali-day.is-today {
      border: 1px solid ${theme.colorPrimary};
    }

    .jalali-day.is-selected {
      background: ${theme.colorPrimary};
      color: ${theme.colorBgContainer};
    }

    .jalali-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: ${theme.sizeUnit}px;
      margin-top: ${2 * theme.sizeUnit}px;
    }

    .jalali-time {
      width: 96px;
      direction: ltr;
      text-align: center;
    }
  `}
`;

const digits = (value: number | string, persian?: boolean) =>
  (persian ? toPersianDigits(String(value)) : String(value));

/** Today as a UTC wall-clock instant, so "today" means the user's today. */
function todayUtc(): Date {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
}

export default function JalaliCalendarPanel({
  value,
  onChange,
  showTime = false,
  persianDigits = false,
  thursdayIsWeekend = false,
  yearSpan = 60,
}: JalaliCalendarPanelProps) {
  const selected = value ?? todayUtc();
  const selectedParts = toJalali(selected);
  const [{ jy, jm }, setShown] = useState({
    jy: selectedParts.jy,
    jm: selectedParts.jm,
  });
  const [timeText, setTimeText] = useState(() => formatJalali(selected, 'HH:mm:ss'));
  const gridRef = useRef<HTMLDivElement>(null);

  // follow the value when the control is driven from outside (Apply, reset)
  useEffect(() => {
    setShown({ jy: selectedParts.jy, jm: selectedParts.jm });
    setTimeText(formatJalali(selected, 'HH:mm:ss'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected.getTime()]);

  const today = todayUtc();
  const todayParts = toJalali(today);
  const monthLength = daysInMonth(jy, jm);
  // weekday of the 1st, 0 = Saturday: how many blanks the grid starts with
  const leading = dayOfWeek(fromJalali(jy, jm, 1));

  const years = useMemo(() => {
    const first = todayParts.jy - yearSpan;
    return Array.from({ length: 2 * yearSpan + 1 }, (_, index) => first + index);
  }, [todayParts.jy, yearSpan]);

  const emit = useCallback(
    (day: number, time = timeText) => {
      const [hours = 0, minutes = 0, seconds = 0] = time
        .split(':')
        .map(part => Number(part) || 0);
      onChange(fromJalali(jy, jm, Math.min(day, daysInMonth(jy, jm)),
        { hours, minutes, seconds }));
    },
    [jm, jy, onChange, timeText],
  );

  const shiftMonth = useCallback((delta: number) => {
    setShown(({ jy: year, jm: month }) => {
      const total = year * 12 + month - 1 + delta;
      return { jy: Math.floor(total / 12), jm: (total % 12) + 1 };
    });
  }, []);

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = {
      // right/left are mirrored: the grid is right-to-left
      ArrowRight: -1, ArrowLeft: 1, ArrowUp: -7, ArrowDown: 7,
    };
    const delta = moves[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    const day = selectedParts.jy === jy && selectedParts.jm === jm
      ? selectedParts.jd
      : 1;
    const next = day + delta;
    if (next >= 1 && next <= monthLength) {
      emit(next);
      return;
    }
    shiftMonth(next < 1 ? -1 : 1);
  };

  return (
    <Wrapper data-test="jalali-calendar">
      <div className="jalali-header">
        <Button buttonSize="xsmall" buttonStyle="tertiary"
          onClick={() => shiftMonth(-1)} aria-label={t('Previous month')}>
          ‹
        </Button>
        <Select
          ariaLabel={t('Month')}
          value={jm}
          options={MONTH_NAMES.map((name, index) => ({ value: index + 1, label: name }))}
          onChange={(month: any) => setShown(shown => ({ ...shown, jm: Number(month) }))}
          showSearch={false}
        />
        <Select
          ariaLabel={t('Year')}
          value={jy}
          options={years.map(year => ({
            value: year,
            label: digits(year, persianDigits),
          }))}
          onChange={(year: any) => setShown(shown => ({ ...shown, jy: Number(year) }))}
        />
        <Button buttonSize="xsmall" buttonStyle="tertiary"
          onClick={() => shiftMonth(1)} aria-label={t('Next month')}>
          ›
        </Button>
      </div>

      <div className="jalali-grid" role="grid" tabIndex={0} ref={gridRef}
        onKeyDown={onKeyDown}>
        {WEEKDAY_NAMES_SHORT.map((name, index) => (
          <div className="jalali-weekday" key={`weekday-${index}`}>{name}</div>
        ))}
        {Array.from({ length: leading }, (_, index) => (
          <div key={`blank-${index}`} />
        ))}
        {Array.from({ length: monthLength }, (_, index) => index + 1).map(day => {
          const dow = (leading + day - 1) % 7;
          const classes = ['jalali-day'];
          if (dow === 6 || (thursdayIsWeekend && dow === 5)) classes.push('is-weekend');
          if (todayParts.jy === jy && todayParts.jm === jm && todayParts.jd === day) {
            classes.push('is-today');
          }
          if (selectedParts.jy === jy && selectedParts.jm === jm
            && selectedParts.jd === day) {
            classes.push('is-selected');
          }
          return (
            <button type="button" key={day} className={classes.join(' ')}
              onClick={() => emit(day)}
              aria-label={formatJalali(fromJalali(jy, jm, day), 'dddd D MMMM YYYY')}>
              {digits(day, persianDigits)}
            </button>
          );
        })}
      </div>

      <div className="jalali-footer">
        <Button buttonSize="xsmall" buttonStyle="link"
          onClick={() => {
            setShown({ jy: todayParts.jy, jm: todayParts.jm });
            onChange(showTime ? new Date() : today);
          }}>
          {t('امروز')}
        </Button>
        {showTime && (
          <Input
            className="jalali-time"
            aria-label={t('Time')}
            value={timeText}
            onChange={event => {
              const next = event.target.value;
              setTimeText(next);
              if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(next)) {
                emit(selectedParts.jy === jy && selectedParts.jm === jm
                  ? selectedParts.jd : 1, next);
              }
            }}
          />
        )}
      </div>
    </Wrapper>
  );
}
