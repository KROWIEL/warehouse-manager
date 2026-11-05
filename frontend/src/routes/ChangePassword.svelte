<script>
  import { createEventDispatcher } from 'svelte'
  import { KeyRound, Loader2 } from 'lucide-svelte'
  import { api } from '../lib/api.js'
  import { toast } from '../lib/stores.js'
  import PasswordFields from '../components/PasswordFields.svelte'

  const dispatch = createEventDispatcher()

  let current = ''
  let next = ''
  let valid = false
  let error = ''
  let busy = false

  async function submit() {
    if (!valid || busy) return
    error = ''
    busy = true
    try {
      const me = await api.post('/profile/password', {
        current_password: current,
        new_password: next
      })
      toast('Пароль изменён', 'success')
      dispatch('done', me)
    } catch (e) {
      error = e.message
    } finally {
      busy = false
    }
  }
</script>

<div class="wrap">
  <form class="card panel fade-up" on:submit|preventDefault={submit}>
    <div class="logo">
      <div class="logo-badge"><KeyRound size={26} color="#fff" /></div>
      <div>
        <h1>Смените пароль</h1>
        <p class="dim">Стартовый пароль знаете не только вы — задайте свой</p>
      </div>
    </div>

    <PasswordFields bind:current bind:next bind:valid />

    {#if error}<div class="error-box">{error}</div>{/if}

    <button class="btn btn-primary" type="submit" disabled={!valid || busy}>
      {#if busy}<Loader2 size={18} class="spin" />{/if}
      Сохранить и войти
    </button>
  </form>
</div>

<style>
  .wrap { min-height: 100vh; display: grid; place-items: center; padding: 20px; }
  .panel { width: 100%; max-width: 400px; padding: 28px 24px; display: flex; flex-direction: column; gap: 15px; }
  .logo { display: flex; align-items: flex-start; gap: 14px; }
  .logo-badge {
    width: 50px; height: 50px; border-radius: 15px; display: grid; place-items: center;
    background: var(--grad); box-shadow: 0 10px 24px -8px var(--accent-glow); flex-shrink: 0;
  }
  h1 { font-size: 21px; font-weight: 800; letter-spacing: -0.4px; }
  .logo p { font-size: 13px; margin-top: 3px; line-height: 1.4; }
  .btn-primary { margin-top: 4px; padding: 13px; }
</style>
