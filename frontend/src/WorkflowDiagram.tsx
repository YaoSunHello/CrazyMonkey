import './WorkflowDiagram.css'

type Stage = {
  n: number
  title: string
  sub: string
  x: number
}

const STAGES: Stage[] = [
  { n: 1, title: 'Upload', sub: 'keeps source + context', x: 300 },
  { n: 2, title: 'Classify', sub: 'sets doc type + goal', x: 492 },
  { n: 3, title: 'Extract', sub: 'tables + metrics', x: 684 },
  { n: 4, title: 'Normalize', sub: 'canonical schema', x: 876 },
  { n: 5, title: 'Review', sub: 'human checks the math', x: 1068 },
  { n: 6, title: 'Export', sub: 'CSV · XLSX · JSON', x: 1260 },
]

const OVAL_RX = 76
const OVAL_RY = 54
const CY = 150
const DOC_X = 108
const OUT_X = 1452

function arrowBetween(x1: number, x2: number, key: string) {
  const midY = CY + (key.charCodeAt(0) % 3 === 0 ? -6 : 6)
  const tipX = x2 - 4
  return (
    <g key={key}>
      <path d={`M${x1},${CY} Q${(x1 + x2) / 2},${midY} ${x2},${CY}`} />
      <path d={`M${tipX - 12},${CY - 8} L${tipX},${CY} L${tipX - 12},${CY + 8}`} />
    </g>
  )
}

export default function WorkflowDiagram() {
  return (
    <div className="board">
      <div className="board__margin" aria-hidden="true" />
      <svg
        className="board__svg"
        viewBox="0 0 1560 320"
        role="img"
        aria-label="Diagram: documents flow through Upload, Classify, Extract, Normalize, Review, and Export to produce structured data."
      >
        <defs>
          <filter id="sketchy" x="-20%" y="-20%" width="140%" height="140%">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.018"
              numOctaves={2}
              seed={7}
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

        {/* connectors + output outline, drawn in accent ink */}
        <g
          filter="url(#sketchy)"
          fill="none"
          stroke="var(--accent-strong)"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {arrowBetween(DOC_X + 66, STAGES[0].x - OVAL_RX, 'a0')}
          {STAGES.slice(0, -1).map((s, i) =>
            arrowBetween(s.x + OVAL_RX, STAGES[i + 1].x - OVAL_RX, `a${s.n}`),
          )}
          {arrowBetween(
            STAGES[STAGES.length - 1].x + OVAL_RX,
            OUT_X - 92,
            'aout',
          )}
          <rect
            x={OUT_X - 92}
            y={CY - 34}
            width={184}
            height={68}
            rx={14}
          />
        </g>

        {/* shapes, drawn in ink */}
        <g
          filter="url(#sketchy)"
          fill="none"
          stroke="var(--ink)"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x={DOC_X - 54} y={CY - 44} width={108} height={72} rx={8} />
          <rect x={DOC_X - 46} y={CY - 52} width={108} height={72} rx={8} />
          <rect x={DOC_X - 38} y={CY - 60} width={108} height={72} rx={8} />

          {STAGES.map((s) => (
            <ellipse key={s.n} cx={s.x} cy={CY} rx={OVAL_RX} ry={OVAL_RY} />
          ))}

          {STAGES.map((s) => (
            <circle
              key={`c${s.n}`}
              cx={s.x - OVAL_RX + 8}
              cy={CY - OVAL_RY + 4}
              r={16}
            />
          ))}
        </g>

        {/* crisp labels, kept outside the sketch filter for legibility */}
        <g className="labels">
          <text x={DOC_X} y={CY - 66} className="tag">
            raw documents
          </text>
          <text x={DOC_X} y={CY + 46} className="tag tag--sub">
            PDF · XLSX
          </text>
          <text x={DOC_X} y={CY + 60} className="tag tag--sub">
            PPTX · CSV · Email
          </text>

          {STAGES.map((s) => (
            <text
              key={`n${s.n}`}
              className="number"
              x={s.x - OVAL_RX + 8}
              y={CY - OVAL_RY + 5}
            >
              {s.n}
            </text>
          ))}
          {STAGES.map((s) => (
            <text key={`t${s.n}`} x={s.x} y={CY - 4} className="title">
              {s.title}
            </text>
          ))}
          {STAGES.map((s) => (
            <text key={`s${s.n}`} x={s.x} y={CY + 20} className="sub">
              {s.sub}
            </text>
          ))}

          <text x={OUT_X} y={CY - 4} className="title title--accent">
            Structured
          </text>
          <text x={OUT_X} y={CY + 20} className="title title--accent">
            Data
          </text>

          <text x={1068} y={68} className="annotation">
            you approve every field
          </text>
          <path
            className="annotation__arrow"
            d="M1090,78 C1082,92 1078,102 1074,112"
          />
        </g>
      </svg>

      <p className="board__stamp">
        sketched by the CrazyMonkey team &middot; hackathon whiteboard, v1
      </p>
    </div>
  )
}
