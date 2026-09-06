import type { JobResult, ResultDocument } from "../workspaceTypes";

export const TRANSACTION_CSV_COLUMNS = [
  "schema_version", "job_id", "profile_id", "case_name", "execution_label", "agent_resolution_status",
  "job_processing_state", "source_id", "source_filename", "source_relative_path", "document_hash",
  "atlas_document_id", "atlas_extraction_status", "document_processing_state", "computational_outcome",
  "account_short_code", "account_number", "currency", "row_id", "source_index", "chain_order",
  "value_date", "value_date_iso", "post_date", "time", "bank_reference", "customer_reference", "trn_type",
  "narrative", "credit", "debit", "signed_movement", "balance", "link_status", "difference", "finding_id",
  "older_row_id", "derived_balance", "comparison_balance", "citation_page", "citation_x0", "citation_top",
  "citation_x1", "citation_bottom",
] as const;

export interface ExactDecimal {
  units: bigint;
  scale: number;
}

export interface TransactionCsvRow {
  sourceId: string;
  rowId: string;
  sourceIndex: number;
  chainOrder: number;
  account: string;
  accountNumber: string;
  currency: string;
  valueDate: string;
  valueDateIso: string;
  narrative: string;
  credit: ExactDecimal | null;
  debit: ExactDecimal | null;
  movement: ExactDecimal | null;
  balance: ExactDecimal | null;
  difference: ExactDecimal | null;
  linkStatus: "PASS" | "FAIL" | "";
  findingId: string;
  citationPage: number;
}

/** RFC 4180 records, including quoted newlines. Never interpret cell contents as code. */
export function parseCsvRecords(input: string): string[][] {
  if (input.length > 32 * 1024 * 1024) throw new Error("The CSV is too large to display safely (32 MiB limit).");
  const text = input.replace(/^\uFEFF/, "");
  const records: string[][] = [];
  let record: string[] = [];
  let field = "";
  let mode: "PLAIN" | "QUOTED" | "CLOSED" = "PLAIN";
  let touched = false;
  const finishField = () => { record.push(field); field = ""; mode = "PLAIN"; };
  const finishRecord = () => {
    finishField();
    records.push(record);
    record = [];
    touched = false;
    if (records.length > 100_001) throw new Error("The CSV exceeds the 100,000-row display limit.");
  };
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    touched = true;
    if (mode === "QUOTED") {
      if (character === '"') {
        if (text[index + 1] === '"') { field += '"'; index += 1; }
        else mode = "CLOSED";
      } else field += character;
    } else if (character === ",") finishField();
    else if (character === "\r" || character === "\n") {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      finishRecord();
    } else if (character === '"' && mode === "PLAIN" && field === "") mode = "QUOTED";
    else {
      if (mode === "CLOSED" || character === '"') throw new Error("The CSV contains an invalid quoted field.");
      field += character;
    }
  }
  if (mode === "QUOTED") throw new Error("The CSV contains an unterminated quoted field.");
  if (touched || record.length > 0) finishRecord();
  return records;
}

/** Decimal arithmetic remains integer-based; Number is reserved for SVG geometry. */
export function parseExactDecimal(text: string): ExactDecimal | null {
  if (text === "") return null;
  const match = /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/.exec(text);
  if (!match || text.length > 180) throw new Error(`Invalid exact decimal in CSV: ${text.slice(0, 40)}`);
  const fraction = match[3] ?? match[4] ?? "";
  const exponent = Number(match[5] ?? "0");
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 100 || fraction.length > 100) {
    throw new Error("A CSV decimal exceeds the supported precision limit.");
  }
  let units = BigInt((match[2] ?? "0") + fraction) * (match[1] === "-" ? -1n : 1n);
  let scale = fraction.length - exponent;
  if (scale < 0) { units *= 10n ** BigInt(-scale); scale = 0; }
  if (scale > 100) throw new Error("A CSV decimal exceeds the supported precision limit.");
  return { units, scale };
}

export function scaledUnits(value: ExactDecimal, scale: number): bigint {
  return value.units * (10n ** BigInt(scale - value.scale));
}

export function sumExact(values: ExactDecimal[]): ExactDecimal {
  const scale = values.reduce((maximum, value) => Math.max(maximum, value.scale), 2);
  return { units: values.reduce((total, value) => total + scaledUnits(value, scale), 0n), scale };
}

export function formatExact(value: ExactDecimal | null, grouped = true): string {
  if (!value) return "Not available";
  const scale = Math.max(2, value.scale);
  const units = scaledUnits(value, scale);
  const digits = (units < 0n ? -units : units).toString().padStart(scale + 1, "0");
  const whole = digits.slice(0, -scale);
  // Retain significant fractional precision, with at least two decimal places.
  const fraction = digits.slice(-scale).replace(/0+$/, "").padEnd(2, "0");
  return `${units < 0n ? "−" : ""}${grouped ? whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") : whole}.${fraction}`;
}

function csvInteger(value: string, field: string, minimum = 0): number {
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < minimum) {
    throw new Error(`The CSV contains an invalid ${field}.`);
  }
  return Number(value);
}

function spreadsheetLiteral(value: string): string {
  return /^[=+@-]/.test(value.replace(/^[ \t\r\n\uFEFF]+/, "")) ? `'${value}` : value;
}

function validIsoDate(value: string): boolean {
  if (value === "") return true;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function parseTransactionCsv(text: string, result: JobResult, expectedRowCount: number): TransactionCsvRow[] {
  const [headers, ...records] = parseCsvRecords(text);
  if (!headers?.length) throw new Error("The transaction CSV is empty.");
  if (new Set(headers).size !== headers.length || TRANSACTION_CSV_COLUMNS.some((column) => !headers.includes(column))) {
    throw new Error("The transaction CSV has missing or duplicate schema columns.");
  }
  if (records.length !== expectedRowCount) throw new Error("The transaction CSV row count does not match this result.");
  const exportedDocuments = result.documents.filter((document) => document.purpose === "SOURCE" && document.processing_state === "SUCCEEDED");
  const documents = new Map(exportedDocuments.map((document) => [document.source_id, document]));
  const links = new Map(exportedDocuments.flatMap((document) => document.transaction_links.map((link) => [
    `${document.source_id}\u0000${link.newer_row_id}`, link,
  ] as const)));
  const sourceRows = new Map(exportedDocuments.flatMap((document) => document.rows.map((row) => [
    `${document.source_id}\u0000${row.row_id}`, { document, row },
  ] as const)));
  if (records.length !== sourceRows.size) throw new Error("The transaction CSV does not cover the result's source rows.");
  const seen = new Set<string>();
  return records.map((record) => {
    if (record.length !== headers.length) throw new Error("A transaction CSV record has the wrong number of fields.");
    const cell = Object.fromEntries(headers.map((header, index) => [header, record[index]])) as Record<typeof TRANSACTION_CSV_COLUMNS[number], string>;
    if (cell.schema_version !== "transactions.v1" || cell.job_id !== result.job_id || cell.profile_id !== result.profile_id
      || cell.execution_label !== "LOCAL_DETERMINISTIC" || cell.agent_resolution_status !== "NOT_RUN") {
      throw new Error("The transaction CSV schema or job identity does not match this review.");
    }
    const identity = `${cell.source_id}\u0000${cell.row_id}` as const;
    const source = sourceRows.get(identity);
    const document = documents.get(cell.source_id);
    if (!source || !document?.statement || seen.has(identity)) throw new Error("The transaction CSV has an unknown or duplicate source row.");
    seen.add(identity);
    const sourceIndex = csvInteger(cell.source_index, "source index");
    const chainOrder = csvInteger(cell.chain_order, "chain order");
    if (sourceIndex !== source.row.index || chainOrder !== document.rows.length - 1 - sourceIndex) {
      throw new Error("The CSV order does not match the original statement balance chain.");
    }
    if (cell.currency !== spreadsheetLiteral(source.row.currency ?? document.statement.currency)
      || cell.account_short_code !== spreadsheetLiteral(document.statement.account_short_code)
      || cell.account_number !== spreadsheetLiteral(source.row.account_number ?? document.statement.account_number)
      || (document.sha256 && cell.document_hash !== document.sha256)) {
      throw new Error("The CSV account, currency or source hash does not match this statement.");
    }
    if (!["PASS", "FAIL", ""].includes(cell.link_status) || !validIsoDate(cell.value_date_iso)) {
      throw new Error("The transaction CSV contains an invalid link status or date.");
    }
    const link = links.get(identity);
    if (cell.finding_id !== (link?.finding_id ?? "") || cell.link_status !== (link?.status ?? "")) {
      throw new Error("The CSV finding does not match the recorded statement check.");
    }
    const page = csvInteger(cell.citation_page, "source page", 1);
    if (page !== source.row.citation.page) throw new Error("The CSV source page does not match the statement evidence.");
    const credit = parseExactDecimal(cell.credit);
    const debit = parseExactDecimal(cell.debit);
    const movement = parseExactDecimal(cell.signed_movement);
    const hasSourceAmount = credit !== null || debit !== null;
    if ((movement !== null) !== hasSourceAmount) {
      throw new Error("The CSV signed movement presence disagrees with its credit and debit.");
    }
    if (movement && hasSourceAmount) {
      // Match StatementRow.amount exactly: a malformed row with both fields is
      // still exported for review, and the canonical movement selects credit.
      const expected = credit ?? debit!;
      const scale = Math.max(expected.scale, movement.scale);
      if (scaledUnits(expected, scale) !== scaledUnits(movement, scale)) throw new Error("The CSV signed movement disagrees with its credit and debit.");
    }
    return {
      sourceId: cell.source_id, rowId: cell.row_id, sourceIndex, chainOrder,
      account: cell.account_short_code, accountNumber: cell.account_number, currency: cell.currency,
      valueDate: cell.value_date, valueDateIso: cell.value_date_iso, narrative: cell.narrative,
      credit, debit, movement, balance: parseExactDecimal(cell.balance), difference: parseExactDecimal(cell.difference),
      linkStatus: cell.link_status as TransactionCsvRow["linkStatus"], findingId: cell.finding_id, citationPage: page,
    };
  });
}

export function statementMovements(rows: TransactionCsvRow[], document: ResultDocument) {
  const source = rows.filter((row) => row.sourceId === document.source_id);
  const selected = source.filter((row) => row.currency === spreadsheetLiteral(document.statement?.currency ?? "")
    && row.account === spreadsheetLiteral(document.statement?.account_short_code ?? "")
    && row.accountNumber === spreadsheetLiteral(document.statement?.account_number ?? ""))
    .sort((left, right) => left.chainOrder - right.chainOrder);
  const movements = selected.flatMap((row) => row.movement ? [row.movement] : []);
  const selectedIds = new Set(selected.map((row) => row.rowId));
  return {
    rows: selected,
    inflows: sumExact(movements.filter((value) => value.units > 0n)),
    outflows: sumExact(movements.filter((value) => value.units < 0n).map((value) => ({ ...value, units: -value.units }))),
    net: sumExact(movements),
    missingMovements: selected.filter((row) => row.movement === null),
    missingBalances: selected.filter((row) => row.balance === null),
    undated: selected.filter((row) => !row.valueDateIso),
    passed: selected.filter((row) => row.linkStatus === "PASS").length,
    failed: selected.filter((row) => row.linkStatus === "FAIL").length,
    unchecked: selected.filter((row) => row.linkStatus === "").length,
    outsideAccount: source.filter((row) => !selectedIds.has(row.rowId)),
  };
}
