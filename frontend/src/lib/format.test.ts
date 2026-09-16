import { describe, expect, it } from 'vitest'
import {
  formatPercent,
  formatPrice,
  formatProbability,
  formatScore,
  formatUsdCompact,
} from '@/lib/format'

describe('format', () => {
  it('formats probabilities as whole percentages', () => {
    expect(formatProbability(0.62)).toBe('%62')
    expect(formatProbability(0.5)).toBe('%50')
    expect(formatProbability(null)).toBe('—')
  })

  it('formats signed percentage changes', () => {
    expect(formatPercent(0.0123)).toBe('+%1,23')
    expect(formatPercent(-0.05)).toBe('%-5,00')
    expect(formatPercent(null)).toBe('—')
  })

  it('uses more decimals for small prices', () => {
    expect(formatPrice(63000)).toContain('63')
    expect(formatPrice(0.1234)).toBe('0,1234')
    expect(formatPrice(null)).toBe('—')
  })

  it('formats scores with a comma separator', () => {
    expect(formatScore(0.1444)).toBe('0,144')
    expect(formatScore(null)).toBe('—')
  })

  it('shortens usd amounts by magnitude', () => {
    expect(formatUsdCompact(2_450_000_000)).toBe('2,45 Mr $')
    expect(formatUsdCompact(1_250_000)).toBe('1,25 Mn $')
    expect(formatUsdCompact(-42_500)).toBe('-42,5 B $')
    expect(formatUsdCompact(120)).toBe('120 $')
    expect(formatUsdCompact(null)).toBe('—')
  })
})
