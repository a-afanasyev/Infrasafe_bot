/**
 * E2E: Protected route guard.
 *
 * Opening /uk/dashboard/board-editor without a valid session must redirect
 * the browser to /uk/login (React Router ProtectedRoute → <Navigate to="/login">).
 */
import { test, expect } from '@playwright/test'

test.describe('Protected route guard — no auth', () => {

  test('GET /uk/dashboard/board-editor redirects to /uk/login', async ({ page }) => {
    // Navigate directly to the protected editor URL
    await page.goto('/uk/dashboard/board-editor')

    // Wait for React Router to resolve the redirect
    await page.waitForURL(/\/uk\/login/, { timeout: 10_000 })

    // Confirm we are on the login page by looking for the login form
    await expect(page.locator('input[type="email"]')).toBeVisible({ timeout: 5_000 })

    await page.screenshot({ path: 'artifacts/route-guard-redirect.png', fullPage: false })
  })

  test('GET /uk/dashboard also redirects unauthenticated users to /uk/login', async ({ page }) => {
    await page.goto('/uk/dashboard')

    await page.waitForURL(/\/uk\/login/, { timeout: 10_000 })

    await expect(page.locator('input[type="email"]')).toBeVisible({ timeout: 5_000 })
  })

})
