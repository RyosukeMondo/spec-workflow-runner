# Task Completion Steps
- Update the relevant `tasks.md` entry with the correct checkbox marker (`[x]` complete, `[-]` in-progress) under the spec directory.
- Run `python spec_workflow_run_tasks.py --project <repo> --spec <name> --dry-run` to ensure the script recognizes the status and would build the right Codex prompt/log without invoking Codex.
- If running the full automation, allow it to produce a commit; verify a new `git rev-parse HEAD` value and corresponding log file under `<project>/<log_dir>/<spec>/`.
- Optionally run `python spec_workflow_monitor.py --project <repo> --spec <name>` to confirm the Rich dashboard shows 0 pending tasks before considering the spec done.