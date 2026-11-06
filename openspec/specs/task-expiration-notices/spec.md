# Task Expiration Notices Specification

## Purpose

Create checkable Google Tasks for item expiration notice days while preserving existing tasks and avoiding duplicate or reopened notices.

## Requirements

### Requirement: Create the exact date-only notice task
For an eligible item without a matching task, the script SHALL create an incomplete task in the configured task list, scheduled for its notice date without an hour. Its title SHALL be `EXPIRATION NOTICE {item-id}: {item-name}` and notes SHALL be `{item-name} (quantity: {item-quantity}) will expire on {expiration-date}.`. It SHALL be a task the user can mark complete, not a calendar event.

#### Scenario: Exact task content
- **WHEN** item `007`, named `Rice`, quantity `3`, expires on 2026-12-10 with notice period 5
- **AND** its notice date is eligible and no matching task exists
- **THEN** the title is `EXPIRATION NOTICE 007: Rice`
- **AND** the notes are `Rice (quantity: 3) will expire on 2026-12-10.`
- **AND** the task is incomplete and scheduled for 2026-12-05 without a scheduled hour

#### Scenario: Date remains unchanged across time zones
- **WHEN** the calculated notice date is 2026-12-05
- **THEN** the task's scheduled day remains 2026-12-05 without converting it into a different local date

### Requirement: Respect task text limits
The script SHALL reject and report an item whose generated title exceeds 1024 characters or whose generated notes exceed 8192 characters. It SHALL NOT truncate identity or content to make an insert succeed. Independent valid items SHALL remain eligible.

#### Scenario: Oversized item name
- **WHEN** an item's generated title exceeds 1024 characters
- **THEN** its row is reported as invalid before task insertion
- **AND** the script does not silently shorten the title

### Requirement: Acknowledge API reminder limitations
The script SHALL create date-only tasks without claiming to configure a scheduled time, reminder time, popup, or email. It SHALL document that the public Tasks API does not expose these controls and that creating a task does not guarantee an alert.

#### Scenario: Task creation succeeds
- **WHEN** the script successfully creates a task
- **THEN** it reports task creation rather than claiming an alert was scheduled or delivered
- **AND** no Calendar reminder or event is created as a substitute

### Requirement: Recognize matching tasks by exact ID and scheduled day
A nondeleted task in the configured list SHALL match if its case-sensitive title starts with `EXPIRATION NOTICE {item-id}:` and its scheduled day equals the notice date. Completed and hidden tasks SHALL count as existing; they SHALL NOT be reopened or recreated. The colon SHALL delimit the ID to prevent partial numeric-ID matches.

#### Scenario: Existing task with a different name
- **WHEN** an incomplete task has the matching date and title `EXPIRATION NOTICE 7: Old name`
- **THEN** item `7` is reported as already existing regardless of its current name or notes

#### Scenario: Completed or hidden notice
- **WHEN** a completed or hidden task matches the item ID and notice date
- **THEN** no new task is created and the existing task's completion state is unchanged

#### Scenario: Prefix collision
- **WHEN** item `1` has no matching task but `EXPIRATION NOTICE 10: Other item` is scheduled for its date
- **THEN** that task does not block creating item `1`'s notice

#### Scenario: Deleted, undated, differently dated, or different-list task
- **WHEN** a matching-prefix task is deleted, has no scheduled day, has another scheduled day, or belongs to another list
- **THEN** it does not block creation in the configured list on the calculated day

### Requirement: Complete duplicate lookup before creating
The script SHALL examine all pages of tasks in the configured list, including completed and hidden tasks, before deciding a notice is absent. An incomplete or failed lookup SHALL NOT be interpreted as absence. It SHALL account for confirmed creations within the run. Sequential reruns with unchanged inputs and task state SHALL not create additional matching notices.

#### Scenario: Duplicate on a later page
- **WHEN** the first page contains no match but a later page contains one
- **THEN** the task is reported as existing rather than duplicated

#### Scenario: Lookup or pagination fails
- **WHEN** any task-list lookup page fails
- **THEN** no task is inserted based on that incomplete lookup
- **AND** the run reports the failure and exits nonzero

#### Scenario: Run twice after completion
- **WHEN** a successful run creates a task and the user marks it complete before the next run
- **THEN** the second run finds it, reports it as existing, and neither recreates nor reopens it

### Requirement: Preserve existing tasks and calendar state
The script SHALL only insert missing tasks in the configured existing list. It SHALL NOT update, complete, reopen, move, or delete existing tasks; create or alter task lists; or inspect or modify calendar events. Changed or removed source rows SHALL not reconcile old notices.

#### Scenario: Changed notice date
- **WHEN** an item's notice date changes and an old task exists on its former notice date
- **THEN** the old task remains unchanged
- **AND** a missing eligible task is created on the new date

#### Scenario: Removed source item
- **WHEN** an item disappears from the sheet
- **THEN** its existing tasks remain unchanged

#### Scenario: Legacy calendar notice
- **WHEN** a calendar event matches the item ID and notice date but no matching task exists in the configured list
- **THEN** the event is not inspected or modified
- **AND** the missing task remains eligible for creation
