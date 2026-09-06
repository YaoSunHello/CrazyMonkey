import { useEffect, useId, useMemo, useState } from "react";
import type { JobResult, ResultDocument, WorkspaceAdapter } from "../workspaceTypes";
import {
  formatExact, parseTransactionCsv, scaledUnits, statementMovements, sumExact,
  type ExactDecimal, type TransactionCsvRow,
} from "../utils/statementCsv";

interface FinancialMovementChartProps {
  result: JobResult;
  document?: ResultDocument;
  fetchCsv: WorkspaceAdapter["fetchTransactionCsv"];
  downloadUrl: string;
  onSelectFinding(findingId: string): void;
}

type CsvState = { state: "LOADING" } | { state: "READY"; text: string } | { state: "ERROR"; message: string };

export function FinancialMovementChart(props: FinancialMovementChartProps) {
  const csv = props.result.exports?.transactions_csv;
  if (!csv) return null;
  return <CsvMovementPanel key={`${props.result.job_id}:${csv.sha256}`} {...props} />;
}

function CsvMovementPanel({ result, document, fetchCsv, downloadUrl, onSelectFinding }: FinancialMovementChartProps) {
  const csv = result.exports!.transactions_csv!;
  const headingId = useId();
  const [state, setState] = useState<CsvState>({ state: "LOADING" });
  const [attempt, setAttempt] = useState(0);
  const jobId = result.job_id;

  useEffect(() => {
    const controller = new AbortController();
    void fetchCsv(jobId, csv.sha256, controller.signal).then((text) => {
      if (!controller.signal.aborted) setState({ state: "READY", text });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setState({
        state: "ERROR",
        message: error instanceof Error ? error.message : "The transaction CSV could not be loaded.",
      });
    });
    return () => controller.abort();
  }, [attempt, csv.sha256, fetchCsv, jobId]);

  const parsed = useMemo(() => {
    if (state.state !== "READY") return undefined;
    try { return { rows: parseTransactionCsv(state.text, result, csv.row_count) }; }
    catch (error) { return { error: error instanceof Error ? error.message : "The CSV could not be validated." }; }
  }, [csv.row_count, result, state]);
  const error = state.state === "ERROR" ? state.message : parsed?.error;
  const movements = parsed?.rows && document ? statementMovements(parsed.rows, document) : undefined;
  const retry = () => { setState({ state: "LOADING" }); setAttempt((current) => current + 1); };

  return (
    <section className="financial-movements" aria-labelledby={headingId}>
      <div className="movement-heading">
        <div>
          <p className="step-label">From the generated transaction CSV</p>
          <h2 id={headingId}>Financial movements</h2>
          <p>{document?.statement
            ? `${document.statement.account_short_code} · ${document.statement.currency} · ${document.filename}`
            : "Select a successfully parsed statement to view its movements."}</p>
        </div>
        <a className="button button-secondary" href={downloadUrl} download={csv.filename}>Download transaction CSV</a>
      </div>
      <p className="movement-disclaimer">Extracted statement data, not financial classification or agent resolution. The download contains all statements in this review.</p>
      {state.state === "LOADING" && <p role="status">Loading the generated transaction CSV…</p>}
      {error && <div className="movement-error" role="alert">
        <strong>Financial movements are unavailable.</strong>
        <p>{error} The statement checks and original evidence remain available below.</p>
        <button className="button button-secondary" type="button" onClick={retry}>Retry CSV connection</button>
      </div>}
      {movements && !error && (movements.rows.length > 0 ? (
        <MovementData key={document!.source_id} data={movements} currency={document!.statement!.currency} onSelectFinding={onSelectFinding} />
      ) : <p role="status">No exported transaction rows match this document's account and currency. {movements.outsideAccount.length > 0 && `${movements.outsideAccount.length} source rows have a different account or currency and are excluded from the chart.`} Nothing has been substituted or estimated.</p>)}
      <p className="movement-provenance">CSV export: {csv.row_count} rows across this review · SHA-256 <code title={csv.sha256}>{csv.sha256.slice(0, 12)}…</code></p>
    </section>
  );
}

function MovementData({ data, currency, onSelectFinding }: {
  data: ReturnType<typeof statementMovements>;
  currency: string;
  onSelectFinding(findingId: string): void;
}) {
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const missing = data.missingMovements.length > 0 || data.missingBalances.length > 0 || data.undated.length > 0 || data.outsideAccount.length > 0;
  const hasMovements = data.missingMovements.length < data.rows.length;
  return <>
    <dl className="movement-kpis">
      <div><dt>Money in <small>Positive movements</small></dt><dd>{formatExact(hasMovements ? data.inflows : null)} <span>{currency}</span></dd></div>
      <div><dt>Money out <small>Negative movements</small></dt><dd>{formatExact(hasMovements ? data.outflows : null)} <span>{currency}</span></dd></div>
      <div><dt>Net movement <small>All available movements</small></dt><dd>{formatExact(hasMovements ? data.net : null)} <span>{currency}</span></dd></div>
    </dl>
    <p className="movement-status-summary">
      {data.rows.length} source rows · {data.passed} balance links pass · {data.failed} fail · {data.unchecked} not checked.
      {" "}An oldest row has no earlier neighbor to check. Chart totals do not certify statement correctness.
    </p>
    {missing && <details className="movement-exclusions">
      <summary>Data coverage: {data.missingMovements.length} missing movements, {data.missingBalances.length} missing balances, {data.undated.length} undated rows{data.outsideAccount.length > 0 && `, ${data.outsideAccount.length} account/currency exclusions`}</summary>
      <p>Missing movements are excluded from totals and bars, not treated as zero. Missing balances create gaps in the balance line. Undated rows remain in source-chain order.</p>
      <ul>
        {data.missingMovements.length > 0 && <li>No movement: source rows {rowNumbers(data.missingMovements)}.</li>}
        {data.missingBalances.length > 0 && <li>No balance: source rows {rowNumbers(data.missingBalances)}.</li>}
        {data.undated.length > 0 && <li>No normalized date: source rows {rowNumbers(data.undated)}. Raw dates remain in the CSV.</li>}
        {data.outsideAccount.length > 0 && <li>Different account or currency: source rows {rowNumbers(data.outsideAccount)}. Excluded from this chart and its totals; retained in the complete CSV and source checks.</li>}
      </ul>
    </details>}
    <MovementSvg rows={data.rows} currency={currency} onSelectFinding={onSelectFinding} />
    <details className="movement-values">
      <summary>View exact transaction values and source checks ({data.rows.length} rows)</summary>
      <div className="movement-table-scroll" role="region" aria-label="Exact transaction values" tabIndex={0}>
        <table>
          <caption>{currency} · Original source-chain order, oldest to newest. Values are read from the generated CSV.</caption>
          <thead><tr>
            <th scope="col">Source row</th><th scope="col">Date</th><th scope="col">Narrative</th>
            <th scope="col">Credit</th><th scope="col">Debit</th><th scope="col">Signed movement</th>
            <th scope="col">Recorded balance</th><th scope="col">Balance check</th>
          </tr></thead>
          <tbody>{data.rows.slice(page * pageSize, (page + 1) * pageSize).map((row) => <tr key={row.rowId}>
            <th scope="row">{row.sourceIndex + 1}<small>PDF p. {row.citationPage}</small></th>
            <td>{row.valueDateIso || row.valueDate || "Not available"}</td><td>{row.narrative || "Not provided"}</td>
            <td>{formatExact(row.credit)}</td><td>{formatExact(row.debit)}</td><td>{formatExact(row.movement)}</td><td>{formatExact(row.balance)}</td>
            <td>{row.findingId
              ? <button type="button" onClick={() => onSelectFinding(row.findingId)}>Inspect {row.linkStatus} · row {row.sourceIndex + 1}</button>
              : "Not checked"}</td>
          </tr>)}</tbody>
        </table>
      </div>
      {data.rows.length > pageSize && <div className="movement-pagination">
        <button type="button" disabled={page === 0} onClick={() => setPage((current) => current - 1)}>Previous rows</button>
        <span aria-live="polite">Rows {page * pageSize + 1}–{Math.min((page + 1) * pageSize, data.rows.length)} of {data.rows.length}</span>
        <button type="button" disabled={(page + 1) * pageSize >= data.rows.length} onClick={() => setPage((current) => current + 1)}>Next rows</button>
      </div>}
    </details>
  </>;
}

function rowNumbers(rows: TransactionCsvRow[]): string {
  return rows.slice(0, 30).map((row) => row.sourceIndex + 1).join(", ") + (rows.length > 30 ? ` and ${rows.length - 30} more (see exact values)` : "");
}

interface PlotPoint {
  rows: TransactionCsvRow[];
  balance: ExactDecimal | null;
  movement: ExactDecimal | null;
}

function MovementSvg({ rows, currency, onSelectFinding }: {
  rows: TransactionCsvRow[];
  currency: string;
  onSelectFinding(findingId: string): void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  // Bound SVG elements for large statements without excluding any row from totals or the exact table.
  const groupSize = Math.max(1, Math.ceil(rows.length / 180));
  const points: PlotPoint[] = [];
  for (let index = 0; index < rows.length; index += groupSize) {
    const group = rows.slice(index, index + groupSize);
    const continuous = group.every((row, offset) => offset === 0 || row.chainOrder === group[offset - 1].chainOrder + 1);
    points.push({
      rows: group,
      // Never bridge a missing balance or imply an unknown movement was zero.
      balance: !continuous || group.some((row) => !row.balance) ? null : group[group.length - 1].balance,
      movement: group.some((row) => !row.movement) ? null : sumExact(group.map((row) => row.movement!)),
    });
  }
  const values = points.flatMap((point) => [point.balance, point.movement].filter((value): value is ExactDecimal => value !== null));
  const scale = values.reduce((maximum, value) => Math.max(maximum, value.scale), 2);
  const balances = points.flatMap((point) => point.balance ? [scaledUnits(point.balance, scale)] : []);
  const low = balances.reduce((minimum, value) => value < minimum ? value : minimum, balances[0] ?? 0n);
  const high = balances.reduce((maximum, value) => value > maximum ? value : maximum, balances[0] ?? 0n);
  const maximumMovement = points.reduce((maximum, point) => {
    const units = point.movement ? scaledUnits(point.movement, scale) : 0n;
    const absolute = units < 0n ? -units : units;
    return absolute > maximum ? absolute : maximum;
  }, 0n);
  const ratio = (numerator: bigint, denominator: bigint) => denominator === 0n ? 0 : Number((numerator * 1_000_000n) / denominator) / 1_000_000;
  const x = (index: number) => 115 + (points.length === 1 ? 365 : (index / (points.length - 1)) * 730);
  const balanceY = (value: ExactDecimal) => high === low ? 93 : 146 - ratio(scaledUnits(value, scale) - low, high - low) * 105;
  const zeroY = 246;
  const movementY = (value: ExactDecimal) => zeroY - ratio(scaledUnits(value, scale), maximumMovement) * 50;
  const barWidth = Math.max(2, Math.min(20, 600 / points.length));
  let priorBalance = false;
  const path = points.map((point, index) => {
    if (!point.balance) { priorBalance = false; return ""; }
    const previous = points[index - 1];
    const adjacent = previous && point.rows[0].chainOrder === previous.rows[previous.rows.length - 1].chainOrder + 1;
    const command = `${priorBalance && adjacent ? "L" : "M"}${x(index)},${balanceY(point.balance)}`;
    priorBalance = true;
    return command;
  }).join(" ");
  const rangeLabel = (point: PlotPoint) => point.rows.length === 1
    ? `Source row ${point.rows[0].sourceIndex + 1}`
    : `Source rows ${point.rows[0].sourceIndex + 1}–${point.rows[point.rows.length - 1].sourceIndex + 1}`;
  return <div className="movement-chart">
    <div className="movement-legend" aria-label="Chart legend">
      <span><i className="legend-balance" aria-hidden="true" />Recorded balance</span>
      <span><i className="legend-inflow" aria-hidden="true" />Positive movement ↑</span>
      <span><i className="legend-outflow" aria-hidden="true" />Negative movement ↓</span>
      <span><i className="legend-failure" aria-hidden="true" />Failed balance link ×</span>
    </div>
    <div className="movement-svg-scroll" role="region" aria-label="Financial movement plot" tabIndex={0}>
    <svg viewBox="0 0 890 330" role="img" aria-labelledby={`${titleId} ${descriptionId}`}>
      <title id={titleId}>Recorded balance and signed movements in {currency}</title>
      <desc id={descriptionId}>Oldest-to-newest source-chain order, not intraday time order. Balance is a line on its own scale; signed movements are bars around zero. Failed links have cross markers. Exact values and keyboard-accessible finding buttons are in the table below.</desc>
      <text x="12" y="20" className="plot-section-title">Balance · {currency}</text>
      <text x="12" y="184" className="plot-section-title">Movement · {currency}</text>
      <line x1="110" x2="855" y1="146" y2="146" className="plot-grid" />
      <line x1="110" x2="855" y1={zeroY} y2={zeroY} className="plot-zero" />
      {balances.length > 0 ? <text x="12" y={high === low ? 96 : 48} className="plot-axis">{axisLabel({ units: high, scale })}</text>
        : <text x="115" y="93" className="plot-axis">{rows.some((row) => row.balance) ? "No continuous balance groups to display" : "No recorded balances available"}</text>}
      {high !== low && <text x="12" y="148" className="plot-axis">{axisLabel({ units: low, scale })}</text>}
      <text x="90" y={zeroY + 4} className="plot-axis">0</text>
      <path d={path} className="balance-path" />
      {points.map((point, index) => {
        const failing = point.rows.find((row) => row.linkStatus === "FAIL");
        const finding = failing ?? point.rows.find((row) => row.findingId);
        const title = `${rangeLabel(point)}: balance ${formatExact(point.balance)} ${currency}; movement ${formatExact(point.movement)} ${currency}${failing ? "; failed balance link" : ""}`;
        const barY = point.movement ? movementY(point.movement) : zeroY;
        return <g key={point.rows[0].rowId} className={finding ? "plot-source-point" : undefined}
          onClick={finding ? () => onSelectFinding(finding.findingId) : undefined}>
          <title>{title}</title>
          {point.balance && <circle cx={x(index)} cy={balanceY(point.balance)} r={points.length > 70 ? 2 : 3} className="balance-point" />}
          {point.movement && <rect x={x(index) - barWidth / 2} y={Math.min(barY, zeroY)} width={barWidth}
            height={Math.max(point.movement.units === 0n ? 1 : 2, Math.abs(zeroY - barY))}
            className={point.movement.units < 0n ? "movement-bar-out" : "movement-bar-in"} />}
          {failing && <text x={x(index)} y={point.balance ? balanceY(point.balance) - 9 : 35} className="plot-failure" textAnchor="middle">×</text>}
        </g>;
      })}
      <text x="115" y="321" className="plot-axis">Oldest · {rows[0].valueDateIso || `source row ${rows[0].sourceIndex + 1}`}</text>
      <text x="845" y="321" className="plot-axis" textAnchor="end">Newest · {rows[rows.length - 1].valueDateIso || `source row ${rows[rows.length - 1].sourceIndex + 1}`}</text>
    </svg>
    </div>
    <p className="movement-chart-note">Recorded balances are plotted as supplied, including failed links; no opening balance is inferred. {groupSize > 1
      ? `Display groups up to ${groupSize} matching source rows per bar (net movement) and plots each group's final recorded balance. Missing values or excluded rows create gaps in the balance line. All matching rows remain in the totals and table.`
      : "Each point/bar represents a source row. Select a point to inspect its check, or use the finding buttons in the exact-values table."}</p>
  </div>;
}

function axisLabel(value: ExactDecimal): string {
  const absolute = value.units < 0n ? -value.units : value.units;
  for (const [power, suffix] of [[12, "T"], [9, "B"], [6, "M"]] as const) {
    const divisor = 10n ** BigInt(value.scale + power);
    if (absolute >= divisor) return `${value.units < 0n ? "−" : ""}${formatExact({ units: absolute * 100n / divisor, scale: 2 })}${suffix}`;
  }
  return formatExact(value);
}
