# Tasks Document

- [x] 1. Create task_fixer module structure and validator
  - File: src/spec_workflow_runner/task_fixer/validator.py
  - Create ValidationIssue, ValidationResult, TaskValidator classes
  - Implement validate_file() method using parse_tasks_file() as baseline
  - Add extended validation rules for checkboxes, task IDs, numbering
  - Purpose: Detect format issues in tasks.md files
  - _Leverage: src/spec_workflow_runner/tui/task_parser.py (parse_tasks_file pattern)_
  - _Requirements: R1 (Format Validation)_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Python Developer specializing in validation and regex patterns | Task: Create TaskValidator class in src/spec_workflow_runner/task_fixer/validator.py following requirement R1, using parse_tasks_file() pattern from task_parser.py for baseline validation | Restrictions: Use frozen dataclasses for immutability, no external dependencies beyond stdlib, validation must be pure (no side effects) | Leverage: src/spec_workflow_runner/tui/task_parser.py | Success: ValidationResult accurately identifies missing checkboxes, invalid task IDs, inconsistent numbering; all validation logic tested with 90%+ coverage_

- [x] 2. Create prompt builder for Claude
  - File: src/spec_workflow_runner/task_fixer/prompt_builder.py
  - Create PromptContext, PromptBuilder classes
  - Implement build_prompt() with template loading and formatting
  - Template path: .spec-workflow/templates/tasks-template.md
  - Purpose: Generate Claude prompts from template and validation issues
  - _Leverage: Config template path pattern, pathlib for template loading_
  - _Requirements: R2 (AI-Powered Format Correction)_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: AI Prompt Engineer with Python development skills | Task: Create PromptBuilder class in src/spec_workflow_runner/task_fixer/prompt_builder.py following requirement R2, building structured prompts with template content, malformed content, and validation issues | Restrictions: Lazy-load template (cache after first load), use frozen dataclass for PromptContext, prompt must instruct Claude to output ONLY markdown | Leverage: Config for template paths, pathlib.Path for file operations | Success: Prompts include all necessary context (template, issues, content), template loaded only once, prompt format verified manually with Claude_

- [x] 3. Create diff generator
  - File: src/spec_workflow_runner/task_fixer/diff_generator.py
  - Create DiffResult, DiffGenerator classes
  - Implement generate_diff() using difflib.unified_diff()
  - Count changes for summary (lines added, removed, modified)
  - Purpose: Create human-readable diffs for user confirmation
  - _Leverage: difflib.unified_diff from standard library_
  - _Requirements: R3 (Diff Preview and Confirmation)_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Python Developer specializing in diff algorithms and text processing | Task: Create DiffGenerator class in src/spec_workflow_runner/task_fixer/diff_generator.py following requirement R3, using difflib.unified_diff() to generate diffs with context lines and change summaries | Restrictions: Use frozen dataclass for DiffResult, handle identical content gracefully (no changes), default 3 context lines | Leverage: difflib.unified_diff | Success: Diffs correctly show additions/deletions/modifications, changes_summary counts accurate, has_changes flag correct, tested with various input combinations_

- [x] 4. Create file writer with atomic operations
  - File: src/spec_workflow_runner/task_fixer/file_writer.py
  - Create WriteResult, FileWriter classes
  - Implement write_with_backup() using atomic write pattern (temp file + rename)
  - Implement restore_from_backup() for rollback capability
  - Purpose: Safely write fixed content with backup creation
  - _Leverage: pathlib.Path, shutil.copy2 for atomic operations_
  - _Requirements: R4 (Safe File Writing with Backup)_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Systems Programmer with expertise in file I/O and atomic operations | Task: Create FileWriter class in src/spec_workflow_runner/task_fixer/file_writer.py following requirement R4, implementing atomic file writes with backup using temp file + rename pattern | Restrictions: Use frozen dataclass for WriteResult, backups must have .backup suffix (unique if exists), all file ops must handle errors gracefully | Leverage: pathlib.Path for file operations, shutil for atomic copy | Success: Writes are atomic (no partial writes), backups created before modification, restore_from_backup() works correctly, all error scenarios handled (permissions, disk full)_

- [x] 5. Create TaskFixer orchestrator with dependency injection
  - File: src/spec_workflow_runner/task_fixer/fixer.py
  - Create FixResult, TaskFixer classes
  - Implement fix_tasks_file() coordinating validation -> prompt -> Claude -> diff
  - Implement apply_fix() delegating to FileWriter
  - Inject all dependencies (Provider, Config, Validator, PromptBuilder, DiffGenerator, FileWriter)
  - Purpose: Orchestrate entire fix process with DI
  - _Leverage: ClaudeProvider from providers.py, subprocess for execution_
  - _Requirements: R2 (AI-Powered Format Correction), R7 (Dependency Injection)_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Software Architect specializing in dependency injection and orchestration patterns | Task: Create TaskFixer orchestrator in src/spec_workflow_runner/task_fixer/fixer.py following requirements R2 and R7, coordinating all components with dependency injection | Restrictions: All dependencies injected via constructor, use frozen dataclass for FixResult, validation must occur before AND after Claude call, subprocess timeout 120 seconds | Leverage: ClaudeProvider.build_command(), subprocess.run() for execution | Success: fix_tasks_file() orchestrates full flow correctly, fixed content validated before returning, all dependencies injectable for testing, error handling at each stage_

- [x] 6. Create factory function and public API
  - File: src/spec_workflow_runner/task_fixer/__init__.py
  - Implement create_task_fixer() factory function
  - Create all default dependency instances
  - Export public API: create_task_fixer, TaskFixer, FixResult, ValidationResult, DiffResult, WriteResult
  - Purpose: Provide simple public API with DI
  - _Leverage: Factory pattern similar to create_provider() in providers.py_
  - _Requirements: R7 (Dependency Injection)_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: API Designer with expertise in factory patterns and clean APIs | Task: Create factory function create_task_fixer() in src/spec_workflow_runner/task_fixer/__init__.py following requirement R7, instantiating all dependencies with sensible defaults | Restrictions: Template path must resolve correctly (.spec-workflow/templates/tasks-template.md), factory must work with minimal config, export only public API | Leverage: Path resolution patterns from existing config loading | Success: create_task_fixer() returns fully initialized TaskFixer, all dependencies created with correct defaults, public API is clean and minimal_

- [x] 7. Add TUI keybinding for auto-fix
  - File: src/spec_workflow_runner/tui/keybindings.py
  - Add 'F' keybinding handler in handle_key()
  - Implement _handle_fix_tasks() method
  - Validate selected spec, create TaskFixer, call fix_tasks_file() (blocking)
  - Return status messages for footer display
  - Purpose: Enable TUI users to trigger auto-fix with F key
  - _Leverage: Existing keybinding handler pattern, ClaudeProvider instantiation pattern_
  - _Requirements: R5 (TUI Integration)_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: UI Developer with expertise in TUI frameworks and event handling | Task: Add 'F' keybinding for auto-fix in src/spec_workflow_runner/tui/keybindings.py following requirement R5, implementing _handle_fix_tasks() using existing handler pattern | Restrictions: Must return tuple[bool, str | None], blocking execution (synchronous), validate spec selection before proceeding, use ClaudeProvider with model='sonnet' | Leverage: Existing _handle_start_runner() pattern for reference | Success: F key triggers auto-fix for selected spec, appropriate error messages for invalid states, status messages show diff summary, execution blocks TUI until complete_

- [x] 8. Add CLI flag for auto-fix
  - File: src/spec_workflow_runner/tui/cli.py
  - Add --fix SPEC_NAME argument to argument parser
  - Implement _handle_fix_command() function
  - Display diff, prompt for confirmation, apply if approved
  - Purpose: Enable CLI users to trigger auto-fix
  - _Leverage: Existing CLI argument pattern, discover_specs(), load_config()_
  - _Requirements: R6 (CLI Integration)_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: CLI Developer with expertise in argparse and command-line UX | Task: Add --fix flag to CLI in src/spec_workflow_runner/tui/cli.py following requirement R6, implementing _handle_fix_command() with diff display and confirmation prompt | Restrictions: Exit code 0 on success/cancellation, non-zero on error, use ClaudeProvider with model='sonnet', must confirm before applying | Leverage: Existing load_config(), discover_specs() functions | Success: --fix SPEC_NAME validates spec exists, displays unified diff, prompts y/n for confirmation, applies fix on y, shows backup path, exits with appropriate codes_

- [x] 9. Update help panel with F keybinding documentation
  - File: src/spec_workflow_runner/tui/views/help_panel.py
  - Add F keybinding entry to "Runner Control" section
  - Document: "F | Auto-fix | Automatically fix format errors in selected spec's tasks.md"
  - Purpose: Document new keybinding in help panel
  - _Leverage: Existing help panel table structure_
  - _Requirements: R5 (TUI Integration)_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Technical Writer with knowledge of UI documentation | Task: Add F keybinding documentation to help panel in src/spec_workflow_runner/tui/views/help_panel.py following requirement R5 | Restrictions: Add to "Runner Control" section, follow existing format (key | action | description), use consistent terminology | Leverage: Existing table.add_row() pattern | Success: F keybinding documented clearly in help panel, appears in correct section, matches existing formatting style_

- [x] 10. Create unit tests for validator
  - File: tests/task_fixer/test_validator.py
  - Test validate_file() with malformed inputs (missing checkboxes, invalid IDs, bad numbering)
  - Test with valid tasks.md files
  - Test edge cases (empty files, no tasks, only comments)
  - Purpose: Ensure validation accuracy and reliability
  - _Leverage: pytest, existing test patterns_
  - _Requirements: R1 (Format Validation), Testability_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: QA Engineer specializing in pytest and validation testing | Task: Create comprehensive unit tests for TaskValidator in tests/task_fixer/test_validator.py covering requirement R1 with 90%+ coverage | Restrictions: Test both valid and invalid inputs, test edge cases, use parametrize for multiple scenarios, no file I/O (use in-memory content) | Leverage: pytest.mark.parametrize for test variations | Success: All validation scenarios tested, edge cases covered, 90%+ code coverage for validator.py, tests run quickly (<1s)_

- [x] 11. Create unit tests for prompt builder
  - File: tests/task_fixer/test_prompt_builder.py
  - Test build_prompt() includes template, malformed content, issues
  - Test template lazy-loading (only loaded once)
  - Mock template file reading
  - Purpose: Ensure prompt correctness and template handling
  - _Leverage: pytest, unittest.mock for file mocking_
  - _Requirements: R2 (AI-Powered Format Correction), Testability_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: QA Engineer with expertise in mocking and prompt validation | Task: Create unit tests for PromptBuilder in tests/task_fixer/test_prompt_builder.py covering requirement R2 with 85%+ coverage | Restrictions: Mock template file reading with unittest.mock, verify prompt structure without calling Claude, test lazy-loading behavior | Leverage: unittest.mock.patch for Path.read_text() | Success: Prompt structure validated, template included correctly, issues formatted properly, lazy-loading tested, 85%+ coverage_

- [x] 12. Create unit tests for diff generator and file writer
  - File: tests/task_fixer/test_diff_generator.py, tests/task_fixer/test_file_writer.py
  - Test generate_diff() with identical/different content, change counting
  - Test write_with_backup() with temp files, backup creation, atomic rename
  - Test restore_from_backup() functionality
  - Test error handling (permissions, disk full scenarios)
  - Purpose: Ensure diff accuracy and safe file operations
  - _Leverage: pytest, tempfile for safe test file creation_
  - _Requirements: R3 (Diff Preview), R4 (Safe File Writing), Testability_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: QA Engineer specializing in file I/O and diff testing | Task: Create unit tests for DiffGenerator and FileWriter in tests/task_fixer/ covering requirements R3 and R4 with 85%+ coverage | Restrictions: Use tempfile.TemporaryDirectory() for file tests, test atomic operations, mock permission errors for error scenarios | Leverage: tempfile for safe test files, pytest.raises for error testing | Success: Diff counting accurate, atomic writes verified, backup creation tested, restore functionality validated, error scenarios covered, 85%+ coverage_

- [x] 13. Create unit tests for TaskFixer orchestrator
  - File: tests/task_fixer/test_fixer.py
  - Mock all dependencies (Provider, Validator, PromptBuilder, DiffGenerator, FileWriter)
  - Test full fix flow: validation -> prompt -> Claude call -> validation -> diff
  - Test error handling at each stage
  - Test skip when file already valid
  - Purpose: Ensure orchestration logic correctness
  - _Leverage: pytest, unittest.mock for dependency mocking_
  - _Requirements: R2 (AI-Powered Format Correction), R7 (DI), Testability_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: QA Engineer with expertise in integration testing and mocking frameworks | Task: Create unit tests for TaskFixer orchestrator in tests/task_fixer/test_fixer.py covering requirements R2 and R7 with 90%+ coverage | Restrictions: Mock ALL dependencies, test orchestration flow not component logic, verify correct error propagation, use MagicMock for subprocess | Leverage: unittest.mock.MagicMock, pytest.fixture for mock setup | Success: Orchestration flow tested end-to-end, error handling verified at each stage, skip logic tested, dependency injection validated, 90%+ coverage_

- [x] 14. Create integration tests for CLI and TUI
  - File: tests/task_fixer/test_integration.py
  - Test CLI --fix flag with valid/invalid specs
  - Test TUI F keybinding with various selection states
  - Use test fixtures for malformed/valid tasks.md files
  - Mock Claude API calls for deterministic testing
  - Purpose: Ensure end-to-end workflows function correctly
  - _Leverage: pytest, existing TUI test patterns, test fixtures_
  - _Requirements: R5 (TUI Integration), R6 (CLI Integration), Testability_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: QA Engineer specializing in integration and end-to-end testing | Task: Create integration tests in tests/task_fixer/test_integration.py covering requirements R5 and R6 with 80%+ coverage of integration paths | Restrictions: Mock subprocess calls to Claude, use test fixtures for tasks.md files, test both success and error paths, verify user-facing messages | Leverage: Existing TUI test patterns from tests/tui/, pytest.fixture for test data | Success: CLI workflow tested (flag parsing, diff display, confirmation), TUI workflow tested (keybinding, selection validation, messages), fixtures cover malformed/valid cases, 80%+ integration coverage_

- [x] 15. Create test fixtures
  - Files: tests/task_fixer/fixtures/malformed_tasks.md, valid_tasks.md
  - Create malformed_tasks.md with various format errors (missing checkboxes, invalid IDs, inconsistent numbering)
  - Create valid_tasks.md following template format exactly
  - Purpose: Provide test data for validation and integration tests
  - _Leverage: Existing tasks-template.md as reference for valid format_
  - _Requirements: Testability_
  - _Prompt: Implement the task for spec task-auto-fix, first run spec-workflow-guide to get the workflow guide then implement the task: Role: QA Engineer with expertise in test data creation | Task: Create test fixture files in tests/task_fixer/fixtures/ with malformed and valid tasks.md samples | Restrictions: malformed_tasks.md must have diverse errors (at least 5 different issue types), valid_tasks.md must match template exactly | Leverage: .spec-workflow/templates/tasks-template.md as reference | Success: malformed_tasks.md triggers multiple validation issues, valid_tasks.md passes validation, fixtures cover common error scenarios, both files are realistic examples_
