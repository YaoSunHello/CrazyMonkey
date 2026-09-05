# ATLAS ingestion core

This component contains the newly implemented ATLAS foundation for
CrazyMonkey:

- strict Pydantic contracts for evidence-linked review records;
- stable content hashes and evidence identifiers;
- bounded, non-executing normalization for text PDF, XLSX, and CSV files;
- a deterministic generator for the fictional Q3 2026 management-fee source
  pack; and
- expected synthetic answers kept under the test tree, outside runtime input.

It does **not** yet include an analyst model adapter, challenger, fee verifier,
API route, review UI, or export/email implementation.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
PYTHONPATH=backend python -m app.atlas.fixtures --output /tmp/crazymonkey-atlas-fixtures
PYTHONPATH=backend python -m unittest discover -s backend/tests -p 'test_atlas_*.py' -v
```

All generated entities, terms, documents, and amounts are synthetic. The
normalizer preserves formulas and reports whether an unverified cached value is
present; it never evaluates workbook formulas or executes document content.
