// Минимальный service worker: нужен только чтобы приложение ставилось
// на домашний экран и открывалось без сети. Данные он не кеширует никогда —
// склад, показывающий вчерашние остатки, хуже, чем честная ошибка сети.
//
// ponytail: файлы со хешем в имени накапливаются в кеше и не чистятся.
// Лечится сменой номера версии ниже — старые кеши удаляются при активации.
const CACHE = 'store-v1'
const SHELL_KEY = '/'
const PRECACHE = ['/manifest.webmanifest', '/favicon.svg', '/icon-192.png']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  // Всё под /api — только из сети, без кеша и без офлайн-подмены.
  if (url.pathname.startsWith('/api/')) return

  if (request.mode === 'navigate') {
    // Оболочку кешируем на каждом удачном заходе: так офлайн-версия index.html
    // всегда ссылается на те же файлы сборки, что закешированы рядом.
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone()
            caches.open(CACHE).then((cache) => cache.put(SHELL_KEY, copy))
          }
          return response
        })
        .catch(async () => (await caches.match(SHELL_KEY)) || Response.error())
    )
    return
  }

  // Статика (в том числе .wasm сканера) лежит с хешем в имени, поэтому
  // отдаём из кеша сразу, а в сеть идём только за тем, чего там нет.
  event.respondWith(
    caches.match(request).then(
      (hit) =>
        hit ||
        fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone()
            caches.open(CACHE).then((cache) => cache.put(request, copy))
          }
          return response
        })
    )
  )
})
