/**
 * E2E: Login flow.
 *
 * Requires a manager user with email + password in the DB.
 * Known fixture: admin@test.com (roles: manager).
 *
 * Without E2E_MANAGER_EMAIL / E2E_MANAGER_PASSWORD the "successful login" test
 * skips itself with an explanatory message so the suite stays green and the gap
 * is visible in reports.
 *
 * TEST FIXTURE (TEST-071):
 *   1) Seed a manager user (idempotent). telegram_id must be a real chat that
 *      started the bot — login requires a Telegram MFA OTP:
 *
 *        docker exec uk-management-bot python scripts/seed_e2e_user.py \
 *          --email admin@test.com --password 'E2eTest!2026' --telegram-id <your_tg_id>
 *
 *   2) Copy tests/e2e/.env.example -> tests/e2e/.env and fill the same values
 *      (playwright.config.ts loads it). Then `npx playwright test`.
 *
 *   Login redirects through an OTP step; this test accepts EITHER landing on
 *   /uk/dashboard OR the OTP entry screen as a successful "login initiated".
 */
import { test, expect } from '@playwright/test'

const MANAGER_EMAIL = process.env.E2E_MANAGER_EMAIL ?? ''
const MANAGER_PASSWORD = process.env.E2E_MANAGER_PASSWORD ?? ''

const fixtureAvailable = Boolean(MANAGER_EMAIL && MANAGER_PASSWORD)

test.describe('Login flow — email + password', () => {

  test('login page renders email and password fields', async ({ page }) => {
    await page.goto('/uk/login')

    await expect(page.locator('input[type="email"]')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('input[type="password"]')).toBeVisible({ timeout: 5_000 })
    await expect(page.locator('button[type="submit"]')).toBeVisible({ timeout: 5_000 })

    await page.screenshot({ path: 'artifacts/login-page.png', fullPage: false })
  })

  test('invalid credentials: API returns 401 and user stays on login page', async ({ page }) => {
    await page.goto('/uk/login')

    const emailInput = page.locator('input[type="email"]')
    const passwordInput = page.locator('input[type="password"]')
    const submitBtn = page.locator('button[type="submit"]')

    await expect(emailInput).toBeVisible({ timeout: 10_000 })
    await expect(emailInput).toBeEnabled()

    // Fill using React-compatible approach: set DOM value via native setter
    // then dispatch input/change events so React 19 state updates.
    await page.evaluate(() => {
      const emailEl = document.querySelector('input[type="email"]') as HTMLInputElement
      const pwEl = document.querySelector('input[type="password"]') as HTMLInputElement
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
      )!.set!

      nativeInputValueSetter.call(emailEl, 'nonexistent@example.com')
      emailEl.dispatchEvent(new Event('input', { bubbles: true }))
      emailEl.dispatchEvent(new Event('change', { bubbles: true }))

      nativeInputValueSetter.call(pwEl, 'WrongPassword123!')
      pwEl.dispatchEvent(new Event('input', { bubbles: true }))
      pwEl.dispatchEvent(new Event('change', { bubbles: true }))
    })

    await expect(emailInput).toHaveValue('nonexistent@example.com', { timeout: 3_000 })
    await expect(passwordInput).toHaveValue('WrongPassword123!', { timeout: 3_000 })

    // Intercept the login POST
    const loginCallPromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/v2/auth/login') && resp.request().method() === 'POST',
      { timeout: 15_000 }
    )

    await submitBtn.click()

    const loginResponse = await loginCallPromise
    const requestBody = loginResponse.request().postData()

    // Verify the request body contained our credentials
    expect(requestBody).toContain('nonexistent@example.com')

    // API must reject invalid credentials
    expect(loginResponse.status()).toBe(401)

    // The apiClient's 401 interceptor fires, tries to refresh (fails), then
    // navigates to login. User ends up back on the login page. That's the
    // observable behavior: login attempt fails and user stays on /uk/login.
    await page.waitForURL(/\/uk\/login/, { timeout: 8_000 })
    await expect(submitBtn).toBeVisible({ timeout: 5_000 })

    await page.screenshot({ path: 'artifacts/login-invalid-creds.png', fullPage: false })
  })

  test('successful login redirects to /uk/dashboard', async ({ page }) => {
    if (!fixtureAvailable) {
      test.skip(true, 'blocked: no test fixture — set E2E_MANAGER_EMAIL and E2E_MANAGER_PASSWORD env vars')
      return
    }

    await page.goto('/uk/login')

    await page.locator('input[type="email"]').fill(MANAGER_EMAIL)
    await page.locator('input[type="password"]').fill(MANAGER_PASSWORD)
    await page.locator('button[type="submit"]').click()

    // Either we land on dashboard (no MFA) or we see the MFA OTP step.
    // Both outcomes are valid "login initiated" states.
    const isDashboard = page.waitForURL(/\/uk\/dashboard/, { timeout: 10_000 })
    const isMfa = page.locator('text=/Код отправлен/i').waitFor({ timeout: 10_000 })

    await Promise.race([isDashboard, isMfa])

    const currentUrl = page.url()
    const onDashboard = currentUrl.includes('/uk/dashboard')
    const onMfa = await page.locator('text=/Код отправлен/i').isVisible()

    expect(onDashboard || onMfa).toBe(true)

    await page.screenshot({ path: 'artifacts/login-success.png', fullPage: false })
  })

})
