export const options = { enabled: true, storageTimezone: 'UTC', businessTimezone: 'Asia/Tehran', shiftMinutes: 0 };
export default () => ({ common: { conf: { JALALI_CALENDAR_FRONTEND_OPTIONS: options } } });
