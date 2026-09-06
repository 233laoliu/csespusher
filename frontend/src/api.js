// 轻量 API 封装：带 JWT 的 fetch
const TOKEN_KEY = 'csespusher_token'

export function getToken() { return localStorage.getItem(TOKEN_KEY) || '' }
export function setToken(t) { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY) }

export async function api(path, { method = 'GET', body, form } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (token) headers['Authorization'] = 'Bearer ' + token
  const opts = { method, headers }
  if (form !== undefined) { opts.body = form }  // FormData，勿设 Content-Type
  else if (body !== undefined) { opts.body = JSON.stringify(body) }
  const resp = await fetch(path, opts)
  const ctype = resp.headers.get('Content-Type') || ''
  if (resp.status === 204) return null
  if (!resp.ok) {
    let detail = await resp.text()
    try { detail = JSON.parse(detail).detail || detail } catch (e) {}
    const msg = detail || ('HTTP ' + resp.status)
    // 登录态失效（token 缺失/过期）时，清掉本地 token 并跳回登录页，
    // 避免所有写操作静默失败（表现为“无法创建学校/无法创建 NTP/进学校空白”）。
    if (resp.status === 401) {
      setToken('')
      if (typeof location !== 'undefined' && !location.pathname.startsWith('/login')) {
        location.href = '/login?next=' + encodeURIComponent(location.pathname)
      }
    }
    throw new Error(msg)
  }
  return ctype.includes('application/json') ? resp.json() : resp.text()
}

export const downloadUrl = (path, filename = '') => {
  // 触发浏览器下载（显式指定带扩展名的文件名，避免部分浏览器丢失扩展名）
  const a = document.createElement('a')
  a.href = path
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}
