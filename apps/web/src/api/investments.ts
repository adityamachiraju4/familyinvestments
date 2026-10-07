import { request } from "./client";
export interface Actual {
  contributed: string;
  current_value: string | null;
  gain_loss: string | null;
  xirr: string | null;
  valuation_date: string | null;
  history_complete: boolean;
}
export interface SIP {
  id: number;
  scheme_name: string;
  source: string;
  category: string;
  monthly_amount: string;
  sip_day: number | null;
  start_date: string;
  status: string;
  scheme_actual: Actual;
}
export interface Point {
  future_contributions: string;
  projected_growth: string;
  projected_value: string;
  total_contributions?: string;
}
export type Horizons = Record<"one_year" | "five_years" | "ten_years", Point>;
export interface Projections {
  scenarios: { name: string; annual_return: string }[];
  assumption_percent: string;
  disclosure: string;
  corpus_complete: boolean;
  starting_corpus: string;
  monthly_sip: string;
  sips: {
    id: number;
    scheme_name: string;
    allocated_starting_corpus: string;
    projections: Horizons;
  }[];
  combined: Horizons;
  chart: (Point & { year: number; total_contributions: string })[];
}
export interface MFSummary extends Actual {
  active_sips: number;
  monthly_sip: string;
  monthly_mf_contributions: string;
}
export const investments = {
  sips: () => request<SIP[]>("/investments/sips"),
  summary: () => request<MFSummary>("/investments/mutual-funds/summary"),
  projections: (rate = "10") =>
    request<Projections>(
      `/investments/sips/projections?annual_return=${encodeURIComponent(rate)}`,
    ),
};
