import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../api'

const routes = [
  { path: '/', name: 'home', component: () => import('../views/Home.vue') },
  { path: '/school/:id', name: 'school', component: () => import('../views/SchoolPublic.vue') },
  { path: '/class/:id', name: 'class', component: () => import('../views/ClassPublic.vue') },
  { path: '/share/:token', name: 'share', component: () => import('../views/SharePage.vue') },
  { path: '/login', name: 'login', component: () => import('../views/Auth.vue') },
  { path: '/register', name: 'register', component: () => import('../views/Auth.vue') },
  { path: '/forgot', name: 'forgot', component: () => import('../views/Auth.vue') },
  { path: '/admin', name: 'admin', component: () => import('../views/Admin.vue'), meta: { auth: true } },
  { path: '/super', name: 'super', component: () => import('../views/Super.vue'), meta: { auth: true } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.auth && !getToken()) {
    return { name: 'login', query: { next: to.fullPath } }
  }
})
