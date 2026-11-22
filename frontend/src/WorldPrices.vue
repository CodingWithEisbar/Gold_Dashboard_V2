<script setup lang="ts">
import { ref, watch } from 'vue'
import { api, timestamp } from './api'
import HourlyPrices from './HourlyPrices.vue'

interface SpotQuote {
  value: string
  observed_at: string
  source_url: string
}

const props = defineProps<{refreshCount: number}>()
const sourceUrl = 'https://www.vang.today/api/prices?type=XAUUSD'
const quote = ref<SpotQuote | null>(null)
const status = ref('')
const loading = ref(false)
const error = ref('')
const formatPrice = new Intl.NumberFormat('vi-VN', {minimumFractionDigits: 2, maximumFractionDigits: 8})

watch(() => props.refreshCount, async (_, __, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  loading.value = true
  error.value = ''
  try {
    const result = await api<SpotQuote | null>('/prices/world/latest', undefined, controller.signal)
    if (controller.signal.aborted) return
    quote.value = result.data
    status.value = result.data_status ?? ''
  } catch (e) {
    if (!controller.signal.aborted) error.value = (e as Error).message
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}, {immediate: true})
</script>

<template>
  <section class="card market-board">
    <header>
      <h2>XAU/USD</h2>
      <a :href="quote?.source_url || sourceUrl" target="_blank" rel="noopener noreferrer">Nguồn Vàng.Today ↗</a>
    </header>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <template v-if="quote">
      <div class="large-price">{{ formatPrice.format(Number(quote.value)) }} <small>USD/oz troy</small></div>
      <p class="muted">Giờ nguồn · {{ timestamp(quote.observed_at) }}<template v-if="status === 'stale'"> · Giá cũ</template></p>
      <p v-if="status === 'sample'" class="notice sample">SAMPLE DATA — NOT REAL MARKET DATA</p>
    </template>
    <p v-else-if="loading" class="muted" role="status">Đang tải giá XAU/USD…</p>
    <p v-else-if="!error" class="muted">Chưa có báo giá XAU/USD đã lưu.</p>
  </section>
  <HourlyPrices market="world" :refresh-count="refreshCount"/>
</template>
