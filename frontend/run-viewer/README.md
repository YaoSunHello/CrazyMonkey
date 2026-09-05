# Run viewer — diagnostic reference prototype

This directory preserves a standalone static viewer from commit `3730bed`. It
renders compatible recorded-run JSON so the old journal-entry and
pipeline-validation result shapes can be inspected without running application
code.

**This is not the product frontend.** The product frontend is
[BEACON](../), and this prototype is not imported, routed, or included in its
build. It has no configured API or backend connection. Opening the viewer, or
seeing data render successfully, is **not proof that BEACON or any backend is
connected or working**.

No sample JSON is bundled with this preserved prototype. To inspect a run,
provide a compatible batch JSON file separately. The preserved HTML still uses
its historical on-screen wording about files from `examples/`; that text does
not mean those files are included or connected automatically.

## Open it

Double-click `index.html`, then choose or drag a compatible JSON file onto the
page. The viewer understands the two historical profile shapes:

- `journal-entries`, with `statement_rows` and `checks`
- `pipeline-validation`, with `extracted_rows` and `verification_results`

The loader normalises those names before rendering. If the directory is being
served over HTTP, `?src=<path>` can also load a file reachable from that page.
A `file://` page cannot fetch a sibling file, so file selection or drag-and-drop
is the reliable local route.

## What this prototype demonstrates

- the split between rows marked ready for export and rows needing a person
- the check report for each statement
- row-level source evidence, including page, original narrative, and reference
  list where present
- a review queue ordered by financial exposure rather than file order
- a visible warning if the viewer's derived count disagrees with the count in
  the loaded envelope

The viewer deliberately distinguishes `UNRESOLVED` from `CANNOT_VERIFY` and
flags a detailed `MATCH` that names no source list. These are historical
diagnostic rendering rules, not the current BEACON contract. Any counts or gates
calculated in this page are presentation cross-checks only; the loaded run
envelope remains authoritative.
