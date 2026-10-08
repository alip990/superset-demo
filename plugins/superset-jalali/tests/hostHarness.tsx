// UNIT TEST ADAPTER ONLY. This is not evidence of Superset host integration.
import React from 'react';
import dayjs from 'dayjs';
export const t = (text: string) => text;
export const css = () => '';
export const styled = { div: () => (props: any) => <div {...props} /> };
export const extendedDayjs = dayjs;
export const Input = (props: any) => <input {...props} />;
export const DatePicker = () => <input aria-label="Gregorian host picker" />;
export const Popover = ({ children, content }: any) => <div>{children}{content}</div>;
export const Button = ({ children, buttonSize, buttonStyle, ...props }: any) => <button {...props}>{children}</button>;
export const Select = ({ ariaLabel, options, onChange, value }: any) =>
  <select aria-label={ariaLabel} value={value} onChange={e => onChange(e.target.value)}>
    {options.map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}
  </select>;
