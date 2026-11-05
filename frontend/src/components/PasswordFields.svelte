<script>
  import { onMount } from 'svelte'
  import { Check, Circle } from 'lucide-svelte'
  import { api } from '../lib/api.js'

  export let current = ''
  export let next = ''
  export let valid = false

  // Тексты требований приходят с сервера — там же, где реальная проверка.
  // Здесь только предикаты, сопоставленные по id, а не по порядку в списке.
  const TESTS = {
    length: (v, min) => v.length >= min,
    upper: (v) => v !== v.toLowerCase(),
    lower: (v) => v !== v.toUpperCase(),
    special: (v) => /[^\p{L}\p{N}\s]/u.test(v)
  }

  let policy = { min_length: 8, rules: [] }
  let repeat = ''

  onMount(async () => {
    try {
      policy = await api.get('/auth/password-policy')
    } catch {
      /* подсказки не критичны: пароль всё равно проверяет сервер */
    }
  })

  $: checks = policy.rules.map((rule) => ({
    ...rule,
    ok: (TESTS[rule.id] || (() => true))(next, policy.min_length)
  }))
  $: matches = next.length > 0 && next === repeat
  $: valid = current.length > 0 && checks.length > 0 && checks.every((c) => c.ok) && matches
</script>

<div class="field">
  <label for="pf-cur">Текущий пароль</label>
  <input id="pf-cur" type="password" bind:value={current} autocomplete="current-password" />
</div>

<div class="field">
  <label for="pf-new">Новый пароль</label>
  <input id="pf-new" type="password" bind:value={next} autocomplete="new-password" />
</div>

<ul class="rules">
  {#each checks as rule}
    <li class:ok={rule.ok}>
      {#if rule.ok}<Check size={15} />{:else}<Circle size={15} />{/if}
      <span>{rule.text}</span>
    </li>
  {/each}
</ul>

<div class="field">
  <label for="pf-rep">Повторите новый пароль</label>
  <input id="pf-rep" type="password" bind:value={repeat} autocomplete="new-password" />
  {#if repeat && !matches}
    <span class="neg" style="font-size:12px">Пароли не совпадают</span>
  {/if}
</div>

<style>
  .rules { list-style: none; display: flex; flex-direction: column; gap: 6px; }
  .rules li {
    display: flex; align-items: center; gap: 8px;
    font-size: 13px; color: var(--text-faint);
    transition: color var(--transition);
  }
  .rules li.ok { color: var(--pos); }
</style>
