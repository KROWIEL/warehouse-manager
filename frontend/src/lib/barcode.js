// Нативного BarcodeDetector в Safari на iOS нет (за флагом он сломан с iOS 18),
// поэтому берём ponyfill того же стандартного API поверх ZXing-C++ в WebAssembly.
// Код сканера от этого не меняется — отличается только строчка импорта.
//
// Версия zxing-wasm закреплена в package.json ровно той, которую ждёт
// barcode-detector: бинарник проверяется по хешу и при расхождении не запустится.
import wasmUrl from 'zxing-wasm/reader/zxing_reader.wasm?url'

// Всё, что реально встречается в рознице, плюс QR — иногда цену клеят им.
export const BARCODE_FORMATS = [
  'ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf', 'qr_code'
]

let pending = null

// Мегабайт WASM не должен тормозить запуск приложения, поэтому модуль
// подгружается динамически — по первому нажатию кнопки «Сканировать».
export function loadDetector() {
  if (!pending) {
    pending = (async () => {
      const { BarcodeDetector, prepareZXingModule } = await import('barcode-detector/ponyfill')
      // По умолчанию пакет тянет .wasm с jsDelivr: это ломает работу без сети
      // и добавляет внешнюю зависимость в рантайме. Отдаём файл из своей сборки.
      await prepareZXingModule({
        overrides: {
          locateFile: (path, prefix) => (path.endsWith('.wasm') ? wasmUrl : prefix + path)
        },
        fireImmediately: true
      })
      return new BarcodeDetector({ formats: BARCODE_FORMATS })
    })()
    // Сорвалась загрузка (нет сети) — даём шанс повторить, а не залипаем навсегда.
    pending.catch(() => { pending = null })
  }
  return pending
}
