# Tasks Document

1. Missing checkbox on this task
  - File: src/example/missing_checkbox.py
  - This task is missing the checkbox marker
  - Purpose: Test missing checkbox detection
  - _Leverage: None_
  - _Requirements: R1_

- [ ] 2. Valid task with checkbox
  - File: src/example/valid.py
  - This task has proper formatting
  - Purpose: Test mixed valid/invalid content
  - _Leverage: None_
  - _Requirements: R2_

- [ ] Wrong numbering here (should be 3)
  - File: src/example/wrong_number.py
  - This task has no number at all
  - Purpose: Test missing task ID detection
  - _Leverage: None_
  - _Requirements: R3_

- [ ] 3. Inconsistent numbering after skip
  - File: src/example/inconsistent.py
  - Came after a task without number
  - Purpose: Test numbering validation
  - _Leverage: None_
  - _Requirements: R4_

- 5. Missing checkbox and skipped number 4
  - File: src/example/skipped.py
  - Both missing checkbox and wrong sequence
  - Purpose: Test multiple validation issues
  - _Leverage: None_
  - _Requirements: R5_

- [x] 6. This one is complete but valid
  - File: src/example/completed.py
  - Properly formatted completed task
  - Purpose: Test completed task handling
  - _Leverage: None_
  - _Requirements: R6_

- [ ] 7.1 Subtask with proper format
  - File: src/example/subtask.py
  - Nested task with correct formatting
  - Purpose: Test subtask validation
  - _Leverage: None_
  - _Requirements: R7_

- [ ] 7.2 Another subtask
  - File: src/example/subtask2.py
  - Second nested task
  - Purpose: Test subtask numbering
  - _Leverage: None_
  - _Requirements: R7_

8. Missing checkbox and wrong sequence after subtasks
  - File: src/example/after_subtasks.py
  - Should be task 8 but missing checkbox
  - Purpose: Test detection after subtasks
  - _Leverage: None_
  - _Requirements: R8_

- [-] 9. Task in progress format
  - File: src/example/in_progress.py
  - Properly formatted in-progress task
  - Purpose: Test in-progress marker
  - _Leverage: None_
  - _Requirements: R9_

- [ ] 10  Missing period after number
  - File: src/example/missing_period.py
  - Task number has no period separator
  - Purpose: Test format validation
  - _Leverage: None_
  - _Requirements: R10_
