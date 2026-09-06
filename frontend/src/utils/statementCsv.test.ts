import { describe, expect, it } from "vitest";
import { resultWithCsvFixture, transactionCsvFixture, type CsvOverride } from "../test/transactionCsvFixtures";
import { formatExact, parseCsvRecords, parseExactDecimal, parseTransactionCsv, statementMovements, sumExact } from "./statementCsv";
import type { JobResult } from "../workspaceTypes";

describe("transaction CSV decoding", () => {
  it("handles BOM, CRLF, quotes, commas, embedded newlines, empty and trailing fields", () => {
    expect(parseCsvRecords('\uFEFFa,b,c\r\n"a,b","say ""hello""\r\nnext",\r\n')).toEqual([
      ["a", "b", "c"], ["a,b", 'say "hello"\r\nnext', ""],
    ]);
    expect(parseCsvRecords("a,b\n1,2")).toEqual([["a", "b"], ["1", "2"]]);
    expect(parseCsvRecords("a,b\n1,")).toEqual([["a", "b"], ["1", ""]]);
  });

  it.each(['"not closed', 'plain"quote', '"closed"suffix', '"closed""'])(
    "rejects malformed quoting: %s", (text) => { expect(() => parseCsvRecords(text)).toThrow(/quot/); },
  );

  it("accepts the exact schema and orders same-day movements by source chain, never time", () => {
    const rows = parseTransactionCsv(transactionCsvFixture(resultWithCsvFixture, {
      "row-newer": { value_date: "31 Aug 2026", value_date_iso: "2026-08-31", time: "08:00", narrative: 'Payment, "quoted"\r\ncontinued' },
      "row-older": { value_date: "31 Aug 2026", value_date_iso: "2026-08-31", time: "23:00" },
    }), resultWithCsvFixture, 2);
    const movements = statementMovements(rows, resultWithCsvFixture.documents[0]);
    expect(movements.rows.map((row) => row.rowId)).toEqual(["row-older", "row-newer"]);
    expect(movements.rows[1].narrative).toBe('Payment, "quoted"\r\ncontinued');
    expect(movements).toMatchObject({ failed: 1, passed: 0, unchecked: 1 });
    expect(movements.missingMovements).toHaveLength(1);
    expect(formatExact(movements.net)).toBe("125.00");
  });

  it("adds the already-negative debit without double-negating it", () => {
    const rows = parseTransactionCsv(transactionCsvFixture(resultWithCsvFixture, {
      "row-newer": { credit: "", debit: "-0.44", signed_movement: "-0.44" },
      "row-older": { credit: "10.00", debit: "", signed_movement: "10.00" },
    }), resultWithCsvFixture, 2);
    const totals = statementMovements(rows, resultWithCsvFixture.documents[0]);
    expect(formatExact(totals.inflows)).toBe("10.00");
    expect(formatExact(totals.outflows)).toBe("0.44");
    expect(formatExact(totals.net)).toBe("9.56");
  });

  it("uses the canonical credit-first movement when a failed source row contains both amounts", () => {
    const rows = parseTransactionCsv(transactionCsvFixture(resultWithCsvFixture, {
      "row-newer": { credit: "10.00", debit: "-7.00", signed_movement: "10.00" },
    }), resultWithCsvFixture, 2);
    expect(formatExact(rows.find((row) => row.rowId === "row-newer")!.movement)).toBe("10.00");
  });

  it.each<[CsvOverride, RegExp]>([
    [{ schema_version: "future.v9" }, /schema or job/],
    [{ job_id: "another-job" }, /schema or job/],
    [{ profile_id: "another-profile" }, /schema or job/],
    [{ source_id: "unknown" }, /unknown or duplicate/],
    [{ row_id: "row-older" }, /order|duplicate/],
    [{ source_index: "1" }, /order/],
    [{ chain_order: "0" }, /order/],
    [{ currency: "USD" }, /account, currency/],
    [{ account_number: "999" }, /account, currency/],
    [{ finding_id: "fake-finding" }, /finding/],
    [{ link_status: "PASS" }, /finding/],
    [{ link_status: "UNKNOWN" }, /status or date/],
    [{ value_date_iso: "2026-02-30" }, /status or date/],
    [{ citation_page: "4" }, /source page/],
    [{ signed_movement: "=SUM(1,2)" }, /decimal/],
    [{ signed_movement: "" }, /presence/],
    [{ credit: "", debit: "", signed_movement: "1.00" }, /presence/],
    [{ signed_movement: "124.00" }, /disagrees/],
  ])("fails closed for an inconsistent export: %j", (override, error) => {
    expect(() => parseTransactionCsv(transactionCsvFixture(resultWithCsvFixture, { "row-newer": override }), resultWithCsvFixture, 2)).toThrow(error);
  });

  it("rejects missing/duplicate headers, row count mismatch, and incomplete records", () => {
    const csv = transactionCsvFixture();
    expect(() => parseTransactionCsv(csv.replace("schema_version", "job_id"), resultWithCsvFixture, 2)).toThrow(/columns/);
    expect(() => parseTransactionCsv(csv, resultWithCsvFixture, 3)).toThrow(/row count/);
    expect(() => parseTransactionCsv(csv.replace(/\r\n$/, ",extra\r\n"), resultWithCsvFixture, 2)).toThrow(/number of fields/);
    expect(() => parseTransactionCsv("", resultWithCsvFixture, 2)).toThrow(/empty/);
  });

  it("does not combine currencies or different accounts and discloses source-row exclusions", () => {
    const original = resultWithCsvFixture.documents[0];
    const result: JobResult = { ...resultWithCsvFixture, documents: [{
      ...original, rows: original.rows.map((row, index) => index === 1 ? { ...row, currency: "USD" } : row),
    }] };
    const rows = parseTransactionCsv(transactionCsvFixture(result), result, 2);
    const selected = statementMovements(rows, result.documents[0]);
    expect(selected.rows.map((row) => row.rowId)).toEqual(["row-newer"]);
    expect(selected.outsideAccount.map((row) => row.rowId)).toEqual(["row-older"]);
  });

  it("preserves spreadsheet-safe literal escaping when validating account identity", () => {
    const original = resultWithCsvFixture.documents[0];
    const result: JobResult = { ...resultWithCsvFixture, documents: [{ ...original, statement: { ...original.statement!, account_number: "=A1" } }] };
    const rows = parseTransactionCsv(transactionCsvFixture(result, { "row-newer": { account_number: "'=A1" }, "row-older": { account_number: "'=A1" } }), result, 2);
    expect(statementMovements(rows, result.documents[0]).rows).toHaveLength(2);
  });
});

describe("exact money aggregation", () => {
  it("preserves cents beyond Number's safe precision and fractional sub-cent values", () => {
    const values = ["90071992547409.01", "0.02", "-0.0001"].map((value) => parseExactDecimal(value)!);
    expect(formatExact(sumExact(values))).toBe("90,071,992,547,409.0299");
    expect(formatExact(sumExact([parseExactDecimal("0.1")!, parseExactDecimal("0.2")!]))).toBe("0.30");
    expect(formatExact(parseExactDecimal("-0.00"))).toBe("0.00");
  });

  it("supports bounded exact exponents without converting money to Number", () => {
    expect(formatExact(parseExactDecimal("1.23e3"))).toBe("1,230.00");
    expect(formatExact(parseExactDecimal("1e-3"))).toBe("0.001");
    expect(formatExact(parseExactDecimal(".5"))).toBe("0.50");
    expect(formatExact(parseExactDecimal("1."))).toBe("1.00");
    expect(() => parseExactDecimal("1e100000")).toThrow(/precision/);
    expect(() => parseExactDecimal("NaN")).toThrow(/decimal/);
    expect(parseExactDecimal("")).toBeNull();
  });
});
