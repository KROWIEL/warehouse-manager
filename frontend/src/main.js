import './app.css'
import App from './App.svelte'

// Service worker нужен только для установки на домашний экран и офлайн-оболочки.
// Регистрируется лишь в защищённом контексте — в остальных браузер его отвергнет.
if ('serviceWorker' in navigator && window.isSecureContext) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* без офлайн-режима приложение работает как обычный сайт */
    })
  })
}

const app = new App({
  target: document.getElementById('app')
})

export default app
