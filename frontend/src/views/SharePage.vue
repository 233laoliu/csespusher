<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { useRoute } from 'vue-router'

const route = useRoute()
const token = route.params.token
const data = ref(null)
const error = ref('')
const classId = ref(null)
const preview = ref(null)
const busy = ref(false)

// Vue 3 SFC <script setup> 的 mustache 表达式会被编译为 setup 暴露属性；
// `location` 是 window 全局不会被代理,模板里直接写 {{ location.origin }} 会抛
// "Cannot read properties of undefined"。显式声明一次解决。
const origin = location.origin

const isWholeSchool = computed(() => data.value && !data.value.classes.length)
const effectiveClassId = computed(() => {
  if (!data.value) return null
  if (data.value.classes.length === 1) return data.value.classes[0].id
  return classId.value
})

onMounted(async () => {
  try { data.value = await api('/api/public/share/' + token) } catch (e) { error.value = e.message }
})

async function loadPreview() {
  if (effectiveClassId.value == null) return
  busy.value = true; error.value = ''
  try {
    preview.value = await api(`/api/public/share/${token}/preview?class_id=${effectiveClassId.value}`)
  } catch (e) { error.value = e.message }
  busy.value = false
}

const FORMAT_EXT = { cses: 'yaml', classisland: 'json', classwidgets: 'json' }

function download(fmt) {
  let url = `/api/public/share/${token}/download/${fmt}`
  if (data.value.classes.length !== 1) url += `?class_id=${effectiveClassId.value}`
  const cls = data.value.classes.find(c => c.id === effectiveClassId.value)
  const name = cls
    ? `${data.value.school.name}-${cls.grade}-${cls.name}.${FORMAT_EXT[fmt]}`
    : ''
  const a = document.createElement('a')
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove()
}

const notice = ref('')
function rawUrl(fmt) {
  return origin + '/api/public/classes/' + effectiveClassId.value + '/raw/' + fmt
}
async function copyRaw(fmt) {
  try {
    await navigator.clipboard.writeText(rawUrl(fmt))
    notice.value = '已复制配置直链，可粘贴到软件「从互联网导入配置」'
  } catch (e) {
    notice.value = '直链：' + rawUrl(fmt)
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
  <main class="page" style="max-width: 860px">
    <div v-if="error" class="msg error">{{ error }}</div>
    <div v-if="!data && !error" class="muted">加载中…</div>

    <template v-if="data">
      <div class="card">
        <div class="muted">{{ data.school.province }} · {{ data.school.city }}</div>
        <h1 style="font-size: 22px">{{ data.school.name }} · 课程表配置</h1>
        <p class="subtitle">下载配置文件后导入对应软件即可使用</p>

        <!-- 班级选择（全校链接） -->
        <div v-if="data.classes.length > 1" class="field">
          <label class="label">选择班级</label>
          <div class="row">
            <button v-for="c in data.classes" :key="c.id" class="btn"
                    :class="{ primary: effectiveClassId === c.id }"
                    @click="classId = c.id">{{ c.grade }} {{ c.name }}</button>
          </div>
        </div>
        <div v-else-if="data.classes.length === 1" class="muted">
          班级：{{ data.classes[0].grade }} {{ data.classes[0].name }}
        </div>

        <div v-if="!data.has_excel" class="msg info">该学校尚未上传课程表，暂时无法下载。</div>

        <template v-else>
          <div v-if="notice" class="msg ok">{{ notice }}</div>
          <h3 style="margin: 18px 0 10px">下载课程表配置文件</h3>
          <div class="row">
            <button class="btn primary" :disabled="effectiveClassId == null" @click="download('cses')">CSES (.yaml)</button>
            <button class="btn primary" :disabled="effectiveClassId == null" @click="download('classisland')">ClassIsland (.json)</button>
            <button class="btn primary" :disabled="effectiveClassId == null" @click="download('classwidgets')">ClassWidgets (.json)</button>
          </div>

          <h3 style="margin: 18px 0 10px">从互联网导入配置（复制直链）</h3>
          <p class="muted" style="margin: 0 0 10px">直链固定不变，可直接粘贴到软件的「从互联网导入配置」功能中使用。</p>
          <div class="row">
            <button class="btn" :disabled="effectiveClassId == null" @click="copyRaw('cses')">复制 CSES 直链</button>
            <button class="btn" :disabled="effectiveClassId == null" @click="copyRaw('classisland')">复制 ClassIsland 直链</button>
            <button class="btn" :disabled="effectiveClassId == null" @click="copyRaw('classwidgets')">复制 ClassWidgets 直链</button>
          </div>

          <h3 style="margin: 18px 0 10px">时间同步（对齐学校打铃）</h3>
          <p class="muted" style="margin: 0 0 10px" v-if="data.ntp && data.ntp.enabled">
            学校打铃系统每天会走偏一点，把下面任意一个地址填进软件的时间同步设置即可。
          </p>
          <div v-if="data.ntp && data.ntp.enabled">
            <div v-if="ntpNotice" class="msg ok">{{ ntpNotice }}</div>
            <div class="row" style="margin-bottom: 8px">
              <span style="min-width: 110px" class="muted">NTP 地址</span>
              <code>{{ data.ntp.address }}</code>
              <button class="btn small" @click="copyText(data.ntp.address, '已复制 NTP 地址')">复制</button>
            </div>
            <div class="row" style="margin-bottom: 8px">
              <span style="min-width: 110px" class="muted">校时接口</span>
<code style="font-size: 12px">{{ origin }}{{ data.ntp.http_time_url }}</code>
                <button class="btn small"
                        @click="copyText(origin + data.ntp.http_time_url, '已复制校时接口')">复制</button>
            </div>
            <div class="muted">
              当前学校时间 {{ data.ntp.local }}（{{ data.ntp.timezone }}）
            </div>
          </div>
          <div v-else class="muted">该校尚未开启时间同步服务。</div>

          <h3 style="margin: 18px 0 10px">软件本体下载</h3>
          <div class="row">
            <a class="btn" :href="data.downloads.classisland" target="_blank">下载 ClassIsland</a>
            <a class="btn" :href="data.downloads.classwidgets" target="_blank">下载 ClassWidgets</a>
          </div>

          <h3 style="margin: 18px 0 10px">课程表预览</h3>
          <button class="btn" :disabled="busy || effectiveClassId == null" @click="loadPreview">
            {{ preview ? '刷新预览' : '加载预览' }}
          </button>
          <div v-if="preview" class="mt">
            <div v-for="d in preview.week" :key="d.day" style="margin-bottom: 12px">
              <div style="font-weight: 600; margin-bottom: 4px">{{ d.name }}</div>
              <div class="row">
                <span v-for="(ev, i) in d.events" :key="i" class="tag">
                  {{ ev.subject }} {{ ev.start }}–{{ ev.end }}
                </span>
              </div>
            </div>
          </div>
        </template>
      </div>
    </template>
  </main>
</template>
