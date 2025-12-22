# TUI Feature Roadmap

## ✅ Implemented (Current Release)

### Display Improvements
- **Better spec count format**: `(1/3) project-name` instead of `project-name (3 specs)`
  - Shows completed/total specs
  - Aligns vertically for better readability
- **Fold by default**: All projects start collapsed
- **Collapse/expand**: Space bar to toggle project visibility

### Filtering
- **Filter remaining tasks**: `f` key to show only projects/specs with unfinished tasks
- **Status badges**: Visual indicators for running/crashed/completed specs

### Navigation
- **Arrow keys**: Up/down navigation through tree
- **Space**: Collapse/expand projects
- **Enter**: Select spec or expand project
- **g/G**: Jump to top/bottom

### Help & UI
- **Help panel**: `?` to toggle keybinding reference
- **Error reporting**: Full tracebacks for debugging
- **Log viewer**: Real-time log display with auto-scroll

## 🚧 Planned (Next Release)

### Auto-scroll for Large Lists
**Problem**: With >30 projects, items scroll off screen and cursor isn't visible
**Solution**: Implement viewport-based rendering
- Only render items near the selected item
- Show indicators for "more items above/below"
- Auto-center selected item in viewport
- Estimated: 2-3 days

### Sorting Options
Add sort modes (toggle with `o` key):
1. **By modified time**: Most recently active projects first
   - Use folder mtime from filesystem
   - Cache and refresh periodically
2. **By remaining tasks**: Projects with most tasks first
   - Sort by `total_tasks - completed_tasks`
3. **Alphabetical**: Default sort order

Toggle between modes with status indicator in footer.
Estimated: 1 day

## 🔮 Future (Next Major Release)

### Auto-Runner Toggle Per Project
**Goal**: Auto-launch runners when tasks remain

**Features**:
- Toggle button (checkbox) next to each project name
- Configuration per project:
  - Provider (Codex/Claude/Gemini)
  - Model selection
  - Polling interval (default: 1 minute)
- Behavior when toggled ON:
  - Poll every N minutes
  - If remaining tasks exist, auto-launch `spec-workflow-run`
  - Show notification when runner starts
- Behavior when toggled OFF:
  - Show confirmation popup
  - Stop auto-polling for that project
- Persistence:
  - Save toggle state and config to `~/.cache/spec-workflow-runner/auto-runner-config.json`
  - Restore on TUI restart

**UI Design**:
```
▶ [x] (2/5) active-project      <- [x] = auto-runner enabled
▶ [ ] (0/3) completed-project   <- [ ] = auto-runner disabled
```

**Implementation Plan**:
1. Add auto-runner state to AppState
2. Create auto-runner manager (separate from RunnerManager)
3. Add toggle keybinding (perhaps 't' key when project selected)
4. Create config dialog for provider/model selection
5. Implement polling loop
6. Add persistence layer
7. Add visual indicators and notifications

Estimated: 5-7 days

### Enhanced Filtering
- Combine filters (e.g., remaining tasks AND active runners)
- Filter by project name (search)
- Filter by spec status (running/crashed/completed)

### Project Groups
- Group projects by directory or tag
- Collapse/expand groups
- Bulk operations on groups

### Terminal UI Improvements
- Mouse support for clicking projects/specs
- Scroll with mouse wheel
- Drag-to-resize panels
- Color themes

## 📊 Testing Strategy

All new features must include:
- Unit tests for business logic
- Integration tests for component interaction
- Regression tests for bugs fixed
- Manual UAT with >30 projects

Current test coverage: 328 tests passing
Target: >90% coverage for all new code

## 🎯 Priority Order

1. **Auto-scroll** (blocker for usability with many projects)
2. **Sorting** (requested, relatively quick to implement)
3. **Auto-runner** (complex feature, needs design review)
4. **Enhanced filtering** (nice-to-have)
5. **Project groups** (future consideration)

## 📝 Notes

- All keybindings documented in help panel (`?`)
- Keep backward compatibility unless explicitly approved
- No emojis in output unless requested
- Focus on terminal efficiency and speed
