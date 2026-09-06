// @vitest-environment node

import { describe, expect, it } from "vitest";
import { HttpWorkspaceAdapter } from "./workspaceAdapter";
import { parseTransactionCsv, statementMovements } from "../utils/statementCsv";

const processEnvironment = (globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
}).process?.env;
const contractBaseUrl = processEnvironment?.CONTRACT_API_BASE_URL;
const contractSampleUrl = processEnvironment?.CONTRACT_SAMPLE_URL;

describe.skipIf(!contractBaseUrl)("live UI bridge contract", () => {
  it("bootstraps the actual health, profile, capability and replay endpoints", async () => {
    const bootstrap = await new HttpWorkspaceAdapter(contractBaseUrl).bootstrap();

    expect(bootstrap.connection.state, bootstrap.issues.join("\n")).toBe("CONNECTED");
    expect(bootstrap.profiles.length).toBeGreaterThan(0);
    expect(bootstrap.capabilities?.api_version).toBe("ui.v1");
    expect(bootstrap.capabilities?.execution.label).toBe("LOCAL_DETERMINISTIC");
    expect(bootstrap.capabilities?.execution.model_calls).toBe(0);
    expect(bootstrap.profiles.map((profile) => profile.id)).toEqual(
      bootstrap.capabilities?.profiles.map((profile) => profile.profile_id),
    );
    expect(bootstrap.replays.every((replay) => replay.kind === "RECORDED_REPLAY")).toBe(true);
  });

  it.skipIf(!contractSampleUrl)("uploads exact sample bytes, waits for the real job, and retrieves its source, JSON and CSV exports", { timeout: 30_000 }, async () => {
    const sampleResponse = await fetch(contractSampleUrl!);
    expect(sampleResponse.ok).toBe(true);
    const original = new Uint8Array(await sampleResponse.arrayBuffer());
    const filename = decodeURIComponent(new URL(contractSampleUrl!).pathname.split("/").pop() || "statement.pdf");
    const file = new File([original], filename, { type: "application/pdf" });
    const adapter = new HttpWorkspaceAdapter(contractBaseUrl);

    const accepted = await adapter.startJob({
      profileId: "journal-entries",
      caseName: "Browser adapter contract — exact uploaded bytes",
      idempotencyKey: `contract-${Date.now()}-${original.byteLength}`,
      entries: [{
        clientFileId: "contract-source-1",
        file,
        relativePath: `contract/nested/${filename}`,
        filename,
        sizeBytes: file.size,
        contentType: file.type,
        status: "SUPPORTED",
        reason: "Contract test source.",
        selected: true,
        purpose: "SOURCE",
      }],
    });

    let status = await adapter.getJob(accepted.job_id);
    for (let attempt = 0; attempt < 100 && !["SUCCEEDED", "PARTIAL", "FAILED"].includes(status.processing_state); attempt += 1) {
      await new Promise((resolve) => globalThis.setTimeout(resolve, 50));
      status = await adapter.getJob(accepted.job_id);
    }
    expect(status.processing_state).toBe("SUCCEEDED");

    const result = await adapter.getResult(accepted.job_id);
    const document = result.documents.find((item) => item.client_file_id === "contract-source-1");
    expect(document?.relative_path).toBe(`contract/nested/${filename}`);
    expect(document?.rows.length).toBeGreaterThan(0);
    expect(document?.rows[0].citation.source_id).toBe(document?.source_id);
    expect(result.agent_resolution.status).toBe("NOT_RUN");

    const servedSource = await fetch(adapter.sourceUrl(result.job_id, document!.source_id));
    expect(servedSource.ok).toBe(true);
    expect(new Uint8Array(await servedSource.arrayBuffer())).toEqual(original);

    const artifact = result.artifacts.find((item) => item.kind === "RESULT_JSON");
    expect(artifact).toBeDefined();
    const servedArtifact = await fetch(adapter.artifactUrl(result.job_id, artifact!.artifact_id));
    expect(servedArtifact.ok).toBe(true);
    const artifactPayload = await servedArtifact.json() as { artifact_kind: string; result: { job_id: string } };
    expect(artifactPayload).toMatchObject({
      artifact_kind: "RESULT_JSON",
      result: { job_id: result.job_id },
    });

    const csvExport = result.exports?.transactions_csv;
    expect(csvExport).toBeDefined();
    const csvText = await adapter.fetchTransactionCsv(result.job_id, csvExport!.sha256);
    const csvRows = parseTransactionCsv(csvText, result, csvExport!.row_count);
    expect(csvRows).toHaveLength(document!.rows.length);
    expect(csvRows.every((row) => row.sourceId === document!.source_id)).toBe(true);
    expect(statementMovements(csvRows, document!).rows.map((row) => row.sourceIndex)).toEqual(
      [...document!.rows].reverse().map((row) => row.index),
    );
    const download = await fetch(adapter.transactionCsvUrl(result.job_id));
    const downloadedBytes = await download.arrayBuffer();
    expect(new TextDecoder().decode(downloadedBytes)).toBe(csvText);
    const digest = await crypto.subtle.digest("SHA-256", downloadedBytes);
    expect(Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("")).toBe(csvExport!.sha256);
    expect(csvText).toContain("\r\n");
  });
});
