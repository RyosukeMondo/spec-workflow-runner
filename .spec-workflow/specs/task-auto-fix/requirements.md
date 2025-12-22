# Requirements Document

## Introduction

The task auto-fix feature enables automatic correction of malformed tasks.md files using Claude Sonnet AI. When users encounter format errors in their task files (missing checkboxes, invalid task IDs, inconsistent numbering), this feature detects issues, generates corrected content, shows a diff preview, and applies fixes with user confirmation. This eliminates manual reformatting and ensures all tasks.md files comply with the project's template format.

## Alignment with Product Vision

This feature supports spec-workflow-runner's goal of streamlining spec-driven development by:
- **Reducing friction**: Automatically fixes format errors instead of requiring manual corrections
- **Enforcing standards**: Ensures all tasks.md files follow the template format consistently
- **Improving reliability**: Validates fixed content before applying, preventing corruption
- **Enhancing user experience**: Provides clear feedback with diff previews and confirmation prompts

## Requirements

### Requirement 1: Format Validation

**User Story:** As a developer, I want the system to detect format errors in my tasks.md file, so that I know what needs to be fixed before attempting auto-correction

#### Acceptance Criteria

1. WHEN a tasks.md file is validated THEN the system SHALL identify all format issues including missing checkboxes, invalid task IDs, and inconsistent numbering
2. WHEN format issues are detected THEN the system SHALL return a structured list of issues with line numbers, severity (error/warning), and descriptive messages
3. IF a tasks.md file has no format issues THEN the system SHALL report the file as valid and skip the fix process
4. WHEN validation completes THEN the system SHALL preserve the original file content without modifications

### Requirement 2: AI-Powered Format Correction

**User Story:** As a developer, I want Claude Sonnet to automatically fix format errors in my tasks.md file, so that I don't have to manually reformat the content

#### Acceptance Criteria

1. WHEN auto-fix is triggered THEN the system SHALL generate a Claude prompt containing the template format, malformed content, and detected issues
2. WHEN the Claude prompt is sent THEN the system SHALL use ClaudeProvider with the 'sonnet' model to generate corrected content
3. IF Claude returns corrected content THEN the system SHALL validate the fixed content to ensure it follows the template format
4. WHEN Claude execution fails THEN the system SHALL return a clear error message and preserve the original file
5. WHEN the fix process completes THEN the system SHALL provide the fixed content to the caller without modifying the file

### Requirement 3: Diff Preview and Confirmation

**User Story:** As a developer, I want to see what changes will be made before applying a fix, so that I can verify the corrections are appropriate

#### Acceptance Criteria

1. WHEN fixed content is generated THEN the system SHALL create a unified diff showing additions, deletions, and modifications with context lines
2. WHEN the diff is generated THEN the system SHALL include a summary showing the total number of changes (lines added, removed, modified)
3. IF there are no differences between original and fixed content THEN the system SHALL report that no changes are needed
4. WHEN presenting the diff THEN the system SHALL display it in a readable format with proper syntax highlighting

### Requirement 4: Safe File Writing with Backup

**User Story:** As a developer, I want my original tasks.md backed up before applying fixes, so that I can recover if something goes wrong

#### Acceptance Criteria

1. WHEN a fix is applied THEN the system SHALL create a backup file with a .backup suffix before modifying the original
2. WHEN writing the fixed content THEN the system SHALL use atomic file operations (write to temp file, then rename)
3. IF the file write operation fails THEN the system SHALL preserve the original file and report the error
4. WHEN the backup is created THEN the system SHALL return the backup file path to the caller
5. IF a backup file already exists THEN the system SHALL create a uniquely named backup to avoid overwriting

### Requirement 5: TUI Integration

**User Story:** As a TUI user, I want to trigger auto-fix for the selected spec using a keybinding, so that I can quickly fix format errors without leaving the interface

#### Acceptance Criteria

1. WHEN the user presses the 'F' key in TUI THEN the system SHALL trigger auto-fix for the currently selected spec
2. IF no spec is selected THEN the system SHALL display an error message in the footer
3. IF the selected spec's tasks.md does not exist THEN the system SHALL display an appropriate error message
4. WHEN auto-fix executes THEN the TUI SHALL block and show a status message indicating the operation is in progress
5. WHEN auto-fix completes THEN the system SHALL display the diff and prompt for confirmation in the footer
6. IF the user confirms the fix THEN the system SHALL apply changes and display a success message
7. IF the user rejects the fix THEN the system SHALL preserve the original file and display a cancellation message

### Requirement 6: CLI Integration

**User Story:** As a CLI user, I want to trigger auto-fix using a command-line flag, so that I can fix format errors in scripts and automation workflows

#### Acceptance Criteria

1. WHEN the user runs the CLI with --fix SPEC_NAME THEN the system SHALL trigger auto-fix for the specified spec
2. IF the specified spec does not exist THEN the system SHALL display an error message and exit with non-zero code
3. WHEN auto-fix executes THEN the CLI SHALL display the diff in the terminal
4. WHEN the diff is shown THEN the CLI SHALL prompt the user to confirm (y/n)
5. IF the user confirms (y) THEN the system SHALL apply changes, display the backup path, and exit with code 0
6. IF the user rejects (n) THEN the system SHALL preserve the original file and exit with code 0
7. IF auto-fix fails THEN the system SHALL display the error message and exit with non-zero code

### Requirement 7: Dependency Injection and Modularity

**User Story:** As a developer maintaining the codebase, I want the auto-fix feature to use dependency injection and follow SOLID principles, so that components are testable and reusable

#### Acceptance Criteria

1. WHEN TaskFixer is instantiated THEN all dependencies (Provider, Config, Validator, PromptBuilder, DiffGenerator, FileWriter) SHALL be injected via constructor
2. WHEN creating a TaskFixer instance THEN a factory function SHALL provide default implementations of all dependencies
3. IF any component needs to be mocked for testing THEN it SHALL be possible to inject mock implementations
4. WHEN components interact THEN they SHALL depend on abstractions (interfaces) not concrete implementations where applicable
5. WHEN a component changes THEN it SHALL not require modifications to other components (Open/Closed Principle)

## Non-Functional Requirements

### Code Architecture and Modularity
- **Single Responsibility Principle**: Each module (validator, prompt_builder, diff_generator, file_writer, fixer) has one clear purpose
- **Modular Design**: All components are isolated in the task_fixer/ module and can be tested independently
- **Dependency Management**: Dependencies are injected, not hard-coded; no circular dependencies
- **Clear Interfaces**: Each component has well-defined inputs/outputs using dataclasses

### Performance
- Auto-fix SHALL complete within 30 seconds for typical tasks.md files (< 100 tasks)
- Claude API calls SHALL have a 120-second timeout to prevent indefinite hangs
- File validation SHALL complete within 1 second for files up to 500 lines
- Diff generation SHALL complete within 500ms for typical file sizes

### Security
- Backup files SHALL be created with the same permissions as the original file
- Temporary files SHALL be created with restrictive permissions (600) and deleted on error
- User input (spec names, file paths) SHALL be validated to prevent path traversal attacks
- Claude prompts SHALL not include sensitive information beyond the tasks.md content

### Reliability
- File write operations SHALL be atomic (no partial writes)
- Original files SHALL never be modified until the user confirms the fix
- All file operations SHALL handle errors gracefully (permissions, disk full, file locks)
- The system SHALL validate fixed content before allowing application

### Usability
- Error messages SHALL be clear and actionable (e.g., "tasks.md not found for spec 'my-spec'")
- Diff output SHALL be color-coded and formatted for readability
- Confirmation prompts SHALL clearly indicate what action will be taken
- Status messages SHALL indicate progress (e.g., "Fixing tasks.md...", "Fix complete")

### Testability
- All components SHALL achieve 80% minimum test coverage (90% for critical paths)
- Each component SHALL be testable in isolation with mocked dependencies
- Test fixtures SHALL include malformed and valid tasks.md samples
- Integration tests SHALL cover both TUI and CLI workflows
