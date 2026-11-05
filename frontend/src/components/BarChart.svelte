<script>
  import { fmtMoney } from '../lib/format.js'

  export let points = []        // [{ label, revenue, units, receipts }]
  export let valueKey = 'revenue'
  export let money = true

  const H = 132
  const MIN_BAR_WIDTH = 26

  let active = null

  $: values = points.map((p) => Number(p[valueKey]) || 0)
  $: max = Math.max(1, ...values)
  // Возвраты могут утянуть столбик в минус — тогда рисуем от нулевой линии.
  $: min = Math.min(0, ...values)
  $: span = max - min
  $: zeroLine = (max / span) * H

  function height(value) {
    return Math.max(2, (Math.abs(value) / span) * H)
  }

  function label(value) {
    return money ? fmtMoney(value, { short: true }) : String(value)
  }
</script>

{#if points.length}
  <div class="wrap">
    <div class="scroll" style="--min-bar:{MIN_BAR_WIDTH}px">
      <div class="plot" style="height:{H}px">
        <div class="zero" style="top:{zeroLine}px"></div>
        {#each points as p, i}
          <button
            type="button"
            class="col"
            class:active={active === i}
            on:click={() => (active = active === i ? null : i)}
          >
            <span
              class="bar"
              class:neg={values[i] < 0}
              style="height:{height(values[i])}px; {values[i] < 0
                ? `top:${zeroLine}px`
                : `top:${zeroLine - height(values[i])}px`}"
            ></span>
            {#if active === i}
              <span class="tip" style="bottom:{H - zeroLine + height(values[i]) + 8}px">
                {label(values[i])}
              </span>
            {/if}
          </button>
        {/each}
      </div>
      <div class="labels">
        {#each points as p, i}
          <span class="tick" class:active={active === i}>{p.label}</span>
        {/each}
      </div>
    </div>
  </div>
{:else}
  <p class="faint" style="font-size:13px">За период продаж не было</p>
{/if}

<style>
  .wrap { margin: 0 -4px; }
  /* Длинные периоды не сжимаем в кашу, а прокручиваем по горизонтали. */
  .scroll { overflow-x: auto; padding: 14px 4px 0; scrollbar-width: thin; }
  .plot { position: relative; display: flex; align-items: flex-end; gap: 5px; min-width: 100%; }
  .zero { position: absolute; left: 0; right: 0; height: 1px; background: var(--border-strong); }
  .col {
    position: relative; flex: 1 0 var(--min-bar); min-width: var(--min-bar);
    height: 100%; background: none; border: none; padding: 0;
  }
  .bar {
    position: absolute; left: 2px; right: 2px;
    background: var(--grad);
    border-radius: 6px 6px 2px 2px;
    transition: height 0.35s var(--transition), top 0.35s var(--transition), opacity var(--transition);
    opacity: 0.85;
  }
  .col:hover .bar, .col.active .bar { opacity: 1; }
  .bar.neg { background: var(--neg); border-radius: 2px 2px 6px 6px; }
  .tip {
    position: absolute; left: 50%; transform: translateX(-50%);
    background: var(--bg-2); border: 1px solid var(--border-strong);
    border-radius: 9px; padding: 4px 9px; font-size: 12px; font-weight: 700;
    white-space: nowrap; box-shadow: var(--shadow); z-index: 2;
  }
  .labels { display: flex; gap: 5px; min-width: 100%; margin-top: 7px; }
  .tick {
    flex: 1 0 var(--min-bar); min-width: var(--min-bar);
    text-align: center; font-size: 10px; color: var(--text-faint);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .tick.active { color: var(--text); font-weight: 700; }
</style>
