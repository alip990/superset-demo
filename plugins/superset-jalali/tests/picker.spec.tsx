import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import dayjs from 'dayjs';
import Picker from '../src/components/JalaliDatePicker';
import Panel from '../src/components/JalaliCalendarPanel';
import { resetJalaliOptions } from '../src/options';
import { options } from './bootstrapHarness';
import { fromJalali } from '../src/core/jalali';
import { businessToStorage, businessNow, storageToBusiness } from '../src/core/timezone';
import { parsePickerText, parseTime } from '../src/core/picker';

beforeEach(() => { options.enabled = true; resetJalaliOptions(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });
const clock = { storageTimezone: 'UTC' as const, businessTimezone: 'Asia/Tehran', shiftMinutes: 0 };

test('partial typing never commits a year or month; blur commits complete Gregorian storage value', async () => {
  const changed = vi.fn();
  render(<Picker showTime onChange={changed} />);
  const input = screen.getByLabelText('Jalali date');
  await userEvent.type(input, '1404');
  expect((input as HTMLInputElement).value).toBe('1404');
  expect(changed).not.toHaveBeenCalled();
  await userEvent.type(input, '/01/01 12:30:00');
  expect(changed).not.toHaveBeenCalled();
  fireEvent.blur(input);
  expect(changed).toHaveBeenCalledTimes(1);
  expect(changed.mock.calls[0][0].format('YYYY-MM-DD HH:mm:ss')).toBe('2025-03-21 09:00:00');
});

test('invalid input stays visible and never becomes a different normalized time', () => {
  const changed = vi.fn(); render(<Picker showTime onChange={changed} />);
  const input = screen.getByLabelText('Jalali date');
  for (const text of ['1404/12/30', '1404/01/01 25:00', '1404/01/01 12:99', '1404/01', '']) {
    fireEvent.change(input, { target: { value: text } }); fireEvent.blur(input);
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect((input as HTMLInputElement).value).toBe(text);
    expect(changed).not.toHaveBeenCalled();
  }
});

test('Enter confirms and Escape restores the existing value', () => {
  const changed = vi.fn(); render(<Picker onChange={changed} defaultValue={dayjs('2025-03-20T20:30:00')} />);
  const input = screen.getByLabelText('Jalali date');
  fireEvent.change(input, { target: { value: '1404/01/02' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(changed.mock.calls[0][0].format('YYYY-MM-DD HH:mm:ss')).toBe('2025-03-21 20:30:00');
  fireEvent.change(input, { target: { value: '140' } });
  fireEvent.keyDown(input, { key: 'Escape' });
  expect((input as HTMLInputElement).value).toBe('1404/01/02');
});

test('Today uses business wall clock and serializes the original instant', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2025-03-20T21:15:00Z'));
  const changed = vi.fn(); render(<Picker showTime onChange={changed} />);
  fireEvent.click(screen.getByText('امروز'));
  expect(changed.mock.calls[0][0].format('YYYY-MM-DD HH:mm:ss')).toBe('2025-03-20 21:15:00');
  expect((screen.getByLabelText('Jalali date') as HTMLInputElement).value).toBe('1404/01/01 00:45:00');
});

test('panel rejects out-of-range time without changing selected day', () => {
  const changed = vi.fn(); render(<Panel value={new Date('2025-03-21T00:00:00Z')} showTime onChange={changed} clock={clock} />);
  const input = screen.getByLabelText('Time');
  for (const value of ['25:00', '12:99', '12:30:99']) fireEvent.change(input, { target: { value } });
  expect(changed).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: '۲۳:۵۹:۵۹' } });
  expect(changed.mock.calls[0][0].toISOString()).toBe('2025-03-21T23:59:59.000Z');
});

test('disabled calendar delegates to the original host picker', () => {
  options.enabled = false; resetJalaliOptions(); render(<Picker />);
  expect(screen.getByLabelText('Gregorian host picker')).toBeTruthy();
  expect(screen.queryByLabelText('Jalali date')).toBeNull();
});

test('IANA historical DST, midnight and fold conversions have known expected values', () => {
  expect(businessToStorage(new Date('2021-07-01T00:00:00Z'), clock).toISOString()).toBe('2021-06-30T19:30:00.000Z');
  expect(storageToBusiness(new Date('2025-03-20T20:30:00Z'), clock).toISOString()).toBe('2025-03-21T00:00:00.000Z');
  expect(businessNow(clock, new Date('2025-03-20T20:30:00Z')).toISOString()).toBe('2025-03-21T00:00:00.000Z');
  for (const time of ['2025-03-09T02:30:00Z', '2025-11-02T01:30:00Z']) {
    expect(() => businessToStorage(new Date(time), { ...clock, businessTimezone: 'America/New_York' })).toThrow();
  }
});

test('pure date and time validation refuses partial and invalid values', () => {
  expect(parsePickerText('1404')).toBeNull(); expect(parsePickerText('1404/01')).toBeNull();
  expect(parsePickerText('۱۴۰۴/۰۱/۰۱')?.toISOString()).toBe('2025-03-21T00:00:00.000Z');
  expect(parseTime('25:00')).toBeNull(); expect(parseTime('12:99')).toBeNull();
  expect(() => fromJalali(1404, 1, 1, { hours: 25 })).toThrow();
});
