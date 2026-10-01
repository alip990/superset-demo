/**
 * Minimal declarations of the Superset modules this plugin imports, used *only*
 * by `npm run typecheck` in this directory. The real build resolves the real
 * packages inside superset-frontend, where these same imports are type-checked
 * for real; the point of this file is to catch a typo or a wrong call signature
 * without a 20-minute frontend install. Signatures are copied from
 * apache/superset 6.1.0 - update them when the plugin is moved to a new tag.
 */
declare module '@superset-ui/core' {
  export const PREVIEW_TIME: Date;
  export const SMART_DATE_ID: string;
  export const SMART_DATE_VERBOSE_ID: string;
  export const SMART_DATE_DETAILED_ID: string;
  export class TimeFormatter {
    constructor(config: {
      id: string;
      label?: string;
      description?: string;
      // the real TimeFormatFunction: TimeFormatter.format() deals with
      // null/undefined itself before calling this
      formatFunc: (value: Date) => string;
      useLocalTime?: boolean;
    });

    format(value: Date | number | null | undefined): string;
  }
  export interface TimeFormatterRegistry {
    registerValue(key: string, value: TimeFormatter): TimeFormatterRegistry;
    get(key?: string): TimeFormatter;
    setDefaultKey(key: string): TimeFormatterRegistry;
  }
  export default function getTimeFormatterRegistry(): TimeFormatterRegistry;
  export function getTimeFormatterRegistry(): TimeFormatterRegistry;
  export function fetchTimeRange(
    timeRange: string,
    columnPlaceholder?: string,
    shifts?: string[],
  ): Promise<{ value: string | string[] } | { error: string }>;
  export const NO_TIME_RANGE: string;
}

declare module '@superset-ui/chart-controls' {
  export const D3_TIME_FORMAT_OPTIONS: [string, string][];
}

declare module '@superset-ui/core/components' {
  import type { ReactNode } from 'react';
  import type { Dayjs } from 'dayjs';

  export const DatePicker: (props: Record<string, unknown>) => JSX.Element;
  export const Input: (props: {
    className?: string;
    disabled?: boolean;
    value?: string;
    placeholder?: string;
    'aria-label'?: string;
    onChange?: (event: { target: { value: string } }) => void;
    onBlur?: () => void;
  }) => JSX.Element;
  export const Popover: (props: {
    trigger?: string;
    placement?: string;
    content?: ReactNode;
    children?: ReactNode;
    destroyTooltipOnHide?: boolean;
    getPopupContainer?: (trigger: HTMLElement) => HTMLElement;
  }) => JSX.Element;
  export const Button: (props: {
    children?: ReactNode;
    onClick?: () => void;
    buttonSize?: string;
    buttonStyle?: string;
    'aria-label'?: string;
    type?: string;
  }) => JSX.Element;
  export const Select: (props: {
    ariaLabel: string;
    value?: unknown;
    options: { value: unknown; label: ReactNode }[];
    onChange: (value: any) => void;
    showSearch?: boolean;
  }) => JSX.Element;
  export type { Dayjs };
}

declare module '@superset-ui/core/utils/dates' {
  import type { Dayjs } from 'dayjs';

  export function extendedDayjs(value?: Date | string | number): Dayjs;
}

declare module '@apache-superset/core/translation' {
  export function t(text: string, ...args: unknown[]): string;
}

declare module '@apache-superset/core/theme' {
  import type { ComponentType } from 'react';

  export interface SupersetTheme {
    [token: string]: any;
  }
  export function css(...args: unknown[]): string;
  type Interpolation =
    | string
    | number
    | ((props: { theme: SupersetTheme }) => string);
  type StyledTag = (
    strings: TemplateStringsArray,
    ...interpolations: Interpolation[]
  ) => ComponentType<any>;
  export const styled: Record<string, StyledTag> & {
    (component: ComponentType<any>): StyledTag;
  };
  export function useTheme(): SupersetTheme;
}

declare module 'src/utils/getBootstrapData' {
  export interface BootstrapData {
    common: {
      conf: Record<string, any>;
      feature_flags: Record<string, boolean>;
      [key: string]: any;
    };
    [key: string]: any;
  }
  export default function getBootstrapData(): BootstrapData;
}

declare module 'src/explore/components/controls/DateFilterControl/utils' {
  export const COMMON_RANGE_OPTIONS: { value: string; label: string }[];
  export const CALENDAR_RANGE_OPTIONS: { value: string; label: string }[];
  export const CURRENT_RANGE_OPTIONS: { value: string; label: string }[];
  export const COMMON_RANGE_VALUES_SET: Set<string>;
  export const CALENDAR_RANGE_VALUES_SET: Set<string>;
  export const CURRENT_RANGE_VALUES_SET: Set<string>;
  export const COMMON_RANGE_SET: Set<string>;
  export const CALENDAR_RANGE_SET: Set<string>;
  export const CURRENT_CALENDAR_RANGE_SET: Set<string>;
  export const DAYJS_FORMAT: string;
}
