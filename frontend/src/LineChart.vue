<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Chart, registerables } from 'chart.js'
Chart.register(...registerables)
const props = defineProps<{labels: string[]; series: {label: string; data: (number | null)[]; color: string}[]; unit: string}>()
const canvas = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null
function render() {
  chart?.destroy()
  if (!canvas.value) return
  chart = new Chart(canvas.value, { type: 'line', data: {labels: props.labels, datasets: props.series.map(s => ({label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.color, tension: 0.15, pointRadius: 2, borderWidth: 2, spanGaps: false}))},
    options: { responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {legend: {labels: {color: '#c6d0dd'}}, tooltip: {callbacks: {label: c => `${c.dataset.label}: ${c.parsed.y?.toLocaleString('vi-VN')} ${props.unit}`}}},
      scales: {x: {ticks: {color: '#94a3b8', maxTicksLimit: 8}, grid: {color: '#ffffff05'}}, y: {ticks: {color: '#94a3b8'}, grid: {color: '#ffffff0a'}, title: {display: true, text: props.unit, color: '#94a3b8'}}}} })
}
onMounted(render)
watch(() => [props.labels, props.series, props.unit], render, {deep: true})
onBeforeUnmount(() => chart?.destroy())
</script>
<template><div class="chart"><canvas ref="canvas" role="img" :aria-label="`Biểu đồ ${unit}; bảng dữ liệu tương ứng bên dưới`"></canvas></div></template>
