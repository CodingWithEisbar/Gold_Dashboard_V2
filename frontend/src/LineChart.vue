<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)
const props = defineProps<{labels: string[]; series: {label: string; data: (number | null)[]; color: string}[]; unit: string}>()
const canvas = ref<HTMLCanvasElement | null>(null)
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
let chart: Chart<'line'> | null = null

function animationOptions() {
  return reducedMotion.matches ? false : { duration: 280, easing: 'easeOutCubic' as const }
}

function datasets() {
  return props.series.map(series => ({
    label: series.label, data: [...series.data], borderColor: series.color, backgroundColor: series.color,
    tension: 0.15, pointRadius: 2, borderWidth: 2, spanGaps: false,
  }))
}

function syncMotion() {
  if (!chart) return
  chart.stop()
  chart.options.animation = animationOptions()
  chart.update('none')
}

onMounted(() => {
  if (!canvas.value) return
  chart = new Chart(canvas.value, {
    type: 'line',
    data: { labels: [...props.labels], datasets: datasets() },
    options: {
      responsive: true, maintainAspectRatio: false, animation: animationOptions(),
      plugins: {
        legend: { labels: { color: '#c6d0dd' } },
        tooltip: { callbacks: { label: c => `${c.dataset.label}: ${c.parsed.y?.toLocaleString('vi-VN')} ${props.unit}` } },
      },
      scales: {
        x: { ticks: {color: '#94a3b8', maxTicksLimit: 8}, grid: {color: '#ffffff05'} },
        y: { ticks: {color: '#94a3b8'}, grid: {color: '#ffffff0a'}, title: {display: true, text: props.unit, color: '#94a3b8'} },
      },
    },
  })
  reducedMotion.addEventListener('change', syncMotion)
})

watch(() => [props.labels, props.series, props.unit], () => {
  if (!chart) return
  chart.data.labels = [...props.labels]
  const previous = chart.data.datasets
  chart.data.datasets = datasets().map(dataset => {
    const existing = previous.find(item => item.label === dataset.label)
    return existing ? Object.assign(existing, dataset) : dataset
  })
  const title = chart.options.scales?.y?.title
  if (title) title.text = props.unit
  chart.update()
}, { deep: true })

onBeforeUnmount(() => {
  reducedMotion.removeEventListener('change', syncMotion)
  chart?.destroy()
})
</script>
<template><div class="chart"><canvas ref="canvas" role="img" :aria-label="`Biểu đồ ${unit}; bảng dữ liệu tương ứng bên dưới`"></canvas></div></template>
