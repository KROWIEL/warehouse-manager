<script>
  import { createEventDispatcher } from 'svelte'
  import { Check, Loader2, Plus, Trash2, X } from 'lucide-svelte'
  import { api } from '../lib/api.js'
  import { catalog, refreshCatalog, toast } from '../lib/stores.js'
  import ColorPicker from '../components/ColorPicker.svelte'
  import IconPicker from '../components/IconPicker.svelte'
  import Modal from '../components/Modal.svelte'

  export let category = null

  const dispatch = createEventDispatcher()

  let id = category?.id ?? null
  let name = category?.name ?? ''
  let color = category?.color ?? '#0ea5e9'
  let icon = category?.icon ?? 'package'
  let busy = false
  let error = ''

  let newSub = ''
  let newAttr = { name: '', kind: 'select', required: false, options: '' }
  let optionDraft = {} // { [attributeId]: 'значение' }

  // Берём актуальную версию из стора: после каждой правки справочник
  // перезагружается, и списки внутри модалки обновляются сами.
  $: live = $catalog.categories.find((c) => c.id === id) || null

  async function saveCategory() {
    error = ''
    if (!name.trim()) return (error = 'Укажите название')
    busy = true
    try {
      if (id) {
        await api.patch(`/catalog/categories/${id}`, { name, color, icon })
      } else {
        const created = await api.post('/catalog/categories', { name, color, icon })
        // Не закрываем окно: сразу после создания категории обычно нужно
        // добавить её поля и подкатегории.
        id = created.id
      }
      await refreshCatalog()
      dispatch('saved')
      toast('Сохранено', 'success')
    } catch (e) {
      error = e.message
    } finally {
      busy = false
    }
  }

  async function act(fn, okMessage) {
    try {
      await fn()
      await refreshCatalog()
      dispatch('saved')
      if (okMessage) toast(okMessage, 'success')
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const addSub = () =>
    newSub.trim() &&
    act(async () => {
      await api.post('/catalog/subcategories', { category_id: id, name: newSub })
      newSub = ''
    })

  const removeSub = (sub) =>
    confirm(`Удалить подкатегорию «${sub.name}»?`) &&
    act(async () => {
      const res = await api.del(`/catalog/subcategories/${sub.id}`)
      toast(res.archived ? 'Убрано в архив — есть товары' : 'Удалено', 'success')
    })

  const addAttribute = () =>
    newAttr.name.trim() &&
    act(async () => {
      await api.post('/catalog/attributes', {
        category_id: id,
        name: newAttr.name,
        kind: newAttr.kind,
        required: newAttr.required,
        options: newAttr.options
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
      })
      newAttr = { name: '', kind: 'select', required: false, options: '' }
    })

  const toggleRequired = (attr) =>
    act(async () => {
      await api.patch(`/catalog/attributes/${attr.id}`, {
        name: attr.name,
        required: !attr.required
      })
    })

  const removeAttribute = (attr) =>
    confirm(`Удалить поле «${attr.name}»? Значения у товаров пропадут.`) &&
    act(async () => {
      const res = await api.del(`/catalog/attributes/${attr.id}`)
      toast(res.archived ? 'Убрано в архив — поле уже заполнено у товаров' : 'Удалено', 'success')
    })

  const addOption = (attr) =>
    (optionDraft[attr.id] || '').trim() &&
    act(async () => {
      await api.post(`/catalog/attributes/${attr.id}/options`, { value: optionDraft[attr.id] })
      optionDraft = { ...optionDraft, [attr.id]: '' }
    })

  const removeOption = (attr, option) =>
    act(async () => {
      await api.del(`/catalog/attributes/${attr.id}/options/${option.id}`)
    })

  async function removeCategory() {
    if (!confirm(`Удалить категорию «${name}»?`)) return
    try {
      const res = await api.del(`/catalog/categories/${id}`)
      toast(res.archived ? 'Категория убрана в архив — в ней есть товары' : 'Категория удалена', 'success')
      await refreshCatalog()
      dispatch('saved')
      dispatch('close')
    } catch (e) {
      toast(e.message, 'error')
    }
  }
</script>

<Modal title={id ? 'Категория' : 'Новая категория'} on:close={() => dispatch('close')}>
  <div class="stack">
    <div class="field">
      <label for="cname">Название</label>
      <input id="cname" bind:value={name} placeholder="Одежда" />
    </div>

    <div class="field">
      <span class="lbl">Цвет</span>
      <ColorPicker bind:value={color} />
    </div>

    <div class="field">
      <span class="lbl">Иконка</span>
      <IconPicker bind:value={icon} />
    </div>

    {#if error}<div class="error-box">{error}</div>{/if}

    <button class="btn btn-primary btn-block" on:click={saveCategory} disabled={busy}>
      {#if busy}<Loader2 size={18} class="spin" />{/if}
      {id ? 'Сохранить' : 'Создать категорию'}
    </button>

    {#if live}
      <div>
        <h3 class="section-title">Подкатегории</h3>
        <div class="stack-sm">
          {#each live.subcategories as sub (sub.id)}
            <div class="row-item">
              <span class="grow ellipsis">{sub.name}</span>
              <button class="btn btn-ghost btn-icon" on:click={() => removeSub(sub)} aria-label="Удалить">
                <Trash2 size={15} />
              </button>
            </div>
          {/each}
          <div class="row">
            <input bind:value={newSub} placeholder="Новая подкатегория" class="grow" />
            <button class="btn btn-icon" on:click={addSub} aria-label="Добавить"><Plus size={18} /></button>
          </div>
        </div>
      </div>

      <div>
        <h3 class="section-title">Поля товара в этой категории</h3>
        <div class="stack-sm">
          {#each live.attributes as attr (attr.id)}
            <div class="attr">
              <div class="between">
                <span style="font-weight:650">{attr.name}</span>
                <div class="row" style="gap:4px">
                  <button
                    class="chip"
                    class:active={attr.required}
                    on:click={() => toggleRequired(attr)}
                    title="Обязательное поле"
                  >
                    обязательное
                  </button>
                  <button class="btn btn-ghost btn-icon" on:click={() => removeAttribute(attr)} aria-label="Удалить">
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>

              {#if attr.kind === 'select'}
                <div class="chips">
                  {#each attr.options as o (o.id)}
                    <span class="chip">
                      {o.value}
                      <button class="x" on:click={() => removeOption(attr, o)} aria-label="Убрать">
                        <X size={12} />
                      </button>
                    </span>
                  {/each}
                </div>
                <div class="row">
                  <input
                    bind:value={optionDraft[attr.id]}
                    placeholder="Новый вариант"
                    class="grow small"
                  />
                  <button class="btn btn-icon" on:click={() => addOption(attr)} aria-label="Добавить">
                    <Plus size={16} />
                  </button>
                </div>
              {:else}
                <span class="faint" style="font-size:12px">Свободный текст</span>
              {/if}
            </div>
          {/each}

          <div class="attr new">
            <input bind:value={newAttr.name} placeholder="Название поля, например Размер" />
            <div class="segmented" style="width:100%">
              <button
                style="flex:1"
                class:active={newAttr.kind === 'select'}
                on:click={() => (newAttr.kind = 'select')}
              >
                Список вариантов
              </button>
              <button
                style="flex:1"
                class:active={newAttr.kind === 'text'}
                on:click={() => (newAttr.kind = 'text')}
              >
                Текст
              </button>
            </div>
            {#if newAttr.kind === 'select'}
              <input bind:value={newAttr.options} placeholder="Варианты через запятую: S, M, L" />
            {/if}
            <label class="check">
              <input type="checkbox" bind:checked={newAttr.required} />
              <span>Обязательное поле</span>
            </label>
            <button class="btn btn-block" on:click={addAttribute}>
              <Plus size={16} /> Добавить поле
            </button>
          </div>
        </div>
      </div>

      <button class="btn btn-danger btn-block" on:click={removeCategory}>
        <Trash2 size={16} /> Удалить категорию
      </button>
    {/if}
  </div>
</Modal>

<style>
  .row-item {
    display: flex; align-items: center; gap: 8px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 8px 12px; font-size: 14px;
  }
  .attr {
    display: flex; flex-direction: column; gap: 9px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 12px;
  }
  .attr.new { border-style: dashed; }
  .small { padding: 9px 12px; font-size: 15px; }
  .chip .x {
    display: grid; place-items: center;
    background: none; border: none; padding: 0; color: inherit; opacity: 0.6;
  }
  .chip .x:hover { opacity: 1; }
  .check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-dim); }
  .check input { width: 17px; height: 17px; accent-color: var(--accent); }
</style>
