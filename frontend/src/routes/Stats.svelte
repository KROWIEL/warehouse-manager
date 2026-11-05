<script>
  import { onMount } from 'svelte'
  import { AlertTriangle, Download, Loader2, Snowflake } from 'lucide-svelte'
  import { api, download, qs } from '../lib/api.js'
  import { fmtMoney, fmtQty, pluralWord, shiftISO, todayISO } from '../lib/format.js'
  import { toast } from '../lib/stores.js'
  import BarChart from '../components/BarChart.svelte'
  import Breakdown from '../components/Breakdown.svelte'
  import PieChart from '../components/PieChart.svelte'

  const PERIODS = [
    { id: 'month', label: 'Месяц' },
    { id: '3m', label: '3 месяца' },
    { id: '6m', label: '6 месяцев' },
    { id: 'year', label: 'Год' },
    { id: 'all', label: 'Всё время' },
    { id: 'custom', label: 'Свой' }
  ]

  let period = 'month'
  let dateFrom = shiftISO(todayISO(), -30)
  let dateTo = todayISO()
  let attributeId = null
  let metric = 'revenue'

  let data = null
  let loading = true
  let exporting = false

  $: params = {
    period,
    date_from: period === 'custom' ? dateFrom : null,
    date_to: period === 'custom' ? dateTo : null,
    attribute_id: attributeId
  }

  async function load() {
    loading = true
    try {
      data = await api.get('/stats' + qs(params))
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      loading = false
    }
  }

  onMount(load)

  function pickPeriod(id) {
    period = id
    if (id !== 'custom') load()
  }

  async function exportXlsx() {
    exporting = true
    try {
      await download('/stats/export.xlsx' + qs(params), 'store-stats.xlsx')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      exporting = false
    }
  }

  $: kpis = data
    ? [
        { label: 'Выручка', value: fmtMoney(data.totals.revenue), accent: true },
        { label: 'Чеков', value: fmtQty(data.totals.receipts) },
        { label: 'Средний чек', value: fmtMoney(data.totals.avg_receipt) },
        { label: 'Продано', value: `${fmtQty(data.totals.units)} шт` },
        { label: 'Скидки', value: fmtMoney(data.totals.discount) },
        { label: 'Возвраты', value: fmtMoney(data.totals.returns_amount) },
        { label: 'Списано', value: fmtMoney(data.totals.writeoff_amount) },
        { label: 'Склад сейчас', value: fmtMoney(data.totals.stock_value) }
      ]
    : []
</script>

<div class="stack">
  <div class="segmented">
    {#each PERIODS as p}
      <button class:active={period === p.id} on:click={() => pickPeriod(p.id)}>{p.label}</button>
    {/each}
  </div>

  {#if period === 'custom'}
    <section class="card pad fade-up">
      <div class="grid-2">
        <div class="field">
          <label for="df">С</label>
          <input id="df" type="date" bind:value={dateFrom} max={dateTo} />
        </div>
        <div class="field">
          <label for="dt">По</label>
          <input id="dt" type="date" bind:value={dateTo} min={dateFrom} />
        </div>
      </div>
      <button class="btn btn-primary btn-block" style="margin-top:12px" on:click={load}>Показать</button>
    </section>
  {/if}

  {#if loading}
    <div class="center"><Loader2 size={26} class="spin" /></div>
  {:else if data}
    <div class="between">
      <span class="faint" style="font-size:12px">{data.label}</span>
      <button class="btn btn-sm" on:click={exportXlsx} disabled={exporting}>
        {#if exporting}<Loader2 size={15} class="spin" />{:else}<Download size={15} />{/if}
        Excel
      </button>
    </div>

    <div class="kpis">
      {#each kpis as k}
        <div class="card kpi" class:accent={k.accent}>
          <span class="faint">{k.label}</span>
          <span class="mono val">{k.value}</span>
        </div>
      {/each}
    </div>

    {#if data.by_category.length}
      <section class="card pad">
        <h3 class="section-title">Выручка по категориям</h3>
        <div class="pie-row">
          <PieChart
            data={data.by_category.map((c) => ({ value: Math.max(0, c.revenue), color: c.color, name: c.name }))}
          />
          <div class="legend">
            {#each data.by_category as c}
              <div class="leg">
                <span class="swatch" style="background:{c.color}"></span>
                <span class="grow ellipsis">{c.name}</span>
                <span class="mono">{fmtQty(c.percent)}%</span>
              </div>
            {/each}
          </div>
        </div>
      </section>
    {/if}

    <section class="card pad">
      <div class="between" style="margin-bottom:4px">
        <h3 class="section-title" style="margin:0">Динамика</h3>
        <div class="segmented">
          <button class:active={metric === 'revenue'} on:click={() => (metric = 'revenue')}>Br</button>
          <button class:active={metric === 'units'} on:click={() => (metric = 'units')}>шт</button>
          <button class:active={metric === 'receipts'} on:click={() => (metric = 'receipts')}>чеки</button>
        </div>
      </div>
      <BarChart points={data.series.points} valueKey={metric} money={metric === 'revenue'} />
    </section>

    <Breakdown title="Поставщики" items={data.by_supplier} />
    <Breakdown title="Подкатегории" items={data.by_subcategory} subtitleKey="category_name" />
    <Breakdown title="Лучше всего продаётся" items={data.top_products} subtitleKey="category_name" />
    {#if data.worst_products.length > 1}
      <Breakdown title="Хуже всего продаётся" items={data.worst_products} subtitleKey="category_name" limit={5} />
    {/if}
    <Breakdown title="Продавцы" items={data.by_user} />
    <Breakdown title="Способы оплаты" items={data.by_payment} />

    {#if data.attributes_available.length}
      <section class="card pad">
        <h3 class="section-title">Разрез по полю товара</h3>
        <select
          bind:value={attributeId}
          on:change={load}
        >
          <option value={null}>Не выбрано</option>
          {#each data.attributes_available as a}
            <option value={a.id}>{a.name} · {a.category_name}</option>
          {/each}
        </select>
        {#if data.by_attribute && data.by_attribute.values.length}
          <div style="margin-top:12px">
            <Breakdown items={data.by_attribute.values} limit={12} />
          </div>
        {/if}
      </section>
    {/if}

    {#if data.stock.low.length}
      <section class="card pad">
        <h3 class="section-title"><AlertTriangle size={13} /> Пора дозаказать</h3>
        <div class="stack-sm">
          {#each data.stock.low as p (p.id)}
            <div class="row">
              <span class="swatch" style="background:{p.color}"></span>
              <div class="grow">
                <div class="ellipsis" style="font-size:14px;font-weight:600">{p.name}</div>
                <div class="faint" style="font-size:12px">{p.supplier_name}</div>
              </div>
              <span class="badge" class:badge-neg={p.stock <= 0} class:badge-warn={p.stock > 0}>
                {fmtQty(p.stock)} из {fmtQty(p.min_stock)}
              </span>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    {#if data.stock.dead.length}
      <section class="card pad">
        <h3 class="section-title">
          <Snowflake size={13} /> Не продаётся больше {data.stock.dead_after_days} дней
        </h3>
        <div class="stack-sm">
          {#each data.stock.dead as p (p.id)}
            <div class="row">
              <span class="swatch" style="background:{p.color}"></span>
              <div class="grow">
                <div class="ellipsis" style="font-size:14px;font-weight:600">{p.name}</div>
                <div class="faint" style="font-size:12px">
                  {p.last_sale ? `продавался ${p.last_sale}` : 'ни разу не продавался'}
                </div>
              </div>
              <div class="right">
                <span class="mono" style="font-weight:700">{fmtMoney(p.value)}</span>
                <span class="faint" style="font-size:11px">{pluralWord(p.stock, 'штука', 'штуки', 'штук')}</span>
              </div>
            </div>
          {/each}
        </div>
      </section>
    {/if}
  {/if}
</div>

<style>
  .center { display: grid; place-items: center; padding: 40px; color: var(--accent); }

  .kpis { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
  @media (min-width: 620px) { .kpis { grid-template-columns: repeat(4, 1fr); } }
  .kpi { padding: 13px 14px; display: flex; flex-direction: column; gap: 3px; font-size: 12px; }
  .kpi .val { font-size: 17px; font-weight: 800; letter-spacing: -0.4px; }
  .kpi.accent {
    background: var(--grad-soft);
    border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  }
  .kpi.accent .val { font-size: 20px; }

  .pie-row { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
  .legend { flex: 1; min-width: 180px; display: flex; flex-direction: column; gap: 7px; }
  .leg { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .swatch { width: 11px; height: 11px; border-radius: 4px; flex-shrink: 0; }

  .section-title { display: flex; align-items: center; gap: 6px; }
  .right { display: flex; flex-direction: column; align-items: flex-end; }
</style>
