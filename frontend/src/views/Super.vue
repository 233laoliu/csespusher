<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const stats = ref(null)
const users = ref([])
const ntpStatus = ref(null)
const error = ref('')
const info = ref('')

function fmtOffset(ms) {
  if (ms == null) return '—'
  const s = ms / 1000
  const a = Math.abs(s)
  const sign = s >= 0 ? '+' : '−'
  if (a < 60) return sign + a.toFixed(1) + ' 秒'
  if (a < 3600) return sign + (a / 60).toFixed(1) + ' 分钟'
  if (a < 86400) return sign + (a / 3600).toFixed(2) + ' 小时'
  return sign + (a / 86400).toFixed(2) + ' 天'
}

async function load() {
  error.value = ''
  try {
    stats.value = await api('/api/super/stats')
    users.value = await api('/api/super/users')
  } catch (e) { error.value = e.message }
  try { ntpStatus.value = await api('/api/admin/ntp/status') } catch (e) { /* 不影响主流程 */ }
}

async function setRole(u, role) {
  error.value = ''
  try {
    await api('/api/super/users/' + u.id, { method: 'PUT', body: { role } })
    await load()
    info.value = '已更新 ' + u.email
  } catch (e) { error.value = e.message }
}

async function toggleActive(u) {
  error.value = ''
  try {
    await api('/api/super/users/' + u.id, { method: 'PUT', body: { is_active: !u.is_active } })
    await load()
  } catch (e) { error.value = e.message }
}

async function removeUser(u) {
  if (!confirm('删除用户 ' + u.email + '？其名下学校将转移给你。')) return
  error.value = ''
  try {
    await api('/api/super/users/' + u.id, { method: 'DELETE' })
    await load()
  } catch (e) { error.value = e.message }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <h1>超级管理员</h1>
    <p class="subtitle">平台运行状态与用户管理</p>

    <div v-if="error" class="msg error">{{ error }}</div>
    <div v-if="info" class="msg ok">{{ info }}</div>

    <div v-if="stats" class="grid cols-3" style="margin-bottom: 24px">
      <div class="card"><div class="muted">用户总数</div><div style="font-size: 26px; font-weight: 600">{{ stats.users_total }}</div></div>
      <div class="card"><div class="muted">学校总数</div><div style="font-size: 26px; font-weight: 600">{{ stats.schools_total }}</div></div>
      <div class="card"><div class="muted">分享链接（本周新增）</div><div style="font-size: 26px; font-weight: 600">{{ stats.shares_total }} <span class="muted" style="font-size:14px">(+{{ stats.shares_week }})</span></div></div>
    </div>

    <div v-if="ntpStatus" class="card" style="margin-bottom: 24px">
      <div class="row">
        <h3 style="margin: 0">NTP 时间同步服务</h3>
        <span class="tag" v-if="ntpStatus.running">运行中</span>
        <span class="tag gray" v-else>未运行</span>
        <div class="spacer"></div>
        <span class="muted">基础端口 {{ ntpStatus.base_port }}<template v-if="ntpStatus.host"> · 对外主机 {{ ntpStatus.host }}</template></span>
      </div>
      <p class="muted" style="margin: 6px 0 12px">
        每所学校一个 UDP 端口，把「真实时间 + 该校累积偏移」广播出去，用于对齐学校打铃。
      </p>
      <div v-if="!ntpStatus.service_enabled" class="msg info">
        当前部署通过 NTP_ENABLED=0 关闭了 NTP 服务。
      </div>
      <table class="table">
        <thead><tr><th>学校</th><th>端口</th><th>监听</th><th>查询数</th><th>每日偏移</th><th>当前偏差</th><th>学校时间</th></tr></thead>
        <tbody>
          <tr v-for="s in ntpStatus.servers" :key="s.id">
            <td style="font-weight: 500">{{ s.school_name }}</td>
            <td><code>{{ s.port }}</code></td>
            <td>
              <span class="tag" v-if="s.listening">正常</span>
              <span class="tag gray" v-else-if="s.error" :title="s.error">异常</span>
              <span class="tag gray" v-else>停用</span>
            </td>
            <td>{{ s.queries }}<span class="muted" v-if="s.unique_clients">（{{ s.unique_clients }} 个来源）</span></td>
            <td>{{ fmtOffset(s.daily_offset_ms) }} / 天</td>
            <td>{{ fmtOffset(s.current_offset_ms) }}</td>
            <td class="muted">{{ s.school_time }}</td>
          </tr>
          <tr v-if="!ntpStatus.servers.length">
            <td colspan="7" class="muted">还没有学校启用 NTP 服务。</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3 style="margin: 0 0 12px">用户管理</h3>
      <table class="table">
        <thead><tr><th>ID</th><th>用户名</th><th>邮箱</th><th>角色</th><th>学校数</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>{{ u.id }}</td>
            <td>{{ u.username }}</td>
            <td>{{ u.email }}</td>
            <td><span class="tag" :class="{ gray: u.role !== 'superadmin' }">{{ u.role }}</span></td>
            <td>{{ u.schools_count }}</td>
            <td><span class="tag" :class="{ gray: !u.is_active }">{{ u.is_active ? '正常' : '停用' }}</span></td>
            <td class="row">
              <button class="btn small" v-if="u.role === 'admin'" @click="setRole(u, 'superadmin')">设为超管</button>
              <button class="btn small" v-else @click="setRole(u, 'admin')">降为管理员</button>
              <button class="btn small" @click="toggleActive(u)">{{ u.is_active ? '停用' : '启用' }}</button>
              <button class="btn small danger" @click="removeUser(u)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </main>
</template>
