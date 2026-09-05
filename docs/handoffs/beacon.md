# BEACON migration handoff

STATUS: MIGRATED

SOURCE WORKSPACE: `${HOME}/Documents/ChatGPT/YLOOKUP WIN/.worktrees/beacon-review-ui`

SOURCE BRANCH: `feature/beacon-review-ui`

SOURCE REMOTE: None configured.

SOURCE COMMITS: None. The source branch is unborn; the files listed below were newly created as untracked work in the isolated BEACON worktree.

DESTINATION REPO: `YaoSunHello/CrazyMonkey`

DESTINATION LOCAL PATH: `${HOME}/Desktop/crazymonkey`

DESTINATION BRANCH: `Leo`

PUSH STATUS: Committed on and pushed to `origin/Leo`; the exact verified commit is recorded in the final migration report.

FILES MIGRATED:

- `frontend/.gitignore`
- `frontend/BEACON.md`
- `frontend/eslint.config.js`
- `frontend/index.html`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/src/**` (application, adapter seam, fixture, components, styling, types, utilities, and tests)
- `docs/handoffs/beacon.md`

FILES INTENTIONALLY NOT MIGRATED:

- Source `.git` data or history.
- Anything outside the isolated `beacon-review-ui` worktree.
- The old `retinapeg/YLOOKUP` repository or baseline.
- Old FundOps code or components.
- All backend code, including Atlas- and Relay-owned paths.
- CrazyMonkey's existing `frontend/README.md`, which was preserved unchanged.
- Source/destination `node_modules`, `dist`, coverage, cache, and other generated artifacts.
- Unrelated files or commits already present on `Leo`.

OLD YLOOKUP CODE INCLUDED: NO

FUNDOPS CODE INCLUDED: NO

DEPENDENCIES ADDED:

- Runtime: `react`, `react-dom`.
- Development: TypeScript, Vite/React plugin, ESLint/TypeScript ESLint, Vitest, jsdom, and Testing Library packages recorded exactly in `frontend/package.json` and `frontend/package-lock.json`.
- Backend dependencies: none.

TESTS:

- Source `npm run typecheck`: PASS.
- Source `npm run lint`: PASS.
- Source `npm test -- --reporter=verbose`: PASS — 6 files, 12 tests.
- Source `npm run build`: PASS — production bundle generated successfully.
- Destination `npm ci`: PASS — 234 packages added, 235 audited, 0 vulnerabilities. npm reported only its informational unapproved optional `fsevents` install-script notice.
- Destination `npm run typecheck`: PASS.
- Destination `npm run lint`: PASS.
- Destination `npm test -- --reporter=verbose`: PASS — 6 files, 12 tests.
- Destination `npm run build`: PASS — 30 modules transformed and a production bundle generated.
- Browser smoke test at `http://127.0.0.1:4173/`: PASS. Verified the labelled fixture landing page; real six-stage progress; derived 6/3/2/1 summary; LP03 £50,000/£37,500/£12,500 calculation; four structured evidence sources and side-letter dialog; human `Reviewed` state while the finding remained `Discrepancy`; usable correction dialog; LP06 `Cannot verify` state and disabled fixture upload; and zero browser console warnings/errors.

KNOWN ISSUES:

- CrazyMonkey does not yet expose BEACON's upload, review-run, progress, result, retry, human-review, correction, or supporting-document `/api/v1` routes.
- Atlas's canonical snake_case contract requires an explicit validated mapper to BEACON's presentation model.
- Concurrent Relay work defines BEACON-compatible export and draft handlers, but the authoritative `/api/runs/...` flow must retain immutable snapshot and explicit-send controls. The legacy BEACON send shape is deliberately rejected.
- Mock mode is a clearly labelled deterministic development fixture; it does not parse selected files.
- PDF/Excel and email sending are disabled until Relay is integrated.
- Frontend validation cannot prove Atlas extraction, Relay outputs, email delivery, or deployment.

INTEGRATION NOTES:

- Default mode is `mock`; no silent fallback from live requests is implemented.
- The fixture carries `mode: SYNTHETIC_DEMO`, a review version, and an explicit no-backend-run notice.
- Its LP01–LP06 values/statuses and 6/3/2/1 totals align with Atlas's committed expected synthetic outcomes.
- Computational and human-review statuses remain separate.
- Evidence content is rendered as structured text, never injected HTML.
- Corrections create a new fixture version and recompute dependent display state.
- Use the backend facade or a validated mapper for Atlas; do not cast raw Atlas payloads directly.
- Use Relay's returned immutable artifact URLs and guarded email preview/send flow.
- Stage only the listed frontend paths and this handoff; preserve all concurrent backend work.
- Push only to `origin Leo`; never force-push.
