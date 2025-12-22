# Product Overview

## Product Purpose
Unified TUI application that replaces separate `spec-workflow-run` and `spec-workflow-monitor` CLIs with a single, interactive terminal interface for managing spec workflows across multiple projects. Provides real-time visibility, control, and monitoring of AI-driven task automation workflows.

## Target Users
Software developers who:
- Manage multiple projects with spec-workflow automation
- Need real-time visibility into AI task execution across projects
- Work primarily in terminal environments (SSH, tmux, screen)
- Run long-running AI workflows that need monitoring
- Want to quickly switch between projects and specs without memorizing CLI flags

## Key Features

1. **Multi-Project Dashboard**: Tree view of all projects under `~/repos` with spec-workflow directories, showing real-time status of each project's specs
2. **Spec Explorer**: Browse specs within each project, view task completion ratios (done/total), filter by status (unfinished, completed, all)
3. **Workflow Runner Control**: Toggle-based runner for each spec with start/stop controls, provider selection (Codex/Claude), and configuration options
4. **Real-time Status Monitor**: Integrated live monitoring showing:
   - Running/idle status per project
   - Execution duration timers
   - Provider in use (Codex/Claude with model)
   - Task progress (in-progress, pending, completed counts)
   - Latest log tail (last 50-200 lines)
5. **Navigation & Filtering**: Keyboard-driven navigation with text filtering, fuzzy search, and quick-jump shortcuts
6. **Autonomous Mode Support**: Background execution with status tracking, enabling "set it and forget it" workflows

## Business Objectives

- **Reduce context switching overhead**: Single interface replaces multiple CLI invocations and mental context management
- **Improve workflow visibility**: Real-time status eliminates need to poll separate monitor instances
- **Enable parallel workflows**: Manage multiple concurrent spec executions across projects from one interface
- **Accelerate iteration cycles**: Faster feedback loops through integrated monitoring and control

## Success Metrics

- **Launch time**: < 500ms to fully rendered dashboard (with cache)
- **Refresh latency**: < 100ms for status updates (local file polling)
- **Concurrent workflows**: Support 5+ simultaneous spec executions without UI degradation
- **Memory footprint**: < 50MB for TUI application (excluding provider subprocesses)
- **User task completion time**: 50% reduction in time to "start monitoring a spec" vs current CLI workflow

## Product Principles

1. **Terminal-first**: Optimized for terminal multiplexers (tmux/screen), SSH-friendly, no GUI dependencies
2. **Single source of truth (SSOT)**: File system is truth source - monitor tasks.md, logs, git state, not in-memory tracking
3. **Fail-fast with clarity**: Validate preconditions (clean git, MCP servers) before execution, surface errors immediately
4. **Composable & scriptable**: Preserve CLI mode for automation, TUI enhances but doesn't replace
5. **Ultra-responsive**: All local operations (navigation, filtering) must feel instant (<16ms)

## Monitoring & Visibility

- **Dashboard Type**: Terminal UI (TUI) using Rich library
- **Real-time Updates**: File system polling (tasks.md, logs) with configurable refresh interval (default 2s)
- **Key Metrics Displayed**:
  - Project tree with spec count and status badges
  - Per-spec task progress bars and counts
  - Active runner status (provider, model, duration, last commit)
  - Log tail with syntax highlighting
  - System stats (CPU/memory of provider processes - if easy to gather)
- **Layout**: Multi-panel layout:
  - Left: Project/spec tree navigator
  - Center: Status dashboard for selected spec
  - Right: Log viewer with auto-scroll
  - Footer: Keyboard shortcuts and status bar

## Future Vision

### Potential Enhancements
- **Remote Access**: Share read-only TUI state via tmux sharing or websocket broadcast
- **Analytics**: Historical metrics (spec completion time, task velocity, provider efficiency)
- **Collaboration**: Multi-user awareness (show who's running what spec)
- **Smart Scheduling**: Queue specs, auto-start next unfinished spec when current completes
- **Provider Switching**: Hot-swap provider mid-spec execution (advanced, risky)
- **Spec Templates**: Quick-create new specs from templates within TUI
- **Git Integration**: Show uncommitted changes, auto-create branches per spec
