<script>
  import { onMount } from 'svelte'
  import { Loader2, Plus, ScanLine, Search, SlidersHorizontal, PackageX } from 'lucide-svelte'
  import { api, qs } from '../lib/api.js'
  import { fmtMoney, fmtQty, pluralWord } from '../lib/format.js'
  import { catalog, toast } from '../lib/stores.js'
  import Icon from '../components/Icon.svelte'
  import Scanner from '../components/Scanner.svelte'
  import ProductForm from './ProductForm.svelte'
  import ProductSheet from './ProductSheet.svelte'

  const STOCK_FILTERS = [
    { id: null, label: 'Все' },
    { id: 'in', label: 'Есть' },
    { id: 'low', label: 'Мало' },
    { id: 'out', label: 'Нет' },
    { id: 'dead', label: 'Не продаётся' }
  ]

  let items = []
  let loading = true
  let search = ''
  let categoryId = null
  let subcategoryId = null
  let supplierId = null
  let stockFilter = null
  let archived = false
  let showFilters = false

  let scanning = false
  let editing = null // { product } | { product: null } для нового
  let openId = null
  let timer

  $: category = $catalog.categories.find((c) => c.id === categoryId) || null
  $: activeFilters =
    (subcategoryId ? 1 : 0) + (supplierId ? 1 : 0) + (stockFilter ? 1 : 0) + (archived ? 1 : 0)

  async function load() {
    loading = true
    try {
      items = await api.get(
        '/products' +
          qs({
            search,
            category_id: categoryId,
            subcategory_id: subcategoryId,
            supplier_id: supplierId,
            stock: stockFilter,
            archived,
            limit: 500
          })
      )
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      loading = false
    }
  }

  onMount(load)

  function debounced() {
    clearTimeout(timer)
    timer = setTimeout(load, 250)
  }

  function pickCategory(id) {
    categoryId = id
    subcategoryId = null
    load()
  }

  async function onScan(code) {
    scanning = false
    try {
      const found = await api.get(`/products/by-barcode/${encodeURIComponent(code)}`)
      openId = found.id
    } catch {
      // Кода нет в базе — подставляем его в поиск, чтобы было видно, что искали.
      search = code
      await load()
      toast('Товар с таким кодом не найден', 'error')
    }
  }

  function attrsLine(product) {
    return product.attributes.map((a) => a.value).join(' · ')
  }
</script>

{#if scanning}
  <Scanner on:detect={(e) => onScan(e.detail)} on:close={() => (scanning = false)} />
{/if}

{#if editing}
  <ProductForm
    product={editing.product}
    on:close={() => (editing = null)}
    on:saved={() => {
      editing = null
      load()
    }}
  />
{/if}

{#if openId}
  <ProductSheet
    productId={openId}
    on:close={() => (openId = null)}
    on:changed={load}
    on:edit={(e) => {
      openId = null
      editing = { product: e.detail }
    }}
  />
{/if}

<div class="stack">
  <div class="search-row">
    <div class="search">
      <Search size={17} class="ico" />
      <input bind:value={search} on:input={debounced} placeholder="Название, код, надпись…" />
    </div>
    <button class="btn btn-icon" on:click={() => (scanning = true)} aria-label="Сканировать">
      <ScanLine size={19} />
    </button>
    <button
      class="btn btn-icon"
      class:has={activeFilters > 0}
      on:click={() => (showFilters = !showFilters)}
      aria-label="Фильтры"
    >
      <SlidersHorizontal size={19} />
      {#if activeFilters}<span class="dot">{activeFilters}</span>{/if}
    </button>
  </div>

  <div class="segmented">
    <button class:active={categoryId === null} on:click={() => pickCategory(null)}>Все</button>
    {#each $catalog.categories as c}
      <button class:active={categoryId === c.id} on:click={() => pickCategory(c.id)}>{c.name}</button>
    {/each}
  </div>

  {#if showFilters}
    <section class="card pad stack-sm fade-up">
      {#if category && category.subcategories.length}
        <div class="field">
          <span class="lbl">Подкатегория</span>
          <select bind:value={subcategoryId} on:change={load}>
            <option value={null}>Любая</option>
            {#each category.subcategories as s}
              <option value={s.id}>{s.name}</option>
            {/each}
          </select>
        </div>
      {/if}
      <div class="field">
        <span class="lbl">Поставщик</span>
        <select bind:value={supplierId} on:change={load}>
          <option value={null}>Любой</option>
          {#each $catalog.suppliers as s}
            <option value={s.id}>{s.name}</option>
          {/each}
        </select>
      </div>
      <div class="field">
        <span class="lbl">Остаток</span>
        <div class="chips">
          {#each STOCK_FILTERS as f}
            <button
              class="chip"
              class:active={stockFilter === f.id}
              on:click={() => {
                stockFilter = f.id
                load()
              }}
            >
              {f.label}
            </button>
          {/each}
        </div>
      </div>
      <button
        class="chip"
        class:active={archived}
        style="align-self:flex-start"
        on:click={() => {
          archived = !archived
          load()
        }}
      >
        Показать архив
      </button>
    </section>
  {/if}

  {#if loading}
    <div class="center"><Loader2 size={26} class="spin" /></div>
  {:else if !items.length}
    <div class="card empty">
      <PackageX size={30} />
      {#if $catalog.categories.length === 0 || $catalog.suppliers.length === 0}
        <span>Сначала создайте категорию и поставщика во вкладке «Настройки»</span>
      {:else if search || activeFilters}
        <span>Ничего не нашлось. Попробуйте изменить условия</span>
      {:else}
        <span>Склад пустой. Добавьте первый товар</span>
      {/if}
    </div>
  {:else}
    <p class="faint" style="font-size:12px;margin-left:4px">
      {pluralWord(items.length, 'товар', 'товара', 'товаров')}
    </p>
    <div class="stack-sm">
      {#each items as p (p.id)}
        <button class="card item" on:click={() => (openId = p.id)}>
          <div class="icon-badge" style="background:{p.category_color}">
            <Icon name={p.category_icon} size={20} />
          </div>
          <div class="grow" style="text-align:left">
            <div class="name ellipsis">{p.name}</div>
            <div class="faint ellipsis" style="font-size:12px">
              {attrsLine(p) || p.category_name} · {p.supplier_name}
            </div>
          </div>
          <div class="right">
            <span class="mono price">{fmtMoney(p.price)}</span>
            <span
              class="badge"
              class:badge-neg={p.stock <= 0}
              class:badge-warn={p.stock > 0 && p.low_stock}
              class:badge-pos={p.stock > 0 && !p.low_stock}
            >
              {fmtQty(p.stock)} шт
            </span>
          </div>
        </button>
      {/each}
    </div>
  {/if}
</div>

<button
  class="fab"
  on:click={() => (editing = { product: null })}
  disabled={!$catalog.categories.length || !$catalog.suppliers.length}
  aria-label="Добавить товар"
>
  <Plus size={24} />
</button>

<style>
  .search-row { display: flex; gap: 8px; }
  .search { position: relative; flex: 1; min-width: 0; }
  .search :global(.ico) {
    position: absolute; left: 13px; top: 50%; transform: translateY(-50%);
    color: var(--text-faint); pointer-events: none;
  }
  .search input { padding-left: 38px; }

  .btn-icon.has { border-color: var(--accent); color: var(--accent); position: relative; }
  .dot {
    position: absolute; top: -5px; right: -5px;
    min-width: 17px; height: 17px; border-radius: 999px;
    background: var(--grad); color: #fff;
    font-size: 10px; font-weight: 800;
    display: grid; place-items: center; padding: 0 4px;
  }

  .center { display: grid; place-items: center; padding: 40px; color: var(--accent); }

  .item {
    display: flex; align-items: center; gap: 12px;
    padding: 11px 13px; width: 100%;
    background: var(--surface); border: 1px solid var(--border);
    text-align: left;
    transition: transform var(--transition), border-color var(--transition);
  }
  .item:active { transform: scale(0.99); }
  .item:hover { border-color: var(--border-strong); }
  .name { font-size: 14px; font-weight: 650; }
  .right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
  .price { font-size: 14px; font-weight: 700; }

  .fab {
    position: fixed; right: 18px; z-index: 41;
    bottom: calc(104px + env(safe-area-inset-bottom));
    width: 56px; height: 56px; border-radius: 50%; border: none;
    background: var(--grad); color: #fff;
    display: grid; place-items: center;
    box-shadow: 0 14px 30px -10px var(--accent-glow);
    transition: transform var(--transition), opacity var(--transition);
  }
  .fab:active { transform: scale(0.94); }
  .fab:disabled { opacity: 0.4; }
</style>
