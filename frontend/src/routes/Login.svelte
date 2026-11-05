<script>
  import { createEventDispatcher } from 'svelte'
  import { Boxes, Loader2 } from 'lucide-svelte'
  import { api } from '../lib/api.js'

  const dispatch = createEventDispatcher()
  let username = ''
  let password = ''
  let error = ''
  let busy = false

  async function submit() {
    if (busy) return
    error = ''
    busy = true
    try {
      const me = await api.post('/auth/login', { username, password })
      dispatch('login', me)
    } catch (e) {
      error = e.message
    } finally {
      busy = false
    }
  }
</script>

<div class="login">
  <form class="card panel fade-up" on:submit|preventDefault={submit}>
    <div class="logo">
      <div class="logo-badge"><Boxes size={28} color="#fff" /></div>
      <div>
        <h1>Склад</h1>
        <p class="dim">Учёт товаров и продаж</p>
      </div>
    </div>

    <div class="field">
      <label for="u">Логин</label>
      <input id="u" bind:value={username} placeholder="логин" autocomplete="username" />
    </div>
    <div class="field">
      <label for="p">Пароль</label>
      <input id="p" type="password" bind:value={password} placeholder="••••••••" autocomplete="current-password" />
    </div>

    {#if error}<div class="error-box">{error}</div>{/if}

    <button class="btn btn-primary" type="submit" disabled={busy || !username || !password}>
      {#if busy}<Loader2 size={18} class="spin" />{/if}
      Войти
    </button>
  </form>
</div>

<style>
  .login { min-height: 100vh; display: grid; place-items: center; padding: 20px; }
  .panel { width: 100%; max-width: 380px; padding: 30px 26px; display: flex; flex-direction: column; gap: 16px; }
  .logo { display: flex; align-items: center; gap: 14px; margin-bottom: 6px; }
  .logo-badge {
    width: 54px; height: 54px; border-radius: 16px; display: grid; place-items: center;
    background: var(--grad); box-shadow: 0 10px 24px -8px var(--accent-glow);
  }
  h1 { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; }
  .logo p { font-size: 13px; margin-top: 2px; }
  .btn-primary { margin-top: 4px; padding: 13px; }
</style>
