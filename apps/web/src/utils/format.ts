export const numeric = (value: unknown): number | null =>
  value === null || value === undefined || value === ""
    ? null
    : Number.isFinite(Number(value))
      ? Number(value)
      : null;
export const money = (value: unknown) =>
  numeric(value) === null
    ? "—"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(numeric(value)!);
export const percent = (value: unknown) =>
  numeric(value) === null
    ? "—"
    : `${numeric(value)! > 0 ? "+" : ""}${numeric(value)!.toFixed(2)}%`;
export const quantity = (value: unknown) =>
  numeric(value) === null
    ? "—"
    : new Intl.NumberFormat("en-IN", { maximumFractionDigits: 4 }).format(
        numeric(value)!,
      );
export const pnlClass = (value: unknown) =>
  numeric(value) === null || numeric(value) === 0
    ? "neutral"
    : numeric(value)! > 0
      ? "positive"
      : "negative";
export function dateLabel(value: string | null | undefined, time = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    ...(time ? { hour: "numeric", minute: "2-digit" } : { year: "numeric" }),
    timeZone: "Asia/Kolkata",
  }).format(date);
}
export const bucketLabels = {
  NIFTY_50: "Nifty 50",
  MID_CAP: "Midcap",
  SMALL_CAP: "Smallcap",
  LARGE_CAP: "Largecap",
  OTHER: "Other",
  UNCLASSIFIED: "Needs classification",
};
