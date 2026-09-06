import { TRANSACTION_CSV_COLUMNS } from "../utils/statementCsv";
import type { JobResult } from "../workspaceTypes";
import { resultFixture } from "./workspaceFixtures";

export const resultWithCsvFixture: JobResult = {
  ...resultFixture,
  exports: { transactions_csv: {
    url: "/api/ui/v1/jobs/job-123/transactions.csv",
    filename: "job-123-transactions.csv",
    content_type: "text/csv; charset=utf-8",
    row_count: 2,
    sha256: "abcdef1234567890".repeat(4),
  } },
};

export type CsvOverride = Partial<Record<typeof TRANSACTION_CSV_COLUMNS[number], string>>;

export function transactionCsvFixture(result = resultWithCsvFixture, overrides: Record<string, CsvOverride> = {}): string {
  const records: string[][] = [Array.from(TRANSACTION_CSV_COLUMNS)];
  for (const document of result.documents) {
    if (document.purpose !== "SOURCE" || document.processing_state !== "SUCCEEDED") continue;
    for (const row of document.rows) {
      const link = document.transaction_links.find((candidate) => candidate.newer_row_id === row.row_id);
      const values: CsvOverride = {
        schema_version: "transactions.v1", job_id: result.job_id, profile_id: result.profile_id, case_name: result.case_name,
        execution_label: result.execution_label, agent_resolution_status: "NOT_RUN", job_processing_state: result.processing_state,
        source_id: document.source_id, source_filename: document.filename, source_relative_path: document.relative_path,
        document_hash: document.sha256, atlas_document_id: document.atlas?.document_id ?? "",
        atlas_extraction_status: document.atlas?.extraction_status, document_processing_state: document.processing_state,
        computational_outcome: document.computational_outcome ?? "", account_short_code: document.statement?.account_short_code,
        account_number: row.account_number ?? document.statement?.account_number, currency: row.currency ?? document.statement?.currency,
        row_id: row.row_id, source_index: String(row.index), chain_order: String(document.rows.length - 1 - row.index),
        value_date: row.value_date, value_date_iso: row.value_date?.match(/^\d{4}-\d{2}-\d{2}$/)?.[0] ?? "", post_date: row.post_date,
        bank_reference: row.bank_reference, narrative: row.narrative, credit: row.credit ?? "", debit: row.debit ?? "",
        signed_movement: row.signed_movement !== undefined ? row.signed_movement ?? "" : row.credit ?? row.debit ?? "",
        balance: row.balance ?? "", link_status: link?.status ?? "", difference: link?.difference ?? "",
        finding_id: link?.finding_id ?? "", older_row_id: link?.older_row_id ?? "", derived_balance: link?.derived_balance ?? "",
        comparison_balance: link?.comparison_balance ?? "", citation_page: String(row.citation.page),
        citation_x0: String(row.citation.bbox.x0), citation_top: String(row.citation.bbox.top),
        citation_x1: String(row.citation.bbox.x1), citation_bottom: String(row.citation.bbox.bottom), ...overrides[row.row_id],
      };
      records.push(TRANSACTION_CSV_COLUMNS.map((column) => values[column] ?? ""));
    }
  }
  return records.map((record) => record.map((field) => /[",\r\n]/.test(field)
    ? `"${field.replaceAll('"', '""')}"` : field).join(",")).join("\r\n") + "\r\n";
}
