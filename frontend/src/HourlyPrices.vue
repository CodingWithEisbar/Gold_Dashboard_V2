<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, money, timestamp, today } from './api'
import LineChart from './LineChart.vue'

interface Point {
  kind: 'gold' | 'spot' | 'future'
  source: string
  symbol: string
  name: string
  business_date: string
  hour: number
  observed_at: string
  time_basis: string
  fetched_at: string
  reference_type: string
  unit: string
  bid: string | null
  ask: string | null
  value: string | null
}

const props = defineProps<{refreshCount: number; market?: 'domestic' | 'world'; symbols?: string[]}>()
const dayMs = 86_400_000
const dateMs = (date: string) => Date.parse(`${date}T00:00:00Z`)
const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10)
const end = ref(today())
const start = ref(isoDay(dateMs(end.value) - 6 * dayMs))
const points = ref<Point[]>([]), chosen = ref('')
const loading = ref(false), error = ref('')
const hours = Array.from({length: 24}, (_, i) => String(i).padStart(2, '0') + ':00')
const days = computed(() => (dateMs(end.value) - dateMs(start.value)) / dayMs + 1)
const validRange = computed(() => days.value >= 1 && days.value <= 31 && end.value <= today())
const labels = computed(() => {
  if (!validRange.value) return []
  if (days.value === 1) return hours
  return Array.from({length: days.value}, (_, offset) => {
    const day = isoDay(dateMs(start.value) + offset * dayMs)
    const label = `${day.slice(8, 10)}/${day.slice(5, 7)}`
    return hours.map(hour => `${label} ${hour}`)
  }).flat()
})
const key = (p: Point) => [p.kind, p.source, p.symbol].join('/')
const marketPoints = computed(() => points.value.filter(p => {
  if (props.market === 'world') return p.kind === 'spot' && p.source === 'vang-today-xauusd'
  if (props.market === 'domestic') return p.kind === 'gold' && p.source === 'vang-today' && (!props.symbols || props.symbols.includes(p.symbol))
  return true
}))
const options = computed(() => [...new Map(marketPoints.value.map(p => [key(p), p])).values()])
watch(options, choices => {
  if (!choices.some(p => key(p) === chosen.value)) chosen.value = choices[0] ? key(choices[0]) : ''
})
const selected = computed(() => marketPoints.value.filter(p => key(p) === chosen.value))
const unit = computed(() => selected.value[0]?.kind === 'gold' ? 'VND/lượng' : 'USD/troy oz')
const series = computed(() => {
  const fields = selected.value[0]?.kind === 'gold' ? ['bid', 'ask'] as const : ['value'] as const
  return fields.map(field => {
    const data = Array<number | null>(labels.value.length).fill(null)
    for (const p of selected.value) {
      const slot = ((dateMs(p.business_date) - dateMs(start.value)) / dayMs) * 24 + p.hour
      if (slot >= 0 && slot < data.length && p[field] != null) data[slot] = Number(p[field])
    }
    return {label: {bid: 'Mua vào', ask: 'Bán ra', value: 'Giá'}[field], data,
      color: field === 'bid' ? '#60d5bb' : '#e9bd71'}
  })
})
watch([start, end, () => props.refreshCount], async (_, __, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  error.value = ''
  if (!validRange.value) {
    points.value = []
    loading.value = false
    return
  }
  loading.value = true
  try {
    const period = new URLSearchParams({from: start.value, to: end.value})
    const result = await api<Point[]>(`/prices/hourly?${period}`, undefined, controller.signal)
    if (controller.signal.aborted) return
    points.value = result.data
  } catch (e) {
    if (!controller.signal.aborted) error.value = (e as Error).message
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}, {immediate: true})
</script>

<template>
  <section class="card chart-card">
    <div class="section-header">
      <div><h2>{{ market === 'world' ? 'Lịch sử XAU/USD theo giờ' : 'Lịch sử giá theo giờ' }}</h2><p class="muted">Báo giá đã lưu cuối mỗi giờ Việt Nam.</p></div>
      <div class="filters">
        <label>Từ ngày<input v-model="start" type="date" :max="today()"></label>
        <label>Đến ngày<input v-model="end" type="date" :max="today()"></label>
        <label v-if="market !== 'world' && options.length">Sản phẩm / hợp đồng<select v-model="chosen">
          <option v-for="p in options" :key="key(p)" :value="key(p)">{{ p.name }}</option>
        </select></label>
      </div>
    </div>
    <p v-if="!validRange" class="notice">Chọn khoảng từ 1 đến 31 ngày, kết thúc muộn nhất hôm nay.</p>
    <p v-else-if="loading" role="status" class="muted">Đang tải báo giá theo giờ…</p>
    <p v-else-if="error" role="alert" class="notice error">{{ error }}</p>
    <template v-else-if="selected.length">
      <p v-if="selected.some(p => p.reference_type === 'sample')" class="notice sample">SAMPLE DATA — NOT REAL MARKET DATA</p>
      <LineChart :labels="labels" :series="series" :unit="unit"/>
      <div class="table-wrap"><table><thead><tr><th>Giờ</th><th>Thời điểm báo giá</th><th>Nguồn</th>
        <template v-if="selected[0].kind === 'gold'"><th>Mua vào</th><th>Bán ra</th></template>
        <th v-else>Giá ({{ unit }})</th><th>Loại dữ liệu</th>
      </tr></thead><tbody><tr v-for="p in selected.slice().reverse()" :key="`${p.business_date}-${p.hour}`">
        <td>{{ hours[p.hour] }}</td><td>{{ timestamp(p.observed_at) }}<small>{{ p.time_basis === 'board_observation' ? 'Giờ đọc bảng' : 'Giờ nguồn' }}</small></td><td>{{ p.source === 'vang-today-xauusd' || p.source === 'vang-today' ? 'Vàng.Today' : p.source }}</td>
        <template v-if="p.kind === 'gold'"><td>{{ money(p.bid) }}</td><td>{{ money(p.ask) }}</td></template>
        <td v-else>{{ Number(p.value).toLocaleString('vi-VN', {maximumFractionDigits: 8}) }}</td><td>{{ p.reference_type }}</td>
      </tr></tbody></table></div>
    </template>
    <p v-else class="muted">Chưa có báo giá đã lưu trong khoảng ngày này.</p>
  </section>
</template>
