# Frontend

BEACON provides the active fund manager workflow:

- upload documents
- view processing status
- inspect extracted values
- edit or approve fields
- export model-ready datasets

Run the main review workspace in live mode against the combined backend as
documented in [BEACON.md](BEACON.md). The existing profile and CLI backend stays
in place; the branch mounts the BEACON review, human-review, and export routes
alongside it. Live mode never falls back to fixture answers when the backend is
unavailable.

The `leo2` Full Pack frontend is also preserved behind
`VITE_ENABLE_PACK_WORKSPACE=1`. It is off by default because its historical
`/api/pack` Python importer is intentionally not included in this consolidation.
Enabling the flag exposes the preserved screen and makes its missing backend
dependency explicit; it does not alter or replace the working BEACON flow.

`run-viewer/` contains the other frontend branch's unlinked, standalone JSON
viewer for historical diagnostic reference. It is not part of the BEACON build.
