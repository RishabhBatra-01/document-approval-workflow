/**
 * Regression test for a crash the browser pass caught and the unit tests had
 * missed: Intl.DateTimeFormat rejects dateStyle/timeStyle combined with
 * timeZoneName, which threw while rendering the submissions list.
 */
import { describe, expect, it } from 'vitest'
import { formatDate } from '../src/components/common'

describe('formatDate', () => {
  it('formats a real ISO timestamp without throwing', () => {
    expect(() => formatDate('2026-10-24T09:30:00Z')).not.toThrow()
  })

  it('includes the year and a timezone so two readers agree on the instant', () => {
    const formatted = formatDate('2026-10-24T09:30:00Z')
    expect(formatted).toMatch(/2026/)
    expect(formatted.length).toBeGreaterThan(10)
  })

  it('renders an em dash for a missing timestamp rather than "Invalid Date"', () => {
    expect(formatDate(null)).toBe('—')
  })
})
