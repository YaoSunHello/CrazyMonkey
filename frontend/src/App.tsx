import ylookupBadge from './assets/ylookup-badge.svg'
import agentFlowSketch from './assets/agent-flow-selection.png'
import WorkflowDiagram from './WorkflowDiagram'
import './App.css'

const REPO_URL = 'https://github.com/YaoSunHello/CrazyMonkey'

const badges = [
  { label: 'Privacy First', tone: 'neutral' },
  { label: 'Claude · AI Extraction', tone: 'accent' },
  { label: 'Codex · Build Agent', tone: 'neutral' },
  { label: 'Private Markets · Fund Data', tone: 'teal' },
  { label: 'Encode Hackathon', tone: 'blue' },
] as const

const agenda = [
  {
    title: 'Ingest messy documents',
    body: 'PDFs, financial statements, NAV packs, and investor reports — whatever lands in the inbox.',
  },
  {
    title: 'Extract with traceability',
    body: 'Raw text, tables, periods, entities, and metrics, each tied back to a source reference.',
  },
  {
    title: 'Normalize into schemas',
    body: 'Consistent, model-ready values instead of a dozen label variants for the same field.',
  },
  {
    title: 'Review low-confidence fields',
    body: 'A workflow built for analysts to validate the numbers a model wasn’t sure about.',
  },
  {
    title: 'Export clean datasets',
    body: 'CSV, Excel, or JSON — ready to drop straight into a model.',
  },
]

function App() {
  return (
    <>
      <header className="site-header">
        <div className="shell site-header__inner">
          <a href="#top" className="wordmark">
            <span className="wordmark__mark">🐒</span>
            CrazyMonkey
          </a>
          <nav className="site-nav">
            <a href="#workflow">Workflow</a>
            <a href="#product">Product</a>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              GitHub
            </a>
          </nav>
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="shell hero__inner">
            <p className="kicker">Hackathon MVP</p>
            <h1>
              Turn messy fund documents into
              <br />
              clean, model-ready data.
            </h1>
            <p className="hero__lede">
              CrazyMonkey is built for fund managers and investment teams. It
              transforms PDFs, statements, NAV packs, and portfolio reports
              into traceable, structured data analysts can validate and
              export &mdash; the step before IC materials get built.
            </p>
            <div className="hero__cta">
              <a
                className="btn btn--primary"
                href={REPO_URL}
                target="_blank"
                rel="noreferrer"
              >
                View on GitHub
              </a>
              <a className="btn btn--ghost" href="#workflow">
                See the workflow
              </a>
            </div>
            <ul className="badge-row">
              {badges.map((badge) => (
                <li key={badge.label} className={`badge badge--${badge.tone}`}>
                  {badge.label}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="section" id="workflow">
          <div className="shell">
            <p className="section__kicker">MVP Workflow</p>
            <h2 className="section__title">
              We sketched this on a notepad before we built it.
            </h2>
            <p className="section__lede">
              Six agent-driven steps take a document from raw upload to a
              structured dataset &mdash; and every field stays traceable back
              to its source.
            </p>
            <WorkflowDiagram />

            <figure className="sketch-panel">
              <img src={agentFlowSketch} alt="Original team whiteboard sketch of the agent flow" />
              <figcaption>the original sketch</figcaption>
            </figure>
          </div>
        </section>

        <section className="section section--alt" id="product">
          <div className="shell">
            <p className="section__kicker">Product Agenda</p>
            <h2 className="section__title">
              Auditable numbers, not summary-only output.
            </h2>
            <div className="agenda-grid">
              {agenda.map((item) => (
                <div key={item.title} className="agenda-card">
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="shell site-footer__inner">
          <p>
            Built at Encode Hackathon &middot;{' '}
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              github.com/YaoSunHello/CrazyMonkey
            </a>
          </p>
          <a
            className="sponsor"
            href="https://www.ylookup.ai/"
            target="_blank"
            rel="noreferrer"
          >
            <img src={ylookupBadge} alt="Sponsor: Ylookup" height={26} />
          </a>
        </div>
      </footer>
    </>
  )
}

export default App
