# Tasks

## 1. Python project and resource configuration

- [x] 1.1 Create `pyproject.toml`, `src/prep_notices/`, the `prep-notices` entry point, Google client dependencies, and pytest/Ruff development configuration; verify editable installation into prep's `.venv` and `prep-notices --help` without credentials.
- [x] 1.2 Implement explicit project-root runtime paths, required `--task-list-id` for notice creation, spreadsheet/sheet-title overrides, and separate `--list-task-lists` mode; verify configuration tests cover missing destinations, incompatible mode options, rejection of the old calendar option, and invocation from another directory without creating runtime files there.
- [x] 1.3 Add project-local `.gitignore` rules for `.secrets`, `.venv`, and tooling/build artifacts; verify synthetic credential paths are ignored with path-scoped `git check-ignore`, without modifying the enclosing repository configuration.

## 2. Google OAuth and task-list discovery

- [x] 2.1 Implement desktop user OAuth with the two Sheets-readonly/Tasks scopes in design decision 3, token reuse, refresh, and explicit recovery paths; verify mocked tests for consent, reuse, refresh, missing/corrupt/revoked credentials, and legacy Calendar scope mismatch without requesting Calendar scopes or deleting credentials automatically.
- [x] 2.2 Implement project-local private credential storage and atomic token updates; verify tests check owner-only file/directory permissions, successful refresh persistence, safe persistence failures, and absence of secrets in error output.
- [x] 2.3 Implement read-only paginated task-list discovery and selected-list metadata validation; verify fake-API tests cover IDs/titles across pages, empty pages with next tokens, incomplete/failing discovery, inaccessible IDs, no default-list fallback, and no spreadsheet calls or list/task writes in discovery mode.
- [x] 2.4 Start the operator README with Sheets/Tasks API enablement, OAuth account ownership, desktop consent/test-user setup, credential placement, WSL callback guidance, manual list creation and ID discovery, and scope recovery; verify prerequisites match the implemented paths/scopes and no real credential appears.

## 3. Sheet ingestion and notice eligibility

- [x] 3.1 Implement sheet selection, spreadsheet time-zone retrieval/validation, and the range-limited typed/formatted grid fetch from design decision 4; verify adapter tests cover sheet selection/ambiguity, quoted titles, original row numbers, omitted trailing cells, and missing/invalid time zones failing before writes.
- [x] 3.2 Implement typed item parsing and validation for `sheet-item-ingestion` and generated task text limits from `task-expiration-notices`; verify parameterized tests cover blank/zero/leading-zero IDs, missing values, native serial versus text/time dates, invalid notice days, displayed quantity, and title/notes boundaries without truncation.
- [x] 3.3 Implement pre-write ID grouping, identical-row consolidation, and conflicting/invalid-group exclusion; verify tests show conflicting groups produce no candidates while an independent valid ID remains eligible.
- [x] 3.4 Implement expiration-minus-days calculation and a single spreadsheet-local today snapshot, with no event end-date calculation; verify fixed-clock tests cover zero notice days, year/leap-day boundaries, arithmetic overflow, past/today decisions, and spreadsheet-local dates differing from UTC/WSL.
- [x] 3.5 Document the six positional columns, native-date requirement, display identity rules, ISO description dates, informational acquisition date, and past/conflict policies in the README; verify examples correspond to passing ingestion tests.

## 4. Tasks duplicate lookup and insertion

- [x] 4.1 Implement a complete pre-write task snapshot with completed/hidden/assigned tasks included, deleted tasks excluded, and all pages followed; verify fake-API tests cover later-page matches, empty pages with a next token, and any lookup/page failure preventing insertion.
- [x] 4.2 Implement exact ID-delimited title-prefix and date-only `due` matching within the selected list; verify tests cover `1` versus `10`, changed names, completed/hidden tasks, deleted/undated/differently dated tasks, list isolation, and no time-zone conversion of the scheduled day.
- [x] 4.3 Implement `tasks.insert` with exact title/notes, date-only RFC3339 `due`, `status=needsAction`, and current-run snapshot updates; verify payload tests cover the `Rice` example, no parent/scheduled-time/reminder/event fields, no list creation, and no existing-task mutations.
- [x] 4.4 Stop further writes on Tasks API errors and disable automatic insert retries; verify failure tests distinguish a rejected insert from an uncertain transport outcome, preserve earlier confirmed creations, and never retry an uncertain insertion blindly.
- [x] 4.5 Document public Tasks API scheduled-time/reminder limitations, insert-only behavior, unchanged tasks after source edits, completed-task duplicate handling, and unsupported overlapping runs; verify documentation distinguishes personal Calendar Tasks visibility from insertion into the old calendar and makes no guaranteed-alert or exactly-once claim.

## 5. CLI orchestration and trustworthy results

- [x] 5.1 Wire CLI mode selection, OAuth/resource preflight, full row validation, complete task lookup, candidate processing, and summaries; verify fake-adapter CLI tests cover read-only discovery, no-data success, expected skips, valid rows continuing despite invalid rows with exit 1, access failures, partial writes, and uncertain results.
- [x] 5.2 Report row outcomes separately from unique notice outcomes, with actionable diagnostics and no tokens/raw secret responses; verify captured-output tests account for blank-ID, consolidated, conflicting, past, existing, created, and failed/uncertain outcomes.
- [x] 5.3 Complete README commands for `.venv` setup, editable installation, `--list-task-lists`, manual invocation with an explicit task-list ID and optional source overrides, exit codes, credential recovery, and SDD steps; verify help and credential-free commands run as written and live Google examples are identified.

## 6. Integrated acceptance verification

- [x] 6.1 Add fake-Tasks repeated-run integration tests using real orchestration and synthetic Sheets responses; verify only missing tasks are created, reruns create none both before and after completion, manual matching tasks are respected, and no existing tasks, lists, or calendar events are modified or inspected through Calendar APIs.
- [x] 6.2 Run `.venv/bin/python -m pytest`, `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`, the installed CLI help smoke test, and `openspec validate add-sheet-expiration-notices --strict`; verify all pass and record evidence against the three specs before marking this task done.
- [ ] 6.3 With operator-provided OAuth credentials, an existing disposable task list, and explicit approval for test resource overrides, perform the live smoke test from design decision 8; verify discovery, one incomplete task on the calculated day with exact text, no duplicate on rerun, and no recreation after manual completion. Keep this task unchecked if credentials or approval are unavailable; do not create lists or claim alert delivery.

## Workflow follow-up

- Review changed decisions through `openspec-explore` or `openspec-update-change` before implementing behavior outside these specs.
- After implementation, evidence review, and operator acceptance, request `openspec-archive-change` (`/opsx-archive`) to promote the delta specs and archive the change.
- Optionally use `openspec-sync-specs` before archive if the operator explicitly wants main specs updated earlier; do not treat sync or archive as implementation tasks.

## Verification evidence

On 2026-11-05, `.venv/bin/python -m pytest` passed all 90 tests on Python 3.14.4.
Ruff lint and format checks, installed CLI `--help`, strict OpenSpec validation,
and the scoped Git whitespace check passed.

- `sheet-item-ingestion`: `test_items.py` and `test_sheets.py` cover native date cells, identity/display preservation, row validation, conflict groups, and spreadsheet-local date eligibility.
- `task-expiration-notices`: `test_google_api.py` and the six `test_integration.py` cases cover exact task payloads, full pagination, manual/completed/hidden matches, repeated runs, preservation of existing tasks, and no blind insert retries.
- `notice-script-operation`: `test_auth.py`, `test_cli.py`, and `test_operation.py` cover OAuth/private storage, explicit configuration, read-only discovery, actionable errors, exit status, and partial/uncertain results.

Task 6.3 remains pending: `.secrets/credentials.json` is absent, and disposable
test resource IDs and explicit live-test approval have not been provided.
No live Google calls or remote writes were made during this verification.
