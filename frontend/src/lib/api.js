async function request(method, path, body) {
  const opts = {
    method,
    credentials: 'same-origin',
    headers: {}
  }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, opts)
  let data = null
  const text = await res.text()
  if (text) {
    try { data = JSON.parse(text) } catch { data = text }
  }
  if (!res.ok) {
    const message = (data && data.detail) || 'Ошибка запроса'
    const err = new Error(typeof message === 'string' ? message : 'Ошибка запроса')
    err.status = res.status
    throw err
  }
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b ?? {}),
  patch: (p, b) => request('PATCH', p, b ?? {}),
  del: (p) => request('DELETE', p)
}

// Собирает query-строку, выбрасывая пустые значения: иначе бэкенд получает
// attribute_id=&stock= и валится на валидации типов.
export function qs(params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '' || value === false) continue
    search.set(key, value)
  }
  const str = search.toString()
  return str ? `?${str}` : ''
}

// Скачивание файла (xlsx, бэкап). Ходим через fetch, а не через прямую ссылку,
// чтобы поймать 401/403 и показать понятную ошибку вместо пустой вкладки.
export async function download(path, fallbackName) {
  const res = await fetch(`/api${path}`, { credentials: 'same-origin' })
  if (!res.ok) {
    const text = await res.text()
    let detail = 'Не удалось скачать файл'
    try { detail = JSON.parse(text).detail || detail } catch { /* не JSON */ }
    throw new Error(detail)
  }
  const disposition = res.headers.get('Content-Disposition') || ''
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  const plain = /filename="?([^";]+)"?/i.exec(disposition)
  const name = utf8 ? decodeURIComponent(utf8[1]) : plain ? plain[1] : fallbackName

  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
