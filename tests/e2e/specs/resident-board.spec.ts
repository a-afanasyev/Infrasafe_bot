/**
 * E2E: Resident Board — public page, no auth required.
 *
 * Verifies that the board renders its key UI elements and that the
 * pair_with_next layout flag places two modules side-by-side.
 */
import { test, expect } from '@playwright/test'
import { execFile } from 'child_process'
import { promisify } from 'util'

const execFileAsync = promisify(execFile)
const BOARD_URL = '/uk/resident-board'

// Helper: run a psql command inside uk-postgres container.
// Uses execFile (not exec) to avoid shell injection.
async function psql(sql: string): Promise<string> {
  const { stdout } = await execFileAsync('docker', [
    'exec', 'uk-postgres',
    'psql', '-U', 'uk_bot', '-d', 'uk_management',
    '-c', sql,
  ])
  return stdout
}

test.describe('Resident Board — public page', () => {

  test('renders without auth: ticker, clock, org name visible', async ({ page }) => {
    await page.goto(BOARD_URL)

    // Ticker bar (green strip at the top with dispatch phone / bot handle)
    const ticker = page.locator('div').filter({ hasText: /Диспетчерская|Telegram-бот/i }).first()
    await expect(ticker).toBeVisible({ timeout: 10_000 })

    // Clock: two-digit hours and minutes separated by colon (e.g. "08:42")
    await expect(page.locator('text=/^\\d{2}:\\d{2}$/')).toBeVisible({ timeout: 5_000 })

    // ЖК name from board config or fallback default
    await expect(
      page.getByText(/Управляющая компания|Boshqaruv kompaniyasi/i, { exact: false })
    ).toBeVisible({ timeout: 10_000 })

    await page.screenshot({ path: 'artifacts/board-renders.png', fullPage: false })
  })

  test('at least one module section header is visible', async ({ page }) => {
    await page.goto(BOARD_URL)

    // Stats tiles, requests card, announcements, rating or hours
    const moduleTitles = page.locator('div').filter({
      hasText: /Текущие заявки|Объявления|Режим работы|Рейтинг жителей|Специалисты|Заявки/i,
    })
    await expect(moduleTitles.first()).toBeVisible({ timeout: 15_000 })

    await page.screenshot({ path: 'artifacts/board-module-visible.png', fullPage: true })
  })

  test('footer shows realtime update timestamp (HH:MM:SS)', async ({ page }) => {
    await page.goto(BOARD_URL)

    const footer = page.locator('footer')
    await expect(footer).toBeVisible({ timeout: 10_000 })
    await expect(footer).toContainText(/\d{2}:\d{2}:\d{2}/)
  })

  test('stats row renders 4 stat tiles', async ({ page }) => {
    await page.goto(BOARD_URL)

    const tiles = page.locator('.rb-stat-tile')
    await expect(tiles).toHaveCount(4, { timeout: 15_000 })
  })

})

test.describe('pair_with_next layout feature', () => {

  /**
   * Sets pair_with_next=true on the "announcements" layout item via a direct
   * DB UPDATE (no auth needed), reloads the board, checks that announcements
   * and the next module share roughly the same Y position (side-by-side row),
   * then restores the original config.
   */
  test('pair_with_next=true renders two modules in one row', async ({ page, request }) => {
    // ── 1. Fetch current public config ───────────────────────────────────────
    const configResp = await request.get('http://localhost:8085/api/v2/public/board-config')
    expect(configResp.ok()).toBeTruthy()
    const config = await configResp.json() as {
      layout: Array<{ id: string; visible: boolean; pair_with_next?: boolean }>
      [key: string]: unknown
    }

    const originalConfigJson = JSON.stringify(config)
    const layout = config.layout

    const annIdx = layout.findIndex((l) => l.id === 'announcements')
    expect(annIdx).toBeGreaterThanOrEqual(0)

    // Patch: set pair_with_next=true for announcements
    const patchedLayout = layout.map((item, i) =>
      i === annIdx ? { ...item, pair_with_next: true } : item
    )
    const patchedConfig = { ...config, layout: patchedLayout }
    const patchedConfigJson = JSON.stringify(patchedConfig)

    // ── 2. Write patched config to DB ────────────────────────────────────────
    await psql(
      `UPDATE board_config SET data = '${patchedConfigJson.replace(/'/g, "''")}'::json WHERE id = (SELECT id FROM board_config ORDER BY id LIMIT 1);`
    )

    try {
      // ── 3. Load board ────────────────────────────────────────────────────────
      await page.goto(BOARD_URL)
      // Allow React Query to fetch the fresh config
      await page.waitForTimeout(2000)

      // Locate the header elements of the paired modules.
      // In ru locale: announcements="Объявления", rating="Оценка жителей"
      const annHeader = page.getByText(/Объявления/i, { exact: false }).first()
      // The module after announcements in default layout is "rating" (Оценка жителей)
      const nextHeader = page.getByText(/Оценка жителей|Часы работы/i, { exact: false }).first()

      await expect(annHeader).toBeVisible({ timeout: 10_000 })
      await expect(nextHeader).toBeVisible({ timeout: 10_000 })

      const annBox = await annHeader.boundingBox()
      const nextBox = await nextHeader.boundingBox()

      expect(annBox).not.toBeNull()
      expect(nextBox).not.toBeNull()

      // Paired modules appear in the same horizontal grid row:
      // their Y positions are close (< 80px difference).
      // Un-paired stacked modules would be separated by 200px+.
      const yDiff = Math.abs(annBox!.y - nextBox!.y)
      expect(yDiff).toBeLessThan(80)

      await page.screenshot({ path: 'artifacts/board-paired-modules.png', fullPage: false })
    } finally {
      // ── 4. Restore original config ───────────────────────────────────────────
      await psql(
        `UPDATE board_config SET data = '${originalConfigJson.replace(/'/g, "''")}'::json WHERE id = (SELECT id FROM board_config ORDER BY id LIMIT 1);`
      )
    }
  })

})
