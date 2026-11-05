<script>
  import { fmtMoney } from '../lib/format.js'
  export let data = []          // [{ value, color, name }]
  export let caption = 'Выручка'
  export let size = 200

  const stroke = 26
  $: r = (size - stroke) / 2
  $: c = 2 * Math.PI * r
  $: total = data.reduce((s, d) => s + d.value, 0)

  $: segments = (() => {
    let acc = 0
    return data
      .filter((d) => d.value > 0)
      .map((d) => {
        const frac = total ? d.value / total : 0
        const seg = { ...d, dash: frac * c, offset: acc * c }
        acc += frac
        return seg
      })
  })()
</script>

<div class="pie" style="width:{size}px;height:{size}px">
  <svg width={size} height={size} viewBox="0 0 {size} {size}">
    <g transform="rotate(-90 {size / 2} {size / 2})">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-strong)" stroke-width={stroke} />
      {#each segments as s}
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={s.color} stroke-width={stroke}
          stroke-dasharray="{s.dash} {c - s.dash}"
          stroke-dashoffset={-s.offset}
          stroke-linecap="butt"
          class="seg"
        />
      {/each}
    </g>
  </svg>
  <div class="center">
    <span class="dim" style="font-size:12px">{caption}</span>
    <span class="val mono">{fmtMoney(total, { short: true })}</span>
  </div>
</div>

<style>
  .pie { position: relative; flex-shrink: 0; }
  .center {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 2px; text-align: center;
  }
  .val { font-size: 19px; font-weight: 800; letter-spacing: -0.5px; }
  .seg { transition: stroke-dasharray 0.5s cubic-bezier(0.4,0,0.2,1), stroke-dashoffset 0.5s cubic-bezier(0.4,0,0.2,1); }
</style>
