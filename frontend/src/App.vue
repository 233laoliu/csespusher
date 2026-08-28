<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, getToken, setToken } from './api'
import { useRouter } from 'vue-router'

const router = useRouter()
const me = ref(null)
const site = ref({ github_url: '', contact_email: '', downloads: {} })

async function loadMe() {
  if (!getToken()) { me.value = null; return }
  try { me.value = await api('/api/auth/me') } catch (e) { me.value = null; setToken('') }
}

onMounted(async () => {
  try { site.value = await api('/api/public/site-info') } catch (e) {}
  loadMe()
  window.addEventListener('csespusher:auth-changed', loadMe)
})

function logout() { setToken(''); me.value = null; window.dispatchEvent(new Event('csespusher:auth-changed')); router.push('/') }
</script>

<template>
  <header class="header">
    <router-link to="/" class="brand">csespusher</router-link>
    <span class="tag gray">CSES · ClassIsland · ClassWidgets 配置分发</span>
    <nav>
      <router-link to="/">主页</router-link>
      <router-link v-if="me" to="/admin">管理</router-link>
      <router-link v-if="me && me.role === 'superadmin'" to="/super">超管</router-link>
      <router-link v-if="!me" to="/login">登录</router-link>
      <template v-else>
        <span class="muted">{{ me.username }}</span>
        <a href="#" @click.prevent="logout">退出</a>
      </template>
    </nav>
  </header>

  <router-view :key="$route.fullPath" />

  <footer class="footer">
    <span>© csespusher</span>
    <a v-if="site.github_url" :href="site.github_url" target="_blank">项目 GitHub</a>
    <span v-if="site.contact_email">联系邮箱：{{ site.contact_email }}</span>
    <span class="spacer"></span>
    <span>配置格式：<a href="https://github.com/SmartTeachCN/CSES" target="_blank">CSES</a></span>
  </footer>
</template>
