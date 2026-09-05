import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { EvidenceReference } from "../types";
import { EvidenceDialog } from "./EvidenceDialog";

const hostileText = '<img src="x" onerror="window.evidenceExecuted=true"><script>alert(1)</script>';

const evidence: EvidenceReference = {
  id: "hostile-evidence",
  documentId: "document-1",
  filename: "hostile.pdf",
  documentRole: "SIDE_LETTER",
  sourceKind: "PDF",
  locator: "Section 1 · page 1",
  quote: hostileText,
  context: "Untrusted uploaded text",
};

function EvidenceHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open evidence</button>
      {open && <EvidenceDialog evidence={evidence} onClose={() => setOpen(false)} />}
    </>
  );
}

describe("EvidenceDialog", () => {
  it("renders untrusted evidence as text, focuses the dialog, and restores focus on Escape", async () => {
    const user = userEvent.setup();
    render(<EvidenceHarness />);
    const trigger = screen.getByRole("button", { name: "Open evidence" });

    await user.click(trigger);

    expect(screen.getByRole("dialog", { name: "Source evidence" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close Source evidence" })).toHaveFocus();
    expect(document.body).toHaveTextContent(hostileText);
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText(/Displayed as structured plain text/)).toBeInTheDocument();

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });
});
