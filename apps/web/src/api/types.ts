export type Decimal = string | number;
export type Bucket =
  "NIFTY_50" | "MID_CAP" | "SMALL_CAP" | "LARGE_CAP" | "OTHER" | "UNCLASSIFIED";
export interface Summary {
  holdings_invested_value: Decimal;
  holdings_market_value: Decimal;
  available_cash: Decimal;
  total_account_value: Decimal;
  total_pnl: Decimal;
  total_pnl_percent: Decimal;
  holding_count: number;
  allocation: Record<Bucket, Decimal>;
  last_sync_at: string | null;
}
export interface Snapshot extends Omit<
  Summary,
  "allocation" | "last_sync_at" | "holding_count"
> {
  snapshot_date: string;
  unclassified_value: Decimal | null;
}
export interface Target {
  month: string;
  total_target: Decimal;
  nifty_target: Decimal;
  midcap_target: Decimal;
  smallcap_target: Decimal;
}
export interface Status {
  connection_status: string;
  last_sync_at: string | null;
  last_authenticated_at: string | null;
  credentials_present: boolean;
  token_valid: boolean;
  refresh_required: boolean;
  last_refresh_at: string | null;
}
export interface Holding {
  tradingsymbol: string;
  exchange: string;
  bucket: Bucket;
  quantity: number;
  average_price: Decimal;
  last_price: Decimal;
  invested_value: Decimal;
  current_value: Decimal;
  unrealised_pnl: Decimal;
  unrealised_pnl_percent: Decimal;
  synced_at: string;
}
export interface HoldingHistory {
  snapshot_date: string;
  unclassified_value: Decimal | null;
  tradingsymbol: string;
  exchange: string;
  bucket: Bucket;
  quantity: number;
  average_price: Decimal;
  last_price: Decimal;
  invested_value: Decimal;
  market_value: Decimal;
  pnl: Decimal;
  pnl_percent: Decimal;
}

export interface Execution {
  symbol: string;
  exchange: string;
  transaction_type: "BUY" | "SELL";
  product: string;
  quantity: number;
  average_price: Decimal;
  amount: Decimal;
  bucket: Bucket;
  executed_at: string;
  order_id: string;
  fill_count: number;
  charges: Decimal | null;
  holding_status:
    "AWAITING_HOLDINGS" | "HOLDING_PRESENT_UNCONFIRMED" | "NETTED_BY_SELLS" | "NOT_APPLICABLE";
}
export interface ActivityOrder {
  symbol: string;
  exchange: string;
  transaction_type: string;
  product: string;
  quantity: number;
  filled_quantity: number;
  status: string;
  average_price: Decimal;
  timestamp: string;
  order_id: string;
}
export interface Activity {
  date: string;
  last_synced_at: string | null;
  executed: Execution[];
  orders: ActivityOrder[];
  awaiting_holdings: Execution[];
  open_pending_count: number;
  rejected_cancelled_count: number;
}
export interface Contributions {
  month: string;
  recorded_from: string | null;
  recorded_buy_amount: Decimal;
  allocation: Record<Bucket, Decimal>;
  history_complete: boolean;
  charges: Decimal | null;
}
export interface RefreshResult {
  status: "ok" | "fresh" | "reconnect_required";
  last_refresh_at: string | null;
  holdings_synced: number;
  orders_synced: number;
  trades_synced: number;
}
