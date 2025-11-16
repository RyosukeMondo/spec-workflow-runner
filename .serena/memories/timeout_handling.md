# Timeout Handling Changes
- `TimeoutBudget` and the `timeout_seconds` setting were removed; the runner now relies on the no-commit circuit breaker instead of a global elapsed-time check.
- `Config` no longer defines `timeout_seconds`, so update any configs to drop that key before using the CLIs.