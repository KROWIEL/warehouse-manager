<script>
  import { createEventDispatcher } from 'svelte'
  import { X } from 'lucide-svelte'
  export let title = ''
  const dispatch = createEventDispatcher()

  function close() { dispatch('close') }
  function onKey(e) { if (e.key === 'Escape') close() }
  function onOverlay(e) { if (e.target === e.currentTarget) close() }
</script>

<svelte:window on:keydown={onKey} />

<div class="overlay" on:click={onOverlay} role="presentation">
  <div class="modal" role="dialog" aria-modal="true">
    <div class="between" style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:700">{title}</h2>
      <button class="btn btn-ghost btn-icon" on:click={close} aria-label="Закрыть">
        <X size={18} />
      </button>
    </div>
    <slot />
  </div>
</div>
