"""File system polling for state changes.

This module implements background file system monitoring using mtime-based change detection.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path

from .models import StateUpdate

logger = logging.getLogger(__name__)


class StatePoller:
    """Background thread that polls file system for changes.

    Monitors tasks.md files, log files, and runner_state.json using mtime-based
    change detection, publishing StateUpdate objects to a queue for the main thread.
    """

    def __init__(
        self,
        projects: list[Path],
        spec_workflow_dir: str,
        specs_subdir: str,
        tasks_filename: str,
        log_dir_name: str,
        state_file: Path,
        update_queue: queue.Queue[StateUpdate],
        refresh_seconds: float = 2.0,
    ):
        """Initialize state poller.

        Args:
            projects: List of project root paths to monitor
            spec_workflow_dir: Name of spec workflow directory (e.g., ".spec-workflow")
            specs_subdir: Name of specs subdirectory (e.g., "specs")
            tasks_filename: Name of tasks file (e.g., "tasks.md")
            log_dir_name: Name of log directory (e.g., "Implementation Logs")
            state_file: Path to runner_state.json file
            update_queue: Queue to publish StateUpdate objects to
            refresh_seconds: Polling interval in seconds
        """
        self.projects = projects
        self.spec_workflow_dir = spec_workflow_dir
        self.specs_subdir = specs_subdir
        self.tasks_filename = tasks_filename
        self.log_dir_name = log_dir_name
        self.state_file = state_file
        self.update_queue = update_queue
        self.refresh_seconds = refresh_seconds

        # Track mtimes for change detection
        self._mtimes: dict[Path, float] = {}

        # Thread control
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Performance metrics tracking
        self._poll_times: list[float] = []
        self._poll_count = 0
        self._metrics_log_interval = 10  # Log metrics every 10 cycles

    def _get_mtime(self, path: Path) -> float | None:
        """Get modification time of a file, returning None if file doesn't exist."""
        try:
            return path.stat().st_mtime
        except (OSError, FileNotFoundError):
            return None

    def _check_file_changed(self, path: Path) -> bool:
        """Check if file has changed since last poll based on mtime."""
        current_mtime = self._get_mtime(path)
        if current_mtime is None:
            # File doesn't exist or can't be read
            return False

        previous_mtime = self._mtimes.get(path)
        if previous_mtime is None or current_mtime > previous_mtime:
            # File is new or has been modified
            self._mtimes[path] = current_mtime
            return True

        return False

    def _poll_cycle(self) -> None:
        """Execute one polling cycle, checking all monitored files."""
        # Check runner state file
        if self._check_file_changed(self.state_file):
            try:
                self.update_queue.put_nowait(
                    StateUpdate(
                        project="",
                        spec=None,
                        update_type="runner_state",
                        data=None,
                    )
                )
            except queue.Full:
                logger.warning("Update queue full, skipping runner_state update")

        # Check each project
        for project_path in self.projects:
            project_name = project_path.name
            spec_workflow_path = project_path / self.spec_workflow_dir
            specs_path = spec_workflow_path / self.specs_subdir

            if not specs_path.exists():
                continue

            # Find all spec directories
            try:
                spec_dirs = [d for d in specs_path.iterdir() if d.is_dir()]
            except OSError as err:
                logger.warning(f"Failed to list specs in {specs_path}: {err}")
                continue

            for spec_dir in spec_dirs:
                spec_name = spec_dir.name

                # Check tasks.md
                tasks_path = spec_dir / self.tasks_filename
                if self._check_file_changed(tasks_path):
                    try:
                        self.update_queue.put_nowait(
                            StateUpdate(
                                project=project_name,
                                spec=spec_name,
                                update_type="tasks",
                                data=None,
                            )
                        )
                    except queue.Full:
                        logger.warning(
                            f"Update queue full, skipping tasks update for {spec_name}"
                        )

                # Check for latest log file in log directory
                log_dir = spec_dir / self.log_dir_name
                if log_dir.exists() and log_dir.is_dir():
                    try:
                        # Find most recently modified log file
                        log_files = [f for f in log_dir.iterdir() if f.is_file()]
                        if log_files:
                            # Get mtimes, filtering out files we can't stat
                            files_with_mtime = [
                                (f, mtime)
                                for f in log_files
                                if (mtime := self._get_mtime(f)) is not None
                            ]
                            if files_with_mtime:
                                latest_log, _ = max(files_with_mtime, key=lambda x: x[1])
                                if self._check_file_changed(latest_log):
                                    self.update_queue.put_nowait(
                                        StateUpdate(
                                            project=project_name,
                                            spec=spec_name,
                                            update_type="logs",
                                            data=str(latest_log),
                                        )
                                    )
                    except (OSError, ValueError, queue.Full) as err:
                        logger.warning(f"Failed to check logs for {spec_name}: {err}")

    def _run(self) -> None:
        """Main polling loop running in background thread."""
        logger.info(f"StatePoller started with refresh interval {self.refresh_seconds}s")

        while not self._stop_event.is_set():
            try:
                # Measure poll cycle time
                start_time = time.perf_counter()
                self._poll_cycle()
                poll_duration_ms = (time.perf_counter() - start_time) * 1000

                # Track timing for metrics
                self._poll_times.append(poll_duration_ms)
                self._poll_count += 1

                # Log metrics periodically if debug logging enabled
                if (
                    logger.isEnabledFor(logging.DEBUG)
                    and self._poll_count % self._metrics_log_interval == 0
                    and self._poll_times
                ):
                    min_ms = min(self._poll_times)
                    max_ms = max(self._poll_times)
                    avg_ms = sum(self._poll_times) / len(self._poll_times)
                    logger.debug(
                        "StatePoller metrics",
                        extra={
                            "extra_context": {
                                "poll_count": self._poll_count,
                                "min_poll_ms": round(min_ms, 2),
                                "max_poll_ms": round(max_ms, 2),
                                "avg_poll_ms": round(avg_ms, 2),
                            }
                        },
                    )
                    # Reset metrics after logging
                    self._poll_times.clear()

            except Exception as err:
                # Catch all exceptions to prevent thread crash
                logger.error(f"Error in poll cycle: {err}", exc_info=True)

            # Wait for refresh interval or stop event
            self._stop_event.wait(self.refresh_seconds)

        logger.info("StatePoller stopped")

    def start(self) -> None:
        """Start the background polling thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("StatePoller already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="StatePoller")
        self._thread.start()

    def stop(self) -> None:
        """Stop the background polling thread gracefully."""
        if self._thread is None:
            return

        logger.info("Stopping StatePoller...")
        self._stop_event.set()

        # Wait for thread to finish (with timeout)
        self._thread.join(timeout=self.refresh_seconds * 2)

        if self._thread.is_alive():
            logger.warning("StatePoller thread did not stop within timeout")
        else:
            logger.info("StatePoller stopped successfully")

        self._thread = None
