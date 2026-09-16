import { ScoreBar } from '@/components/domain/ScoreBar'
import { formatProbability, formatScore } from '@/lib/format'
import { moduleLabel, componentLabel } from '@/components/domain/moduleLabels'
import type { ModuleSignal } from '@/api/types'
import { tr } from '@/i18n/tr'

/**
 * Hangi modül ne dedi ve ne kadar veriyle dedi.
 * Kapsaması sıfır olan modül "veri yok" olarak görünür; gizlenmez (CLAUDE.md §2).
 */
export function ModuleBreakdown({ modules }: { modules: ModuleSignal[] }) {
  if (modules.length === 0) {
    return <p className="text-sm text-muted">{tr.coin.noModules}</p>
  }
  return (
    <div className="flex flex-col gap-3">
      {modules.map((module) => (
        <div key={module.module} className="flex flex-col gap-1">
          <ScoreBar
            label={moduleLabel(module.module)}
            score={module.score}
            muted={module.coverage === 0}
            hint={
              module.coverage === 0
                ? tr.coin.noData
                : `${tr.coin.coverage} ${formatProbability(module.coverage)} · ${tr.confidence.label} ${formatScore(module.confidence, 2)}`
            }
          />
          {module.components && Object.keys(module.components).length > 0 ? (
            <ul className="ml-2 flex flex-col gap-0.5 border-l border-border pl-2">
              {Object.entries(module.components).map(([name, value]) => (
                <li key={name} className="flex items-baseline justify-between gap-2 text-xs">
                  <span className="text-muted">{componentLabel(name)}</span>
                  <span className="num">{formatScore(value, 2)}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
    </div>
  )
}
