import { describe, expect, it } from 'vitest'
import { phrasesToText, textToPhrases } from './styleForm'

describe('styleForm', () => {
  it('round-trips phrases and drops blanks and duplicates', () => {
    expect(textToPhrases('leverage\n\nrobust\nLeverage')).toEqual(['leverage', 'robust'])
    expect(phrasesToText(['leverage', 'robust'])).toBe('leverage\nrobust')
  })
})
