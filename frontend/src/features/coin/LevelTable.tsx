import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { formatPrice, formatScore } from '@/lib/format'
import type { Levels } from '@/api/types'
import { tr } from '@/i18n/tr'

/** Mekanik seviyeler: kaç kez dokunulmuş ve fiyattan kaç ATR uzakta. */
export function LevelTable({ levels }: { levels: Levels | null }) {
  if (!levels || levels.levels.length === 0) {
    return <p className="text-sm text-muted">{tr.coin.noLevels}</p>
  }
  const profile = levels.volume_profile
  return (
    <div className="flex flex-col gap-2">
      {profile ? (
        <p className="text-xs text-muted">
          {tr.coin.poc}: <span className="num">{formatPrice(profile.poc)}</span> ·{' '}
          {tr.coin.valueArea}:{' '}
          <span className="num">
            {formatPrice(profile.value_area_low)} – {formatPrice(profile.value_area_high)}
          </span>
        </p>
      ) : null}
      <Table>
        <thead>
          <Tr>
            <Th>{tr.coin.levelKind}</Th>
            <Th align="right">{tr.coin.levelPrice}</Th>
            <Th align="right">{tr.coin.touches}</Th>
            <Th align="right">{tr.coin.distanceAtr}</Th>
          </Tr>
        </thead>
        <tbody>
          {levels.levels.map((level) => (
            <Tr key={`${level.kind}-${level.price}`}>
              <Td>
                <span className={level.kind === 'high' ? 'text-down' : 'text-up'}>
                  {level.kind === 'high' ? tr.coin.resistance : tr.coin.support}
                </span>
              </Td>
              <Td align="right" mono>
                {formatPrice(level.price)}
              </Td>
              <Td align="right" mono>
                {level.touches}
              </Td>
              <Td align="right" mono>
                {formatScore(level.distance_atr, 2)}
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}
