# Leo pipeline fixture migration

STATUS: MIGRATED

SOURCE WORKSPACE: the original local workspace (unborn branch; no remote)

SOURCE BRANCH: `feature/relay-outputs` (local unborn branch; no commits and no remote)

CRAZYMONKEY BRANCH: `Leo`

FILES MIGRATED:

- `samples/leo_pipeline_snapshot.json` - a CrazyMonkey-native selective adaptation of the one synthetic snapshot fixture authored by this agent.
- `backend/tests/test_leo_pipeline_snapshot.py` - minimal standard-library contract and safety checks for the adapted fixture.
- `docs/handoffs/leo-relay-fixture.md` - this migration record.

FILES INTENTIONALLY NOT MIGRATED:

- Every pre-existing or concurrently created file from the mistaken workspace.
- All old application, exporter, UI, API, Docker, startup, dependency, schema, test, and documentation files.
- The source fixture was not copied wholesale because its original names and contract belonged to the mistaken project. Only this agent's newly authored fixture concept was selectively adapted to CrazyMonkey's fresh metric schema.

DEPENDENCIES ADDED: None. The test uses only the Python standard library.

TESTS:

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s backend/tests -p 'test_leo_pipeline_snapshot.py' -v`
- Result: PASS - 5 tests.
- A broad `backend/tests/test_*.py` discovery also encountered concurrently added, unowned tests under `backend/tests/relay/`; those failed collection because their package path/dependencies were not configured. This migration does not stage, alter, or claim those tests.

KNOWN ISSUES:

- The fixture is explicitly synthetic and bundles no source document bytes, so its source hash remains null rather than invented.
- It is a shared contract fixture, not a real parser, model call, PDF/Excel generator, or email transport.
- Delivery remains deliberately gated: PDF and Excel are `NOT_GENERATED`; email has an empty recipient and `send_authorized` is false.

INTEGRATION NOTES:

- Every `normalized_metrics` row includes the required fields from `backend/app/schemas/extracted_metric.schema.json`.
- Analyst proposals, red-team concerns, and verifier results reference known metric and evidence IDs.
- One verifier result is intentionally `INDETERMINATE` because the adjusted EBITDA label requires human review.
- The fixture and test reject legacy project identifiers and do not include old repository code or history.
