# Notice Script Operation Specification

## Purpose

Let an operator run the notice script manually with authorized Sheets and Tasks access, protected local credentials, and trustworthy results.

## Requirements

### Requirement: Run manually with explicit resource configuration
The tool SHALL be a manually invoked Python CLI runnable on WSL. Notice creation SHALL default to spreadsheet ID `1kWkRswlbvOWXcmwqWnyssDSIvwoIIKo3J3ZXwX8bnqI` and require an explicit existing task-list ID. It SHALL allow spreadsheet ID and optional exact sheet title overrides. It SHALL NOT substitute a default list or accept a calendar ID as a destination selector.

#### Scenario: Default source with explicit destination
- **WHEN** the operator runs the script with only a task-list ID
- **THEN** it reads the specified shared spreadsheet and inserts only into that task list in the OAuth account

#### Scenario: Missing destination
- **WHEN** the operator requests notice creation without a task-list ID
- **THEN** the CLI reports a configuration error before any task writes

#### Scenario: Explicit overrides
- **WHEN** the operator specifies a test spreadsheet ID, task-list ID, and sheet title
- **THEN** the script uses only those configured resources

#### Scenario: Inaccessible target
- **WHEN** the configured task list cannot be accessed
- **THEN** the run reports an error rather than creating a list or writing to another list

### Requirement: Discover existing task lists without writes
The CLI SHALL offer a separate read-only mode that lists the OAuth account's existing task-list titles and IDs across all result pages. This mode SHALL require neither a destination ID nor spreadsheet access. It SHALL never create lists, tasks, or calendar events, and SHALL report a nonzero exit status if discovery is incomplete or fails.

#### Scenario: Discover a destination
- **WHEN** the operator runs task-list discovery
- **THEN** the CLI lists titles and IDs from all pages without making writes or reading the spreadsheet
- **AND** the operator can use an ID as the destination for a later notice-creation run

### Requirement: Authenticate through user OAuth
The script SHALL use Google user OAuth with an initial browser consent flow, reuse valid locally stored credentials, and refresh expired access tokens when authorized. The operator SHALL provide a desktop OAuth client and authorize Tasks access; notice creation also requires sheet read access. Authentication or refresh failure SHALL be explicit and SHALL stop task processing.

#### Scenario: First authorized run
- **WHEN** no saved token exists and a valid desktop OAuth client is available
- **THEN** the script guides the operator through browser authorization and stores the resulting credentials locally

#### Scenario: Subsequent run
- **WHEN** a saved token is valid or can be refreshed
- **THEN** the script uses it without requiring unnecessary browser consent

#### Scenario: Missing or revoked credentials
- **WHEN** the client file is absent or token refresh is rejected
- **THEN** the run explains the recovery step, exits nonzero, and makes no task writes

### Requirement: Protect local resources and credentials
Project-owned source, configuration, credentials, dependency environment, tests, and documentation SHALL reside under `/home/albertonicoli/workspace/Dev/prep`. Credential files SHALL be owner-only readable/writable on WSL, excluded from version control, and never printed in logs. OAuth SHALL request only sheet read access and Tasks access; no Calendar scopes SHALL be requested.

#### Scenario: Token persistence
- **WHEN** authorization creates or refreshes a token file
- **THEN** the file remains under the project directory with owner-only permissions and is excluded from version control
- **AND** logs do not expose its contents

#### Scenario: Run from a different working directory
- **WHEN** the installed CLI is invoked from outside prep
- **THEN** it resolves project-owned runtime files under prep rather than creating them in the caller's directory

### Requirement: Report row outcomes and exit status
The script SHALL report created notices, existing notices, ignored blank-ID rows, consolidated rows, past-date skips, and invalid/conflicting rows. Errors SHALL include row numbers or affected operations and actionable reasons. A run SHALL exit zero only when no validation, authentication, configuration, or API errors occurred; expected skips alone SHALL not cause failure.

#### Scenario: Mixed valid and invalid data
- **WHEN** valid items and an invalid row are processed
- **THEN** valid items are handled, the invalid row is reported, and the final summary reflects all outcomes
- **AND** the process exits nonzero even if some tasks were created

#### Scenario: No eligible items
- **WHEN** the source has no data rows or only blank IDs and past notice dates
- **THEN** the run reports the corresponding zero-create and skip counts and exits zero

### Requirement: Expose Tasks API failures and partial completion
On a Tasks API failure, the script SHALL stop further task writes, preserve and report confirmed prior creations, and exit nonzero. A lookup failure SHALL never justify an insertion. An insert whose outcome is uncertain SHALL be reported as uncertain, not successful, and SHALL NOT be blindly retried. A later manual rerun SHALL recheck existing tasks before insertion.

#### Scenario: Failure after earlier creation
- **WHEN** one insertion succeeds and a later Tasks operation fails
- **THEN** the successful task remains, later writes stop, and the run reports partial completion with a nonzero exit status

#### Scenario: Uncertain insertion result
- **WHEN** an insertion request times out without a confirmed result
- **THEN** the run reports the affected item/date as uncertain and does not automatically repeat the insertion
- **AND** a subsequent manual run checks the selected list for a matching task

### Requirement: Document setup and operational limits
Operator documentation SHALL describe API enablement, OAuth/WSL setup, list discovery and selection, invocation, credential recovery, and exit status. It SHALL explain date-only tasks, the lack of API reminder controls, completed-task duplicate handling, spreadsheet-local past-date skips, and unsupported overlapping runs. Changed or removed rows SHALL not reconcile tasks; the former calendar destination SHALL no longer be used.

#### Scenario: Operator setup guidance
- **WHEN** an operator follows the project documentation
- **THEN** they can identify the required access, credential locations, and manual run command without exposing secrets
- **AND** they can distinguish creating a checkable date-only task from guaranteeing an alert
