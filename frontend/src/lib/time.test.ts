import { describe, expect, it } from 'vitest'
import { ageSeconds, relativeTime } from '@/lib/time'

const now = new Date('2026-01-01T12:00:00Z')
const labels = { never: 'hiç' }

describe('relativeTime', () => {
  it('handles null as never', () => {
    expect(relativeTime(null, now, labels)).toBe('hiç')
  })
  it('formats seconds, minutes, hours and days', () => {
    expect(relativeTime('2026-01-01T11:59:48Z', now, labels)).toBe('12 sn önce')
    expect(relativeTime('2026-01-01T11:57:00Z', now, labels)).toBe('3 dk önce')
    expect(relativeTime('2026-01-01T09:30:00Z', now, labels)).toBe('2 sa önce')
    expect(relativeTime('2025-12-28T12:00:00Z', now, labels)).toBe('4 g önce')
  })
  it('never returns negative for future timestamps', () => {
    expect(relativeTime('2026-01-01T12:00:05Z', now, labels)).toBe('0 sn önce')
  })
})

describe('ageSeconds', () => {
  it('returns null for missing and seconds otherwise', () => {
    expect(ageSeconds(null, now)).toBeNull()
    expect(ageSeconds('2026-01-01T11:59:30Z', now)).toBe(30)
  })
})
