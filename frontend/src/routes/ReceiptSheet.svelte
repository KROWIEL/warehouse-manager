<script>
  import { createEventDispatcher } from 'svelte'
  import { Loader2, RotateCcw, Trash2, User } from 'lucide-svelte'
  import { api } from '../lib/api.js'
  import { fmtDateFull, fmtMoney, fmtQty, parseNum, todayISO } from '../lib/format.js'
  import { toast } from '../lib/stores.js'
  import Modal from '../components/Modal.svelte'

  export let sale

  const dispatch = createEventDispatcher()

  let returning = null // { item, qty, reason }
  let busy = false
  let error = ''

  $: gross = sale.items.reduce((s, i) => s + i.subtotal, 0)

  function startReturn(item) {
    error = ''
    returning = { item, qty: String(item.qty - item.returned), reason: '' }
  }

  async function submitReturn() {
    error = ''
    const qty = parseNum(returning.qty)
    if (!Number.isFinite(qty) || qty <= 0) return (error = 'Укажите количество')

    busy = true
    try {
      const res = await api.post('/sales/returns', {
        sale_item_id: returning.item.id,
        qty,
        reason: returning.reason,
        occurred_at: todayISO()
      })
      toast(`Возврат ${fmtMoney(res.refund)}`, 'success')
      returning = null
      dispatch('changed')
      dispatch('close')
    } catch (e) {
      error = e.message
    } finally {
      busy = false
    }
  }

  async function removeSale() {
    if (!confirm('Удалить чек целиком? Товар вернётся на склад.')) return
    try {
      await api.del(`/sales/${sale.id}`)
      toast('Чек удалён', 'success')
      dispatch('changed')
      dispatch('close')
    } catch (e) {
      toast(e.message, 'error')
    }
  }
</script>

<Modal title={`Чек №${sale.id}`} on:close={() => dispatch('close')}>
  <div class="stack">
    <div class="head">
      <div>
        <div style="font-weight:700">{fmtDateFull(sale.occurred_at)}</div>
        <div class="faint" style="font-size:12px">
          {sale.payment_label}{#if sale.author} · {sale.author}{/if}
        </div>
      </div>
      <div class="mono" style="font-size:20px;font-weight:800">{fmtMoney(sale.total)}</div>
    </div>

    {#if sale.customer}
      <div class="row faint" style="font-size:13px">
        <User size={14} /> {sale.customer}
      </div>
    {/if}

    <div class="stack-sm">
      {#each sale.items as item (item.id)}
        <div class="line">
          <span class="tag" style="background:{item.category_color}"></span>
          <div class="grow">
            <div class="ellipsis" style="font-size:14px;font-weight:600">{item.product_name}</div>
            <div class="faint" style="font-size:12px">
              {fmtQty(item.qty)} × {fmtMoney(item.unit_price)}
              {#if item.returned > 0}
                <span class="neg">· возвращено {fmtQty(item.returned)}</span>
              {/if}
            </div>
          </div>
          <span class="mono" style="font-weight:700">{fmtMoney(item.subtotal)}</span>
          {#if item.returned < item.qty}
            <button class="btn btn-ghost btn-icon" on:click={() => startReturn(item)} aria-label="Возврат">
              <RotateCcw size={15} />
            </button>
          {/if}
        </div>
      {/each}
    </div>

    <div class="totals">
      <div class="between"><span class="faint">Сумма позиций</span><span class="mono">{fmtMoney(gross)}</span></div>
      {#if sale.discount > 0}
        <div class="between">
          <span class="faint">Скидка</span><span class="mono neg">−{fmtMoney(sale.discount)}</span>
        </div>
      {/if}
      <div class="between" style="font-weight:800">
        <span>Итого</span><span class="mono">{fmtMoney(sale.total)}</span>
      </div>
    </div>

    {#if sale.note}
      <p class="faint" style="font-size:13px">{sale.note}</p>
    {/if}

    {#if returning}
      <section class="card pad stack-sm fade-up">
        <h3 class="section-title">Возврат «{returning.item.product_name}»</h3>
        <div class="grid-2">
          <div class="field">
            <label for="rqty">Сколько вернуть</label>
            <input id="rqty" bind:value={returning.qty} inputmode="decimal" />
          </div>
          <div class="field">
            <label for="rreason">Причина</label>
            <input id="rreason" bind:value={returning.reason} placeholder="необязательно" />
          </div>
        </div>
        {#if error}<div class="error-box">{error}</div>{/if}
        <div class="row" style="gap:8px">
          <button class="btn grow" on:click={() => (returning = null)}>Отмена</button>
          <button class="btn btn-primary grow" on:click={submitReturn} disabled={busy}>
            {#if busy}<Loader2 size={16} class="spin" />{/if}
            Вернуть
          </button>
        </div>
      </section>
    {:else}
      <button class="btn btn-danger btn-block" on:click={removeSale}>
        <Trash2 size={16} /> Удалить чек
      </button>
    {/if}
  </div>
</Modal>

<style>
  .head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .line { display: flex; align-items: center; gap: 10px; }
  .tag { width: 4px; align-self: stretch; min-height: 34px; border-radius: 999px; flex-shrink: 0; }
  .totals {
    display: flex; flex-direction: column; gap: 6px; font-size: 14px;
    border-top: 1px solid var(--border); padding-top: 12px;
  }
</style>
