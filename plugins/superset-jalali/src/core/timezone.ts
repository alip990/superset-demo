/** Dates representing wall clocks use UTC fields. Never use the browser zone. */
export interface ClockOptions {
  storageTimezone: 'wall' | 'UTC';
  businessTimezone: string;
  shiftMinutes: number;
}

export function instantToWall(instant: Date, zone: string): Date {
  const fields: Record<string, number> = {};
  new Intl.DateTimeFormat('en-GB-u-ca-gregory-nu-latn', {
    timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(instant).forEach(part => { fields[part.type] = Number(part.value); });
  return new Date(Date.UTC(fields.year, fields.month - 1, fields.day,
    fields.hour, fields.minute, fields.second, instant.getUTCMilliseconds()));
}

export function storageToBusiness(value: Date, clock: ClockOptions): Date {
  if (clock.shiftMinutes) return new Date(value.getTime() + clock.shiftMinutes * 60000);
  return clock.storageTimezone === 'UTC' ? instantToWall(value, clock.businessTimezone) : value;
}

export function businessToStorage(wall: Date, clock: ClockOptions): Date {
  if (clock.shiftMinutes) return new Date(wall.getTime() - clock.shiftMinutes * 60000);
  if (clock.storageTimezone === 'wall') return wall;
  // Sample surrounding offsets, then validate candidates by round-trip. This
  // rejects both DST gaps and folds instead of silently normalizing user input.
  const candidates = new Set<number>();
  for (const hours of [-36, 0, 36]) {
    const sample = new Date(wall.getTime() + hours * 3600000);
    const offset = instantToWall(sample, clock.businessTimezone).getTime() - sample.getTime();
    const candidate = wall.getTime() - offset;
    if (instantToWall(new Date(candidate), clock.businessTimezone).getTime() === wall.getTime()) {
      candidates.add(candidate);
    }
  }
  if (candidates.size !== 1) throw new RangeError('Ambiguous or nonexistent business time');
  return new Date([...candidates][0]);
}

export function businessNow(clock: ClockOptions, now = new Date()): Date {
  return clock.shiftMinutes
    ? new Date(now.getTime() + clock.shiftMinutes * 60000)
    : instantToWall(now, clock.businessTimezone);
}
