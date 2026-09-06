import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './style.css'

const app = createApp(App)

/**
 * 全局错误兜底：把任何组件渲染错误、路由加载错误、未处理的 Promise 拒绝
 * 都直接渲染到页面上的红色浮窗里。
 *
 * 起因：school107 等学校的班级页曾出现"header/footer 都在但中间 main 区空白"，
 *      由于 production build 下 Vue 默认吞掉 warning 级别的渲染错误，
 *      加上 vue-router 的懒加载 promise reject 默认也不会回显到页面上，
 *      用户看到的只是空白，再叠加 <router-view :key> 强制重建，进一步掩盖了
 *      真正的根因。从此以后任何视图组件抛错都能立刻肉眼看清楚。
 */
function showErrorOverlay(label, err) {
  try {
    let node = document.getElementById('wb-error-overlay')
    if (!node) {
      node = document.createElement('pre')
      node.id = 'wb-error-overlay'
      Object.assign(node.style, {
        position: 'fixed',
        left: '16px',
        right: '16px',
        top: '80px',
        zIndex: 99999,
        background: '#1a0a0a',
        color: '#ffb4b4',
        padding: '14px 18px',
        borderRadius: '8px',
        whiteSpace: 'pre-wrap',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
        fontSize: '13px',
        lineHeight: '1.55',
        border: '1px solid #5a1a1a',
        maxHeight: '60vh',
        overflow: 'auto',
        boxShadow: '0 10px 30px rgba(0,0,0,.4)',
      })
      const close = document.createElement('button')
      close.textContent = '×'
      Object.assign(close.style, {
        position: 'absolute', top: '6px', right: '8px',
        background: 'transparent', color: '#ffb4b4',
        border: 'none', fontSize: '18px', cursor: 'pointer', lineHeight: 1,
      })
      close.onclick = () => node.remove()
      node.appendChild(close)
      const body = document.createElement('div')
      body.id = 'wb-error-overlay-body'
      node.appendChild(body)
      document.body.appendChild(node)
    }
    const body = node.querySelector('#wb-error-overlay-body')
    const stack = (err && err.stack) ? err.stack : (err && err.message) ? err.message : String(err)
    const item = document.createElement('div')
    item.style.borderTop = '1px solid #5a1a1a'
    item.style.paddingTop = '8px'
    item.style.marginTop = '8px'
    item.textContent = `[${label}] ${stack}\n`
    body.appendChild(item)
    // 控制台也保留一份，便于 DevTools 端查看更多上下文
    // eslint-disable-next-line no-console
    console.error('[wb-overlay]', label, err)
  } catch (_) { /* overlay 自身失败就不再挣扎 */ }
}

app.config.errorHandler = (err, _instance, info) => {
  showErrorOverlay('vue:' + (info || 'error'), err)
}

router.onError((err) => {
  showErrorOverlay('router', err)
})

window.addEventListener('unhandledrejection', (e) => {
  showErrorOverlay('unhandledrejection', e.reason || new Error('unhandledrejection'))
})

app.use(router).mount('#app')
