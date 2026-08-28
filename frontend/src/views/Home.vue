<script setup>
import { onMounted, ref, computed } from 'vue'
import { api } from '../api'

const groups = ref([])
const site = ref({ downloads: {} })
const q = ref('')
const loading = ref(true)
const error = ref('')

const filtered = computed(() => {
  if (!q.value.trim()) return groups.value
  const kw = q.value.trim()
  const out = []
  for (const prov of groups.value) {
    const cities = []
    for (const c of prov.cities) {
      const schools = c.schools.filter(s => s.name.includes(kw) || c.city.includes(kw) || prov.province.includes(kw))
      if (schools.length) cities.push({ city: c.city, schools })
    }
    if (cities.length) out.push({ province: prov.province, cities })
  }
  return out
})

onMounted(async () => {
  try {
    site.value = await api('/api/public/site-info')
    groups.value = await api('/api/public/schools')
  } catch (e) { error.value = '加载失败：' + e.message }
  loading.value = false
})
</script>

<template>
  <main class="page">
    <h1>课程表配置分发平台</h1>
    <p class="subtitle">为学校收集课程表，一键生成 CSES / ClassIsland / ClassWidgets 配置文件</p>

    <!-- 下载按钮 -->
    <div class="grid cols-3" style="margin-bottom: 28px">
      <div class="card">
        <div class="row">
          <div style="font-size: 28px">🏝️</div>
          <div>
            <div style="font-weight: 600; font-size: 16px">ClassIsland</div>
            <div class="muted">功能丰富的桌面课程表小组件</div>
          </div>
          <div class="spacer"></div>
          <a class="btn primary" :href="site.downloads.classisland" target="_blank">下载 ClassIsland</a>
        </div>
      </div>
      <div class="card">
        <div class="row">
          <div style="font-size: 28px">⏰</div>
          <div>
            <div style="font-weight: 600; font-size: 16px">Class Widgets</div>
            <div class="muted">轻量课程表小部件</div>
          </div>
          <div class="spacer"></div>
          <a class="btn primary" :href="site.downloads.classwidgets" target="_blank">下载 ClassWidgets</a>
        </div>
      </div>
      <div class="card">
        <div class="row">
          <div style="font-size: 28px">📄</div>
          <div>
            <div style="font-weight: 600; font-size: 16px">示例课程表</div>
            <div class="muted">Excel 模板样例，管理员按此格式填写</div>
          </div>
          <div class="spacer"></div>
          <a class="btn" href="/api/public/sample-excel" download="示例课程表.xlsx">下载示例 Excel</a>
        </div>
      </div>
    </div>

    <!-- 学校列表 -->
    <div class="card">
      <div class="row" style="margin-bottom: 14px">
        <h2 style="margin: 0; font-size: 18px">已收集的学校</h2>
        <div class="spacer"></div>
        <input class="input" style="max-width: 260px" v-model="q" placeholder="搜索学校 / 省市…" />
      </div>

      <div v-if="error" class="msg error">{{ error }}</div>
      <div v-if="loading" class="muted">加载中…</div>
      <div v-else-if="!filtered.length" class="muted">暂无学校。管理员可登录后上传课程表。</div>

      <div v-for="prov in filtered" :key="prov.province" style="margin-bottom: 18px">
        <div style="font-weight: 600; margin-bottom: 8px">
          <span class="tag">{{ prov.province }}</span>
        </div>
        <div v-for="c in prov.cities" :key="c.city" style="margin-left: 12px; margin-bottom: 8px">
          <div class="muted" style="margin-bottom: 6px">{{ c.city }}</div>
          <div class="row">
            <router-link
              v-for="s in c.schools" :key="s.id"
              :to="`/school/${s.id}`"
              class="card" style="padding: 10px 16px; display: inline-flex; gap: 8px; align-items: center"
            >
              <span>{{ s.name }}</span>
              <span class="tag gray">{{ s.grade_count }} 个年级</span>
            </router-link>
          </div>
        </div>
      </div>
    </div>
  </main>
</template>
