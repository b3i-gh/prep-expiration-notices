# Design

## Context

See `proposal.md` for motivation and the three delta specs for the behavior contract. The target directory was empty before OpenSpec initialization: there is no application, test suite, or dependency convention to preserve. The project uses the `spec-driven` schema and Copilot integration.

The revised plan replaces the unimplemented Calendar destination with Google Tasks. The user confirmed date-only checkable tasks despite API reminder limitations, an explicit existing task-list ID, spreadsheet-local past-date checks, and completed/hidden matches counting as existing. Python, manual WSL execution, user OAuth, native Sheets dates, row-error handling, and the balanced notice text remain unchanged. Live resources have not been inspected.

All project-owned resources must stay in `/home/albertonicoli/workspace/Dev/prep`, corresponding to `\\wsl.localhost\WSL02\home\albertonicoli\workspace\Dev\prep`.

## Goals / Non-Goals

**Goals:** Keep date/row decisions independently testable, isolate Google API effects, and make sequential reruns safe without a local synchronization database. Keep setup small enough for a single operator.

**Non-Goals:** A generic synchronization framework, unattended deployment, automatic task-list creation, Calendar API integration, task-time/reminder configuration, transactional rollback of successful inserts, or guarantees about notification delivery and concurrent writers.

## Decisions

### 1. Small typed Python CLI with official Google clients

Use Python 3.11+ with a project-local `.venv`, `pyproject.toml`, and a console entry point named `prep-notices`. Use `google-api-python-client`, `google-auth-httplib2`, and `google-auth-oauthlib`; use standard-library dates, `zoneinfo`, argument parsing, and typed data structures. Add pytest and Ruff as development tools.

Keep a small `src/prep_notices/` package with separate responsibilities for CLI orchestration, item parsing/date calculation, OAuth, and Sheets/Tasks adapters. Prefer functions and a small immutable item record over a framework. Tests inject fake adapters and a fixed clock; production uses the same decision logic.

Alternative: Apps Script would reduce local OAuth setup but move source/execution into Google's environment and depart from the selected local Python workflow. A service account would require additional sharing and was not selected.

### 2. Explicit configuration and project-local runtime files

Default to the supplied spreadsheet ID. Notice creation requires `--task-list-id`; support `--spreadsheet-id` and `--sheet-title` overrides. Accept actual task-list IDs rather than interpreting calendar URLs or calendar IDs. Do not retain `--calendar-id`.

Provide `prep-notices --list-task-lists` as a separate read-only discovery mode, mutually exclusive with notice-creation resource options. Authenticate, call `tasklists.list`, follow every `nextPageToken`, and print existing titles and IDs. Discovery requires neither a destination ID nor a spreadsheet read. It does not create task lists or select one by name. Notice creation uses `tasklists.get` to validate the explicitly chosen list; an inaccessible list fails without a default-list fallback.

Tasks belong to the OAuth account and a task list, not to the formerly specified calendar. The operator creates a dedicated list manually in Google Tasks if desired and obtains its ID through discovery. Calendar Tasks visibility depends on the signed-in account and client settings; it does not imply insertion into a named calendar.

Use project-root-relative `.secrets/credentials.json` for the user-supplied desktop client and `.secrets/token.json` for saved authorization, not paths relative to the invocation directory. Resolve the project root explicitly from the installed editable package. Put `.venv`, local tooling caches, and `.secrets` under prep and ignore them in the project `.gitignore`. Do not modify the enclosing home-directory Git repository's settings.

Create `.secrets` with mode 0700 and credential files with mode 0600; normalize permissions before loading existing credentials. Persist refreshed tokens atomically through an owner-only temporary file in the same directory. Fail explicitly if a safe local write is impossible. Do not copy real credentials into examples or fixtures.

Alternative: global user-config directories are conventional but conflict with the requested project-local resource layout. No local notice database is needed because the task list is the authority for duplicate checks. Automatic list creation or title-based selection would add writes and ambiguity the user did not choose.

### 3. OAuth scopes and access preflight

Use a desktop OAuth client and `InstalledAppFlow` with a loopback callback. Request:

- `https://www.googleapis.com/auth/spreadsheets.readonly`
- `https://www.googleapis.com/auth/tasks`

Enable the Sheets and Tasks APIs, not Calendar. Use the same two-scope desktop setup for both CLI modes; discovery calls only Tasks and does not require access to the configured spreadsheet. The Tasks scope permits more operations than the application uses, so constrain writes to inserting missing tasks in the explicit list.

Reuse a valid token and refresh an expired token with a refresh token. Missing client credentials, corrupt tokens, denied consent, scope mismatch, and rejected refreshes must have explicit recovery instructions. A failed refresh must not silently switch identity or substitute resources.

For notice creation, preflight authentication, spreadsheet selection/read and time zone, selected task-list metadata, and the complete task snapshot before any insertion. List readability does not prove every insert will succeed; permission/quota errors must still be surfaced. Discovery skips the Sheet preflight. Document consent-screen test users, possible testing-mode token expiry, and how to open the consent URL in a Windows browser if WSL cannot launch one. Keep the loopback server bound locally; do not use deprecated out-of-band OAuth or ask the operator to paste tokens into chat.

If a token from the earlier Calendar design exists, do not silently reuse its broader grants or assume it authorizes Tasks. Report the scope mismatch and document explicit reauthorization/revocation steps; the script must not automatically delete credentials or revoke access.

### 4. Read typed cells and displayed identity in the same data fetch

Fetch sheet metadata, including `properties.timeZone`, to select the sole sheet or validate an explicit title. Read the selected sheet's quoted A1 range `A2:F` using `spreadsheets.get` with a field mask for grid offsets and cells' `effectiveValue`, `formattedValue`, and `effectiveFormat.numberFormat.type`. Escape apostrophes in sheet titles. This gives native numeric dates plus displayed IDs/quantities together, avoiding locale-dependent string parsing and mismatches from separate formatted/unformatted reads.

Use original grid offsets to preserve sheet row numbers and pad missing trailing cells when interpreting rows. Skip whitespace-only IDs before validating other cells. Preserve formatted leading zeros, trim surrounding whitespace, and treat IDs case-sensitively; numeric zero is not blank. Missing cells and Sheets error values in required fields are errors, never default values.

For expiration, require a numeric date-formatted cell (`DATE`, or `DATE_TIME` with no fractional day), excluding booleans and nonfinite numbers. Google Sheets serial dates use the epoch 1899-12-30. Convert integral serial days to a Python `date`; reject fractional time values, strings, unsupported ranges, and arithmetic overflow. Notice days must be a finite nonnegative integral numeric value, not boolean. Preserve displayed nonblank quantity without imposing an unrequested positive-integer rule. Acquisition date is informational and is neither needed nor validated for notice computation.

Generate the final task title/notes during row validation; reject a title over 1024 characters or notes over 8192 characters with a row error, never truncate them. Validate all input groups before beginning writes. Consolidate equal notice data for repeated IDs; a differing notice field or invalid member excludes the whole ID group. Report row numbers.

Compute the notice date safely, with no next-day event boundary. Validate the spreadsheet time zone with `ZoneInfo` and capture spreadsheet-local today once using the injectable clock. A missing or invalid zone is a configuration error, not a reason to default to the WSL/UTC/calendar zone. Skip past dates without rescheduling them.

Alternative: parsing displayed dates is locale-sensitive. `values.get` with unformatted serials alone loses formatted identifiers and cannot establish native date formatting.

### 5. Task lookup is authoritative, paginated, and completion-aware

Call `tasks.list` for the explicit task-list ID with `showCompleted=true`, `showHidden=true`, `showDeleted=false`, and `showAssigned=true`. Fetch all pages, including after an empty page with a next token, before any task insertion. Including hidden tasks is essential because Google's own clients can hide completed tasks. Do not filter by completion date, update time, or scheduled-day bounds; compare the returned scheduled dates directly.

Use nondeleted tasks only, regardless of completion/hidden status. A title matches the exact prefix `EXPIRATION NOTICE {id}:`, so numeric ID `1` does not match `10`. The `due` field's date must equal the calculated notice date. An undated task or a task in another list does not match. Names, notes, provenance, and completion state do not participate in identity; a manually created matching task also prevents insertion.

Google's `due` field represents a scheduled day; it is not a task deadline or a controllable scheduled time. Validate it as RFC3339 and compare its date-only value without converting midnight into the spreadsheet/WSL time zone. Completed matching tasks must not be recreated or reopened. Calendar events are not read and cannot block task creation.

Keep this snapshot only within the run and record each confirmed insertion in it. Sequential, nonoverlapping runs are supported; races with another writer are not solved by a read-then-insert strategy.

Alternative: checking incomplete tasks only would recreate completed notices. A local-only registry would miss manually created tasks and drift from remote state. Fetching the entire selected list is simple and avoids date-filter boundary errors, at the cost of more reads for large lists.

### 6. Date-only task insertion and honest reminder semantics

Call `tasks.insert` in the selected existing list with the exact `title` and `notes`, `status: needsAction`, and `due: YYYY-MM-DDT00:00:00.000Z` for the notice day. The RFC3339 timestamp is only the API's encoding of a date; it is not a midnight alarm and must not be produced by time-zone conversion. Omit parent/previous so the new task is a normal top-level task. Use ISO expiration dates in notes.

For item `007`/`Rice`, quantity `3`, expiring 2026-12-10 with five notice days, insert title `EXPIRATION NOTICE 007: Rice`, notes `Rice (quantity: 3) will expire on 2026-12-10.`, and `due: 2026-12-05T00:00:00.000Z`. There are no event start/end fields or Calendar reminders.

The public Tasks API has no supported fields for scheduled time or reminder settings. Do not promise email/popup delivery or add Calendar events as a workaround. The user accepts this limitation in exchange for a checkable activity for the day.

### 7. Fail visibly without hiding partial writes

Use exit 0 for an error-free run, including an empty sheet, duplicates, blank IDs, and past-date skips. Use exit 1 for row validation errors, configuration/authentication/API failures, and uncertain inserts; standard CLI usage errors may use exit 2.

Print row-level reasons and a summary with separate counts for created, existing, blank-ID ignored, consolidated, past-date skipped, invalid/conflicting rows, and API failures. Identify counts as row counts or unique notice counts so consolidation is not misleading. Do not expose OAuth secrets or complete raw API responses.

Row errors do not stop independent valid candidates. Tasks API failures stop later task writes; report confirmed earlier creations without rolling them back. A failed or partial lookup is never equivalent to no match. Disable automatic insert retries: a transport failure may occur after Google committed the task. Report unknown insertion outcomes by item/date and instruct the operator to rerun manually, which rechecks the task list. Do not mark an unconfirmed insertion as created. An incomplete list-discovery operation also exits nonzero and is not reported as a complete inventory.

Alternative: retrying every failed insertion may create duplicates; swallowing failures produces a false-success exit status.

### 8. Verification and SDD progression

Map focused tests to the scenario names in the three specs. Test pure parsing/date rules, text limits, and task payloads with synthetic fixtures; mock task/list pagination, completed/hidden matches, OAuth refresh, permission failures, and partial/uncertain writes. Verify discovery makes no spreadsheet or write calls. A two-run fake-Tasks integration test must prove that the second run inserts nothing, including after a task is marked complete.

Run the project's pytest suite, Ruff lint/format checks, package installation/CLI help smoke test, and strict OpenSpec validation. Keep package environments and caches local. Do not require Google credentials for automated tests.

A real API smoke test is a separate operator-approved step using an existing disposable task list and explicit test spreadsheet overrides: one eligible synthetic row, first run creates one incomplete task, second creates none. The operator can mark the test task complete and rerun to verify it is not recreated. Visually confirm the scheduled date, text, and completion checkbox, not guaranteed alert delivery. No task list is created by the script. If credentials or approval are unavailable, record the live test as pending rather than claiming success.

Workflow from prep:

1. Review these artifacts; use `openspec-explore` for unresolved ideas and `openspec-update-change` for changed decisions before coding.
2. Explicitly request `openspec-apply-change` (project command `/opsx-apply`) for `add-sheet-expiration-notices`; implement task by task and keep checkboxes honest.
3. Validate implementation against scenarios and collect test evidence. A blocked live check stays visibly pending.
4. Request `openspec-archive-change` (`/opsx-archive`) only after accepting the completed change. Archive promotes the delta requirements into the main specs. Use `openspec-sync-specs` only if main specs need updating before archive.

## Risks / Trade-offs

- [Unknown live sheet shape, time zone, and resource access] -> Validate the positional/native-date contract, spreadsheet zone, and explicit task-list access; report mismatches rather than guessing.
- [No API-controlled alert time or reminder] -> Document the accepted limitation; task creation is not evidence that an alert will occur.
- [Tasks belong to a different resource than calendar events] -> Require the OAuth account's task-list ID and explain Calendar Tasks visibility separately.
- [Completed/hidden tasks omitted by client defaults] -> Explicitly include them in a complete paginated duplicate lookup.
- [Changed or removed rows leave old notices] -> Preserve existing tasks as requested; reconciliation is a separate change.
- [Concurrent invocations or external writers can race] -> Document single-run operation; do not claim atomic exactly-once insertion.
- [Network loss after insertion] -> Stop without blind write retries and recheck on a manual rerun; immediate remote visibility cannot be guaranteed.
- [Partial writes cannot be rolled back safely] -> Retain confirmed successes, emit nonzero status, and rerun after remediation.
- [OAuth access applies beyond these particular resources] -> Request Sheets-readonly and Tasks scopes only, keep files private, and constrain writes to missing tasks in the explicit list.
- [Spreadsheet edits during a run] -> Process one fetched data snapshot; later edits take effect on the next run and do not reconcile old notices.

## Migration Plan

There is no existing application or main capability spec to migrate. This planning revision replaces the unimplemented `calendar-expiration-notices` delta with `task-expiration-notices` and does not retain Calendar integration. Previously created calendar events, if any exist outside this project, remain untouched and do not suppress task creation.

During apply, create the package, tests, local ignore rules, and operator README; install into `.venv`, then run credential-free checks. The operator supplies the desktop client, authorizes Sheets/Tasks access, and selects an existing task-list ID before an approved live test. The actual list ID is a runtime input, not a planning assumption.

Rollback means stopping invocation and, if needed, revoking OAuth access. The script does not delete already-created tasks; cleanup must be separately reviewed and performed by the operator.

## API References

- [Sheets spreadsheets.get and field masks](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/get)
- [Sheets serial date epoch](https://developers.google.com/workspace/sheets/api/reference/rest/v4/DateTimeRenderOption)
- [Tasks fields, date-only due semantics, and text limits](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks)
- [Task listing, pagination, and completed/hidden flags](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/list)
- [Task insertion and authorization scope](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/insert)
- [Task-list discovery and pagination](https://developers.google.com/workspace/tasks/reference/rest/v1/tasklists/list)
