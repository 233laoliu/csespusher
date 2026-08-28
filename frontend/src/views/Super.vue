<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const stats = ref(null)
const users = ref([])
const error = ref('')
const info = ref('')

async function load() {
  error.value = ''
  try {
    stats.value = await api('/api/super/stats')
    users.value = await api('/api/super/users')
  } catch (e) { error.value = e.message }
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
