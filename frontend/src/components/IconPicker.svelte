<script>
  import Icon from './Icon.svelte'
  import { CATEGORY_ICONS } from '../lib/icons.js'
  export let value = 'package'
  export let options = CATEGORY_ICONS
</script>

<div class="grid">
  {#each options as name}
    <button
      type="button"
      class="opt"
      class:sel={value === name}
      on:click={() => (value = name)}
      aria-label={name}
    >
      <Icon {name} size={20} />
    </button>
  {/each}
</div>

<style>
  .grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(44px, 1fr));
    gap: 8px; max-height: 168px; overflow-y: auto; padding: 2px;
  }
  .opt {
    aspect-ratio: 1; display: grid; place-items: center;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; color: var(--text-dim);
    transition: all var(--transition);
  }
  .opt:hover { color: var(--text); border-color: var(--border-strong); }
  .opt.sel { background: var(--grad); color: #fff; border-color: transparent; }
</style>
