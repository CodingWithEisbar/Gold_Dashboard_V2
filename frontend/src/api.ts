export interface Product { id: string; name: string; provider_id: string; product_code: string; location: string; purity: string }
export interface Quote { bid: string; ask: string; business_date: string; source: string; observed_at: string; data_status: string; reference_type: string; label: string; spread_vnd_per_luong: string }
export interface HistoryRow extends Partial<Quote> {
  business_date: string; data_status: string; premium_status?: string;
  premium?: { world_reference_vnd_per_luong: string; premium_pct: string; premium_absolute_vnd_per_luong: string } | null;
  spot?: {value: string}; fx?: {value: string};
}
export interface Source { id: string; name: string; source_url: string; license_status: string; license_note: string; status: string; latest_observed_at: string | null; last_error_code: string | null; reference_types: string[] }
export interface Simulation { invested_vnd: string; net_proceeds_vnd: string; net_pnl_vnd: string; net_return_pct: string; break_even_exit_bid: string; holding_days?: number; scenario_future_bid?: string; entry?: Quote; exit?: Quote; label?: string; path?: {business_date: string; net_pnl_vnd: string | null}[]; path_assumption?: string }
export interface Envelope<T> { data: T; data_status?: string; assumptions?: string[] }

export async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<Envelope<T>> {
  const response = await fetch(`/api/v1${path}`, { signal, headers: body ? {'Content-Type': 'application/json'} : {},
    method: body ? 'POST' : 'GET', body: body ? JSON.stringify(body) : undefined })
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.detail || `Lỗi HTTP ${response.status}`)
  return payload
}
export function money(value?: string | null): string {
  if (value == null) return '—'
  const negative = value.startsWith('-')
  const [integer, fraction = ''] = value.replace(/^-/, '').split('.')
  const rounded = BigInt(integer || '0') + (Number(fraction[0] || '0') >= 5 ? 1n : 0n)
  return `${negative && rounded > 0n ? '−' : ''}${new Intl.NumberFormat('vi-VN').format(rounded)} ₫`
}
export function pct(value?: string): string { return value == null ? '—' : `${Number(value).toLocaleString('vi-VN', {maximumFractionDigits: 2})}%` }
export function timestamp(value?: string | null): string { return value ? new Intl.DateTimeFormat('vi-VN', {dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh'}).format(new Date(value)) : 'Chưa có dữ liệu' }
export function today(): string { return new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date()) }
