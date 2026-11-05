<script>
  import { fmtMoney, fmtQty, pluralWord } from '../lib/format.js'

  export let items = []
  export let title = ''
  export let fallbackColor = '#0ea5e9'
  export let subtitleKey = null
  export let limit = 8

  let expanded = false
  $: shown = expanded ? items : items.slice(0, limit)
  $: peak = Math.max(1, ...items.map((i) => Math.abs(i.revenue)))
</script>

{#if items.length}
  <section class="card pad">
    {#if title}<h3 class="section-title">{title}</h3>{/if}
    <div class="stack-sm">
      {#each shown as item (item.id ?? item.name)}
        <div class="line">
          <div class="between" style="align-items:baseline">
            <span class="name ellipsis">
              {item.name}
              {#if subtitleKey && item[subtitleKey]}
                <span class="faint" style="font-size:12px"> · {item[subtitleKey]}</span>
              {/if}
            </span>
            <span class="mono value" class:neg={item.revenue < 0}>{fmtMoney(item.revenue)}</span>
          </div>
          <div class="track">
            <div
              class="fill"
              style="width:{(Math.abs(item.revenue) / peak) * 100}%; background:{item.color || fallbackColor}"
            ></div>
          </div>
          <div class="between faint" style="font-size:12px">
            <span>{pluralWord(item.units, 'штука', 'штуки', 'штук')}</span>
            <span>{fmtQty(item.percent)}%</span>
          </div>
        </div>
      {/each}
    </div>

    {#if items.length > limit}
      <button class="btn btn-ghost btn-sm btn-block" style="margin-top:10px" on:click={() => (expanded = !expanded)}>
        {expanded ? 'Свернуть' : `Показать все (${items.length})`}
      </button>
    {/if}
  </section>
{/if}

<style>
  .line { display: flex; flex-direction: column; gap: 5px; }
  .name { font-size: 14px; font-weight: 600; }
  .value { font-size: 14px; font-weight: 700; }
  .track { height: 7px; border-radius: 999px; background: var(--surface-strong); overflow: hidden; }
  .fill { height: 100%; border-radius: 999px; transition: width 0.45s var(--transition); }
</style>
