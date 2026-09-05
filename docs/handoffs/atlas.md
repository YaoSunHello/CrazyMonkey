# ATLAS migration handoff

STATUS: MIGRATED

SOURCE WORKSPACE: `/Users/leonardaarons-ditson/Documents/ChatGPT/YLOOKUP WIN/.worktrees/atlas-core`

SOURCE BRANCH: `feature/atlas-core`

DESTINATION REPO: `YaoSunHello/CrazyMonkey`

DESTINATION BRANCH: `Leo`

FILES MIGRATED:

- `atlas/src/ylookup_core/ids.py` -> `backend/app/atlas/ids.py`
- `atlas/src/ylookup_core/models.py` -> `backend/app/atlas/models.py`
- `atlas/src/ylookup_core/ingestion.py` -> `backend/app/atlas/ingestion.py`
- `atlas/src/ylookup_core/fixtures.py` -> `backend/app/atlas/fixtures.py`
- `atlas/tests/expected/synthetic_expected.json` -> `backend/tests/atlas/expected/synthetic_expected.json`
- A truthful package initializer, component README, and focused migration tests were added in CrazyMonkey.

FILES INTENTIONALLY NOT MIGRATED:

- Source bootstrap commit `fca662d` (`AGENTS.md`, `docs/CONTRACTS.md`): it belongs to the mistaken local repository baseline, not the ATLAS component.
- `atlas/pyproject.toml`: it declared unfinished entry points and duplicated CrazyMonkey's backend dependency setup.
- `atlas/README.md`: it claimed pipeline, API, model adapter, verifier, and run-versioning modules that were not created.
- `atlas/src/ylookup_core/__init__.py`: it imported the nonexistent `pipeline.py` module.
- No files or commits from `retinapeg/YLOOKUP` or FundOps were copied, merged, or cherry-picked.

DEPENDENCIES ADDED:

- `reportlab` in `backend/requirements.txt`, used only to generate the synthetic PDF fixtures.

TESTS:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend <python> -m unittest discover -s backend/tests -p 'test_atlas_*.py' -v` -> 8 tests passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend <python> -c 'from app.main import app; from app.atlas import normalize_file'` -> existing API and ATLAS imported together.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend <python> -m app.atlas.fixtures --output <temporary-directory>` -> generated the expected eight-file synthetic source pack.

KNOWN ISSUES:

- This migration is the implemented ATLAS foundation only: contracts, source IDs, source normalization, fixture generation, and test-only expected data.
- Analyst/challenger orchestration, deterministic fee verification, API routes, UI integration, exports, and email are not part of the migrated source diff.
- PDF normalization supports text PDFs only; image-only PDFs require a future OCR path and fail explicitly.
- Workbook formulas are preserved but never calculated; missing or unverified caches remain visibly marked.

INTEGRATION NOTES:

- Import with `PYTHONPATH=backend`, for example `from app.atlas import normalize_file`.
- Generate fixtures with `PYTHONPATH=backend python -m app.atlas.fixtures --output <directory>`.
- Runtime code does not read `backend/tests/atlas/expected/synthetic_expected.json`.
- All fixture names, terms, and amounts are fictional synthetic data.
