<script>
  import { onMount } from 'svelte'
  import {
    Archive, Database, Download, KeyRound, Loader2, LogOut, Moon, Plus, Sun,
    Trash2, Undo2
  } from 'lucide-svelte'
  import { api, download } from '../lib/api.js'
  import { applyTheme, catalog, refreshCatalog, theme, toast, user } from '../lib/stores.js'
  import Avatar from '../components/Avatar.svelte'
  import AvatarPicker from '../components/AvatarPicker.svelte'
  import Icon from '../components/Icon.svelte'
  import Modal from '../components/Modal.svelte'
  import PasswordFields from '../components/PasswordFields.svelte'
  import CategoryForm from './CategoryForm.svelte'

  let displayName = ''
  let avatarKey = 'fox'
  let savingProfile = false

  let editingCategory = null // { category } | { category: null }
  let editingSupplier = null // { id, name, note } | { id: null, ... }
  let supplierBusy = false
  let supplierError = ''

  let passwordOpen = false
  let current = ''
  let next = ''
  let valid = false
  let passwordBusy = false
  let passwordError = ''

  let archive = null
  let loadingArchive = false
  let backupBusy = false

  $: if ($user && displayName === '') {
    displayName = $user.display_name
    avatarKey = $user.avatar
  }
  $: profileChanged =
    $user && (displayName.trim() !== $user.display_name || avatarKey !== $user.avatar)

  async function saveProfile() {
    if (!displayName.trim()) return toast('Имя не может быть пустым', 'error')
    savingProfile = true
    try {
      const me = await api.patch('/profile', { display_name: displayName, avatar: avatarKey })
      user.set(me)
      toast('Профиль обновлён', 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      savingProfile = false
    }
  }

  async function switchTheme() {
    const next = $theme === 'dark' ? 'light' : 'dark'
    applyTheme(next)
    try {
      const me = await api.patch('/profile', { theme: next })
      user.set(me)
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  async function changePassword() {
    if (!valid) return
    passwordError = ''
    passwordBusy = true
    try {
      await api.post('/profile/password', { current_password: current, new_password: next })
      toast('Пароль изменён', 'success')
      passwordOpen = false
      current = ''
      next = ''
    } catch (e) {
      passwordError = e.message
    } finally {
      passwordBusy = false
    }
  }

  async function saveSupplier() {
    supplierError = ''
    if (!editingSupplier.name.trim()) return (supplierError = 'Укажите название')
    supplierBusy = true
    try {
      const body = { name: editingSupplier.name, note: editingSupplier.note }
      if (editingSupplier.id) await api.patch(`/catalog/suppliers/${editingSupplier.id}`, body)
      else await api.post('/catalog/suppliers', body)
      await refreshCatalog()
      editingSupplier = null
      toast('Сохранено', 'success')
    } catch (e) {
      supplierError = e.message
    } finally {
      supplierBusy = false
    }
  }

  async function removeSupplier() {
    if (!confirm(`Удалить поставщика «${editingSupplier.name}»?`)) return
    try {
      const res = await api.del(`/catalog/suppliers/${editingSupplier.id}`)
      toast(res.archived ? 'Убран в архив — на нём есть товары' : 'Поставщик удалён', 'success')
      await refreshCatalog()
      editingSupplier = null
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  async function loadArchive() {
    loadingArchive = true
    try {
      const full = await api.get('/catalog?include_archived=true')
      const rows = []
      for (const c of full.categories) {
        if (c.archived) rows.push({ table: 'categories', id: c.id, label: `Категория «${c.name}»` })
        for (const s of c.subcategories) {
          if (s.archived)
            rows.push({ table: 'subcategories', id: s.id, label: `${c.name} → ${s.name}` })
        }
        for (const a of c.attributes) {
          if (a.archived)
            rows.push({ table: 'attributes', id: a.id, label: `Поле «${a.name}» в «${c.name}»` })
        }
      }
      for (const s of full.suppliers) {
        if (s.archived) rows.push({ table: 'suppliers', id: s.id, label: `Поставщик «${s.name}»` })
      }
      archive = rows
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      loadingArchive = false
    }
  }

  async function restore(row) {
    try {
      await api.post(`/catalog/${row.table}/${row.id}/restore`)
      await refreshCatalog()
      await loadArchive()
      toast('Восстановлено', 'success')
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  async function downloadBackup() {
    backupBusy = true
    try {
      await download('/backup', 'store-backup.db')
      toast('Копия базы скачана', 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      backupBusy = false
    }
  }

  async function logout() {
    try {
      await api.post('/auth/logout')
    } catch {
      /* сессия всё равно больше не нужна */
    }
    user.set(null)
  }

  onMount(loadArchive)
</script>

{#if editingCategory}
  <CategoryForm
    category={editingCategory.category}
    on:close={() => (editingCategory = null)}
    on:saved={loadArchive}
  />
{/if}

{#if editingSupplier}
  <Modal
    title={editingSupplier.id ? 'Поставщик' : 'Новый поставщик'}
    on:close={() => (editingSupplier = null)}
  >
    <div class="stack">
      <div class="field">
        <label for="sname">Название</label>
        <input id="sname" bind:value={editingSupplier.name} placeholder="ООО Ромашка" />
      </div>
      <div class="field">
        <label for="snote">Заметка</label>
        <input id="snote" bind:value={editingSupplier.note} placeholder="телефон, условия, что угодно" />
      </div>
      {#if supplierError}<div class="error-box">{supplierError}</div>{/if}
      <button class="btn btn-primary btn-block" on:click={saveSupplier} disabled={supplierBusy}>
        {#if supplierBusy}<Loader2 size={18} class="spin" />{/if}
        Сохранить
      </button>
      {#if editingSupplier.id}
        <button class="btn btn-danger btn-block" on:click={removeSupplier}>
          <Trash2 size={16} /> Удалить
        </button>
      {/if}
    </div>
  </Modal>
{/if}

{#if passwordOpen}
  <Modal title="Смена пароля" on:close={() => (passwordOpen = false)}>
    <div class="stack">
      <PasswordFields bind:current bind:next bind:valid />
      {#if passwordError}<div class="error-box">{passwordError}</div>{/if}
      <button class="btn btn-primary btn-block" on:click={changePassword} disabled={!valid || passwordBusy}>
        {#if passwordBusy}<Loader2 size={18} class="spin" />{/if}
        Сменить пароль
      </button>
    </div>
  </Modal>
{/if}

<div class="stack">
  <section class="card pad stack">
    <div class="row">
      <Avatar name={avatarKey} size={54} />
      <div class="grow">
        <div style="font-size:17px;font-weight:750">{$user?.display_name}</div>
        <div class="faint" style="font-size:13px">{$user?.username}</div>
      </div>
      <button class="btn btn-icon" on:click={switchTheme} aria-label="Тема">
        {#if $theme === 'dark'}<Sun size={18} />{:else}<Moon size={18} />{/if}
      </button>
    </div>

    <div class="field">
      <label for="dname">Как вас зовут</label>
      <input id="dname" bind:value={displayName} />
    </div>

    <div class="field">
      <span class="lbl">Аватар</span>
      <AvatarPicker bind:value={avatarKey} />
    </div>

    {#if profileChanged}
      <button class="btn btn-primary btn-block fade-up" on:click={saveProfile} disabled={savingProfile}>
        {#if savingProfile}<Loader2 size={18} class="spin" />{/if}
        Сохранить профиль
      </button>
    {/if}

    <div class="row" style="gap:8px">
      <button class="btn grow" on:click={() => (passwordOpen = true)}>
        <KeyRound size={16} /> Пароль
      </button>
      <button class="btn grow" on:click={logout}>
        <LogOut size={16} /> Выйти
      </button>
    </div>
  </section>

  <section class="card pad">
    <div class="between" style="margin-bottom:10px">
      <h3 class="section-title" style="margin:0">Категории и поля товаров</h3>
      <button
        class="btn btn-sm"
        on:click={() => (editingCategory = { category: null })}
        aria-label="Новая категория"
      >
        <Plus size={15} /> Добавить
      </button>
    </div>

    {#if !$catalog.categories.length}
      <p class="faint" style="font-size:13px">
        Пока ни одной категории. Создайте первую — например «Одежда» с полями «Размер» и «Надпись».
      </p>
    {:else}
      <div class="stack-sm">
        {#each $catalog.categories as c (c.id)}
          <button class="entry" on:click={() => (editingCategory = { category: c })}>
            <div class="icon-badge" style="background:{c.color};width:36px;height:36px;border-radius:11px">
              <Icon name={c.icon} size={17} />
            </div>
            <div class="grow" style="text-align:left">
              <div style="font-size:14px;font-weight:650">{c.name}</div>
              <div class="faint" style="font-size:12px">
                {c.product_count} тов. · {c.subcategories.length} подкат. · {c.attributes.length} пол.
              </div>
            </div>
          </button>
        {/each}
      </div>
    {/if}
  </section>

  <section class="card pad">
    <div class="between" style="margin-bottom:10px">
      <h3 class="section-title" style="margin:0">Поставщики</h3>
      <button
        class="btn btn-sm"
        on:click={() => (editingSupplier = { id: null, name: '', note: '' })}
      >
        <Plus size={15} /> Добавить
      </button>
    </div>

    {#if !$catalog.suppliers.length}
      <p class="faint" style="font-size:13px">
        У каждого товара обязательно есть поставщик — добавьте хотя бы одного.
      </p>
    {:else}
      <div class="stack-sm">
        {#each $catalog.suppliers as s (s.id)}
          <button
            class="entry"
            on:click={() => (editingSupplier = { id: s.id, name: s.name, note: s.note })}
          >
            <div class="grow" style="text-align:left">
              <div style="font-size:14px;font-weight:650">{s.name}</div>
              <div class="faint ellipsis" style="font-size:12px">
                {s.product_count} тов.{#if s.note} · {s.note}{/if}
              </div>
            </div>
          </button>
        {/each}
      </div>
    {/if}
  </section>

  {#if archive?.length}
    <section class="card pad">
      <h3 class="section-title"><Archive size={13} /> Архив</h3>
      <p class="faint" style="font-size:12px;margin-bottom:10px">
        Это не удалилось, потому что на записи ссылаются товары. Можно вернуть.
      </p>
      <div class="stack-sm">
        {#each archive as row (row.table + row.id)}
          <div class="row-item">
            <span class="grow ellipsis" style="font-size:13px">{row.label}</span>
            <button class="btn btn-ghost btn-icon" on:click={() => restore(row)} aria-label="Вернуть">
              <Undo2 size={15} />
            </button>
          </div>
        {/each}
      </div>
    </section>
  {:else if loadingArchive}
    <div class="row faint" style="justify-content:center;font-size:13px">
      <Loader2 size={15} class="spin" /> Проверяю архив
    </div>
  {/if}

  <section class="card pad">
    <h3 class="section-title"><Database size={13} /> Данные</h3>
    <p class="faint" style="font-size:12px;margin-bottom:10px">
      Вся база — один файл. Копию можно скачать в любой момент, она консистентна
      даже если в этот момент кто-то оформляет продажу.
    </p>
    <button class="btn btn-block" on:click={downloadBackup} disabled={backupBusy}>
      {#if backupBusy}<Loader2 size={16} class="spin" />{:else}<Download size={16} />{/if}
      Скачать копию базы
    </button>
  </section>
</div>

<style>
  .entry {
    display: flex; align-items: center; gap: 11px; width: 100%;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 13px; padding: 9px 11px;
    transition: border-color var(--transition), transform var(--transition);
  }
  .entry:hover { border-color: var(--border-strong); }
  .entry:active { transform: scale(0.99); }

  .row-item {
    display: flex; align-items: center; gap: 8px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 7px 11px;
  }
  .section-title { display: flex; align-items: center; gap: 6px; }
</style>
