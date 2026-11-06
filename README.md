# Prep expiration notices

A manual Python CLI that reads item rows in Google Sheets and creates missing,
date-only Google Tasks. Creating a task does **not** configure or guarantee an
alert. Implementation follows
`openspec/changes/add-sheet-expiration-notices/`.

## Local installation (WSL, Python 3.11+)

Run in a WSL terminal:

```bash
cd /home/albertonicoli/workspace/Dev/prep
python3 -m venv .venv
mkdir -p .cache/tmp
TMPDIR="$PWD/.cache/tmp" PIP_CACHE_DIR="$PWD/.cache/pip" \
  .venv/bin/python -m pip install -e '.[dev]'
.venv/bin/prep-notices --help
```

Keep the editable installation and project directory together. Runtime files
resolve under this project, even when the command is invoked elsewhere.

If Python reports missing `ensurepip`, install your distribution's matching
`python3-venv` package. If `uv` is already available, this alternative also works:

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv venv --allow-existing --seed .venv
UV_CACHE_DIR="$PWD/.cache/uv" uv pip install --python .venv/bin/python -e '.[dev]'
```

## Google setup (operator action; not needed for automated tests)

1. In a Google Cloud project, enable **Google Sheets API** and **Google Tasks API**.
   Calendar API access is not needed.
2. Configure the OAuth consent screen. For an external app in Testing, add the
   Google account you will use as a test user. Testing-mode refresh tokens can
   expire; authorization may need to be repeated.
3. Create an OAuth client of type **Desktop app** and download its JSON locally.
   Do not paste credentials or tokens into chat or commit them.
4. Create `prep/.secrets` with `mkdir -m 700 .secrets`, place the downloaded
   client at `.secrets/credentials.json`, and run
   `chmod 600 .secrets/credentials.json`. The script saves `.secrets/token.json`
   privately and atomically; both files are ignored by Git.
5. Use an account that can read the spreadsheet. Tasks belong to **that OAuth
   account**, not the originally supplied calendar. Create a dedicated task list
   manually in Google Tasks if desired.

The script requests only `spreadsheets.readonly` and `tasks` scopes. The Tasks
scope technically allows other changes; this tool only inserts missing tasks.
On first use, open the printed Google authorization URL in a browser and consent.
In WSL, opening it in the Windows browser is fine when localhost forwarding
works. The callback listens on loopback for up to 180 seconds. If the callback
cannot connect, fix WSL localhost forwarding and rerun; do not expose the callback
publicly or use a deprecated copy/paste token flow.

For revoked/corrupt credentials or old Calendar scopes, inspect the account's
Google app permissions and revoke the obsolete grant if appropriate. Manually
remove **only** `.secrets/token.json`, then rerun to authorize again. The script
never deletes tokens or changes accounts silently. Missing client files, denied
consent, and refresh failures stop the run without writes.

Discover task-list IDs (live Google access, but no remote writes or sheet read):

```bash
.venv/bin/prep-notices --list-task-lists
```

This lists titles and IDs across all pages. Copy the ID of an existing list,
not its title, a calendar URL, a calendar ID, or `@default`.

## Spreadsheet contract

The default file is the supplied shared spreadsheet. It must contain one sheet,
unless `--sheet-title` selects an exact title. Row 1 is ignored; columns are
positional, regardless of their header names:

| Column | Meaning | Required for a nonblank ID |
|---|---|---|
| A | Item ID | Yes; displayed text preserves leading zeros; zero is valid |
| B | Item name | Yes |
| C | Quantity bought | Yes; displayed value is retained, including units |
| D | Acquisition date | No; informational and not validated |
| E | Expiration date | Yes; native Sheets date, with no fractional time |
| F | Notice days | Yes; numeric nonnegative whole days |

Columns beyond F are ignored. Blank/whitespace IDs are ignored before validation.
IDs, names, and quantities are trimmed. IDs are case-sensitive; `001` and `1` are
different. Dates must be native date cells, not text such as `'10/12/2026`.
The script uses Sheets serial dates, not locale-dependent text parsing.

The notice day is expiration minus notice days. Today is captured once in the
spreadsheet's configured time zone; earlier days are skipped and reported,
not moved to today. A missing/invalid spreadsheet time zone stops the run.
Dates in task notes use `YYYY-MM-DD`.

Identical repeated rows consolidate into one candidate (acquisition date is
irrelevant). Conflicting rows sharing an ID, or an invalid member of that ID
group, exclude the whole group. Errors include original sheet row numbers;
independent valid items still proceed and the run exits nonzero. Generated
titles over 1024 characters or notes over 8192 characters are rejected, not
silently truncated.

## Notice behavior

The script fetches all task pages in the **selected list**, including completed,
hidden, and assigned tasks. A nondeleted task with the exact case-sensitive
title prefix `EXPIRATION NOTICE {ID}:` and the same scheduled day prevents a new
task. A different name/quantity does not cause an update. ID `1` does not match
ID `10`. Completed tasks are neither recreated nor reopened. Deleted, undated,
other-date, and other-list tasks do not block creation.

A missing task is inserted as an incomplete top-level activity for the day:

```text
Title: EXPIRATION NOTICE 007: Rice
Notes: Rice (quantity: 3) will expire on 2026-12-10.
Day:   2026-12-05 (five notice days)
```

The API encodes that day as `2026-12-05T00:00:00.000Z`; this is **not a midnight
alarm**. Google Tasks API cannot configure its scheduled hour, reminder time,
popup, or email. You can mark the task complete in Google Tasks. Its appearance
in the signed-in account's Calendar Tasks view depends on client settings; it is
not inserted into the originally specified calendar.

The tool never updates, completes, reopens, moves, or deletes existing tasks and
never creates lists. Changed expiration dates can create a task on a new day
while leaving the old one; removed sheet rows leave old tasks untouched.
Calendar events are not read and do not suppress Tasks creation.

Do not run overlapping invocations: read-then-insert is not atomic against other
writers. API failures stop further writes and retain confirmed earlier tasks.
An incomplete lookup is never treated as absence. An uncertain insertion is
reported separately and is **not automatically retried**; manually rerun to
recheck remote state after resolving the error. No exactly-once or transactional
rollback guarantee is made.

## Manual runs and results

These commands use live Google access and can create tasks (except discovery):

```bash
.venv/bin/prep-notices --task-list-id 'YOUR_EXISTING_TASK_LIST_ID'
.venv/bin/prep-notices --task-list-id 'TEST_LIST_ID' \
  --spreadsheet-id 'TEST_SPREADSHEET_ID' --sheet-title 'Items'
```

The summary distinguishes unique notices (`created`, `existing`, `past_notices`,
`uncertain_notices`, `not_processed_notices`) from source rows (`blank_id_rows`,
`consolidated_rows`, `invalid_rows`). Consolidated duplicate rows can also belong
to a skipped past notice. Errors include affected operations or original sheet
row numbers; the output never dumps provider responses or OAuth tokens.

Exit codes: **0** means no errors, including expected skips or an empty source;
**1** means validation/authentication/configuration/API errors or an uncertain
insert, even if some tasks were created; **2** means invalid CLI arguments.
On failure, confirmed successes remain; fix the reported issue and rerun
manually. Live tests should use explicit disposable resource overrides, not the
default source and a production task list.

## Development and SDD

Credential-free checks, from prep:

```bash
.venv/bin/python -m pytest --basetemp=.cache/test-tmp
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/prep-notices --help
openspec validate add-sheet-expiration-notices --strict
```

The OpenSpec specs are the acceptance contract; tests cover sheet ingestion,
task deduplication/payloads, and safe operation. Use `openspec-explore` to discuss
uncertainties, `openspec-update-change` to revise the plan, and
`openspec-apply-change` to continue implementation. In Copilot these skills can
be requested in plain language; `/opsx-*` prompt aliases are not available in
every client. After verification and acceptance, request
`openspec-archive-change`; do not archive while the live smoke test is pending.
