import type { RunProgress } from '../types'
import './RunAnimation.css'

const STAGE_LABELS = ['Upload', 'Classify', 'Extract', 'Normalize', 'Review', 'Export']

const N = STAGE_LABELS.length
const OVAL_RX = 74
const OVAL_RY = 50
const CY = 90
const GAP = 190
const START_X = 110
const VIEW_W = START_X + GAP * (N - 1) + OVAL_RX + 40

function stageX(i: number) {
  return START_X + GAP * i
}

export default function RunAnimation({ progress }: { progress: RunProgress | null }) {
  const activeIndex = progress?.stageIndex ?? 0
  const isDone = progress?.done ?? false

  return (
    <div className="run-animation">
      <div className="run-animation__scroll">
        <svg
          className="run-animation__svg"
          viewBox={`0 0 ${VIEW_W} 180`}
          role="img"
          aria-label={`Agent pipeline running, currently on ${STAGE_LABELS[activeIndex]}`}
        >
          <defs>
            <filter id="ra-sketchy" x="-20%" y="-20%" width="140%" height="140%">
              <feTurbulence
                type="fractalNoise"
                baseFrequency="0.018"
                numOctaves={2}
                seed={11}
                result="noise"
              />
              <feDisplacementMap
                in="SourceGraphic"
                in2="noise"
                scale={5}
                xChannelSelector="R"
                yChannelSelector="G"
              />
            </filter>
          </defs>

          <g filter="url(#ra-sketchy)" fill="none" stroke="var(--accent-strong)" strokeWidth={2.5} strokeLinecap="round">
            {STAGE_LABELS.slice(0, -1).map((_, i) => {
              const x1 = stageX(i) + OVAL_RX
              const x2 = stageX(i + 1) - OVAL_RX
              const tipX = x2 - 4
              return (
                <g key={`arrow-${i}`}>
                  <path d={`M${x1},${CY} Q${(x1 + x2) / 2},${CY - 8} ${x2},${CY}`} />
                  <path d={`M${tipX - 12},${CY - 8} L${tipX},${CY} L${tipX - 12},${CY + 8}`} />
                </g>
              )
            })}
          </g>

          <g filter="url(#ra-sketchy)" fill="none" strokeWidth={2.5} strokeLinecap="round">
            {STAGE_LABELS.map((_, i) => {
              const complete = isDone ? true : i < activeIndex
              const active = !isDone && i === activeIndex
              const stroke = complete ? 'var(--teal)' : active ? 'var(--accent-strong)' : 'var(--ink)'
              return (
                <ellipse
                  key={`oval-${i}`}
                  cx={stageX(i)}
                  cy={CY}
                  rx={OVAL_RX}
                  ry={OVAL_RY}
                  stroke={stroke}
                  strokeWidth={active ? 3.5 : 2.5}
                  className={active ? 'run-animation__oval--pulse' : ''}
                />
              )
            })}
          </g>

          <g className="run-animation__labels">
            {STAGE_LABELS.map((label, i) => {
              const complete = isDone ? true : i < activeIndex
              const active = !isDone && i === activeIndex
              return (
                <text
                  key={`label-${i}`}
                  x={stageX(i)}
                  y={CY + 6}
                  className={`ra-title${active ? ' ra-title--active' : ''}${complete ? ' ra-title--done' : ''}`}
                >
                  {complete ? `✓ ${label}` : label}
                </text>
              )
            })}
          </g>
        </svg>
      </div>

      <p className="run-animation__caption">{progress?.caption ?? 'Getting started…'}</p>
    </div>
  )
}
