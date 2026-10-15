// Centralised date/time formatting — the whole app displays in IST (Asia/Kolkata)
// regardless of the viewing computer's timezone.

const IST = "Asia/Kolkata";

const DT_OPTS: Intl.DateTimeFormatOptions = {
  timeZone: IST, year: "numeric", month: "short", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true,
};
const DATE_OPTS: Intl.DateTimeFormatOptions = {
  timeZone: IST, year: "numeric", month: "short", day: "2-digit",
};

function toDate(value: unknown, assumeUtc: boolean): Date | null {
  if (value == null || value === "") return null;
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
  let s = String(value);
  // A bare "YYYY-MM-DD..." with no timezone is stamped: server times are UTC,
  // device event times are already IST (+05:30).
  const hasTz = /([zZ]|[+-]\d\d:?\d\d)$/.test(s);
  if (!hasTz && /^\d{4}-\d{2}-\d{2}/.test(s)) {
    s += assumeUtc ? "Z" : "+05:30";
  }
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

/** Server timestamps (stored as UTC) -> IST date+time. */
export function formatIST(value?: unknown): string {
  const d = toDate(value, true);
  return d ? d.toLocaleString("en-IN", DT_OPTS) : "-";
}

/** Date-only in IST. */
export function formatDateIST(value?: unknown): string {
  const d = toDate(value, true);
  return d ? d.toLocaleDateString("en-IN", DATE_OPTS) : "-";
}

/** Device event times (already IST local, e.g. punch LogDate) -> IST date+time. */
export function formatDeviceIST(value?: unknown): string {
  const d = toDate(value, false);
  return d ? d.toLocaleString("en-IN", DT_OPTS) : "-";
}

/** Relative "x ago". assumeUtc=true for server timestamps, false for device-IST times. */
export function timeAgoIST(value?: unknown, assumeUtc = true): string {
  const d = toDate(value, assumeUtc);
  if (!d) return "Just now";
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 0) return "Just now";
  if (sec < 60) return "Just now";
  if (sec < 3600) return `${Math.floor(sec / 60)} mins ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} hrs ago`;
  return assumeUtc ? formatIST(value) : formatDeviceIST(value);
}
