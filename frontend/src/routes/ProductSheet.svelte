<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import {
    Loader2, PackagePlus, PackageMinus, ClipboardCheck, Pencil, Trash2, Barcode
  } from 'lucide-svelte'
  import { api } from '../lib/api.js'
  import { fmtMoney, fmtQty, parseNum, todayISO } from '../lib/format.js'
  import { toast } from '../lib/stores.js'
  import Icon from '../components/Icon.svelte'
  import Modal from '../components/Modal.svelte'

  export let productId

  const dispatch = createEventDispatcher()

  const OPS = [
    { kind: 'receipt', label: 'Приход', icon: PackagePlus, hint: 'Сколько поступило' },
    { kind: 'writeoff', label: 'Списание', icon: PackageMinus, hint: 'Сколько списать' },
    { kind: 'adjust', label: 'Пересчёт', icon: ClipboardCheck, hint: 'Сколько лежит фактически' }
  ]

  let product = null
  let loading = true
  let op = 'receipt'
  let qty = ''
  let reason = ''
  let occurred = todayISO()
  let busy = false
  let error = ''

  $: current = OPS.find((o) => o.kind === op)

  async function load() {
    try {
      product = await api.get(`/products/${productId}`)
    } catch (e) {
      toast(e.message, 'error')
      dispatch('close')
    } finally {
      loading = false
    }
  }

  onMount(load)

  async function apply() {
    error = ''
    const value = parseNum(qty)
    if (!Number.isFinite(value) || value < 0) return (error = 'Укажите количество')
    if (op !== 'adjust' && value <= 0) return (error = 'Количество должно быть больше нуля')

    busy = true
    try {
      const res = await api.post(`/products/${productId}/movements`, {
        kind: op,
        qty: value,
        reason,
        occurred_at: occurred
      })
      if (res.delta === 0) toast('Расхождений нет', 'info')
      else toast(`Остаток: ${fmtQty(res.stock)}`, 'success')
      qty = ''
      reason = ''
      await load()
      dispatch('changed')
    } catch (e) {
      error = e.message
    } finally {
      busy = false
    }
  }

  async function undo(movement) {
    if (!confirm('Отменить эту операцию?')) return
    try {
      await api.del(`/products/${productId}/movements/${movement.id}`)
      await load()
      dispatch('changed')
      toast('Операция отменена', 'success')
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  async function remove() {
    if (!confirm(`Удалить «${product.name}»?`)) return
    try {
      const res = await api.del(`/products/${productId}`)
      toast(res.archived ? 'Товар убран в архив — он уже продавался' : 'Товар удалён', 'success')
      dispatch('changed')
      dispatch('close')
    } catch (e) {
      toast(e.message, 'error')
    }
  }
</script>

<Modal title="Карточка товара" on:close={() => dispatch('close')}>
  {#if loading}
    <div class="center"><Loader2 size={26} class="spin" /></div>
  {:else if product}
    <div class="stack">
      <div class="row">
        <div class="icon-badge" style="background:{product.category_color}">
          <Icon name={product.category_icon} size={21} />
        </div>
        <div class="grow">
          <div style="font-size:16px;font-weight:700">{product.name}</div>
          <div class="faint" style="font-size:12px">
            {product.category_name}{#if product.subcategory_name} · {product.subcategory_name}{/if}
          </div>
        </div>
        <div class="right">
          <div class="mono" style="font-size:16px;font-weight:800">{fmtMoney(product.price)}</div>
          <span
            class="badge"
            class:badge-neg={product.stock <= 0}
            class:badge-warn={product.stock > 0 && product.low_stock}
            class:badge-pos={product.stock > 0 && !product.low_stock}
          >
            {fmtQty(product.stock)} шт
          </span>
        </div>
      </div>

      <div class="props">
        <div class="prop"><span class="faint">Поставщик</span><span>{product.supplier_name}</span></div>
        {#each product.attributes as attr}
          <div class="prop"><span class="faint">{attr.name}</span><span>{attr.value}</span></div>
        {/each}
        {#if product.min_stock > 0}
          <div class="prop"><span class="faint">Минимум</span><span>{fmtQty(product.min_stock)} шт</span></div>
        {/if}
        {#if product.barcode}
          <div class="prop">
            <span class="faint">Штрихкод</span>
            <span class="mono row" style="gap:6px"><Barcode size={14} />{product.barcode}</span>
          </div>
        {/if}
        {#if product.note}
          <div class="prop"><span class="faint">Заметка</span><span>{product.note}</span></div>
        {/if}
      </div>

      <div>
        <h3 class="section-title">Операция со складом</h3>
        <div class="segmented" style="width:100%">
          {#each OPS as o}
            <button
              type="button"
              class:active={op === o.kind}
              style="flex:1"
              on:click={() => {
                op = o.kind
                error = ''
              }}
            >
              <svelte:component this={o.icon} size={15} />
              {o.label}
            </button>
          {/each}
        </div>

        <div class="stack-sm" style="margin-top:12px">
          <div class="grid-2">
            <div class="field">
              <label for="mqty">{current.hint}</label>
              <input id="mqty" bind:value={qty} inputmode="decimal" placeholder="0" />
            </div>
            <div class="field">
              <label for="mdate">Дата</label>
              <input id="mdate" type="date" bind:value={occurred} />
            </div>
          </div>
          <div class="field">
            <label for="mreason">Причина или комментарий</label>
            <input
              id="mreason"
              bind:value={reason}
              placeholder={op === 'writeoff' ? 'Брак, витрина, потеря…' : 'необязательно'}
            />
          </div>
          {#if error}<div class="error-box">{error}</div>{/if}
          <button class="btn btn-primary btn-block" on:click={apply} disabled={busy}>
            {#if busy}<Loader2 size={18} class="spin" />{/if}
            {current.label}
          </button>
        </div>
      </div>

      {#if product.history.length}
        <div>
          <h3 class="section-title">История движений</h3>
          <div class="stack-sm">
            {#each product.history as h (h.id)}
              <div class="hist">
                <span class="mono qty" class:pos={h.qty > 0} class:neg={h.qty < 0}>
                  {h.qty > 0 ? '+' : ''}{fmtQty(h.qty)}
                </span>
                <div class="grow">
                  <div style="font-size:13px;font-weight:600">{h.label}</div>
                  <div class="faint" style="font-size:11px">
                    {h.occurred_at}{#if h.author} · {h.author}{/if}{#if h.reason} · {h.reason}{/if}
                  </div>
                </div>
                {#if !h.sale_id}
                  <button class="btn btn-ghost btn-icon" on:click={() => undo(h)} aria-label="Отменить">
                    <Trash2 size={15} />
                  </button>
                {/if}
              </div>
            {/each}
          </div>
        </div>
      {/if}

      <div class="row" style="gap:8px">
        <button class="btn grow" on:click={() => dispatch('edit', product)}>
          <Pencil size={16} /> Изменить
        </button>
        <button class="btn btn-danger" on:click={remove} aria-label="Удалить">
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  {/if}
</Modal>

<style>
  .center { display: grid; place-items: center; padding: 30px; color: var(--accent); }
  .right { text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }

  .props {
    display: flex; flex-direction: column; gap: 7px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 12px 14px;
  }
  .prop { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
  .prop span:last-child { font-weight: 600; text-align: right; }

  .hist {
    display: flex; align-items: center; gap: 10px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 8px 10px;
  }
  .qty { font-size: 14px; font-weight: 800; min-width: 44px; }
</style>
