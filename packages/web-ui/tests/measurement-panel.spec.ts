import { test, expect } from '@playwright/test'

const measurementHint = 'Measurement comparisons activate once an optimisation run completes.'

test.describe('Measurement panel', () => {
  test('shows measurement prerequisites by default', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByText('Measurement Check')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Compare' })).toBeVisible()
    await expect(page.getByText(measurementHint)).toBeVisible()
  })
})
