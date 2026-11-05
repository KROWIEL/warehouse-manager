<script>
  import { onMount } from 'svelte'
  import { Loader2, Minus, Plus, Receipt, ScanLine, Search, ShoppingCart, X } from 'lucide-svelte'
  import { api, qs } from '../lib/api.js'
  import { fmtDate, fmtMoney, fmtQty, parseNum, pluralWord, todayISO } from '../lib/format.js'
  import { catalog, toast } from '../lib/stores.js'
  import Scanner from '../components/Scanner.svelte'
  import ReceiptSheet from './ReceiptSheet.svelte'

  const PAYMENTS = [
    { id: 'cash', label: 'Наличные' },
    { id: 'card', label: 'Карта' },
    { id: 'transfer', label: 'Перевод' }
  ]
  const QUICK_DISCOUNTS = [5, 10, 15, 20]

  let mode = 'cart'
  let search = ''
  let found = []
  let searching = false
  let scanning = false
  let timer

  // Витрина: список товаров с остатком. Открыта сразу, потому что продавать
  // тыканьем в список — основной способ, а поиск и сканер нужны, когда товаров
  // много. Прятать её за кнопку значило заставлять искать даже ради одного товара.
  let stockList = []
  let loadingStock = true
  let browseCategory = null

  // Позиция корзины: цена — строка, чтобы можно было стереть и вписать свою.
  let cart = []
  let discount = ''
  let payment = 'cash'
  let customer = ''
  let note = ''
  let occurred = todayISO()
  let busy = false
  let error = ''

  let receipts = []
  let loadingReceipts = false
  let openSale = null

  $: gross = cart.reduce((sum, line) => {
    const qty = parseNum(line.qty) || 0
    const price = line.price === '' ? line.product.price : parseNum(line.price) || 0
    return sum + qty * price
  }, 0)
  $: discountValue = Math.max(0, parseNum(discount || '0') || 0)
  $: total = Math.max(0, gross - discountValue)

  async function runSearch() {
    if (!search.trim()) {
      found = []
      return
    }
    searching = true
    const asked = search
    try {
      const rows = await api.get('/products' + qs({ search: asked, stock: 'in', limit: 30 }))
      // Ответы приходят не в том порядке, в котором ушли запросы: пока летел
      // ответ, строка поиска могла измениться или товар уже добавили в чек.
      if (asked === search) found = rows
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      searching = false
    }
  }

  function debounced() {
    clearTimeout(timer)
    timer = setTimeout(runSearch, 250)
  }

  async function loadStock() {
    loadingStock = true
    try {
      stockList = await api.get('/products' + qs({ stock: 'in', limit: 500 }))
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      loadingStock = false
    }
  }

  // Есть поиск — показываем найденное, нет — всю витрину.
  $: browseList = browseCategory
    ? stockList.filter((p) => p.category_id === browseCategory)
    : stockList
  $: shown = search.trim() ? found : browseList
  $: inCart = new Map(cart.map((line) => [line.product.id, parseNum(line.qty) || 0]))

  function add(product) {
    const existing = cart.find((l) => l.product.id === product.id)
    if (existing) {
      const next = (parseNum(existing.qty) || 0) + 1
      if (next > product.stock) {
        toast(`На складе только ${fmtQty(product.stock)}`, 'error')
        return
      }
      existing.qty = String(next)
      cart = cart
    } else {
      cart = [...cart, { product, qty: '1', price: '' }]
    }
    search = ''
    found = []
  }

  function step(line, delta) {
    const next = (parseNum(line.qty) || 0) + delta
    if (next <= 0) {
      cart = cart.filter((l) => l !== line)
      return
    }
    if (next > line.product.stock) {
      toast(`На складе только ${fmtQty(line.product.stock)}`, 'error')
      return
    }
    line.qty = String(next)
    cart = cart
  }

  async function onScan(code) {
    scanning = false
    try {
      const product = await api.get(`/products/by-barcode/${encodeURIComponent(code)}`)
      if (product.stock <= 0) {
        toast(`«${product.name}» закончился на складе`, 'error')
        return
      }
      add(product)
    } catch {
      toast('Товар с таким кодом не найден', 'error')
    }
  }

  async function checkout() {
    error = ''
    if (!cart.length) return
    for (const line of cart) {
      const qty = parseNum(line.qty)
      if (!Number.isFinite(qty) || qty <= 0) return (error = `Количество «${line.product.name}» неверное`)
      if (line.price !== '' && !Number.isFinite(parseNum(line.price)))
        return (error = `Цена «${line.product.name}» неверная`)
    }
    if (discountValue > gross) return (error = 'Скидка больше суммы чека')

    busy = true
    try {
      const res = await api.post('/sales', {
        items: cart.map((line) => ({
          product_id: line.product.id,
          qty: parseNum(line.qty),
          unit_price: line.price === '' ? null : parseNum(line.price)
        })),
        discount: discountValue,
        payment_method: payment,
        customer,
        note,
        occurred_at: occurred
      })
      toast(`Продано на ${fmtMoney(res.total)}`, 'success')
      cart = []
      discount = ''
      customer = ''
      note = ''
      occurred = todayISO()
      if (receipts.length || mode === 'receipts') loadReceipts()
      // Остатки в витрине после продажи уже другие.
      loadStock()
    } catch (e) {
      error = e.message
    } finally {
      busy = false
    }
  }

  async function loadReceipts() {
    loadingReceipts = true
    try {
      receipts = await api.get('/sales' + qs({ limit: 60 }))
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      loadingReceipts = false
    }
  }

  function switchMode(next) {
    mode = next
    if (next === 'receipts' && !receipts.length) loadReceipts()
  }

  onMount(() => {
    loadStock()
    // Чеки подгружаем сразу: возврат ищут чаще, чем листают историю.
    loadReceipts()
  })
</script>

{#if scanning}
  <Scanner on:detect={(e) => onScan(e.detail)} on:close={() => (scanning = false)} />
{/if}

{#if openSale}
  <ReceiptSheet
    sale={openSale}
    on:close={() => (openSale = null)}
    on:changed={loadReceipts}
  />
{/if}

<div class="stack">
  <div class="segmented" style="align-self:center">
    <button class:active={mode === 'cart'} on:click={() => switchMode('cart')}>
      <ShoppingCart size={15} /> Продажа
      {#if cart.length}<span class="count">{cart.length}</span>{/if}
    </button>
    <button class:active={mode === 'receipts'} on:click={() => switchMode('receipts')}>
      <Receipt size={15} /> Чеки
    </button>
  </div>

  {#if mode === 'cart'}
    <div class="search-row">
      <div class="search">
        <Search size={17} class="ico" />
        <input bind:value={search} on:input={debounced} placeholder="Найти товар" />
        {#if searching}<Loader2 size={16} class="spin tail" />{/if}
      </div>
      <button class="btn btn-icon" on:click={() => (scanning = true)} aria-label="Сканировать">
        <ScanLine size={19} />
      </button>
    </div>

    {#if !search.trim() && $catalog.categories.length > 1}
      <div class="segmented">
        <button class:active={browseCategory === null} on:click={() => (browseCategory = null)}>
          Все
        </button>
        {#each $catalog.categories as c}
          <button class:active={browseCategory === c.id} on:click={() => (browseCategory = c.id)}>
            {c.name}
          </button>
        {/each}
      </div>
    {/if}

    {#if loadingStock && !search.trim()}
      <div class="center"><Loader2 size={22} class="spin" /></div>
    {:else if shown.length}
      <div class="card pad stack-sm fade-up hits">
        {#each shown as p (p.id)}
          <button class="hit" on:click={() => add(p)}>
            <span class="tag" style="background:{p.category_color}"></span>
            <div class="grow" style="text-align:left">
              <div class="ellipsis" style="font-size:14px;font-weight:600">{p.name}</div>
              <div class="faint" style="font-size:12px">
                {p.attributes.map((a) => a.value).join(' · ') || p.category_name} · осталось {fmtQty(p.stock)}
              </div>
            </div>
            {#if inCart.has(p.id)}
              <span class="badge badge-pos">{fmtQty(inCart.get(p.id))} в чеке</span>
            {/if}
            <span class="mono" style="font-weight:700">{fmtMoney(p.price)}</span>
          </button>
        {/each}
      </div>
    {:else if search.trim() && !searching}
      <div class="card pad faint" style="font-size:13px">
        Ничего не нашлось. Очистите поиск, чтобы выбрать товар из списка
      </div>
    {:else if !search.trim()}
      <div class="card pad faint" style="font-size:13px">
        {browseCategory ? 'В этой категории нет товаров с остатком' : 'На складе пока нет остатков'}
      </div>
    {/if}

    {#if cart.length}
      <div class="stack-sm">
        {#each cart as line (line.product.id)}
          <div class="card pad line">
            <div class="between">
              <div class="grow">
                <div class="ellipsis" style="font-size:14px;font-weight:650">{line.product.name}</div>
                <div class="faint" style="font-size:12px">осталось {fmtQty(line.product.stock)}</div>
              </div>
              <button
                class="btn btn-ghost btn-icon"
                on:click={() => (cart = cart.filter((l) => l !== line))}
                aria-label="Убрать"
              >
                <X size={16} />
              </button>
            </div>
            <div class="controls">
              <div class="stepper">
                <button on:click={() => step(line, -1)} aria-label="Меньше"><Minus size={15} /></button>
                <input bind:value={line.qty} inputmode="decimal" />
                <button on:click={() => step(line, 1)} aria-label="Больше"><Plus size={15} /></button>
              </div>
              <div class="field grow">
                <input
                  bind:value={line.price}
                  inputmode="decimal"
                  placeholder={`Цена ${fmtQty(line.product.price)}`}
                />
              </div>
              <span class="mono sum">
                {fmtMoney(
                  (parseNum(line.qty) || 0) *
                    (line.price === '' ? line.product.price : parseNum(line.price) || 0)
                )}
              </span>
            </div>
          </div>
        {/each}
      </div>

      <section class="card pad stack-sm">
        <h3 class="section-title">Оплата</h3>
        <div class="segmented" style="width:100%">
          {#each PAYMENTS as p}
            <button style="flex:1" class:active={payment === p.id} on:click={() => (payment = p.id)}>
              {p.label}
            </button>
          {/each}
        </div>

        <div class="field">
          <span class="lbl">Скидка на чек, Br</span>
          <input bind:value={discount} inputmode="decimal" placeholder="0" />
          <div class="chips">
            {#each QUICK_DISCOUNTS as percent}
              <button class="chip" on:click={() => (discount = (gross * percent / 100).toFixed(2))}>
                −{percent}%
              </button>
            {/each}
            {#if discountValue > 0}
              <button class="chip" on:click={() => (discount = '')}>Убрать</button>
            {/if}
          </div>
        </div>

        <div class="grid-2">
          <div class="field">
            <label for="cust">Покупатель</label>
            <input id="cust" bind:value={customer} placeholder="необязательно" />
          </div>
          <div class="field">
            <label for="sdate">Дата</label>
            <input id="sdate" type="date" bind:value={occurred} />
          </div>
        </div>
        <div class="field">
          <label for="snote">Комментарий</label>
          <input id="snote" bind:value={note} placeholder="необязательно" />
        </div>
      </section>

      {#if error}<div class="error-box">{error}</div>{/if}

      <div class="card pad checkout">
        <div class="between">
          <span class="faint" style="font-size:13px">
            {pluralWord(cart.length, 'позиция', 'позиции', 'позиций')}
            {#if discountValue > 0}· скидка {fmtMoney(discountValue)}{/if}
          </span>
          <span class="mono grand">{fmtMoney(total)}</span>
        </div>
        <button class="btn btn-primary btn-block" on:click={checkout} disabled={busy}>
          {#if busy}<Loader2 size={18} class="spin" />{/if}
          Провести продажу
        </button>
      </div>
    {/if}
  {:else if loadingReceipts}
    <div class="center"><Loader2 size={26} class="spin" /></div>
  {:else if !receipts.length}
    <div class="card empty">
      <Receipt size={30} />
      <span>Продаж ещё не было</span>
    </div>
  {:else}
    <div class="stack-sm">
      {#each receipts as sale (sale.id)}
        <button class="card receipt" on:click={() => (openSale = sale)}>
          <div class="grow" style="text-align:left">
            <div style="font-size:14px;font-weight:650">
              {fmtDate(sale.occurred_at)} · №{sale.id}
            </div>
            <div class="faint ellipsis" style="font-size:12px">
              {sale.items.map((i) => i.product_name).join(', ')}
            </div>
          </div>
          <div class="right">
            <span class="mono" style="font-size:15px;font-weight:800">{fmtMoney(sale.total)}</span>
            <span class="badge">{sale.payment_label}</span>
          </div>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .count {
    background: rgba(255, 255, 255, 0.28); border-radius: 999px;
    padding: 0 6px; font-size: 11px; margin-left: 2px;
  }
  .search-row { display: flex; gap: 8px; }
  .search { position: relative; flex: 1; min-width: 0; }
  .search :global(.ico) {
    position: absolute; left: 13px; top: 50%; transform: translateY(-50%);
    color: var(--text-faint); pointer-events: none;
  }
  .search input { padding-left: 38px; }
  .search :global(.tail) {
    position: absolute; right: 13px; top: 50%; margin-top: -8px; color: var(--accent);
  }

  /* Витрина может быть длинной — прокручиваем её, а не всю страницу с корзиной. */
  .hits { max-height: 46vh; overflow-y: auto; }

  .hit {
    display: flex; align-items: center; gap: 10px;
    background: none; border: none; padding: 6px 0; width: 100%;
  }
  .tag { width: 4px; align-self: stretch; min-height: 32px; border-radius: 999px; flex-shrink: 0; }

  .center { display: grid; place-items: center; padding: 40px; color: var(--accent); }

  .line { display: flex; flex-direction: column; gap: 10px; }
  .controls { display: flex; align-items: center; gap: 8px; }
  .stepper {
    display: flex; align-items: center; flex-shrink: 0;
    border: 1px solid var(--border); border-radius: 999px;
    background: var(--surface-strong); overflow: hidden;
  }
  .stepper button {
    width: 34px; height: 38px; border: none; background: none;
    display: grid; place-items: center; color: var(--text-dim);
  }
  .stepper button:active { background: var(--surface); }
  .stepper input {
    width: 46px; text-align: center; border: none; background: none;
    padding: 0; border-radius: 0; font-weight: 700;
  }
  .stepper input:focus { box-shadow: none; }
  .controls .field input { padding: 10px 12px; font-size: 15px; }
  .sum { font-size: 14px; font-weight: 700; flex-shrink: 0; min-width: 74px; text-align: right; }

  .checkout { display: flex; flex-direction: column; gap: 12px; }
  .grand { font-size: 24px; font-weight: 800; letter-spacing: -0.6px; }

  .receipt { display: flex; align-items: center; gap: 12px; padding: 11px 13px; width: 100%; }
  .right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
</style>
