export function formatRelativeTime(input: string | number | Date, nowInput?: string | number | Date): string {
  const now = nowInput ? new Date(nowInput).getTime() : Date.now();
  const time = new Date(input).getTime();
  if (Number.isNaN(time)) return '';

  const diffMs = time - now;
  const absMs = Math.abs(diffMs);
  const rtf = (Intl as any)?.RelativeTimeFormat
    ? new Intl.RelativeTimeFormat(undefined, { numeric: 'auto', style: 'narrow' })
    : null;

  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const week = 7 * day;
  const month = 30 * day;
  const year = 365 * day;

  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [year, 'year'],
    [month, 'month'],
    [week, 'week'],
    [day, 'day'],
    [hour, 'hour'],
    [minute, 'minute'],
  ];

  for (const [unitMs, unit] of units) {
    if (absMs >= unitMs || unit === 'minute') {
      const value = Math.round(diffMs / unitMs);
      if (rtf) return (rtf as Intl.RelativeTimeFormat).format(value, unit);
      const suffix = value <= 0 ? 'ago' : 'from now';
      return `${Math.abs(value)} ${String(unit)}${Math.abs(value) === 1 ? '' : 's'} ${suffix}`;
    }
  }
  return 'just now';
}

export function formatLocalDatetime(input: string | number | Date): string {
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  } as Intl.DateTimeFormatOptions);
}


