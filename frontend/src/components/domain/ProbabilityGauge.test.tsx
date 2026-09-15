import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProbabilityGauge } from '@/components/domain/ProbabilityGauge'

describe('ProbabilityGauge', () => {
  it('shows the probability as text, not only as colour', () => {
    render(<ProbabilityGauge pUp={0.62} label="1 saat" />)
    expect(screen.getByText('%62')).toBeInTheDocument()
    expect(screen.getByText('1 saat')).toBeInTheDocument()
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '62')
  })

  it('renders a neutral gauge at fifty percent', () => {
    render(<ProbabilityGauge pUp={0.5} />)
    const value = screen.getByText('%50')
    expect(value.className).toContain('text-neutral')
  })

  it('marks a downward probability', () => {
    render(<ProbabilityGauge pUp={0.3} />)
    expect(screen.getByText('%30').className).toContain('text-down')
  })
})
