<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { useRoute } from 'vue-router'

const route = useRoute()
const school = ref(null)
const error = ref('')

onMounted(async () => {
  try {
    school.value = await api('/api/public/schools/' + route.params.id)
  } catch (e) { error.value = e.message }
})
</script>

<template>
  <main class="page">
    <div v-if="error" class="msg error">{{ error }}</div>
    <template v-if="school">
      <div class="muted">{{ school.province }} · {{ school.city }}</div>
      <h1>{{ school.name }}</h1>
      <p class="subtitle">选择年级，点击班级查看课表并获取配置文件</p>

      <div class="grid cols-3">
        <div v-for="g in school.grades" :key="g.id" class="card">
          <div style="font-weight: 600; margin-bottom: 8px">{{ g.name }}</div>
          <div class="row" style="flex-wrap: wrap; gap: 8px">
            <router-link v-for="c in g.classes" :key="c.id"
                         :to="{ name: 'class', params: { id: c.id } }"
                         class="tag gray class-link">{{ c.name }}</router-link>
          </div>
        </div>
      </div>
      <div v-if="!school.grades.length" class="muted mt">该学校尚未录入年级班级。</div>
    </template>
  </main>
</template>

<style scoped>
.class-link {
  cursor: pointer;
  text-decoration: none;
  padding: 4px 12px;
  transition: background 0.15s, color 0.15s;
}
.class-link:hover {
  background: var(--accent);
  color: #fff;
}
</style>
