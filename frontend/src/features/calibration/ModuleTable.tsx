import { Badge } from '@/components/ui/Badge'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { formatCount, formatProbability } from '@/lib/format'
import type { ModuleSummary } from '@/api/types'
import { tr } from '@/i18n/tr'

/** Modülün "işe yarıyor mu" hükmü: K26 gereği alt sınır + en az 200 örnek. */
function verdict(row: ModuleSummary): { label: string; tone: 'up' | 'down' | 'muted' } {
  if (row.beats_reference == null) return { label: tr.calibration.verdicts.unknown, tone: 'muted' }
  if (!row.has_proof_sample) return { label: tr.calibration.verdicts.proving, tone: 'muted' }
  return row.beats_reference
    ? { label: tr.calibration.verdicts.beats, tone: 'up' }
    : { label: tr.calibration.verdicts.fails, tone: 'down' }
}

export function ModuleTable({
  modules,
  reference,
}: {
  modules: ModuleSummary[]
  reference: number | null
}) {
  if (modules.length === 0) {
    return <p className="text-sm text-muted">{tr.calibration.moduleEmpty}</p>
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted">
        {tr.calibration.referenceLine}: <span className="num">{formatProbability(reference)}</span>{' '}
        · {tr.calibration.referenceHint}
      </p>
      <Table>
        <thead>
          <tr>
            <Th>{tr.calibration.moduleColumn}</Th>
            <Th align="right">{tr.calibration.sampleCount}</Th>
            <Th align="right">{tr.calibration.skipped}</Th>
            <Th align="right">{tr.calibration.hitRate}</Th>
            <Th align="right">{tr.calibration.ciLabel}</Th>
            <Th align="right">{tr.calibration.verdict}</Th>
          </tr>
        </thead>
        <tbody>
          {modules.map((row) => {
            const state = verdict(row)
            return (
              <Tr key={row.module}>
                <Td>{row.label_tr}</Td>
                <Td align="right" mono>
                  {formatCount(row.n)}
                </Td>
                <Td align="right" mono>
                  {formatCount(row.skipped)}
                </Td>
                <Td align="right" mono>
                  {formatProbability(row.hit_rate)}
                </Td>
                <Td align="right" mono>
                  {row.hit_ci_low == null
                    ? tr.common.none
                    : `${formatProbability(row.hit_ci_low)} – ${formatProbability(row.hit_ci_high)}`}
                </Td>
                <Td align="right">
                  <Badge tone={state.tone}>{state.label}</Badge>
                </Td>
              </Tr>
            )
          })}
        </tbody>
      </Table>
    </div>
  )
}
