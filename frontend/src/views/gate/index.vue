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
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>通行编号</span>
        <input v-model="filters.keyword" placeholder="按通行编号检索" />
      </label>
      <label class="filter-item">
        <span>车牌号码</span>
        <input v-model="filters.plate" placeholder="按车牌号码检索" />
      </label>
      <label class="filter-item">
        <span>关联箱号</span>
        <input v-model="filters.container" placeholder="按关联箱号检索" />
      </label>
      <label class="filter-item">
        <span>通行状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item filter-check">
        <input v-model="filters.incomplete" type="checkbox" />
        <span>只看资料缺失（车牌或箱号）</span>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>资料缺失</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-missing': row['资料缺失'] }">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>
            <span v-if="row['资料缺失']" class="missing-tag">缺{{ row['缺失字段'] }}</span>
            <span v-else>—</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无闸口通行数据，可先登记通行记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条闸口通行记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/gate'
const columns = ["通行编号", "车牌号码", "关联箱号", "进出方向", "通行时间", "道口编号", "值守人员", "通行状态"]
const actions = ["确认放行", "拦截车辆", "复核通行"]
const statuses = ["待放行", "已放行", "已拦截", "已复核"]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<{ label: string; value: number }[]>([])
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref({ keyword: '', plate: '', container: '', status: '', incomplete: false })

function resetFilters() {
  filters.value = { keyword: '', plate: '', container: '', status: '', incomplete: false }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '通行记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await response.json()
    if (!response.ok || !result.ok) {
      throw new Error(result.message ?? '闸口通行动作未生效，请稍后重试')
    }
    // 动作结果先就地写回当前行，再与列表、道口看板一起刷新，保证两个页面口径一致
    if (result.entry) {
      const index = rows.value.findIndex((item) => item.id === result.entry.id)
      if (index >= 0) {
        rows.value[index] = result.entry
      }
    }
    noticeMessage.value = result.message ?? ''
    await Promise.all([reload(), loadSummary()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '闸口通行操作失败'
  }
}

async function loadSummary() {
  try {
    const payload = await fetchJson<{ items: { label: string; value: number }[] }>(`${ENDPOINT}/summary`)
    stats.value = payload.items ?? []
  } catch {
    stats.value = []
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.plate) query.set('plate', filters.value.plate)
  if (filters.value.container) query.set('container', filters.value.container)
  if (filters.value.status) query.set('status', filters.value.status)
  if (filters.value.incomplete) query.set('incomplete', 'true')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('通行记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '闸口通行列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadSummary()
})
</script>

<style scoped>
.row-missing td {
  background: #fff7ed;
}
.missing-tag {
  color: #b45309;
  font-size: 12px;
}
.notice-text {
  color: var(--brand);
}
.filter-check {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
</style>
