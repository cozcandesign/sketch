import { describe, expect, it } from 'vitest'
import { isVersionMismatch } from '@/lib/build'

describe('isVersionMismatch', () => {
  it('warns when the two commits differ', () => {
    expect(isVersionMismatch('aaa1111', 'bbb2222')).toBe(true)
  })

  it('stays quiet when they match', () => {
    expect(isVersionMismatch('aaa1111', 'aaa1111')).toBe(false)
  })

  it('stays quiet when either side is unknown', () => {
    expect(isVersionMismatch('aaa1111', 'bilinmiyor')).toBe(false)
    expect(isVersionMismatch('bilinmiyor', 'bbb2222')).toBe(false)
    expect(isVersionMismatch('aaa1111', undefined)).toBe(false)
  })
})
