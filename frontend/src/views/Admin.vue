<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const schools = ref([])
const error = ref('')
const info = ref('')
const busy = ref(false)

const showCreate = ref(false)
const form = ref({ name: '', province: '', city: '' })

const current = ref(null)
const shares = ref([])
const extras = ref([])
const members = ref([])
const newMemberEmail = ref('')
const fileInput = ref(null)
const newExtraKey = ref('')
const newExtraValue = ref('')
const extraKeyInput = ref('')
const extraFileInput = ref(null)

async function load() {
  error.value = ''
  try { schools.value = await api('/api/admin/schools') } catch (e) { error.value = e.message }
}

async function createSchool() {
  busy.value = true; error.value = ''
  try {
    await api('/api/admin/schools', { method: 'POST', body: form.value })
    showCreate.value = false
    form.value = { name: '', province: '', city: '' }
    await load()
  } catch (e) { error.value = e.message }
  busy.value = false
}

async function openSchool(s) {
  error.value = ''; info.value = ''
  try {
    current.value = await api('/api/admin/schools/' + s.id)
    shares.value = await api('/api/admin/schools/' + s.id + '/shares')
    const rows = await api('/api/admin/schools/' + s.id + '/extra-configs')
    extras.value = rows.map(r => ({ ...r, valueRaw: typeof r.value === 'string' ? r.value : JSON.stringify(r.value) }))
    members.value = await api('/api/admin/schools/' + s.id + '/members')
  } catch (e) { error.value = e.message }
}

async function upload() {
  if (!fileInput.value || !fileInput.value.files.length) return
  busy.value = true; error.value = ''; info.value = ''
  const fd = new FormData()
  fd.append('file', fileInput.value.files[0])
  try {
    const r = await api('/api/admin/schools/' + current.value.id + '/upload', { method: 'POST', form: fd })
    info.value = '上传成功：' + r.grades + ' 个年级，' + r.subjects + ' 个科目，' + r.timelines + ' 条时间线，' + r.extras + ' 项杂项配置'
    await openSchool(current.value)
  } catch (e) { error.value = e.message }
  busy.value = false
  if (fileInput.value) fileInput.value.value = ''
}

async function addMember() {
  if (!newMemberEmail.value) return
  busy.value = true; error.value = ''
  try {
    await api('/api/admin/schools/' + current.value.id + '/members?email=' + encodeURIComponent(newMemberEmail.value), { method: 'POST' })
    newMemberEmail.value = ''
    members.value = await api('/api/admin/schools/' + current.value.id + '/members')
  } catch (e) { error.value = e.message }
  busy.value = false
}

async function removeMember(m) {
  if (!confirm('移除协作成员 ' + m.username + '？')) return
  try {
    await api('/api/admin/members/' + m.id, { method: 'DELETE' })
    members.value = members.value.filter(x => x.id !== m.id)
  } catch (e) { error.value = e.message }
}

async function createShare(classId) {
  error.value = ''
  try {
    await api('/api/admin/schools/' + current.value.id + '/shares', { method: 'POST', body: { class_id: classId } })
    shares.value = await api('/api/admin/schools/' + current.value.id + '/shares')
  } catch (e) { error.value = e.message }
}

async function removeShare(s) {
  try {
    await api('/api/admin/shares/' + s.id, { method: 'DELETE' })
    shares.value = shares.value.filter(x => x.id !== s.id)
  } catch (e) { error.value = e.message }
}

function shareUrl(s) { return location.origin + '/share/' + s.token }

async function copyText(text, msg) {
  try { await navigator.clipboard.writeText(text); info.value = msg }
  catch (e) { info.value = text }
}

async function copyLink(s) { await copyText(shareUrl(s), '已复制分享链接') }

function shareByClassId() {
  const m = {}
  for (const s of shares.value) if (s.class_id) m[s.class_id] = s
  return m
}

const allClasses = () => {
  if (!current.value) return []
  return current.value.grades.flatMap(g => g.classes.map(c => ({ ...c, grade: g.name })))
}

async function addExtra() {
  if (!newExtraKey.value) return
  error.value = ''
  let value = newExtraValue.value
  try { value = JSON.parse(newExtraValue.value) } catch (e) { /* 保留原始字符串 */ }
  try {
    await api('/api/admin/schools/' + current.value.id + '/extra-configs/' + encodeURIComponent(newExtraKey.value),
      { method: 'POST', body: { value } })
    newExtraKey.value = ''; newExtraValue.value = ''
    info.value = '已添加配置'
    await refreshExtras()
  } catch (e) { error.value = e.message }
}

async function deleteExtra(x) {
  if (!confirm('删除配置项「' + x.key + '」？')) return
  try {
    await api('/api/admin/schools/' + current.value.id + '/extra-configs/' + encodeURIComponent(x.key),
      { method: 'DELETE' })
    await refreshExtras()
  } catch (e) { error.value = e.message }
}

async function uploadExtra() {
  if (!extraKeyInput.value || !extraFileInput.value || !extraFileInput.value.files.length) {
    error.value = '上传配置需要填写配置名并选择文件'
    return
  }
  error.value = ''
  const fd = new FormData()
  fd.append('file', extraFileInput.value.files[0])
  try {
    await api('/api/admin/schools/' + current.value.id + '/extra-configs-upload/' + encodeURIComponent(extraKeyInput.value),
      { method: 'POST', form: fd })
    info.value = '已上传配置 ' + extraKeyInput.value
    extraKeyInput.value = ''
    extraFileInput.value.value = ''
    await refreshExtras()
  } catch (e) { error.value = e.message }
}

async function refreshExtras() {
  const rows = await api('/api/admin/schools/' + current.value.id + '/extra-configs')
  extras.value = rows.map(r => ({ ...r, valueRaw: typeof r.value === 'string' ? r.value : JSON.stringify(r.value) }))
}

async function saveExtra(x) {
  error.value = ''
  let value = x.valueRaw
  try { value = JSON.parse(x.valueRaw) } catch (e) { /* 保留原始字符串 */ }
  try {
    await api('/api/admin/schools/' + current.value.id + '/extra-configs',
      { method: 'PUT', body: { configs: { [x.key]: value } } })
    info.value = '已保存 ' + x.key
    const rows = await api('/api/admin/schools/' + current.value.id + '/extra-configs')
    extras.value = rows.map(r => ({ ...r, valueRaw: typeof r.value === 'string' ? r.value : JSON.stringify(r.value) }))
  } catch (e) { error.value = e.message }
}

async function deleteSchool(s) {
  if (!confirm('删除学校「' + s.name + '」及其全部数据？此操作不可恢复。')) return
  try {
    await api('/api/admin/schools/' + s.id, { method: 'DELETE' })
    current.value = null
    await load()
  } catch (e) { error.value = e.message }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <h1>管理</h1>
    <p class="subtitle">创建学校、上传课程表、分发分享链接</p>

    <div v-if="error" class="msg error">{{ error }}</div>
    <div v-if="info" class="msg ok">{{ info }}</div>

    <div v-if="!current">
      <div class="row" style="margin-bottom: 14px">
        <h2 style="margin: 0; font-size: 18px">我的学校</h2>
        <div class="spacer"></div>
        <button class="btn primary" @click="showCreate = !showCreate">{{ showCreate ? '取消' : '＋ 创建学校' }}</button>
      </div>

      <div v-if="showCreate" class="card" style="margin-bottom: 16px; max-width: 520px">
        <div class="field"><label class="label">学校名称</label>
          <input class="input" v-model="form.name" placeholder="例如：杭州市示范中学" /></div>
        <div class="row">
          <div class="field" style="flex:1"><label class="label">省份</label>
            <input class="input" v-model="form.province" placeholder="浙江省" /></div>
          <div class="field" style="flex:1"><label class="label">城市</label>
            <input class="input" v-model="form.city" placeholder="杭州市" /></div>
        </div>
        <button class="btn primary" :disabled="busy || !form.name" @click="createSchool">创建</button>
      </div>

      <div class="grid cols-3">
        <div v-for="s in schools" :key="s.id" class="card" style="cursor: pointer" @click="openSchool(s)">
          <div class="row">
            <div style="font-weight: 600">{{ s.name }}</div>
            <span class="tag" v-if="s.has_excel">已上传</span>
            <span class="tag gray" v-else>未上传</span>
          </div>
          <div class="muted">{{ s.province || '—' }} · {{ s.city || '—' }} · {{ s.grades.length }} 个年级</div>
        </div>
      </div>
      <div v-if="!schools.length" class="muted mt">还没有学校，点击右上角创建。</div>
    </div>

    <div v-else>
      <div class="row">
        <button class="btn" @click="current = null">← 返回</button>
        <h2 style="margin: 0; font-size: 20px">{{ current.name }}</h2>
        <span class="tag gray">{{ current.province }} {{ current.city }}</span>
        <div class="spacer"></div>
        <button class="btn danger small" @click="deleteSchool(current)">删除学校</button>
      </div>

      <div class="card mt">
        <h3 style="margin: 0 0 8px">上传课程表 Excel</h3>
        <p class="muted" style="margin: 0 0 12px">
          格式：每个 sheet = 一个年级；config sheet 存放科目 / 时间线 / 杂项配置。重新上传会覆盖旧数据。
        </p>
        <div class="row">
          <input type="file" accept=".xlsx" ref="fileInput" class="input" style="max-width: 340px" />
          <button class="btn primary" :disabled="busy" @click="upload">上传并解析</button>
        </div>
      </div>

      <div class="card mt">
        <h3 style="margin: 0 0 4px">班级配置链接</h3>
        <p class="muted" style="margin: 0 0 12px">
          每个班级的链接是固定的，重复点击不会生成新链接。直链可用于软件「从互联网导入配置」。
        </p>
        <div class="row" style="margin-bottom: 12px">
          <button class="btn" @click="createShare(null)">＋ 全校分享页</button>
        </div>
        <table class="table">
          <thead><tr><th>班级</th><th>分享页</th><th>配置直链（ClassIsland）</th><th></th></tr></thead>
          <tbody>
            <tr v-for="s in shares" :key="s.id">
              <td>{{ s.class_name ? s.class_name : '全校' }}</td>
              <td>
                <a :href="'/share/' + s.token" target="_blank">/share/{{ s.token.slice(0, 8) }}…</a>
              </td>
              <td>
                <template v-if="s.class_id">
                  <code style="font-size: 12px">/api/public/classes/{{ s.class_id }}/raw/classisland</code>
                </template>
                <span v-else class="muted">—</span>
              </td>
              <td class="row" style="gap: 6px">
                <button class="btn small" @click="copyLink(s)">复制分享页</button>
                <button v-if="s.class_id" class="btn small"
                        @click="copyText(location.origin + '/api/public/classes/' + s.class_id + '/raw/classisland', '已复制配置直链')">
                  复制直链
                </button>
                <button class="btn small danger" @click="removeShare(s)">删除</button>
              </td>
            </tr>
            <tr v-if="!shares.length"><td colspan="4" class="muted">暂无链接，点击上方按钮或班级按钮生成</td></tr>
          </tbody>
        </table>
        <div class="row" style="margin-top: 12px; flex-wrap: wrap; gap: 8px">
          <button v-for="c in allClasses()" :key="c.id" class="btn small"
                  :disabled="!!shareByClassId()[c.id]"
                  @click="createShare(c.id)">
            {{ shareByClassId()[c.id] ? '✓ ' : '＋ ' }}{{ c.grade }} {{ c.name }}
          </button>
        </div>
      </div>

      <div class="card mt">
        <h3 style="margin: 0 0 4px">杂项配置（软件独有配置）</h3>
        <p class="muted" style="margin: 0 0 12px">来自 config sheet 的 AB/AC 列，可在此添加、删除、编辑或上传配置文件。</p>
        <div v-for="x in extras" :key="x.key" class="row" style="margin-bottom: 10px">
          <span style="min-width: 200px; font-family: Consolas, monospace">{{ x.key }}</span>
          <input class="input" v-model="x.valueRaw" style="flex:1" />
          <button class="btn small primary" @click="saveExtra(x)">保存</button>
          <button class="btn small danger" @click="deleteExtra(x)">删除</button>
        </div>
        <div v-if="!extras.length" class="muted">暂无杂项配置。</div>

        <div style="border-top: 1px solid rgba(0,0,0,0.08); margin-top: 14px; padding-top: 14px">
          <div style="font-weight: 600; margin-bottom: 8px">新增配置</div>
          <div class="row" style="margin-bottom: 8px">
            <input class="input" style="max-width: 260px" v-model="newExtraKey" placeholder="配置名（如 classisland.theme）" />
            <input class="input" style="flex:1" v-model="newExtraValue" placeholder='配置值（JSON 或纯文本，如 "Light"）' />
            <button class="btn small primary" :disabled="!newExtraKey" @click="addExtra">添加</button>
          </div>
          <div class="row">
            <input class="input" style="max-width: 260px" v-model="extraKeyInput" placeholder="配置名" />
            <input type="file" ref="extraFileInput" class="input" style="max-width: 300px" accept=".json,.txt,.yaml,.yml,.xml" />
            <button class="btn small" @click="uploadExtra">上传文件</button>
          </div>
        </div>
      </div>

      <div class="card mt">
        <h3 style="margin: 0 0 12px">协作成员</h3>
        <div class="row" style="margin-bottom: 12px">
          <input class="input" style="max-width: 280px" v-model="newMemberEmail" placeholder="输入已注册用户的邮箱" />
          <button class="btn" :disabled="busy || !newMemberEmail" @click="addMember">添加</button>
        </div>
        <div v-for="m in members" :key="m.id" class="row" style="margin-bottom: 6px">
          <span style="font-weight: 500">{{ m.username }}</span>
          <span class="muted">{{ m.email }}</span>
          <span class="tag gray">{{ m.role === 'owner' ? '创建者' : '协作' }}</span>
          <div class="spacer"></div>
          <button v-if="m.role !== 'owner'" class="btn small danger" @click="removeMember(m)">移除</button>
        </div>
      </div>
    </div>
  </main>
</template>
