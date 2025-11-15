# Suggested Commands
- Setup venv & deps: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt rich`
- List CLI options: `python spec_workflow_run_tasks.py --help` and `python spec_workflow_monitor.py --help`
- Run automation loop for a project/spec: `python spec_workflow_run_tasks.py --project /path/to/repo --spec my-spec`
- Smoke test without Codex call: `python spec_workflow_run_tasks.py --project /path/to/repo --spec my-spec --dry-run`
- Watch progress dashboard: `python spec_workflow_monitor.py --project /path/to/repo --spec my-spec`
- Check parsed task stats quickly: `python - <<'PY' 'from spec_workflow_utils import read_task_stats; from pathlib import Path; print(read_task_stats(Path(".../tasks.md")))' PY`