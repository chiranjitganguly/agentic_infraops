/**
 * E2E smoke test (T071).
 *
 * Mocks the backend API routes so the test runs without a live backend stack.
 * Validates the critical user journey: load → submit FAQ → see answer → toggle theme.
 */
import { test, expect } from '@playwright/test'

test.describe('Infra Q&A UI smoke test', () => {
  test.beforeEach(async ({ page }) => {
    // --- Mock GET /api/v1/auth/me ---
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: 'smoke-test@example.com',
          role: 'developer',
          api_key_expires_at: null,
          daily_provisioning_count: 2,
          daily_provisioning_limit: 10,
        }),
      }),
    )

    // --- Mock POST /api/v1/requests (FAQ response) ---
    await page.route('**/api/v1/requests', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          infra_request_id: 'req-smoke-001',
          intent: 'faq',
          status: 'answered',
          answer: 'Use VPC peering for cross-project connectivity.',
          sources: ['docs/networking.md'],
          correlation_id: 'corr-smoke-001',
        }),
      }),
    )

    await page.goto('/')
  })

  test('header shows user_id and role after auth', async ({ page }) => {
    // Auth loads asynchronously — wait for user_id to appear
    await expect(page.getByText('smoke-test@example.com')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('developer')).toBeVisible()
  })

  test('typing a FAQ question and pressing Enter renders the answer', async ({ page }) => {
    // Wait for auth to settle
    await page.waitForTimeout(300)

    const textarea = page.getByRole('textbox', { name: /message input/i })
    await textarea.fill('What is VPC peering?')
    await textarea.press('Enter')

    // Loading indicator should appear then resolve
    await expect(page.getByText('Use VPC peering for cross-project connectivity.')).toBeVisible({
      timeout: 5000,
    })
  })

  test('clicking theme toggle adds dark class to <html>', async ({ page }) => {
    await page.waitForTimeout(300)

    // Find the theme toggle button
    const toggle = page.getByRole('button', { name: /switch to dark mode/i })
    await toggle.click()

    // Verify dark class applied to html element
    const htmlClass = await page.evaluate(() => document.documentElement.className)
    expect(htmlClass).toContain('dark')
  })

  test('clicking theme toggle again removes dark class', async ({ page }) => {
    await page.waitForTimeout(300)

    const toggle = page.getByRole('button', { name: /switch to dark mode/i })
    await toggle.click() // → dark

    const toggleAgain = page.getByRole('button', { name: /switch to light mode/i })
    await toggleAgain.click() // → light

    const htmlClass = await page.evaluate(() => document.documentElement.className)
    expect(htmlClass).not.toContain('dark')
  })

  test('no uncaught console errors during the smoke journey', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (err) => errors.push(err.message))

    await page.waitForTimeout(300)

    const textarea = page.getByRole('textbox', { name: /message input/i })
    await textarea.fill('What is VPC peering?')
    await textarea.press('Enter')

    await page.waitForTimeout(1000)

    expect(errors).toHaveLength(0)
  })
})
