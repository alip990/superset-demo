import { parseLiteral, toLatinDigits } from './jalali';

/** A year/month literal is valid range syntax but is unfinished picker input. */
export function parsePickerText(text: string): Date | null {
  const value = toLatinDigits(text.trim());
  if (!/^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?$/.test(value)) return null;
  return parseLiteral(value)?.date ?? null;
}

export function parseTime(text: string): {hours: number; minutes: number; seconds: number} | null {
  const value = toLatinDigits(text.trim());
  if (!/^\d{1,2}:\d{2}(?::\d{2})?$/.test(value)) return null;
  const [hours, minutes, seconds = 0] = value.split(':').map(Number);
  return hours < 24 && minutes < 60 && seconds < 60 ? { hours, minutes, seconds } : null;
}
