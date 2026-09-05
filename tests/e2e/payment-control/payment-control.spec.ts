import { test, expect } from '@playwright/test'

test('real upload → activate → apartment balance → source record → deactivate', async ({ page, request }) => {
  await page.goto('/uk/dashboard/payment-control?account=001')
  await expect(page.getByText('Нет активных данных по этому лицевому счёту. Это не означает нулевой долг.')).toBeVisible()
  await page.getByLabel('CSV / XLSX').setInputFiles({ name: 'balance.csv', mimeType: 'text/csv', buffer: Buffer.from('account_number;debt;prepayment\n001;120000;0\n002;0;50000\n') })
  await page.getByRole('button', { name: 'Проверить файл' }).click()
  const activate = page.getByRole('button', { name: 'Подтвердить и активировать' })
  await expect(activate).toBeEnabled()
  // The apartment still has no confirmed balance during preview.
  const before = await request.get('http://127.0.0.1:18085/api/v2/payment-control/apartments/1')
  expect((await before.json()).status).toBe('no_data')
  await activate.click()
  await expect(page.getByRole('button', { name: 'Деактивировать' })).toBeVisible()
  const after = await request.get('http://127.0.0.1:18085/api/v2/payment-control/apartments/1')
  expect((await after.json()).current.debt).toBe('120000.00')
  await page.screenshot({ path: 'artifacts/payment-control-service.png', fullPage: true })
  await page.goto('/uk/dashboard/addresses')
  await page.getByText('Тестовый двор', { exact: true }).click()
  await page.getByText('Тестовая улица 1', { exact: true }).click()
  await page.getByText('1', { exact: true }).last().click()
  await expect(page.getByText('120000.00 UZS', { exact: true })).toBeVisible()
  await page.screenshot({ path: 'artifacts/payment-control-apartment.png', fullPage: true })
  await page.getByRole('link', { name: 'Сверить в сервисе платежей' }).click()
  await expect(page).toHaveURL(/account=001/)
  await expect(page.getByRole('heading', { name: /balance.csv/ })).toBeVisible()
  await page.getByLabel('Причина деактивации').fill('Проверка исправленной выгрузки')
  await page.getByRole('button', { name: 'Деактивировать', exact: true }).click()
  await expect(page.getByText('Нет активных данных по этому лицевому счёту. Это не означает нулевой долг.')).toBeVisible()
})

test('a row with a bad amount blocks activation and leaves the apartment unconfirmed', async ({ page, request }) => {
  await page.goto('/uk/dashboard/payment-control?account=001')
  await page.getByLabel('CSV / XLSX').setInputFiles({
    name: 'broken.csv', mimeType: 'text/csv',
    buffer: Buffer.from('account_number;debt;prepayment\n001;abc;0\n'),
  })
  await page.getByRole('button', { name: 'Проверить файл' }).click()
  await expect(page.getByRole('button', { name: 'Подтвердить и активировать' })).toBeDisabled()
  await expect(page.getByRole('heading', { name: /broken.csv/ })).toBeVisible()
  const balance = await request.get('http://127.0.0.1:18085/api/v2/payment-control/apartments/1')
  expect((await balance.json()).current).toBeNull()
})

test('re-uploading identical content returns the same import instead of a second one', async ({ page }) => {
  const file = {
    name: 'repeat.csv', mimeType: 'text/csv',
    buffer: Buffer.from('account_number;debt;prepayment\n003;7000;0\n'),
  }
  await page.goto('/uk/dashboard/payment-control')
  await page.getByLabel('CSV / XLSX').setInputFiles(file)
  await page.getByRole('button', { name: 'Проверить файл' }).click()
  const heading = page.getByRole('heading', { name: /repeat.csv/ })
  await expect(heading).toBeVisible()
  const first = await heading.textContent()
  await page.getByLabel('CSV / XLSX').setInputFiles(file)
  await page.getByRole('button', { name: 'Проверить файл' }).click()
  await expect(heading).toHaveText(first!.trim())
  await expect(page.getByRole('button', { name: new RegExp(`^#${first!.trim().split(' ')[0].slice(1)} · repeat.csv`) })).toHaveCount(1)
})

test('apartment profile shows the Mening uyim account number', async ({ page }) => {
  await page.goto('/uk/dashboard/addresses')
  await page.getByText('Тестовый двор', { exact: true }).click()
  await page.getByText('Тестовая улица 1', { exact: true }).click()
  await page.getByText('1', { exact: true }).last().click()
  await expect(page.getByText('Лицевой счёт «Mening uyim»')).toBeVisible()
  await expect(page.getByText('001', { exact: true })).toBeVisible()
})

test('the section renders in Uzbek for a uz interface', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('i18nextLng', 'uz'))
  await page.goto('/uk/dashboard/payment-control?account=001')
  await expect(page.getByRole('heading', { name: 'To‘lovlar nazorati' })).toBeVisible()
  await expect(page.getByText('Bu hisob bo‘yicha faol ma’lumot yo‘q. Bu qarz nol ekanini anglatmaydi.')).toBeVisible()
})
