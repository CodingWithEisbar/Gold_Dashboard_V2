<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface RequestEntry {
  id: number
  started_at: string
  method: 'GET' | 'POST'
  endpoint: string
  status: number
  duration_ms: number
}

interface RunEntry {
  id: number
  source: string
  started_at: string
  finished_at: string | null
  status: string
  inserted: number
  duplicates: number
  quarantined: number
  error_code: string | null
}

interface LogPage<T> {
  data: T[]
  has_next: boolean
  write_failed?: boolean
  detail?: string
}

const view = ref<'requests' | 'ingestion-runs'>('requests')
const requests = ref<RequestEntry[]>([])
const runs = ref<RunEntry[]>([])
const method = ref('')
const statusClass = ref('')
const page = ref(1)
const hasNext = ref(false)
const loading = ref(false)
const error = ref('')
const needsToken = ref(false)
const writeFailed = ref(false)
const tokenInput = ref('')
const token = ref('')
const reload = ref(0)
const clock = new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'short', timeStyle: 'medium', timeZone: 'Asia/Ho_Chi_Minh',
})
const runStatus: Record<string, string> = {
  success: 'Thành công', skipped: 'Bỏ qua', quarantined: 'Cần kiểm tra',
  source_unavailable: 'Nguồn không khả dụng', failed: 'Thất bại', running: 'Đang chạy',
}

function changeView(next: typeof view.value) {
  view.value = next
  page.value = 1
}

watch([method, statusClass], () => { page.value = 1 })

function authorize() {
  token.value = tokenInput.value.trim()
  tokenInput.value = ''
  reload.value++
}

async function logPage<T>(path: string, signal: AbortSignal): Promise<LogPage<T> | null> {
  const headers = token.value ? {Authorization: `Bearer ${token.value}`} : undefined
  const response = await fetch(`/api/v1/gateway/${path}`, {headers, signal})
  const payload = await response.json() as LogPage<T>
  if (response.status === 401) {
    needsToken.value = true
    error.value = token.value ? 'Token truy cập không hợp lệ.' : ''
    return null
  }
  if (!response.ok) throw new Error(payload.detail || `Lỗi HTTP ${response.status}`)
  needsToken.value = false
  return payload
}

watch([view, method, statusClass, page, reload], async (_, __, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  const query = new URLSearchParams({page: String(page.value)})
  error.value = ''
  loading.value = true
  try {
    if (view.value === 'requests') {
      if (method.value) query.set('method', method.value)
      if (statusClass.value) query.set('status_class', statusClass.value)
      const result = await logPage<RequestEntry>(`requests?${query}`, controller.signal)
      if (result && !controller.signal.aborted) {
        requests.value = result.data
        hasNext.value = result.has_next
        writeFailed.value = Boolean(result.write_failed)
      }
    } else {
      const result = await logPage<RunEntry>(`ingestion-runs?${query}`, controller.signal)
      if (result && !controller.signal.aborted) {
        runs.value = result.data
        hasNext.value = result.has_next
      }
    }
  } catch (e) {
    if (!controller.signal.aborted) error.value = (e as Error).message
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}, {immediate: true})

let timer: number
onMounted(() => {
  timer = window.setInterval(() => {
    if (page.value === 1 && !document.hidden && !loading.value && !needsToken.value) reload.value++
  }, 15_000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <section class="card gateway-monitor" aria-label="Nhật ký hệ thống">
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <form v-if="needsToken" class="gateway-access" @submit.prevent="authorize">
      <label>Token truy cập<input v-model="tokenInput" type="password" required autocomplete="off"></label>
      <button class="button" type="submit" :disabled="loading">Mở nhật ký</button>
    </form>
    <template v-else>
      <div class="gateway-toolbar">
        <div class="gateway-views" role="group" aria-label="Loại nhật ký">
          <button class="quiet" :aria-pressed="view === 'requests'" @click="changeView('requests')">Yêu cầu API</button>
          <button class="quiet" :aria-pressed="view === 'ingestion-runs'" @click="changeView('ingestion-runs')">Lượt thu thập giá</button>
        </div>
        <button class="quiet" :disabled="loading" @click="reload++">Làm mới nhật ký</button>
      </div>

      <div v-if="view === 'requests'" class="filters gateway-filters">
        <label>Phương thức
          <select v-model="method"><option value="">Tất cả</option><option>GET</option><option>POST</option></select>
        </label>
        <label>Mã HTTP
          <select v-model="statusClass">
            <option value="">Tất cả</option><option value="2">2xx</option><option value="3">3xx</option>
            <option value="4">4xx</option><option value="5">5xx</option>
          </select>
        </label>
      </div>

      <p v-if="view === 'requests' && writeFailed" class="notice">Một số yêu cầu chưa được lưu vào nhật ký.</p>
      <p v-if="loading" class="muted" role="status">Đang tải nhật ký…</p>
      <div v-else-if="view === 'requests' && requests.length" class="table-wrap gateway-table">
        <table>
          <caption class="sr-only">Yêu cầu API</caption>
          <thead><tr><th>Thời điểm</th><th>Phương thức</th><th>Endpoint</th><th>Mã HTTP</th><th>Thời lượng</th></tr></thead>
          <tbody>
            <tr v-for="entry in requests" :key="entry.id">
              <td>{{ clock.format(new Date(entry.started_at)) }}</td>
              <td><span class="gateway-method" :class="entry.method.toLowerCase()">{{ entry.method }}</span></td>
              <td><code>{{ entry.endpoint === '(unknown)' ? 'Chưa xác định' : entry.endpoint }}</code></td>
              <td :class="entry.status >= 400 ? 'loss' : 'gain'">{{ entry.status }}</td>
              <td>{{ entry.duration_ms }} ms</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="view === 'ingestion-runs' && runs.length" class="table-wrap gateway-table">
        <table>
          <caption class="sr-only">Lượt thu thập giá</caption>
          <thead><tr><th>Bắt đầu</th><th>Nguồn</th><th>Kết quả</th><th>Mới</th><th>Trùng</th><th>Chờ kiểm tra</th><th>Thời lượng</th></tr></thead>
          <tbody>
            <tr v-for="entry in runs" :key="entry.id">
              <td>{{ clock.format(new Date(entry.started_at)) }}</td>
              <td>{{ entry.source }}</td>
              <td>{{ runStatus[entry.status] || entry.status }}<small v-if="entry.error_code">{{ entry.error_code }}</small></td>
              <td>{{ entry.inserted }}</td><td>{{ entry.duplicates }}</td><td>{{ entry.quarantined }}</td>
              <td>{{ entry.finished_at ? `${Date.parse(entry.finished_at) - Date.parse(entry.started_at)} ms` : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="!error" class="muted">Chưa có nhật ký phù hợp.</p>

      <div v-if="page > 1 || hasNext" class="gateway-pagination">
        <button class="quiet" :disabled="page === 1 || loading" @click="page--">Trang trước</button>
        <span class="muted">Trang {{ page }}</span>
        <button class="quiet" :disabled="!hasNext || loading" @click="page++">Trang sau</button>
      </div>
    </template>
  </section>
</template>
