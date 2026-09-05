<script setup>
import { computed, ref, watch } from 'vue'
import { api, setToken } from '../api'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const mode = computed(() => {
  if (route.name === 'register') return 'register'
  if (route.name === 'forgot') return 'forgot'
  return 'login'
})

const email = ref('')
const username = ref('')
const password = ref('')
const code = ref('')
const newPassword = ref('')
const busy = ref(false)
const error = ref('')
const info = ref('')

watch(mode, () => { error.value = ''; info.value = ''; code.value = ''; password.value = ''; newPassword.value = '' })

async function doLogin() {
  error.value = ''; info.value = ''; busy.value = true
  try {
    const r = await api('/api/auth/login', { method: 'POST', body: { email: email.value, password: password.value } })
    setToken(r.token)
    window.dispatchEvent(new Event('csespusher:auth-changed'))
    router.push(route.query.next || (r.user.role === 'superadmin' ? '/super' : '/admin'))
  } catch (e) { error.value = e.message }
  busy.value = false
}

async function sendCode(purpose) {
  error.value = ''; info.value = ''; busy.value = true
  try {
    const r = await api('/api/auth/send-code', { method: 'POST', body: { email: email.value, purpose } })
    info.value = r.channel === 'console'
      ? '验证码已生成（开发模式：请查看服务器控制台输出）'
      : '验证码已发送到您的邮箱'
  } catch (e) { error.value = e.message }
  busy.value = false
}

async function doRegister() {
  error.value = ''; info.value = ''; busy.value = true
  try {
    await api('/api/auth/register', { method: 'POST', body: {
      email: email.value, username: username.value, password: password.value
    } })
    info.value = '注册成功，验证码已发送到邮箱（用于激活）'
  } catch (e) { error.value = e.message }
  busy.value = false
}

async function doReset() {
  error.value = ''; info.value = ''; busy.value = true
  try {
    await api('/api/auth/reset-password', { method: 'POST', body: {
      email: email.value, code: code.value, password: newPassword.value
    } })
    info.value = '密码已重置，请使用新密码登录'
    setTimeout(() => router.push('/login'), 1200)
  } catch (e) { error.value = e.message }
  busy.value = false
}
</script>

<template>
  <main class="page" style="max-width: 460px">
    <h1>{{ mode === 'register' ? '注册管理员账号' : mode === 'forgot' ? '重置密码' : '登录' }}</h1>
    <p class="subtitle">
      {{ mode === 'register' ? '邮箱 + 用户名注册' : mode === 'forgot' ? '验证码 + 新密码' : '邮箱 + 密码登录' }}
    </p>

    <div class="card">
      <div v-if="error" class="msg error">{{ error }}</div>
      <div v-if="info" class="msg info">{{ info }}</div>

      <template v-if="mode === 'register'">
        <div class="field">
          <label class="label">邮箱</label>
          <input class="input" v-model="email" type="email" placeholder="you@example.com" />
        </div>
        <div class="field">
          <label class="label">用户名</label>
          <input class="input" v-model="username" placeholder="展示名称" />
        </div>
        <div class="field">
          <label class="label">密码</label>
          <input class="input" v-model="password" type="password" placeholder="至少 6 位" />
        </div>
        <button class="btn primary" :disabled="busy || !email || !username || password.length < 6" @click="doRegister">注册</button>
        <div class="mt muted">已有账号？<router-link to="/login">去登录</router-link></div>
      </template>

      <template v-else-if="mode === 'forgot'">
        <div class="field">
          <label class="label">邮箱</label>
          <input class="input" v-model="email" type="email" placeholder="you@example.com" />
        </div>
        <div class="field">
          <label class="label">验证码</label>
          <div class="row">
            <input class="input" v-model="code" maxlength="6" placeholder="6 位数字" style="flex:1" />
            <button class="btn" :disabled="busy || !email" @click="sendCode('reset')">发送验证码</button>
          </div>
        </div>
        <div class="field">
          <label class="label">新密码</label>
          <input class="input" v-model="newPassword" type="password" placeholder="至少 6 位" />
        </div>
        <button class="btn primary" :disabled="busy || !email || code.length !== 6 || newPassword.length < 6" @click="doReset">重置密码</button>
        <div class="mt muted">想起来了？<router-link to="/login">去登录</router-link></div>
      </template>

      <template v-else>
        <div class="field">
          <label class="label">邮箱</label>
          <input class="input" v-model="email" type="email" placeholder="you@example.com" />
        </div>
        <div class="field">
          <label class="label">密码</label>
          <input class="input" v-model="password" type="password" placeholder="登录密码" @keyup.enter="doLogin" />
        </div>
        <button class="btn primary" :disabled="busy || !email || password.length < 6" @click="doLogin">登录</button>
        <div class="mt muted">
          没有账号？<router-link to="/register">注册</router-link>
          <span style="margin: 0 8px">·</span>
          <router-link to="/forgot">忘记密码？</router-link>
        </div>
      </template>
    </div>
  </main>
</template>
