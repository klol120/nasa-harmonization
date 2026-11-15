/** Minimal RFC-4180 CSV writer (quoted fields, embedded commas/newlines). */

const escape = (v: unknown) => {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function toCsv<T extends object>(rows: T[], columns?: (keyof T)[]): string {
  if (!rows.length && !columns) return "";
  const cols = columns ?? (Object.keys(rows[0]) as (keyof T)[]);
  const lines = [cols.map(escape).join(",")];
  for (const r of rows) lines.push(cols.map((c) => escape(r[c])).join(","));
  return lines.join("\n");
}
