import { writable } from 'svelte/store'

import { api } from './api.js'

export const user = writable(null)

export const theme = writable('light')

const THEME_KEY = 'sm_theme'

export function applyTheme(value) {
  document.documentElement.setAttribute('data-theme', value)
  localStorage.setItem(THEME_KEY, value)
  theme.set(value)
}

export function storedTheme() {
  return localStorage.getItem(THEME_KEY) || 'light'
}

/* ===== Справочники ===== */
// Категории, поля и поставщики нужны почти на каждом экране, поэтому лежат
// в одном сторе и перезагружаются точечно после правок в настройках.
export const catalog = writable({ categories: [], suppliers: [] })

export async function refreshCatalog() {
  const data = await api.get('/catalog')
  catalog.set(data)
  return data
}

/* ===== Toasts ===== */
export const toasts = writable([])
let toastId = 0

export function toast(message, kind = 'info') {
  const id = ++toastId
  toasts.update((list) => [...list, { id, message, kind }])
  setTimeout(() => {
    toasts.update((list) => list.filter((t) => t.id !== id))
  }, 3200)
}
