<script>
  import { getIcon } from '../lib/icons.js'
  export let name = 'package'
  export let size = 20
  export let color = 'currentColor'
  export let strokeWidth = 2
  $: Cmp = getIcon(name)
</script>

<svelte:component this={Cmp} {size} {color} {strokeWidth} />
