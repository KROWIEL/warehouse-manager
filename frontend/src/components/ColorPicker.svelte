<script>
  import { PALETTE } from '../lib/icons.js'
  export let value = '#0ea5e9'
</script>

<div class="row-colors">
  {#each PALETTE as c}
    <button
      type="button"
      class="dot"
      class:sel={value === c}
      style="background:{c};color:{c}"
      on:click={() => (value = c)}
      aria-label={c}
    ></button>
  {/each}
</div>

<style>
  .row-colors { display: flex; flex-wrap: wrap; gap: 8px; }
  .dot {
    width: 28px; height: 28px; border-radius: 50%; border: 2px solid transparent;
    transition: transform var(--transition), box-shadow var(--transition);
  }
  .dot:hover { transform: scale(1.12); }
  .dot.sel { box-shadow: 0 0 0 2px var(--bg-2), 0 0 0 4px currentColor; transform: scale(1.1); }
</style>
