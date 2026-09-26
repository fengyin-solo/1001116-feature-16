<template>
  <section class="page" data-module="gate">
    <header class="page-head">
      <div>
        <h2>闸口通行管理</h2>
        <p class="page-desc">维护通行记录，围绕通行编号、车牌号码、关联箱号、进出方向做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记通行记录</button>
        <button class="btn" type="button" @click="exportRows">导出闸口通行清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article
        v-for="item in statCards"
        :key="item.label"
        class="stat-card"
        :class="{ clickable: item.key === 'incomplete', active: incompleteOnly && item.key === 'incomplete' }"
        @click="item.key === 'incomplete' && toggleIncomplete()"
      >
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="item.danger ? 'danger-text' : ''">{{ item.value }}</strong>
      </article>
    </div>

    <div class="tab-bar" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab"
        type="button"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <template v-if="activeTab === 'list'">
      <form class="filter-bar" @submit.prevent="reloadList">
        <label class="filter-item">
          <span>通行编号</span>
          <input v-model="keyword" placeholder="按通行编号检索" />
        </label>
        <label class="filter-item">
          <span>通行状态</span>
          <select v-model="statusFilter">
            <option value="">全部状态</option>
            <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
          </select>
        </label>
        <label class="filter-check">
          <input v-model="incompleteOnly" type="checkbox" @change="reloadList" />
          <span>只看车牌号码或关联箱号缺失</span>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-missing': row.incomplete }">
            <td v-for="column in columns" :key="column">
              <template v-if="isMissingCell(row, column)">
                <span class="tag tag-danger">缺失</span>
              </template>
              <template v-else-if="column === '通行状态'">
                <span class="tag" :class="statusTagClass(String(row.status))">{{ row[column] }}</span>
              </template>
              <template v-else>{{ row[column] ?? '—' }}</template>
            </td>
            <td class="row-actions">
              <button class="link" type="button" @click="openDetail(Number(row.id))">查看详情</button>
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                :disabled="busyId === row.id"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的闸口通行记录</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ total }} 条闸口通行记录</span>
        <span v-if="feedback" :class="feedback.ok ? 'ok-text' : 'error-text'">{{ feedback.text }}</span>
      </footer>
    </template>

    <template v-else>
      <div v-if="!board.length" class="empty-state board-empty">暂无道口通行数据</div>
      <div class="board-grid">
        <article v-for="group in board" :key="group['道口编号']" class="board-card">
          <header class="board-head">
            <strong>道口 {{ group['道口编号'] }}</strong>
            <span class="board-keeper">值守：{{ group['值守人员'] || '—' }}</span>
          </header>
          <div class="board-counts">
            <span class="board-count" data-status="待放行">待放行 <b>{{ group['待放行'] }}</b></span>
            <span class="board-count" data-status="已放行">已放行 <b>{{ group['已放行'] }}</b></span>
            <span class="board-count" data-status="已拦截">已拦截 <b>{{ group['已拦截'] }}</b></span>
            <span class="board-count" data-status="已复核">已复核 <b>{{ group['已复核'] }}</b></span>
          </div>
          <div class="board-latest">
            <span class="board-label">最近通行</span>
            <button class="link" type="button" @click="openDetail(Number(group['最近通行'].id))">
              {{ group['最近通行']['通行编号'] }} · {{ group['最近通行']['车牌号码'] || '车牌缺失' }}
            </button>
            <span class="tag" :class="statusTagClass(String(group['最近通行'].status))">
              {{ group['最近通行'].status }}
            </span>
            <span class="board-time">{{ group['最近通行']['通行时间'] || '—' }}</span>
          </div>
        </article>
      </div>
    </template>

    <div v-if="detail" class="drawer-mask" @click.self="closeDetail">
      <aside class="drawer">
        <header class="drawer-head">
          <h3>通行记录详情</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>
        <div class="drawer-body">
          <p v-if="detailError" class="error-text">{{ detailError }}</p>
          <template v-else>
            <div class="detail-status">
              <span class="tag tag-lg" :class="statusTagClass(String(detail.status))">{{ detail.status }}</span>
              <span v-if="detail.reviewed" class="tag tag-lg tag-review">已复核</span>
              <span v-if="detail.incomplete" class="tag tag-lg tag-danger">
                缺少{{ missingLabel(detail) }}
              </span>
            </div>
            <dl class="detail-list">
              <div v-for="field in detailFields" :key="field" class="detail-row">
                <dt>{{ field }}</dt>
                <dd :class="{ 'missing-text': isMissingCell(detail, field) }">
                  {{ isMissingCell(detail, field) ? '缺失' : (detail[field] || '—') }}
                </dd>
              </div>
              <div class="detail-row">
                <dt>复核时间</dt>
                <dd>{{ detail['复核时间'] || '尚未复核' }}</dd>
              </div>
            </dl>
          </template>
        </div>
        <footer v-if="detail" class="drawer-foot">
          <button
            v-for="action in actions"
            :key="action"
            class="btn"
            :class="action === '确认放行' ? 'primary' : ''"
            type="button"
            :disabled="busyId === detail.id"
            @click="runAction(action, detail)"
          >
            {{ action }}
          </button>
        </footer>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | string[] | null>
type Stats = Record<string, number>
type BoardGroup = {
  道口编号: string
  值守人员: string
  待放行: number
  已放行: number
  已拦截: number
  已复核: number
  最近通行: Row
  records: Row[]
}

const ENDPOINT = '/api/gate'
const columns = ['通行编号', '车牌号码', '关联箱号', '进出方向', '通行时间', '道口编号', '值守人员', '通行状态']
const detailFields = ['通行编号', '车牌号码', '关联箱号', '进出方向', '通行时间', '道口编号', '值守人员']
const actions = ['确认放行', '拦截车辆', '复核通行']
const statuses = ['待放行', '已放行', '已拦截', '已复核']
const tabs = [
  { key: 'list', label: '通行记录' },
  { key: 'board', label: '道口看板' },
] as const

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const board = ref<BoardGroup[]>([])
const stats = ref<Stats>({})
const activeTab = ref<'list' | 'board'>('list')
const keyword = ref('')
const statusFilter = ref('')
const incompleteOnly = ref(false)
const feedback = ref<{ ok: boolean; text: string } | null>(null)

const detail = ref<Row | null>(null)
const detailError = ref('')
const busyId = ref<number | null>(null)

const statCards = ref([
  { label: '今日进闸车次', value: 0, key: 'in' },
  { label: '今日出闸车次', value: 0, key: 'out' },
  { label: '待放行', value: 0, key: 'pending' },
  { label: '已放行', value: 0, key: 'released' },
  { label: '拦截车次', value: 0, key: 'blocked', danger: true },
  { label: '信息缺失待补录', value: 0, key: 'incomplete', danger: true },
])

function isMissingCell(row: Row, column: string): boolean {
  return (column === '车牌号码' || column === '关联箱号')
    && Array.isArray(row.missing_fields)
    && (row.missing_fields as string[]).includes(column)
}

function missingLabel(row: Row): string {
  return Array.isArray(row.missing_fields) ? (row.missing_fields as string[]).join('、') : ''
}

function statusTagClass(status: string): string {
  if (status === '已放行') return 'tag-released'
  if (status === '已拦截') return 'tag-danger'
  if (status === '已复核') return 'tag-review'
  return 'tag-pending'
}

function toggleIncomplete() {
  incompleteOnly.value = !incompleteOnly.value
  void reloadList()
}

function switchTab(key: 'list' | 'board') {
  activeTab.value = key
  if (key === 'board') {
    void reloadBoard()
  }
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  incompleteOnly.value = false
  void reloadList()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  feedback.value = { ok: false, text: '通行记录登记入口尚未接入审批流' }
}

function buildListQuery(): string {
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
  if (statusFilter.value) params.set('status', statusFilter.value)
  if (incompleteOnly.value) params.set('incomplete', 'true')
  params.set('size', '200')
  return params.toString()
}

async function runAction(action: string, row: Row) {
  feedback.value = null
  busyId.value = Number(row.id)
  try {
    // 后端 EntryPayload 要求动作放在 values 里；动作结果以响应体 ok/message 为准。
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message || '闸口通行动作未生效，请稍后重试')
    }
    feedback.value = { ok: true, text: payload.message || `已${action}` }
    await Promise.all([
      reloadList(),
      reloadStats(),
      reloadBoard(true),
      detail.value ? reloadDetail(Number(detail.value.id)) : Promise.resolve(),
    ])
  } catch (error) {
    feedback.value = {
      ok: false,
      text: error instanceof Error ? error.message : '闸口通行操作失败',
    }
  } finally {
    busyId.value = null
  }
}

async function reloadList() {
  try {
    const response = await request(`${ENDPOINT}?${buildListQuery()}`)
    if (!response.ok) {
      throw new Error('通行记录列表读取失败')
    }
    const payload = await response.json() as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    feedback.value = {
      ok: false,
      text: error instanceof Error ? error.message : '闸口通行列表读取失败',
    }
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    stats.value = (await response.json()) as Stats
    statCards.value[0].value = stats.value['今日进闸'] ?? 0
    statCards.value[1].value = stats.value['今日出闸'] ?? 0
    statCards.value[2].value = stats.value['待放行'] ?? 0
    statCards.value[3].value = stats.value['已放行'] ?? 0
    statCards.value[4].value = stats.value['已拦截'] ?? 0
    statCards.value[5].value = stats.value['信息缺失'] ?? 0
  } catch {
    // 看板统计失败不阻塞列表操作
  }
}

async function reloadBoard(silent = false) {
  try {
    const response = await request(`${ENDPOINT}/board`)
    if (!response.ok) {
      throw new Error('道口看板读取失败')
    }
    const payload = await response.json() as { items?: BoardGroup[] }
    board.value = payload.items ?? []
  } catch (error) {
    if (!silent) {
      feedback.value = {
        ok: false,
        text: error instanceof Error ? error.message : '道口看板读取失败',
      }
    }
  }
}

async function openDetail(entryId: number) {
  detail.value = null
  detailError.value = ''
  await router.replace({ query: { ...route.query, entry: String(entryId) } })
  await reloadDetail(entryId)
}

async function reloadDetail(entryId: number) {
  try {
    const response = await request(`${ENDPOINT}/${entryId}`)
    if (!response.ok) {
      throw new Error('通行详情读取失败')
    }
    detail.value = (await response.json()) as Row
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : '通行详情读取失败'
  }
}

async function closeDetail() {
  detail.value = null
  detailError.value = ''
  const query = { ...route.query }
  delete query.entry
  await router.replace({ query })
}

onMounted(async () => {
  await Promise.all([reloadList(), reloadStats(), reloadBoard(true)])
  // 返回页面时带 entry 参数会重新打开详情，保证刷新/前后导航后看到的结果一致。
  const entryId = Number(route.query.entry)
  if (entryId > 0) {
    await reloadDetail(entryId)
  }
})
</script>

<style scoped>
.tab-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.tab { border: 1px solid var(--border); background: #fff; border-radius: 6px; padding: 6px 16px; cursor: pointer; }
.tab.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.filter-item select { padding: 4px 8px; border: 1px solid var(--border); border-radius: 6px; }
.filter-check { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.stat-card.clickable { cursor: pointer; }
.stat-card.active { border-color: var(--brand); box-shadow: 0 0 0 1px var(--brand) inset; }
.danger-text { color: #b42318; }
.ok-text { color: #067647; }
.missing-text { color: #b42318; }
.row-missing { background: #fff8f7; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; border: 1px solid transparent; }
.tag-lg { padding: 3px 12px; font-size: 13px; }
.tag-pending { background: #f2f4f7; color: #475467; border-color: #d8dee6; }
.tag-released { background: #e7f6ec; color: #067647; border-color: #aee6c3; }
.tag-danger { background: #fdecec; color: #b42318; border-color: #f5c2c0; }
.tag-review { background: #e8f0fe; color: #1f6feb; border-color: #b9d2fc; }
.board-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.board-card { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.board-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.board-keeper { color: var(--muted); font-size: 12px; }
.board-counts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.board-count { font-size: 12px; color: var(--muted); }
.board-count[data-status='待放行'] b { color: #475467; }
.board-count[data-status='已放行'] b { color: #067647; }
.board-count[data-status='已拦截'] b { color: #b42318; }
.board-count[data-status='已复核'] b { color: #1f6feb; }
.board-latest { display: flex; align-items: center; gap: 8px; border-top: 1px dashed var(--border); padding-top: 8px; font-size: 13px; flex-wrap: wrap; }
.board-label { color: var(--muted); font-size: 12px; }
.board-time { color: var(--muted); font-size: 12px; margin-left: auto; }
.board-empty { padding: 32px; background: #fff; border: 1px solid var(--border); border-radius: 8px; }
.drawer-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.35); display: flex; justify-content: flex-end; z-index: 20; }
.drawer { width: 420px; max-width: 92vw; background: #fff; min-height: 100vh; display: flex; flex-direction: column; }
.drawer-head { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px; border-bottom: 1px solid var(--border); }
.drawer-head h3 { margin: 0; font-size: 16px; }
.drawer-body { flex: 1; padding: 16px; overflow: auto; }
.detail-status { display: flex; gap: 8px; margin-bottom: 16px; }
.detail-list { margin: 0; }
.detail-row { display: flex; justify-content: space-between; gap: 16px; padding: 8px 0; border-bottom: 1px dashed var(--border); font-size: 13px; }
.detail-row dt { color: var(--muted); margin: 0; }
.detail-row dd { margin: 0; text-align: right; }
.drawer-foot { padding: 12px 16px; border-top: 1px solid var(--border); display: flex; gap: 8px; }
</style>
