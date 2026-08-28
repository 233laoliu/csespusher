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
    throw new Error(detail || ('HTTP ' + resp.status))
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
