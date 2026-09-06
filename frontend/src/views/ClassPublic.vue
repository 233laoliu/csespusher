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

// Vue 3 SFC <script setup> 的模板编译会把 mustache 表达式收集为 setup 暴露属性。
// `location` 是 window 全局,setup 不会代理它,所以模板里直接写 {{ location.origin }}
// 会让渲染函数访问 setupState.location（undefined）→ .origin 抛错。
// 显式声明一次,模板/事件处理器/函数体内都能直接用。
const origin = location.origin

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
  return origin + '/api/public/classes/' + route.params.id + '/raw/' + fmt
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

const ntpNotice = ref('')
async function copyText(text, msg) {
  try {
    await navigator.clipboard.writeText(text)
    ntpNotice.value = msg
  } catch (e) {
    ntpNotice.value = text
  }
  setTimeout(() => { ntpNotice.value = '' }, 4000)
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

        <div class="card mt" v-if="info.ntp && info.ntp.enabled">
          <h3 style="margin: 0 0 6px">时间同步（对齐学校打铃）</h3>
          <p class="muted" style="margin: 0 0 10px">
            学校打铃系统每天会走偏一点，把下面任意一个地址填进软件的时间同步设置，
            软件时间就会跟着学校铃声走。
          </p>
          <div v-if="ntpNotice" class="msg ok">{{ ntpNotice }}</div>
          <div class="row" style="margin-bottom: 8px">
            <span style="min-width: 110px" class="muted">NTP 地址</span>
            <code>{{ info.ntp.address }}</code>
            <button class="btn small" @click="copyText(info.ntp.address, '已复制 NTP 地址')">复制</button>
          </div>
          <div class="row">
            <span style="min-width: 110px" class="muted">校时接口</span>
            <code class="raw-url">{{ origin }}{{ info.ntp.http_time_url }}</code>
            <button class="btn small"
                    @click="copyText(origin + info.ntp.http_time_url, '已复制校时接口')">复制</button>
          </div>
          <div class="muted" style="margin-top: 8px">
            当前学校时间 {{ info.ntp.local }}（{{ info.ntp.timezone }}）
          </div>
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
