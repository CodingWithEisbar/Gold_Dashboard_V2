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
const groups = computed(() => props.sources.map(source => ({
  source,
  products: props.products.filter(product => product.provider_id === source.id),
})).filter(group => group.products.length))
const visible = computed(() => groups.value.filter(({source}) => !selected.value || source.id === selected.value))
</script>

<template>
  <div class="market-toolbar filters">
    <label>Nguồn niêm yết
      <select v-model="selected"><option value="">Tất cả nguồn</option>
        <option v-for="{source} in groups" :key="source.id" :value="source.id">{{ source.name }}</option>
      </select>
    </label>
  </div>
  <section v-for="{source, products: listed} in visible" :key="source.id" class="card market-board">
    <header><h2>{{ source.name }}</h2>
      <a :href="source.source_url" target="_blank" rel="noopener noreferrer">Bảng giá gốc ↗</a>
    </header>
    <div class="table-wrap"><table>
      <caption class="sr-only">Báo giá mới nhất của {{ source.name }}, đơn vị VND/lượng</caption>
      <thead><tr><th>Sản phẩm</th><th>Mua vào</th><th>Bán ra</th><th>Chênh lệch</th><th>Thời điểm báo giá</th></tr></thead>
      <tbody><tr v-for="p in listed" :key="p.id">
        <td>{{ p.name }}<small>{{ p.location.endsWith('_LISTED') ? 'Bảng niêm yết chung' : p.location }}</small></td>
        <td>{{ money(quotes[p.id]?.bid) }}</td><td>{{ money(quotes[p.id]?.ask) }}</td>
        <td>{{ money(quotes[p.id]?.spread_vnd_per_luong) }}</td>
        <td>{{ timestamp(quotes[p.id]?.observed_at) }}
          <small v-if="quotes[p.id]">{{ quotes[p.id]?.time_basis === 'board_observation' ? 'Giờ đọc bảng' : 'Giờ nguồn' }}<template v-if="quotes[p.id]?.data_status === 'stale'"> · Giá cũ</template></small>
        </td>
      </tr></tbody>
    </table></div>
  </section>
  <HourlyPrices market="domestic" :source="selected" :refresh-count="refreshCount"/>
</template>
