<script>
  import { avatar } from '../lib/avatars.js'
  export let name = 'fox'
  export let size = 40
  $: a = avatar(name)
</script>

<div
  class="avatar"
  style="width:{size}px;height:{size}px;background:{a.grad};font-size:{size * 0.55}px"
>
  {a.emoji}
</div>

<style>
  .avatar {
    display: grid;
    place-items: center;
    border-radius: 50%;
    flex-shrink: 0;
    box-shadow: 0 6px 16px -6px rgba(0, 0, 0, 0.5);
    line-height: 1;
    user-select: none;
  }
</style>
