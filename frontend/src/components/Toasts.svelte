<script>
  import { toasts } from '../lib/stores.js'
  import { CheckCircle2, AlertCircle, Info } from 'lucide-svelte'
  const icons = { success: CheckCircle2, error: AlertCircle, info: Info }
</script>

<div class="wrap">
  {#each $toasts as t (t.id)}
    <div class="toast {t.kind}">
      <svelte:component this={icons[t.kind] || Info} size={18} />
      <span>{t.message}</span>
    </div>
  {/each}
</div>

<style>
  .wrap {
    position: fixed; z-index: 100; left: 0; right: 0; bottom: 96px;
    display: flex; flex-direction: column; align-items: center; gap: 8px;
    pointer-events: none; padding: 0 16px;
  }
  .toast {
    display: flex; align-items: center; gap: 10px;
    background: var(--bg-2); color: var(--text);
    border: 1px solid var(--border-strong);
    padding: 12px 18px; border-radius: 14px;
    box-shadow: var(--shadow); font-size: 14px; font-weight: 500;
    animation: rise 0.3s cubic-bezier(0.4,0,0.2,1) both;
    max-width: 440px;
  }
  .toast.success { color: var(--pos); }
  .toast.error { color: var(--neg); }
  @keyframes rise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
</style>
