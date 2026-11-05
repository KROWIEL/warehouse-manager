<script>
  import { AVATAR_KEYS, avatar } from '../lib/avatars.js'
  export let value = 'fox'
</script>

<div class="grid">
  {#each AVATAR_KEYS as key}
    <button
      type="button"
      class="opt"
      class:sel={value === key}
      style="background:{avatar(key).grad}"
      on:click={() => (value = key)}
      aria-label={key}
    >
      {avatar(key).emoji}
    </button>
  {/each}
</div>

<style>
  .grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(46px, 1fr));
    gap: 9px; max-height: 210px; overflow-y: auto; padding: 3px;
  }
  .opt {
    aspect-ratio: 1; display: grid; place-items: center;
    border: 2px solid transparent; border-radius: 50%;
    font-size: 22px; line-height: 1;
    opacity: 0.55;
    transition: opacity var(--transition), transform var(--transition), box-shadow var(--transition);
  }
  .opt:hover { opacity: 0.85; }
  .opt.sel {
    opacity: 1; transform: scale(1.06);
    box-shadow: 0 0 0 2px var(--bg-2), 0 0 0 4px var(--accent);
  }
</style>
