# Claude Development Guidelines

## Backward Compatibility

**No backward compatibility required unless explicitly requested.**

When refactoring or modifying code:
- Prioritize clean, modern implementations over maintaining compatibility
- Break existing APIs/interfaces freely if it improves the codebase
- Only preserve backward compatibility when the user specifically asks for it

## Code Quality Enforcement

**Pre-commit Hooks**: Mandatory linting, formatting, tests before commits

**Code Metrics (KPI)** - excluding comments/blank lines:
- Max 500 lines/file
- Max 50 lines/function
- 80% test coverage minimum (90% for critical paths)

**Architecture**: SOLID, DI mandatory, SSOT, KISS, SLAP
- All external deps injected (APIs, DBs, queues)
- No testability blockers (no globals, mockable dependencies)

**Error Handling**:
- Fail fast: validate at entry, reject invalid immediately
- Structured logging: JSON format with timestamp, level, service, event, context
- Custom exception hierarchy with error codes
- Never log secrets/PII

**Development**: CLI first, GUI later. Debug mode mandatory for all services.
