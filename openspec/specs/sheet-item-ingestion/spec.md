# Sheet Item Ingestion Specification

## Purpose

Turn rows from the specified shared Google Sheet into validated items with date-only expiration notice tasks.

## Requirements

### Requirement: Select the source sheet and columns
The script SHALL read the configured spreadsheet without modifying it. Without an explicit sheet title, it SHALL select the sole sheet and reject an ambiguous selection. It SHALL skip row 1 and map columns A-F to ID, name, quantity, acquisition date, expiration date, and notice days. Columns beyond F SHALL be ignored.

#### Scenario: Read the supplied single-sheet file
- **WHEN** the configured file contains one sheet with a header and item rows
- **THEN** the script reads its rows after the header using the stated positional mapping
- **AND** the acquisition date is not used to calculate notice dates

#### Scenario: Explicit sheet selection
- **WHEN** a sheet title is configured
- **THEN** the script selects that exact sheet or reports that it does not exist

#### Scenario: Ambiguous source
- **WHEN** more than one sheet exists and no sheet title is configured
- **THEN** the run fails before any task is created

### Requirement: Ignore absent item IDs and preserve identity
The script SHALL ignore rows with null, empty, or whitespace-only IDs. Numeric zero SHALL be a valid ID. Nonblank IDs SHALL be trimmed, case-sensitive display strings, preserving leading zeros. Names and quantities SHALL use trimmed displayed values without inventing missing values.

#### Scenario: Blank ID with other populated cells
- **WHEN** a row has a whitespace-only ID and otherwise populated cells
- **THEN** the row is ignored without validation errors or task writes

#### Scenario: Zero and leading-zero IDs
- **WHEN** rows display IDs `0`, `001`, and `1`
- **THEN** all three are valid, distinct item identities

### Requirement: Validate data required for a notice
For a nonblank ID, the script SHALL require a nonblank name and quantity, a native Sheets expiration date without a time component, and finite nonnegative integer notice days. It SHALL reject invalid or out-of-range dates and arithmetic, report the original sheet row number and reason, and exclude the row while allowing independent valid rows to continue.

#### Scenario: Invalid notice period
- **WHEN** rows contain notice periods of -1, 1.5, a boolean, or nonnumeric text
- **THEN** each row is reported as invalid and no notice is created for it

#### Scenario: Missing cells or text dates
- **WHEN** a nonblank-ID row lacks a required cell or has expiration text rather than a native date
- **THEN** the row is reported as invalid, including its sheet row number
- **AND** a separate valid row remains eligible for processing

#### Scenario: Acquisition date does not drive eligibility
- **WHEN** a row has valid required notice data and a blank acquisition date
- **THEN** it remains eligible because acquisition date is informational

### Requirement: Resolve repeated IDs before writing
The script SHALL consolidate rows identical in normalized ID, name, displayed quantity, expiration date, and notice days into one candidate. If rows with the same ID conflict in these fields, or any such row is invalid, it SHALL exclude the whole ID group and report affected rows before task writes for that group. Acquisition date differences SHALL not constitute a notice conflict.

#### Scenario: Identical repeated rows
- **WHEN** two rows define the same normalized notice data
- **THEN** they produce only one candidate and the repeated row is reported as consolidated

#### Scenario: Conflicting repeated ID
- **WHEN** two rows use the same ID with different expiration dates or quantities
- **THEN** neither produces a notice
- **AND** both row numbers are reported as a conflict

#### Scenario: Invalid row sharing an ID
- **WHEN** a valid row and an invalid row share a nonblank ID
- **THEN** the entire ID group is excluded and reported rather than accepting the valid row silently

### Requirement: Calculate dates and skip past notices
The script SHALL calculate notice date as expiration date minus notice days, without UTC conversion. It SHALL capture today's date in the spreadsheet's configured time zone once per run. Notice dates earlier than today SHALL be skipped and reported without being treated as errors; today and future dates SHALL remain eligible. Displayed expiration dates SHALL use YYYY-MM-DD.

#### Scenario: Advance notice crossing a year boundary
- **WHEN** expiration is 2027-01-03 and notice days is 5
- **THEN** the calculated notice date is 2026-12-29

#### Scenario: Past and current notices
- **WHEN** spreadsheet-local today is 2026-11-03 and notice dates are 2026-11-02 and 2026-11-03
- **THEN** the earlier notice is skipped and reported
- **AND** the notice for today remains eligible

#### Scenario: Local date differs from UTC
- **WHEN** UTC and the spreadsheet's configured time zone have different current dates
- **THEN** eligibility uses the spreadsheet-local current date
