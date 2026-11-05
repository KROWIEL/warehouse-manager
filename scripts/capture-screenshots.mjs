/**
 * Product screenshots for README / GitHub Pages.
 *
 * Prerequisites:
 *   - App running at http://localhost:8080 with demo data
 *   - From frontend/: npm i -D playwright && npx playwright install chromium
 *
 *   WM_USER=demo WM_PASS='...' node scripts/capture-screenshots.mjs
 */
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(join(ROOT, 'frontend', 'package.json'))
const { chromium } = require('playwright')

const OUT = join(ROOT, 'docs', 'screenshots')
const BASE = process.env.WM_URL || 'http://localhost:8080'
const USER = process.env.WM_USER || 'demo'
const PASS = process.env.WM_PASS
if (!PASS) {
  console.error('Set WM_PASS to the demo account password, then re-run.')
  process.exit(1)
}

mkdirSync(OUT, { recursive: true })

async function settle(page, ms = 600) {
  await page.waitForTimeout(ms)
}

async function shot(page, name) {
  const path = join(OUT, `${name}.png`)
  await page.screenshot({ path, fullPage: false })
  console.log('wrote', path)
}

async function login(page) {
  await page.goto(BASE + '/')
  await page.waitForSelector('#u, .bottom-nav, .splash', { timeout: 20000 })
  if (await page.locator('#u').count()) {
    await page.fill('#u', USER)
    await page.fill('#p', PASS)
    await page.click('button[type="submit"]')
    await page.waitForSelector('.bottom-nav', { timeout: 20000 })
  }
  await settle(page, 800)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const desktop = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    deviceScaleFactor: 1,
    locale: 'ru-RU',
  })
  const page = await desktop.newPage()
  await login(page)

  await page.goto(BASE + '/#/')
  await page.waitForSelector('.bottom-nav')
  await settle(page, 1000)
  await shot(page, 'warehouse')

  await page.goto(BASE + '/#/sale')
  await page.waitForSelector('button.hit', { timeout: 15000 })
  await settle(page, 800)
  const hits = page.locator('button.hit')
  const n = await hits.count()
  if (n === 0) throw new Error('no products on sale screen')
  for (const i of [0, 1, Math.min(2, n - 1)]) {
    await hits.nth(i).click()
    await settle(page, 250)
  }
  await page.waitForSelector('text=Провести продажу', { timeout: 5000 })
  await page.locator('text=Провести продажу').scrollIntoViewIfNeeded()
  await settle(page, 400)
  await shot(page, 'sale')

  await page.goto(BASE + '/#/stats')
  await settle(page, 1400)
  await shot(page, 'stats')

  await page.goto(BASE + '/#/settings')
  await settle(page, 800)
  await shot(page, 'settings')

  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'dark')
    localStorage.setItem('sm_theme', 'dark')
  })
  await page.goto(BASE + '/#/')
  await settle(page, 1000)
  await shot(page, 'warehouse-dark')
  await desktop.close()

  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    locale: 'ru-RU',
  })
  const m = await mobile.newPage()
  await login(m)
  await m.goto(BASE + '/#/')
  await settle(m, 1000)
  await shot(m, 'mobile')
  await mobile.close()
  await browser.close()
  console.log('done')
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
