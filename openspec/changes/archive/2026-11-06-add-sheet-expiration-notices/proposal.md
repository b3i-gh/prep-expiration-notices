# Proposal

## Why

Items recorded in a shared Google Sheet need advance expiration notices that can be checked off as completed. A repeatable script should create missing Google Tasks for the notice day, without recreating completed notices or promising alerts the public API cannot configure.

## What Changes

- Introduce a manually invoked Python CLI on WSL, using user OAuth to read the shared spreadsheet and insert Google Tasks into an explicitly configured existing task list.
- Read the sole sheet, skip the header and blank IDs, and interpret six positional columns: ID, name, quantity, acquisition date, expiration date, and notice days.
- Create incomplete, checkable tasks scheduled for expiration date minus notice days, with no scheduled hour. Use the spreadsheet's time zone to determine today's date.
- Use the exact title `EXPIRATION NOTICE {item-id}: {item-name}` and notes `{item-name} (quantity: {item-quantity}) will expire on {expiration-date}.`.
- Skip and report past notice dates. Report invalid rows and conflicting repeated IDs, continue with valid independent rows, and return a nonzero exit status if errors occur.
- Skip existing matching tasks on the calculated date, including completed and hidden tasks. Deleted tasks do not block creation. Do not update, reopen, or delete existing tasks.
- Require a task-list ID and provide a read-only list-discovery command; do not create lists or fall back to a default list.
- Replace the earlier unimplemented Calendar integration entirely. Existing calendar events are neither inspected nor modified.
- Provide credential-safe configuration, focused tests, and setup/run instructions.
- Keep project resources under `/home/albertonicoli/workspace/Dev/prep`, equivalent to the requested WSL UNC path.

## Capabilities

### New Capabilities

- `sheet-item-ingestion`: Read the specified sheet, preserve item identity, validate rows, and calculate eligible notice dates.
- `task-expiration-notices`: Create date-only Google Tasks and avoid duplicate notices by item identity and scheduled day, including completed notices.
- `notice-script-operation`: Configure and authenticate the manual CLI, protect credentials, and expose actionable run results.

### Modified Capabilities

None. The initialized project has no existing capability specs or implementation.

## Impact

- New Python CLI, Google Sheets/Tasks API adapters, tests, dependency configuration, and operator documentation; no existing application is changed.
- Default spreadsheet: `https://docs.google.com/spreadsheets/d/1kWkRswlbvOWXcmwqWnyssDSIvwoIIKo3J3ZXwX8bnqI/edit?usp=sharing`.
- Destination: a user-supplied existing task-list ID in the OAuth account. The previously supplied calendar URL is no longer a configuration input; a calendar ID is not a task-list ID.
- Requires a user-provided Google Cloud OAuth desktop client, enabled Sheets and Tasks APIs, sheet read permission, and authorized access to the selected task list.
- Google Tasks can appear in the signed-in account's Calendar Tasks view, subject to client settings; they are not inserted into the previously specified calendar. The public Tasks API cannot configure scheduled times or reminder settings, and alert delivery is not guaranteed.
- Live resource contents, permissions, column formats, spreadsheet time zone, and task-list ID have not been verified. Native date cells and the stated column order remain the agreed input contract.
- Out of scope: automatic scheduling, web UI, Google Sheets writes, automatic task-list creation, task/event reconciliation or deletion, Calendar API integration, custom reminder times, multi-sheet workflows, and concurrent invocations.
