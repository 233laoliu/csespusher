<script setup>
import { onMounted, ref } from 'vue'
import { api, downloadUrl } from '../api'
import { useRoute } from 'vue-router'

const route = useRoute()
const info = ref(null)
const preview = ref(null)
const error = ref('')
const notice = ref('')

const FORMAT_LABELS = { cses: 'CSES', classisland: 'ClassIsland', classwidgets: 'ClassWidgets' }
const FORMAT_EXT = { cses: 'yaml', classisland: 'json', classwidgets: 'json' }

function downloadClass(fmt) {
  const name = info.value
    ? `${info.value.school.name}-${info.value.grade.name}-${info.value.class.name}.${FORMAT_EXT[fmt]}`
    : ''
  downloadUrl('/api/public/classes/' + route.params.id + '/download/' + fmt, name)
}

onMounted(async () => {
  try {
    info.value = await api('/api/public/classes/' + route.params.id)
    if (info.value.has_excel) {
      preview.value = await api('/api/public/classes/' + route.params.id + '/preview')
    }
  } catch (e) { error.value = e.message }
})

function rawUrl(fmt) {
  return location.origin + '/api/public/classes/' + route.params.id + '/raw/' + fmt
}

async function copyRaw(fmt) {
  const url = rawUrl(fmt)
  try {
    await navigator.clipboard.writeText(url)
    notice.value = '已复制 ' + FORMAT_LABELS[fmt] + ' 配置直链，可粘贴到软件「从互联网导入配置」'
  } catch (e) {
    notice.value = '直链：' + url
  }
  setTimeout(() => { notice.value = '' }, 4000)
}
</script>

<template>
  <main class="page">
    <div v-if="error" class="msg error">{{ error }}</div>
    <div v-if="notice" class="msg ok">{{ notice }}</div>
    <template v-if="info">
      <div class="muted">
        <router-link :to="{ name: 'school', params: { id: info.school.id } }" class="link">
          {{ info.school.name }}</router-link>
        &nbsp;/&nbsp;{{ info.grade.name }}&nbsp;/&nbsp;{{ info.class.name }}
      </div>
      <h1>{{ info.class.name }}</h1>

      <template v-if="info.has_excel">
        <div class="card">
          <h3 style="margin: 0 0 8px">获取配置文件</h3>
          <p class="muted" style="margin: 0 0 12px">
            下载文件，或复制直链用于软件「从互联网导入配置」功能。直链固定不变，课程表更新后无需更换。
          </p>
          <table class="table">
            <thead><tr><th>格式</th><th>下载文件</th><th>配置直链（从互联网导入）</th></tr></thead>
            <tbody>
              <tr v-for="fmt in info.formats" :key="fmt">
                <td style="font-weight: 500">{{ FORMAT_LABELS[fmt] || fmt }}</td>
                <td>
                  <button class="btn small primary" @click="downloadClass(fmt)">⬇ 下载</button>
                </td>
                <td class="row" style="gap: 8px">
                  <code class="raw-url">{{ rawUrl(fmt) }}</code>
                  <button class="btn small" @click="copyRaw(fmt)">复制链接</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card mt" v-if="preview">
          <h3 style="margin: 0 0 12px">课表预览</h3>
          <div v-for="d in preview.week" :key="d.day" style="margin-bottom: 14px">
            <div style="font-weight: 600; margin-bottom: 6px">{{ d.name }}</div>
            <div class="row" style="flex-wrap: wrap; gap: 6px">
              <span v-for="(ev, i) in d.events" :key="i" class="tag">
                {{ ev.start }}–{{ ev.end }} {{ ev.subject }}
              </span>
            </div>
          </div>
        </div>
      </template>
      <div v-else class="muted mt">该学校尚未上传课程表，暂无配置可获取。</div>
    </template>
  </main>
</template>

<style scoped>
.link { color: var(--accent); text-decoration: none; }
.link:hover { text-decoration: underline; }
.raw-url {
  font-size: 12px;
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
