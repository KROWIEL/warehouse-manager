export function fmtMoney(value, opts = {}) {
  const num = Number(value || 0)
  const sign = opts.sign && num > 0 ? '+' : ''
  const digits = opts.short && Math.abs(num) >= 1000 ? 0 : 2
  const formatted = num.toLocaleString('ru-RU', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  })
  return `${sign}${formatted}\u00A0Br`
}

// Количество: целые без «.00», дробные — без хвостовых нулей.
export function fmtQty(value) {
  const num = Number(value || 0)
  return num.toLocaleString('ru-RU', { maximumFractionDigits: 3 })
}

export function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}

export function fmtDateFull(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  })
}

export function todayISO() {
  // Локальная дата, а не UTC: иначе поздним вечером продажа уезжает на завтра.
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

export function shiftISO(iso, days) {
  const d = new Date(iso)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

// Принимает и точку, и запятую как десятичный разделитель — важно для мобильных
// клавиатур, где под рукой оказывается то одно, то другое.
export function parseNum(value) {
  if (typeof value === 'number') return value
  if (value === null || value === undefined || value === '') return NaN
  return parseFloat(String(value).replace(/\s/g, '').replace(',', '.'))
}

// «5 товаров», «21 товар», «2 товара»
export function plural(n, one, few, many) {
  const abs = Math.abs(Math.round(n)) % 100
  const last = abs % 10
  if (abs > 10 && abs < 20) return many
  if (last > 1 && last < 5) return few
  if (last === 1) return one
  return many
}

export function pluralWord(n, one, few, many) {
  return `${fmtQty(n)} ${plural(n, one, few, many)}`
}
