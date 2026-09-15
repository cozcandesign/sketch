import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { HitBadge, OutcomeBadge } from '@/components/domain/OutcomeBadge'
import { confidenceLabelTr } from '@/components/domain/confidence'
import { formatPercent, formatPrice, formatProbability, formatScore } from '@/lib/format'
import { formatDateTime } from '@/lib/time'
import { modelLabel } from '@/features/predictions/modelLabel'
import type { Prediction } from '@/api/types'
import { HORIZON_LABELS, type HorizonKey } from '@/api/types'
import { tr } from '@/i18n/tr'

export function PredictionTable({
  rows,
  onSelect,
}: {
  rows: Prediction[]
  onSelect: (id: number) => void
}) {
  const columns = tr.predictions.columns
  return (
    <Table>
      <thead>
        <tr>
          <Th>{columns.asOf}</Th>
          <Th>{columns.symbol}</Th>
          <Th>{columns.horizon}</Th>
          <Th>{columns.model}</Th>
          <Th align="right">{columns.pUp}</Th>
          <Th>{columns.confidence}</Th>
          <Th align="right">{columns.priceAt}</Th>
          <Th align="right">{columns.change}</Th>
          <Th>{columns.result}</Th>
          <Th>{columns.hit}</Th>
          <Th align="right">{columns.brier}</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <Tr key={row.id} onClick={() => onSelect(row.id)}>
            <Td mono>{formatDateTime(row.as_of)}</Td>
            <Td>{row.symbol}</Td>
            <Td>{HORIZON_LABELS[row.horizon as HorizonKey] ?? row.horizon}</Td>
            <Td>{modelLabel(row.model_version)}</Td>
            <Td align="right" mono>
              {formatProbability(row.p_up)}
            </Td>
            <Td>{confidenceLabelTr(row.confidence_label)}</Td>
            <Td align="right" mono>
              {formatPrice(row.price_at)}
            </Td>
            <Td align="right" mono>
              {formatPercent(row.outcome?.realized_return)}
            </Td>
            <Td>
              <OutcomeBadge outcome={row.outcome} />
            </Td>
            <Td>
              <HitBadge hit={row.outcome?.hit} />
            </Td>
            <Td align="right" mono>
              {formatScore(row.outcome?.brier)}
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}
