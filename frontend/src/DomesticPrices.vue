<script setup lang="ts">
import { computed, ref } from 'vue'
import { money, timestamp, type Product, type Quote, type Source } from './api'
import HourlyPrices from './HourlyPrices.vue'

const props = defineProps<{
  products: Product[]
  sources: Source[]
  quotes: Record<string, Quote | null>
  refreshCount: number
}>()
const selected = ref('')
const feed = computed(() => props.sources.find(s => s.id === 'vang-today'))
const listed = computed(() => props.products.filter(p => p.provider_id === 'vang-today'))
const brands = computed(() => [...new Set(listed.value.map(p => p.brand || p.name))].sort((a, b) => a.localeCompare(b, 'vi')))
const visible = computed(() => brands.value.filter(brand => !selected.value || brand === selected.value)
  .map(brand => ({brand, products: listed.value.filter(p => (p.brand || p.name) === brand)})))
const symbols = computed(() => visible.value.flatMap(group => group.products.map(p => p.id)))
</script>

<template>
  <div class="market-toolbar filters">
    <label>Thương hiệu
      <select v-model="selected"><option value="">Tất cả thương hiệu</option>
        <option v-for="brand in brands" :key="brand" :value="brand">{{ brand }}</option>
      </select>
    </label>
  </div>
  <section v-for="{brand, products: items} in visible" :key="brand" class="card market-board">
    <header><h2>{{ brand }}</h2>
      <a v-if="feed" :href="feed.source_url" target="_blank" rel="noopener noreferrer">Vàng.Today ↗</a>
    </header>
    <div class="table-wrap"><table>
      <caption class="sr-only">Báo giá mới nhất của {{ brand }}, đơn vị VND/lượng</caption>
      <thead><tr><th>Sản phẩm</th><th>Mua vào</th><th>Bán ra</th><th>Chênh lệch</th><th>Thời điểm báo giá</th></tr></thead>
      <tbody><tr v-for="p in items" :key="p.id">
        <td>{{ p.name }}<small>{{ p.location }}</small></td>
        <td>{{ money(quotes[p.id]?.bid) }}</td><td>{{ money(quotes[p.id]?.ask) }}</td>
        <td>{{ money(quotes[p.id]?.spread_vnd_per_luong) }}</td>
        <td>{{ timestamp(quotes[p.id]?.observed_at) }}
          <small v-if="quotes[p.id]">{{ quotes[p.id]?.time_basis === 'board_observation' ? 'Giờ đọc bảng' : 'Giờ nguồn' }}<template v-if="quotes[p.id]?.data_status === 'stale'"> · Giá cũ</template></small>
        </td>
      </tr></tbody>
    </table></div>
  </section>
  <HourlyPrices market="domestic" :symbols="symbols" :refresh-count="refreshCount"/>
</template>
