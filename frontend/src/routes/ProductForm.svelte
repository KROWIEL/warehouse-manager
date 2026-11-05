<script>
  import { createEventDispatcher } from 'svelte'
  import { Check, Loader2, Plus, ScanLine, X } from 'lucide-svelte'
  import { api } from '../lib/api.js'
  import { parseNum } from '../lib/format.js'
  import { catalog, refreshCatalog, toast } from '../lib/stores.js'
  import Modal from '../components/Modal.svelte'
  import Scanner from '../components/Scanner.svelte'

  export let product = null

  const dispatch = createEventDispatcher()
  const isNew = !product

  let name = product?.name ?? ''
  let categoryId = product?.category_id ?? $catalog.categories[0]?.id ?? null
  let subcategoryId = product?.subcategory_id ?? null
  let supplierId = product?.supplier_id ?? $catalog.suppliers[0]?.id ?? null
  let price = product ? String(product.price) : ''
  let barcode = product?.barcode ?? ''
  let minStock = product ? String(product.min_stock) : '0'
  let note = product?.note ?? ''
  let initialQty = ''

  // Значения настраиваемых полей: { [attribute_id]: 'значение' }
  let values = {}
  if (product) {
    for (const a of product.attributes) values[a.attribute_id] = a.value
  }

  let scanning = false
  let busy = false
  let error = ''
  let newSub = null // строка ввода новой подкатегории; null — поле скрыто
  let newOption = null // { attributeId, value }

  $: category = $catalog.categories.find((c) => c.id === categoryId) || null
  $: attributes = category?.attributes ?? []
  $: subcategories = category?.subcategories ?? []

  function onCategoryChange() {
    // У другой категории свой набор полей, старые значения к ней не относятся.
    subcategoryId = null
    values = {}
    newSub = null
    newOption = null
  }

  async function addSubcategory() {
    const value = (newSub || '').trim()
    if (!value) {
      newSub = null
      return
    }
    try {
      const created = await api.post('/catalog/subcategories', {
        category_id: categoryId,
        name: value
      })
      await refreshCatalog()
      subcategoryId = created.id
      newSub = null
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  async function addOption() {
    const value = (newOption?.value || '').trim()
    if (!value) {
      newOption = null
      return
    }
    try {
      const created = await api.post(`/catalog/attributes/${newOption.attributeId}/options`, {
        value
      })
      await refreshCatalog()
      values = { ...values, [newOption.attributeId]: created.value }
      newOption = null
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  async function save() {
    error = ''
    const parsedPrice = parseNum(price || '0')
    const parsedMin = parseNum(minStock || '0')
    const parsedQty = parseNum(initialQty || '0')

    if (!name.trim()) return (error = 'Укажите название товара')
    if (!categoryId) return (error = 'Сначала создайте категорию в настройках')
    if (!supplierId) return (error = 'Сначала добавьте поставщика в настройках')
    if (!Number.isFinite(parsedPrice) || parsedPrice < 0) return (error = 'Цена указана неверно')
    if (!Number.isFinite(parsedMin) || parsedMin < 0) return (error = 'Минимум указан неверно')
    if (!Number.isFinite(parsedQty) || parsedQty < 0) return (error = 'Количество указано неверно')

    const body = {
      name,
      category_id: categoryId,
      subcategory_id: subcategoryId || null,
      supplier_id: supplierId,
      price: parsedPrice,
      barcode: barcode.trim() || null,
      min_stock: parsedMin,
      note,
      attributes: values,
      initial_qty: isNew ? parsedQty : 0
    }

    busy = true
    try {
      if (isNew) await api.post('/products', body)
      else await api.patch(`/products/${product.id}`, body)
      toast(isNew ? 'Товар добавлен' : 'Изменения сохранены', 'success')
      dispatch('saved')
    } catch (e) {
      error = e.message
    } finally {
      busy = false
    }
  }
</script>

{#if scanning}
  <Scanner
    on:detect={(e) => {
      barcode = e.detail
      scanning = false
    }}
    on:close={() => (scanning = false)}
  />
{/if}

<Modal title={isNew ? 'Новый товар' : 'Товар'} on:close={() => dispatch('close')}>
  <form class="stack" on:submit|preventDefault={save}>
    <div class="field">
      <label for="pname">Название</label>
      <input id="pname" bind:value={name} placeholder="Майка Rick and Morty" />
    </div>

    <div class="field">
      <label for="pcat">Категория</label>
      <select id="pcat" bind:value={categoryId} on:change={onCategoryChange}>
        {#each $catalog.categories as c}
          <option value={c.id}>{c.name}</option>
        {/each}
      </select>
    </div>

    <div class="field">
      <label for="psub">Подкатегория</label>
      <div class="row">
        <select id="psub" bind:value={subcategoryId} class="grow">
          <option value={null}>Без подкатегории</option>
          {#each subcategories as s}
            <option value={s.id}>{s.name}</option>
          {/each}
        </select>
        <button
          class="btn btn-icon"
          type="button"
          on:click={() => (newSub = newSub === null ? '' : null)}
          aria-label="Новая подкатегория"
        >
          {#if newSub === null}<Plus size={18} />{:else}<X size={18} />{/if}
        </button>
      </div>
      {#if newSub !== null}
        <div class="row">
          <input bind:value={newSub} placeholder="Название подкатегории" class="grow" />
          <button class="btn btn-primary btn-icon" type="button" on:click={addSubcategory} aria-label="Создать">
            <Check size={18} />
          </button>
        </div>
      {/if}
    </div>

    <div class="field">
      <label for="psup">Поставщик</label>
      <select id="psup" bind:value={supplierId}>
        {#each $catalog.suppliers as s}
          <option value={s.id}>{s.name}</option>
        {/each}
      </select>
    </div>

    {#each attributes as attr (attr.id)}
      <div class="field">
        <label for={`attr-${attr.id}`}>
          {attr.name}{#if attr.required}<span class="neg"> *</span>{/if}
        </label>
        {#if attr.kind === 'select'}
          <div class="row">
            <select id={`attr-${attr.id}`} bind:value={values[attr.id]} class="grow">
              <option value={undefined}>Не указано</option>
              {#each attr.options as o}
                <option value={o.value}>{o.value}</option>
              {/each}
            </select>
            <button
              class="btn btn-icon"
              type="button"
              on:click={() =>
                (newOption = newOption?.attributeId === attr.id ? null : { attributeId: attr.id, value: '' })}
              aria-label="Новый вариант"
            >
              {#if newOption?.attributeId === attr.id}<X size={18} />{:else}<Plus size={18} />{/if}
            </button>
          </div>
          {#if newOption?.attributeId === attr.id}
            <div class="row">
              <input bind:value={newOption.value} placeholder={`Новое значение «${attr.name}»`} class="grow" />
              <button class="btn btn-primary btn-icon" type="button" on:click={addOption} aria-label="Добавить">
                <Check size={18} />
              </button>
            </div>
          {/if}
        {:else}
          <input id={`attr-${attr.id}`} bind:value={values[attr.id]} placeholder={attr.name} />
        {/if}
      </div>
    {/each}

    <div class="grid-2">
      <div class="field">
        <label for="pprice">Цена, Br</label>
        <input id="pprice" bind:value={price} inputmode="decimal" placeholder="0" />
      </div>
      <div class="field">
        <label for="pmin">Минимум на складе</label>
        <input id="pmin" bind:value={minStock} inputmode="decimal" placeholder="0" />
      </div>
    </div>

    {#if isNew}
      <div class="field">
        <label for="pqty">Сколько сейчас на складе</label>
        <input id="pqty" bind:value={initialQty} inputmode="decimal" placeholder="0" />
      </div>
    {/if}

    <div class="field">
      <label for="pcode">Штрихкод</label>
      <div class="row">
        <input id="pcode" bind:value={barcode} inputmode="numeric" placeholder="необязательно" class="grow" />
        <button class="btn btn-icon" type="button" on:click={() => (scanning = true)} aria-label="Сканировать">
          <ScanLine size={18} />
        </button>
      </div>
    </div>

    <div class="field">
      <label for="pnote">Заметка</label>
      <input id="pnote" bind:value={note} placeholder="необязательно" />
    </div>

    {#if error}<div class="error-box">{error}</div>{/if}

    <button class="btn btn-primary btn-block" type="submit" disabled={busy}>
      {#if busy}<Loader2 size={18} class="spin" />{/if}
      {isNew ? 'Добавить товар' : 'Сохранить'}
    </button>
  </form>
</Modal>
