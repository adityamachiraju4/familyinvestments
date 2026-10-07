import type { ReactNode } from "react";
import { money, percent, pnlClass } from "../utils/format";
export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && <h2>{title}</h2>}
      {children}
    </section>
  );
}
export function State({
  loading,
  error,
  empty,
}: {
  loading?: boolean;
  error?: string;
  empty?: string;
}) {
  return loading ? (
    <div className="skeleton" role="status" aria-label="Loading portfolio data">
      <span />
      <span />
      <span />
    </div>
  ) : (
    <p className="empty" role={error ? "alert" : undefined}>
      {error === "Zerodha connection expired"
        ? "Connect Zerodha to update these values."
        : error || empty}
    </p>
  );
}
export function Metric({
  label,
  value,
  detail,
  pnl = false,
}: {
  label: string;
  value: unknown;
  detail?: string;
  pnl?: boolean;
}) {
  return (
    <Card>
      <p className="eyebrow">{label}</p>
      <div className={`metric ${pnl ? pnlClass(value) : ""}`}>
        {money(value)}
      </div>
      {detail && <p className="muted">{detail}</p>}
    </Card>
  );
}
export function Pnl({ value, rate }: { value: unknown; rate: unknown }) {
  return (
    <span className={pnlClass(value)}>
      {money(value)} <small>{percent(rate)}</small>
    </span>
  );
}
