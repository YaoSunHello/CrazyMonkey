import { MockReviewAdapter } from "./mockReviewAdapter";

describe("MockReviewAdapter exports", () => {
  it("refuses to prepare a draft for an unavailable fixture version", async () => {
    const adapter = new MockReviewAdapter();
    const { reviewId } = await adapter.startSyntheticReview();
    const review = await adapter.getReview(reviewId);

    expect(await adapter.prepareEmail(reviewId, review.version)).toEqual(expect.objectContaining({
      status: "DRAFT",
      recipient: "",
    }));
    await expect(adapter.prepareEmail(reviewId, review.version + 1)).rejects.toThrow(
      "The requested development fixture version is unavailable.",
    );
  });

  it("refuses a different fixture version instead of exporting the currently stored snapshot", async () => {
    const adapter = new MockReviewAdapter();
    const { reviewId } = await adapter.startSyntheticReview();
    const review = await adapter.getReview(reviewId);

    expect(await adapter.requestExport(reviewId, "json", review.version)).toEqual(expect.objectContaining({
      available: true,
      filename: expect.stringContaining("development-fixture.json"),
    }));
    await expect(adapter.requestExport(reviewId, "json", review.version + 1)).rejects.toThrow(
      "The requested development fixture version is unavailable.",
    );
  });
});

describe("MockReviewAdapter corrections", () => {
  it("creates a new version and recomputes all dependent finding state", async () => {
    const adapter = new MockReviewAdapter();
    const { reviewId } = await adapter.startSyntheticReview();
    const before = await adapter.getReview(reviewId);
    const original = before.findings.find((finding) => finding.investorId === "LP03")!;

    expect(original.status).toBe("DISCREPANCY");
    expect(original.expectedValue?.amount).toBe(37_500);
    expect(original.difference?.amount).toBe(12_500);
    expect(original.versions).toHaveLength(1);

    const corrected = await adapter.correctTerm(reviewId, original.id, {
      annualRate: 2,
      note: "Confirmed against the signed agreement.",
      reviewerName: "Test reviewer",
    });

    expect(corrected.status).toBe("MATCH");
    expect(corrected.humanReviewState).toBe("UNREVIEWED");
    expect(corrected.expectedValue?.amount).toBe(50_000);
    expect(corrected.difference?.amount).toBe(0);
    expect(corrected.calculation?.inputs).toContainEqual({
      label: "Applicable annual fee",
      value: "2%",
    });
    expect(corrected.calculation?.expression).toBe("£10,000,000 × 2% × 0.25");
    expect(corrected.calculation?.result.amount).toBe(50_000);
    expect(corrected.explanation).toContain("corrected to 2% by Test reviewer");
    expect(corrected.challengerConcern).toBeUndefined();
    expect(corrected.verifierStatement).toContain("£50,000.00");
    expect(corrected.checksPerformed).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "recompute",
          label: "Fee calculation recomputed using the corrected term",
          state: "COMPLETE",
        }),
        expect.objectContaining({
          id: "compare",
          label: "Administrator value compared with the corrected result",
          state: "COMPLETE",
        }),
      ]),
    );
    expect(corrected.versions).toHaveLength(2);
    expect(corrected.versions[1]).toEqual(
      expect.objectContaining({
        version: 2,
        reason: "Confirmed against the signed agreement.",
        applicableRate: 2,
        expectedValue: { amount: 50_000, currency: "GBP" },
      }),
    );
    expect(corrected.notes.at(-1)).toEqual(
      expect.objectContaining({
        author: "Test reviewer",
        body: "Corrected extracted annual fee to 2%. Confirmed against the signed agreement.",
      }),
    );

    const persisted = await adapter.getReview(reviewId);
    expect(persisted.findings.find((finding) => finding.id === original.id)).toEqual(corrected);
  });

  it("advances the review-wide version after an action on a different finding", async () => {
    const adapter = new MockReviewAdapter();
    const { reviewId } = await adapter.startSyntheticReview();
    const before = await adapter.getReview(reviewId);
    const lp03 = before.findings.find((finding) => finding.investorId === "LP03")!;
    const lp04 = before.findings.find((finding) => finding.investorId === "LP04")!;

    await adapter.updateHumanReview(reviewId, lp04.id, {
      state: "REVIEWED",
      reviewerName: "First reviewer",
    });
    const corrected = await adapter.correctTerm(reviewId, lp03.id, {
      annualRate: 2,
      note: "Confirmed against the signed agreement.",
      reviewerName: "Second reviewer",
    });

    expect(corrected.versions.at(-1)?.version).toBe(3);
    expect((await adapter.getReview(reviewId)).version).toBe(3);
  });
});
