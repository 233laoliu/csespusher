<script setup>
import { computed, ref, watch } from 'vue'
import { api, setToken } from '../api'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const mode = computed(() => route.name === 'register' ? 'register' : 'login')

const email = ref('')
const username = ref('')
const password = ref('')
const code = ref('')
const step = ref('email')       // login: email -> code ; register: form -> code(optional)
const busy = ref(false)
const error = ref('')
const info = ref('')

watch(mode, () => { error.value = ''; info.value = ''; step.value = 'email'; code.value = '' })

async function sendCode() {
  error.value = ''; busy.value = true
  try {
    const r = await api('/api/auth/send-code', { method: 'POST', body: { email: email.value, purpose: 'login' } })
    info.value = r.channel === 'console'
      ? '验证码已生成（开发模式：请查看服务器控制台输出）'
      : '验证码已发送到您的邮箱'
    step.value = 'code'
  } catch (e) { error.value = e.message }
  busy.value = false
}

async function doLogin() {
  error.value = ''; busy.value = true
  try {
    const r = await api('/api/auth/login', { method: 'POST', body: { email: email.value, code: code.value } })
    setToken(r.token)
    window.dispatchEvent(new Event('csespusher:auth-changed'))
    router.push(route.query.next || (r.user.role === 'superadmin' ? '/super' : '/admin'))
  } catch (e) { error.value = e.message }
  busy.value = false
}

async function doRegister() {
  error.value = ''; busy.value = true
  try {
    await api('/api/auth/register', { method: 'POST', body: { email: email.value, username: username.value, password: password.value } })
    info.value = '注册成功，验证码已发送，请直接登录'
    await sendCode()
  } catch (e) { error.value = e.message }
  busy.value = false
}
</script>

<template>
  <main class="page" style="max-width: 460px">
    <h1>{{ mode === 'register' ? '注册管理员账号' : '登录' }}</h1>
    <p class="subtitle">{{ mode === 'register' ? '邮箱 + 用户名注册' : '邮箱 + 验证码登录' }}</p>

    <div class="card">
      <div v-if="error" class="msg error">{{ error }}</div>
      <div v-if="info" class="msg info">{{ info }}</div>

      <template v-if="mode === 'register' && step === 'email'">
        <div class="field">
          <label class="label">邮箱</label>
          <input class="input" v-model="email" type="email" placeholder="you@example.com" />
        </div>
        <div class="field">
          <label class="label">用户名</label>
          <input class="input" v-model="username" placeholder="展示名称" />
        </div>
        <div class="field">
          <label class="label">密码（用于账号信息校验）</label>
          <input class="input" v-model="password" type="password" placeholder="至少 6 位" />
        </div>
        <button class="btn primary" :disabled="busy || !email || !username || password.length < 6" @click="doRegister">注册并发送验证码</button>
        <div class="mt muted">已有账号？<router-link to="/login">去登录</router-link></div>
      </template>

      <template v-else>
        <div class="field">
          <label class="label">邮箱</label>
          <input class="input" v-model="email" type="email" placeholder="you@example.com" :disabled="step === 'code'" />
        </div>
        <div class="field" v-if="step === 'email'">
          <button class="btn primary" :disabled="busy || !email" @click="sendCode">发送验证码</button>
        </div>
        <template v-else>
          <div class="field">
            <label class="label">验证码</label>
            <input class="input" v-model="code" maxlength="6" placeholder="6 位数字" />
          </div>
          <div class="row">
            <button class="btn primary" :disabled="busy || code.length !== 6" @click="doLogin">登录</button>
            <button class="btn" :disabled="busy" @click="sendCode">重新发送</button>
          </div>
        </template>
        <div class="mt muted" v-if="mode === 'login'">没有账号？<router-link to="/register">注册</router-link></div>
      </template>
    </div>
  </main>
</template>
