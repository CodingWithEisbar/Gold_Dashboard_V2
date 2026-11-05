<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, money, pct, timestamp, today, type Product, type Quote, type HistoryRow, type Source, type Simulation } from './api'
import LineChart from './LineChart.vue'

const tabs = ['Tổng quan', 'Phân tích premium', 'Mô phỏng lịch sử', 'Phòng kịch bản', 'Dữ liệu & nguồn']
const tab = ref(0), products = ref<Product[]>([]), productId = ref('sjc-bar-1l-hcm')
const quotes = ref<Record<string, Quote | null>>({}), rows = ref<HistoryRow[]>([]), sources = ref<Source[]>([])
const loading = ref(false), error = ref(''), days = ref(30), result = ref<Simulation | null>(null), resultStatus = ref('')
const assumptions = ref<string[]>([]), submitting = ref(false)
const endDate = ref(today()), entryDate = ref(today()), exitDate = ref('')
const quantity = ref('1'), unit = ref('luong'), manualEntry = ref('')
const buyFee = ref('0'), sellFee = ref('0'), storageFee = ref('0'), tax = ref('0')
const scenarioEntry = ref(''), reference = ref(''), spread = ref('')
const scenarios = ref([{name: 'Thận trọng', world: '-10', premium: '5'}, {name: 'Cơ sở', world: '0', premium: '10'}, {name: 'Tích cực', world: '10', premium: '15'}])
const scenarioResults = ref<Simulation[]>([])
const latest = computed(() => quotes.value[productId.value])
const product = computed(() => products.value.find(p => p.id === productId.value))
const available = computed(() => rows.value.filter(row => row.data_status !== 'missing'))
const missing = computed(() => rows.value.filter(row => row.data_status === 'missing'))
const premiums = computed(() => rows.value.filter(row => row.premium))
const sample = computed(() => Object.values(quotes.value).some(q => q?.reference_type === 'sample') || rows.value.some(r => r.data_status === 'sample'))
const startDate = computed(() => { const d = new Date(`${endDate.value}T12:00:00Z`); d.setUTCDate(d.getUTCDate() - days.value + 1); return d.toISOString().slice(0, 10) })
const query = computed(() => `product_id=${encodeURIComponent(productId.value)}&from=${startDate.value}&to=${endDate.value}`)
const series = computed(() => tab.value === 1
  ? [{label: 'Premium', data: rows.value.map(r => r.premium ? Number(r.premium.premium_pct) : null), color: '#e9bd71'}]
  : [{label: 'Cửa hàng bán ra · ask', data: rows.value.map(r => r.ask ? Number(r.ask) : null), color: '#e9bd71'},
     {label: 'Cửa hàng mua vào · bid', data: rows.value.map(r => r.bid ? Number(r.bid) : null), color: '#60d5bb'},
     {label: 'Thế giới quy đổi', data: rows.value.map(r => r.premium ? Number(r.premium.world_reference_vnd_per_luong) : null), color: '#819bef'}])
const stats = ref<{median_pct: string | null; percentile_rank_pct: string | null; count: number} | null>(null)
let controller: AbortController | null = null

async function loadHistory() {
  controller?.abort(); controller = new AbortController()
  const signal = controller.signal
  loading.value = true; error.value = ''
  try {
    const [history, statistics] = await Promise.all([
      api<HistoryRow[]>(`/prices/history?${query.value}`, undefined, signal),
      api<{median_pct: string | null; percentile_rank_pct: string | null; count: number}>(`/premiums/statistics?${query.value}`, undefined, signal),
    ])
    rows.value = history.data; stats.value = statistics.data
  } catch (e) { if (!(e instanceof DOMException && e.name === 'AbortError')) { error.value = (e as Error).message; rows.value = [] } }
  finally { if (!signal.aborted) loading.value = false }
}
async function refresh() {
  loading.value = true; error.value = ''
  try {
    const [catalog, health] = await Promise.all([api<Product[]>('/catalog/products'), api<Source[]>('/data-sources/status')])
    products.value = catalog.data; sources.value = health.data
    const prices = await Promise.all(products.value.map(async p => [p.id, (await api<Quote | null>(`/quotes/latest?product_id=${p.id}`)).data] as const))
    quotes.value = Object.fromEntries(prices)
    await loadHistory()
  } catch (e) { error.value = (e as Error).message; loading.value = false }
}
function costs() { return {quantity: quantity.value, unit: unit.value, buy_fees_vnd: buyFee.value, sell_fees_vnd: sellFee.value, storage_fees_vnd: storageFee.value, applicable_tax_vnd: tax.value} }
async function simulate() {
  submitting.value = true; error.value = ''; result.value = null
  try {
    const data = await api<Simulation>('/simulations/historical', {...costs(), product_id: productId.value, entry_date: entryDate.value, exit_date: exitDate.value || null, manual_entry_ask: manualEntry.value || null, include_path: true})
    result.value = data.data; assumptions.value = data.assumptions || []; resultStatus.value = data.data_status || ''
  } catch (e) { error.value = (e as Error).message } finally { submitting.value = false }
}
async function runScenario() {
  submitting.value = true; error.value = ''; scenarioResults.value = []
  try {
    const results = await Promise.all(scenarios.value.map(s => api<Simulation>('/simulations/scenario', {...costs(), entry_ask: scenarioEntry.value, world_reference_now: reference.value, future_spread: spread.value, world_change_pct: s.world, future_premium_pct: s.premium})))
    scenarioResults.value = results.map(r => r.data); result.value = results[1].data; assumptions.value = results[1].assumptions || []; resultStatus.value = 'scenario'
  } catch (e) { error.value = (e as Error).message } finally { submitting.value = false }
}
watch([productId, days, endDate], () => { result.value = null; void loadHistory() })
watch(tab, () => { result.value = null; scenarioResults.value = []; error.value = '' })
onMounted(refresh)
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <a class="brand" href="#main" aria-label="Gold Premium, đến nội dung"><span class="brand-mark">◈</span><span>GOLD<span class="brand-sub">PREMIUM TRACKER</span></span></a>
      <div class="nav-caption">KHÔNG GIAN PHÂN TÍCH</div>
      <nav aria-label="Điều hướng chính"><button v-for="(name, i) in tabs" :key="name" :class="{active: tab === i}" :aria-current="tab === i ? 'page' : undefined" @click="tab = i"><span class="nav-number">0{{ i + 1 }}</span>{{ name }}</button></nav>
      <div class="sidebar-note"><span class="gold">◷</span><b>Dữ liệu có nguồn gốc.</b><p>Đúng đơn vị. Đúng chiều giá.<br>Mọi giả định đều được ghi rõ.</p><small>Giờ Việt Nam · UTC+7</small></div>
    </aside>
    <div class="workspace">
      <header class="topbar"><span>THỊ TRƯỜNG VÀNG / <b>{{ tabs[tab] }}</b></span><button class="quiet" :disabled="loading" @click="refresh">↻ Làm mới dữ liệu</button></header>
      <main id="main">
        <div class="page-heading"><div><p class="eyebrow">GOLD PREMIUM · INVESTMENT SIMULATOR</p><h1>{{ tabs[tab] }}</h1><p class="muted">Hiểu chênh lệch. Nhìn rõ chi phí. Mô phỏng trên dữ liệu đã kiểm chứng.</p></div><span class="tag">VND / lượng · 9999</span></div>
        <div v-if="sample" class="notice sample" role="status">SAMPLE DATA — NOT REAL MARKET DATA · Dữ liệu tổng hợp dùng để kiểm thử.</div>
        <div v-if="error" class="notice error" role="alert">{{ error }} <button class="quiet" @click="refresh">Thử tải lại</button></div>
        <div v-if="loading" class="notice" role="status">Đang tải dữ liệu từ hệ thống…</div>

        <template v-if="tab === 0">
          <div class="section-label">BÁO GIÁ MỚI NHẤT <span>Cửa hàng mua vào = giá bạn bán lại</span></div>
          <div class="quote-grid"><article v-for="p in products.filter(p => p.product_code !== 'BAR_1_CHI')" :key="p.id" class="card quote-card">
            <div class="card-top"><span class="provider">{{ p.provider_id.toUpperCase() }} <small>{{ p.location }}</small></span><span class="status">{{ quotes[p.id]?.data_status || 'missing' }}</span></div>
            <h2>{{ p.name }}</h2><div class="price-label">CỬA HÀNG BÁN RA · ASK</div><div class="large-price">{{ money(quotes[p.id]?.ask) }}</div>
            <div class="split"><div><span>Mua vào · bid</span><b>{{ money(quotes[p.id]?.bid) }}</b></div><div><span>Chênh lệch</span><b>{{ money(quotes[p.id]?.spread_vnd_per_luong) }}</b></div></div>
            <footer>{{ timestamp(quotes[p.id]?.observed_at) }} <span>{{ quotes[p.id]?.reference_type || 'Chưa có báo giá' }}</span></footer>
          </article></div>
          <div v-if="!Object.values(quotes).some(Boolean) && !loading" class="empty"><span class="empty-symbol">◈</span><h2>Lịch sử bắt đầu từ dữ liệu thật</h2><p>Chưa có báo giá hợp lệ. Cấu hình nguồn được cấp phép hoặc nhập CSV qua CLI để bắt đầu theo dõi.</p><button class="button" @click="tab = 4">Xem nguồn & cách nhập dữ liệu →</button></div>
        </template>

        <template v-if="tab === 0 || tab === 1">
          <section class="card chart-card"><div class="section-header"><div><h2>{{ tab === 1 ? 'Premium theo thời gian' : 'Diễn biến giá vàng' }}</h2><p class="muted">Khoảng trống biểu thị ngày thiếu báo giá. Không tự lấy giá ngày trước.</p></div><div class="filters"><label>Sản phẩm<select v-model="productId"><option v-for="p in products" :key="p.id" :value="p.id">{{ p.name }} · {{ p.location }}</option></select></label><label>Kết thúc<input v-model="endDate" type="date" :max="today()"></label><label>Khoảng thời gian<select v-model="days"><option v-for="d in [7, 30, 90, 365]" :key="d" :value="d">{{ d }} ngày</option></select></label></div></div>
            <div v-if="tab === 1" class="metric-strip"><div><span>Median sản phẩm trong kỳ</span><b>{{ pct(stats?.median_pct || undefined) }}</b></div><div><span>Percentile báo giá cuối kỳ</span><b>{{ pct(stats?.percentile_rank_pct || undefined) }}</b></div><div><span>Snapshot có premium</span><b>{{ stats?.count || 0 }}</b></div></div>
            <LineChart v-if="available.length" :labels="rows.map(r => r.business_date)" :series="series" :unit="tab === 1 ? '%' : 'VND/lượng'"/>
            <div v-else class="chart-empty">Chưa có dữ liệu trong khoảng ngày đã chọn.</div>
            <p v-if="premiums.some(p => p.premium_status === 'indicative_daily')" class="notice">Premium indicative/daily: snapshot nội địa, thế giới và FX lệch quá 30 phút; không phải premium tức thời.</p>
            <div class="table-wrap"><table><caption class="sr-only">Báo giá và premium theo ngày</caption><thead><tr><th>Ngày</th><th>Mua vào</th><th>Bán ra</th><th>Thế giới quy đổi</th><th>Premium</th><th>Chất lượng / nguồn</th></tr></thead><tbody><tr v-for="row in rows.slice().reverse()" :key="row.business_date"><td>{{ row.business_date }}</td><td>{{ money(row.bid) }}</td><td>{{ money(row.ask) }}</td><td>{{ money(row.premium?.world_reference_vnd_per_luong) }}</td><td>{{ pct(row.premium?.premium_pct) }}</td><td>{{ row.data_status }} · {{ row.reference_type || 'missing' }}<small>{{ row.premium_status }} {{ row.source }}</small></td></tr></tbody></table></div>
            <a class="text-link" :href="`/api/v1/prices/export.csv?${query}`">↓ Xuất CSV của kỳ đã chọn</a>
          </section>
          <div class="two-columns"><section class="card"><h2>XAU/USD · USD/troy oz</h2><LineChart v-if="premiums.length" :labels="rows.map(r => r.business_date)" :series="[{label: 'XAU/USD', data: rows.map(r => r.spot ? Number(r.spot.value) : null), color: '#e9bd71'}]" unit="USD/troy oz"/><p v-else class="muted">Chưa có snapshot thế giới để hiển thị.</p></section><section class="card"><h2>USD/VND · reference mid</h2><LineChart v-if="premiums.length" :labels="rows.map(r => r.business_date)" :series="[{label: 'USD/VND', data: rows.map(r => r.fx ? Number(r.fx.value) : null), color: '#60d5bb'}]" unit="VND/USD"/><p v-else class="muted">Chưa có snapshot FX tham chiếu. Tỷ giá không bảo đảm giao dịch được.</p></section></div>
        </template>

        <template v-if="tab === 2 || tab === 3">
          <div v-if="tab === 3" class="notice">SCENARIO, NOT OBSERVED PRICE · Các kịch bản do bạn điều chỉnh; không phải dự báo thị trường.</div>
          <div class="sim-layout"><form class="card" @submit.prevent="tab === 2 ? simulate() : runScenario()"><h2>{{ tab === 2 ? 'Thiết lập giao dịch lý thuyết' : 'Giả định của bạn' }}</h2>
            <template v-if="tab === 2"><label>Sản phẩm & vùng<select v-model="productId"><option v-for="p in products" :key="p.id" :value="p.id">{{ p.name }} · {{ p.location }}</option></select></label><div class="two-columns"><label>Ngày mua<input v-model="entryDate" type="date" :max="today()" required></label><label>Ngày bán<input v-model="exitDate" type="date" :min="entryDate" :max="today()"><small>Để trống: ngày có báo giá mới nhất</small></label></div><label>Giá mua thực tế, tùy chọn (VND/lượng)<input v-model="manualEntry" inputmode="decimal" placeholder="Chỉ nhập nếu dùng giá manual"><small>Được ghi nhãn manual, không tạo báo giá lịch sử.</small></label><p class="muted">{{ product?.name }} · Báo giá mới nhất {{ timestamp(latest?.observed_at) }}</p></template>
            <template v-else><label>Giá mua ask (VND/lượng)<input v-model="scenarioEntry" inputmode="decimal" required></label><label>Thế giới quy đổi hiện tại (VND/lượng)<input v-model="reference" inputmode="decimal" required></label><label>Spread tương lai (VND/lượng)<input v-model="spread" inputmode="decimal" required></label></template>
            <div class="two-columns"><label>Khối lượng<input v-model="quantity" inputmode="decimal" required></label><label>Đơn vị<select v-model="unit"><option value="luong">Lượng · 37,5 g</option><option value="chi">Chỉ · 3,75 g</option></select></label></div>
            <details><summary>Phí & thuế tùy chọn · mặc định 0</summary><label>Phí mua (VND)<input v-model="buyFee" inputmode="decimal"></label><label>Phí bán (VND)<input v-model="sellFee" inputmode="decimal"></label><label>Phí lưu trữ (VND)<input v-model="storageFee" inputmode="decimal"></label><label>Thuế áp dụng (VND)<input v-model="tax" inputmode="decimal"></label><small>Không tự áp thuế suất pháp lý. Nhập tổng phí cho giao dịch.</small></details>
            <template v-if="tab === 3"><fieldset v-for="s in scenarios" :key="s.name"><legend>{{ s.name }} · giả định</legend><div class="two-columns"><label>Thế giới thay đổi (%)<input v-model="s.world" inputmode="decimal" required></label><label>Premium tương lai (%)<input v-model="s.premium" inputmode="decimal" required></label></div></fieldset></template>
            <button class="button full" :disabled="submitting" type="submit">{{ submitting ? 'Đang tính…' : 'Xem kết quả mô phỏng →' }}</button>
          </form><section class="card result-panel" aria-live="polite"><p class="eyebrow">{{ result ? resultStatus : 'KẾT QUẢ MÔ PHỎNG' }}</p><template v-if="result"><h2>Lãi / lỗ ròng lý thuyết</h2><div class="result-value" :class="result.net_pnl_vnd.startsWith('-') ? 'loss' : 'gain'">{{ result.net_pnl_vnd.startsWith('-') ? '' : '+' }}{{ money(result.net_pnl_vnd) }}</div><p>{{ result.net_pnl_vnd.startsWith('-') ? 'Lỗ' : 'Lãi / hòa vốn' }} · {{ pct(result.net_return_pct) }} trên tổng vốn thực bỏ ra</p><dl><div><dt>Tổng vốn đầu tư</dt><dd>{{ money(result.invested_vnd) }}</dd></div><div><dt>Thu hồi sau phí</dt><dd>{{ money(result.net_proceeds_vnd) }}</dd></div><div><dt>Giá bid hòa vốn / lượng</dt><dd>{{ money(result.break_even_exit_bid) }}</dd></div><div v-if="result.holding_days != null"><dt>Thời gian nắm giữ</dt><dd>{{ result.holding_days }} ngày</dd></div></dl><p v-if="result.entry" class="provenance">Mua: {{ result.entry.source }} · {{ result.entry.reference_type }} · {{ timestamp(result.entry.observed_at) }}<br>Bán: {{ result.exit?.source }} · {{ result.exit?.reference_type }} · {{ timestamp(result.exit?.observed_at) }}</p><ul class="assumptions"><li v-for="a in assumptions" :key="a">{{ a }}</li></ul></template><div v-else class="result-placeholder"><span>↗</span><h2>Nhìn rõ hiệu quả đầu tư</h2><p>Chọn ngày có dữ liệu hoặc nhập giả định. Kết quả được tính ở backend; giá thiếu sẽ được thông báo.</p></div>
            <template v-if="scenarioResults.length"><LineChart :labels="scenarios.map(s => s.name)" :series="[{label: 'P&L theo giả định', data: scenarioResults.map(r => Number(r.net_pnl_vnd)), color: '#e9bd71'}]" unit="VND"/><table><thead><tr><th>Kịch bản</th><th>Bid giả định</th><th>P&L</th></tr></thead><tbody><tr v-for="(s, i) in scenarioResults" :key="i"><td>{{ scenarios[i].name }}</td><td>{{ money(s.scenario_future_bid) }}</td><td>{{ money(s.net_pnl_vnd) }}</td></tr></tbody></table></template>
          </section></div>
        </template>

        <section v-if="tab === 2 && result?.path?.length" class="card"><h2>Backtest lãi / lỗ lý thuyết qua ngày</h2><p class="muted">{{ result.path_assumption }}</p><LineChart :labels="result.path.map(p => p.business_date)" :series="[{label: 'P&L lý thuyết', data: result.path.map(p => p.net_pnl_vnd == null ? null : Number(p.net_pnl_vnd)), color: '#e9bd71'}]" unit="VND"/><div class="table-wrap"><table><thead><tr><th>Ngày</th><th>P&L</th></tr></thead><tbody><tr v-for="p in result.path" :key="p.business_date"><td>{{ p.business_date }}</td><td>{{ money(p.net_pnl_vnd) }}</td></tr></tbody></table></div></section>

        <template v-if="tab === 4">
          <div class="notice">Không có quyền thu thập đã xác nhận → nguồn tự động bị khóa. Chỉ nhập dữ liệu bạn có quyền sử dụng.</div>
          <section class="card"><h2>Tình trạng nguồn dữ liệu</h2><div class="table-wrap"><table><thead><tr><th>Nguồn</th><th>Giấy phép</th><th>Lần quan sát cuối</th><th>Trạng thái</th><th>Loại dữ liệu</th></tr></thead><tbody><tr v-for="source in sources" :key="source.id"><td><a :href="source.source_url" target="_blank" rel="noopener noreferrer">{{ source.name }} ↗</a><small>{{ source.license_note }}</small></td><td>{{ source.license_status }}</td><td>{{ timestamp(source.latest_observed_at) }}</td><td>{{ source.status }}<small>{{ source.last_error_code }}</small></td><td>{{ source.reference_types.join(', ') || 'Chưa nhập' }}</td></tr></tbody></table></div></section>
          <div class="two-columns"><section class="card"><h2>Nhập CSV qua CLI</h2><p class="muted">File UTF-8, đúng schema, timestamp có timezone, đơn vị cố định. Thực hiện trên môi trường quản trị nội bộ.</p><pre>python -m app.jobs.import_csv /imports/prices.csv
  --import-root /imports
  --confirm-data-rights</pre><p>Không có public endpoint ghi giá. Quản trị viên cần xác nhận nguồn và quyền lưu trữ trước khi nhập.</p></section><section class="card"><h2>Chính sách tham chiếu ngày</h2><p>Snapshot hợp lệ cuối cùng trước hoặc đúng 18:00 Việt Nam, trong cửa sổ tối đa 120 phút. Không carry-forward qua ngày.</p><p class="muted">Giữ riêng provider / sản phẩm / vùng; quarantine nếu biến động vượt ngưỡng. Premium lệch giờ được gắn nhãn indicative/daily.</p><p>{{ missing.length }} ngày thiếu trong kỳ {{ startDate }} → {{ endDate }}</p><details v-if="missing.length"><summary>Xem ngày thiếu</summary><p class="missing-days">{{ missing.map(r => r.business_date).join(' · ') }}</p></details></section></div>
        </template>
        <footer class="page-footer"><span>GOLD PREMIUM · Dữ liệu, không phải cam kết lợi nhuận.</span><span>1 lượng = 37,5 g · 1 troy oz = 31,1034768 g</span></footer>
      </main>
    </div>
  </div>
</template>
