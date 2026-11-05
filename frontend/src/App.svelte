<script>
  import { onMount } from 'svelte'
  import Router, { location, push } from 'svelte-spa-router'
  import { Boxes, ScanBarcode, ChartPie, Settings as SettingsIcon, Loader2 } from 'lucide-svelte'

  import { api } from './lib/api.js'
  import { applyTheme, refreshCatalog, storedTheme, toast, user } from './lib/stores.js'
  import Toasts from './components/Toasts.svelte'
  import Login from './routes/Login.svelte'
  import ChangePassword from './routes/ChangePassword.svelte'
  import Warehouse from './routes/Warehouse.svelte'
  import Sale from './routes/Sale.svelte'
  import Stats from './routes/Stats.svelte'
  import Settings from './routes/Settings.svelte'

  let loading = true

  const routes = {
    '/': Warehouse,
    '/sale': Sale,
    '/stats': Stats,
    '/settings': Settings,
    '*': Warehouse
  }

  const nav = [
    { path: '/', label: 'Склад', icon: Boxes },
    { path: '/sale', label: 'Продажа', icon: ScanBarcode },
    { path: '/stats', label: 'Статистика', icon: ChartPie },
    { path: '/settings', label: 'Настройки', icon: SettingsIcon }
  ]

  onMount(async () => {
    applyTheme(storedTheme())
    try {
      const me = await api.get('/auth/me')
      await ready(me)
    } catch {
      user.set(null)
    } finally {
      loading = false
    }
  })

  // Справочники нужны почти на каждом экране, но до смены стартового пароля
  // весь остальной API закрыт — тогда и не запрашиваем.
  async function ready(me) {
    user.set(me)
    applyTheme(me.theme)
    if (!me.must_change_password) {
      try {
        await refreshCatalog()
      } catch (e) {
        toast(e.message, 'error')
      }
    }
  }

  async function handleLogin(e) {
    await ready(e.detail)
    push('/')
  }
</script>

{#if loading}
  <div class="splash">
    <Loader2 size={34} class="spin" />
  </div>
{:else if !$user}
  <Login on:login={handleLogin} />
{:else if $user.must_change_password}
  <ChangePassword on:done={(e) => ready(e.detail)} />
{:else}
  <div class="shell">
    <main class="content">
      <div class="container">
        <Router {routes} />
      </div>
    </main>

    <nav class="bottom-nav">
      <div class="nav-inner">
        {#each nav as item}
          <a href={'#' + item.path} class="nav-item" class:active={$location === item.path}>
            <svelte:component this={item.icon} size={21} />
            <span>{item.label}</span>
          </a>
        {/each}
      </div>
    </nav>
  </div>
{/if}

<Toasts />

<style>
  .splash { display: grid; place-items: center; height: 100vh; color: var(--accent); }
  :global(.spin) { animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .shell { min-height: 100vh; padding-bottom: calc(96px + env(safe-area-inset-bottom)); }
  .content { padding: 20px 0 12px; }

  .bottom-nav {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 40;
    display: flex; justify-content: center;
    padding: 0 10px calc(10px + env(safe-area-inset-bottom));
    pointer-events: none;
  }
  .nav-inner {
    pointer-events: auto;
    display: flex; gap: 3px;
    background: var(--surface-strong);
    border: 1px solid var(--border-strong);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    border-radius: 999px;
    padding: 6px;
    box-shadow: var(--shadow);
    width: 100%; max-width: 480px;
  }
  .nav-item {
    flex: 1;
    display: flex; flex-direction: column; align-items: center; gap: 3px;
    padding: 9px 4px; border-radius: 999px;
    color: var(--text-faint); font-size: 11px; font-weight: 600;
    transition: color var(--transition), background var(--transition);
  }
  .nav-item.active { color: #fff; background: var(--grad); }
  .nav-item:not(.active):hover { color: var(--text); }
</style>
