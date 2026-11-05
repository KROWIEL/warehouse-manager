<script>
  import { createEventDispatcher, onDestroy, onMount } from 'svelte'
  import { Loader2, X, ScanLine, CornerDownLeft } from 'lucide-svelte'
  import { loadDetector } from '../lib/barcode.js'

  const dispatch = createEventDispatcher()

  // Гонять WASM на каждом кадре бессмысленно: 10 распознаваний в секунду
  // ловят код мгновенно и не греют телефон.
  const FRAME_INTERVAL = 100

  let video
  let stream = null
  let detector = null
  let stopped = false
  let starting = true
  let error = ''
  let manual = ''
  let lastFrame = 0

  function describe(e) {
    switch (e && e.name) {
      case 'NotAllowedError':
      case 'SecurityError':
        return 'Доступ к камере запрещён. Разрешите камеру для этого сайта в настройках браузера.'
      case 'NotFoundError':
      case 'DevicesNotFoundError':
        return 'Камера не найдена.'
      case 'NotReadableError':
      case 'TrackStartError':
        return 'Камера занята другим приложением.'
      default:
        return (e && e.message) || 'Не удалось включить камеру.'
    }
  }

  onMount(async () => {
    // getUserMedia работает только в защищённом контексте: https или localhost.
    // С телефона по локальному IP камера не включится — говорим это прямо,
    // а не показываем бесконечный спиннер.
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      error = 'Камера доступна только по https. Введите код вручную.'
      starting = false
      return
    }
    try {
      const [ready, media] = await Promise.all([
        loadDetector(),
        navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1280 },
            height: { ideal: 720 }
          },
          audio: false
        })
      ])
      if (stopped) {
        media.getTracks().forEach((t) => t.stop())
        return
      }
      detector = ready
      stream = media
      video.srcObject = media
      await video.play()
      starting = false
      queue()
    } catch (e) {
      error = describe(e)
      starting = false
    }
  })

  function queue() {
    if (stopped) return
    if (video?.requestVideoFrameCallback) {
      video.requestVideoFrameCallback((now) => scan(now))
    } else {
      setTimeout(() => scan(performance.now()), FRAME_INTERVAL)
    }
  }

  async function scan(now) {
    if (stopped) return
    if (now - lastFrame < FRAME_INTERVAL) {
      queue()
      return
    }
    lastFrame = now
    try {
      const codes = await detector.detect(video)
      const value = codes.find((c) => c.rawValue)?.rawValue
      if (value) {
        submit(value)
        return
      }
    } catch {
      // Кадр ещё не готов или распознавание сорвалось — пробуем следующий.
    }
    queue()
  }

  function stop() {
    stopped = true
    // Без явной остановки треков индикатор камеры на iPhone продолжает гореть.
    if (stream) {
      stream.getTracks().forEach((t) => t.stop())
      stream = null
    }
    if (video) video.srcObject = null
  }

  onDestroy(stop)

  function submit(value) {
    const code = String(value || '').trim()
    if (!code) return
    if (navigator.vibrate) navigator.vibrate(60)
    stop()
    dispatch('detect', code)
  }

  function close() {
    stop()
    dispatch('close')
  }
</script>

<div class="scanner">
  <!-- playsinline и muted обязательны: без них iOS открывает поток
       на весь экран поверх интерфейса -->
  <video bind:this={video} playsinline muted autoplay></video>

  <div class="shade">
    <div class="top">
      <span class="hint">
        {#if starting}
          <Loader2 size={16} class="spin" /> Включаю камеру
        {:else if error}
          Введите код вручную
        {:else}
          <ScanLine size={16} /> Наведите на штрихкод
        {/if}
      </span>
      <button class="btn btn-icon close" on:click={close} aria-label="Закрыть">
        <X size={20} />
      </button>
    </div>

    {#if !error}
      <div class="frame" class:live={!starting}>
        <span class="beam"></span>
      </div>
    {:else}
      <div class="err">{error}</div>
    {/if}

    <form class="manual" on:submit|preventDefault={() => submit(manual)}>
      <input
        bind:value={manual}
        placeholder="Код цифрами"
        inputmode="numeric"
        autocomplete="off"
      />
      <button class="btn btn-primary btn-icon" type="submit" disabled={!manual.trim()} aria-label="Найти">
        <CornerDownLeft size={18} />
      </button>
    </form>
  </div>
</div>

<style>
  .scanner { position: fixed; inset: 0; z-index: 120; background: #000; }
  video { width: 100%; height: 100%; object-fit: cover; }

  .shade {
    position: absolute; inset: 0;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: calc(14px + env(safe-area-inset-top)) 14px calc(16px + env(safe-area-inset-bottom));
  }
  .top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .hint {
    display: inline-flex; align-items: center; gap: 7px;
    background: rgba(0, 0, 0, 0.55); color: #fff;
    padding: 9px 14px; border-radius: 999px;
    font-size: 13px; font-weight: 600;
    backdrop-filter: blur(6px);
  }
  .close { background: rgba(0, 0, 0, 0.55); border-color: transparent; color: #fff; }

  .frame {
    align-self: center;
    width: min(78vw, 320px); aspect-ratio: 4 / 3;
    border-radius: 18px;
    box-shadow: 0 0 0 100vmax rgba(0, 0, 0, 0.45);
    border: 2px solid rgba(255, 255, 255, 0.85);
    position: relative; overflow: hidden;
  }
  .beam { display: none; }
  .frame.live .beam {
    display: block;
    position: absolute; left: 0; right: 0; height: 2px;
    background: #0ea5e9; box-shadow: 0 0 12px 2px #0ea5e9;
    animation: sweep 2s ease-in-out infinite;
  }
  @keyframes sweep { 0%, 100% { top: 6%; } 50% { top: 94%; } }

  .err {
    align-self: center; max-width: 320px; text-align: center;
    background: rgba(0, 0, 0, 0.65); color: #fff;
    padding: 14px 18px; border-radius: 16px; font-size: 14px; line-height: 1.45;
  }

  .manual { display: flex; gap: 8px; }
  .manual input {
    background: rgba(255, 255, 255, 0.95); color: #101828; border-color: transparent;
  }
</style>
