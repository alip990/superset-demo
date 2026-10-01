/**
 * Not shipped: superset/Dockerfile only copies src/. This file reproduces, line
 * for line, how the components of apache/superset 6.1.0 use the exports the
 * patches redirect, so `npm run typecheck` fails here if a prop or a signature
 * drifts away from what upstream passes - the one kind of breakage an offline
 * check can still catch without installing the whole frontend.
 */
import type { Dayjs } from 'dayjs';
import { JalaliDatePicker, fetchTimeRange } from '../src/index';

const DAYJS_FORMAT = 'YYYY-MM-DD[T]HH:mm:ss';
declare const dttmToDayjs: (dttm: string) => Dayjs;
declare const onChange: (control: string, value: string) => void;
declare const isOverflowingFilterBar: boolean;

// CustomFrame.tsx, "Start (inclusive)" and "End (exclusive)"
export const since = (
  <JalaliDatePicker
    showTime
    defaultValue={dttmToDayjs('2025-03-10T00:00:00')}
    onChange={(datetime: Dayjs) =>
      onChange('sinceDatetime', datetime.format(DAYJS_FORMAT))
    }
    allowClear={false}
    getPopupContainer={(triggerNode: HTMLElement) =>
      isOverflowingFilterBar
        ? (triggerNode.parentNode as HTMLElement)
        : document.body
    }
  />
);

// CustomFrame.tsx, "Anchor to"
export const anchor = (
  <JalaliDatePicker
    showTime
    defaultValue={dttmToDayjs('now')}
    onChange={(datetime: Dayjs) =>
      onChange('anchorValue', datetime.format(DAYJS_FORMAT))
    }
    allowClear={false}
    className="control-anchor-to-datetime"
    getPopupContainer={(triggerNode: HTMLElement) =>
      triggerNode.parentNode as HTMLElement
    }
  />
);

// DateFilterLabel.tsx: both call sites of fetchTimeRange
export async function labelUsage(value: string): Promise<string> {
  const { value: actualRange, error } = (await fetchTimeRange(value)) as {
    value?: string;
    error?: string;
  };
  return error ?? actualRange ?? '';
}
