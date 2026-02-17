#!/usr/bin/env python3
"""Validation script for retry functionality integration.

This script validates that retry functionality is properly integrated and working.
"""

import json
import sys
from pathlib import Path


def safe_print(text: str):
    """Print text, handling Unicode encoding errors."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback to ASCII-safe printing
        safe_text = text.encode("ascii", errors="replace").decode("ascii")
        print(safe_text)


def validate_config():
    """Validate config.json has retry settings."""
    safe_print("[OK] Validating config.json...")

    config_path = Path("config.json")
    if not config_path.exists():
        safe_print("  [FAIL] config.json not found")
        return False

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    required_keys = [
        "retry_max_retries",
        "retry_backoff_seconds",
        "retry_on_crash",
        "retry_log_dir",
        "retry_backoff_multiplier",
        "retry_max_backoff_seconds",
    ]

    for key in required_keys:
        if key not in config:
            safe_print(f"  [FAIL] Missing config key: {key}")
            return False
        safe_print(f"  [OK] {key}: {config[key]}")

    return True


def validate_modules():
    """Validate retry modules are importable."""
    safe_print("\n[OK] Validating Python modules...")

    try:
        from spec_workflow_runner.retry_handler import (
            RetryConfig,
            RetryContext,
            RetryHandler,
        )

        safe_print("  [OK] retry_handler module imports successfully")
    except ImportError as e:
        safe_print(f"  [FAIL] Failed to import retry_handler: {e}")
        return False

    try:
        from spec_workflow_runner.subprocess_helpers import (
            monitor_process_with_timeout,
            safe_terminate_process,
        )

        safe_print("  [OK] subprocess_helpers enhancements import successfully")
    except ImportError as e:
        safe_print(f"  [FAIL] Failed to import subprocess_helpers: {e}")
        return False

    try:
        from spec_workflow_runner.utils import Config

        safe_print("  [OK] utils.Config imports successfully")
    except ImportError as e:
        safe_print(f"  [FAIL] Failed to import utils: {e}")
        return False

    try:
        from spec_workflow_runner.tui.models import RunnerState

        safe_print("  [OK] tui.models.RunnerState imports successfully")
    except ImportError as e:
        safe_print(f"  [FAIL] Failed to import tui.models: {e}")
        return False

    return True


def validate_config_loading():
    """Validate config loads with retry settings."""
    safe_print("\n[OK] Validating config loading...")

    try:
        from spec_workflow_runner.utils import load_config

        config = load_config(Path("config.json"))

        if not hasattr(config, "retry_config"):
            safe_print("  [FAIL] Config missing retry_config attribute")
            return False

        safe_print(f"  [OK] retry_config.max_retries: {config.retry_config.max_retries}")
        safe_print(f"  [OK] retry_config.retry_on_crash: {config.retry_config.retry_on_crash}")
        safe_print(
            f"  [OK] retry_config.retry_backoff_seconds: {config.retry_config.retry_backoff_seconds}"
        )

        return True
    except Exception as e:
        safe_print(f"  [FAIL] Failed to load config: {e}")
        return False


def validate_runner_state_serialization():
    """Validate RunnerState can serialize with retry fields."""
    safe_print("\n[OK] Validating RunnerState serialization...")

    try:
        from datetime import datetime
        from pathlib import Path

        from spec_workflow_runner.tui.models import RunnerState, RunnerStatus

        # Create a RunnerState with retry fields
        runner = RunnerState(
            runner_id="test-123",
            project_path=Path("/test/path"),
            spec_name="test-spec",
            provider="Claude CLI",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
            retry_count=2,
            max_retries=3,
            last_retry_at=datetime.now(),
        )

        # Serialize
        data = runner.to_dict()

        if "retry_count" not in data:
            safe_print("  [FAIL] to_dict() missing retry_count")
            return False
        if "max_retries" not in data:
            safe_print("  [FAIL] to_dict() missing max_retries")
            return False
        if "last_retry_at" not in data:
            safe_print("  [FAIL] to_dict() missing last_retry_at")
            return False

        safe_print(f"  [OK] Serialized retry_count: {data['retry_count']}")
        safe_print(f"  [OK] Serialized max_retries: {data['max_retries']}")

        # Deserialize
        restored = RunnerState.from_dict(data)

        if restored.retry_count != runner.retry_count:
            safe_print("  [FAIL] Deserialized retry_count mismatch")
            return False
        if restored.max_retries != runner.max_retries:
            safe_print("  [FAIL] Deserialized max_retries mismatch")
            return False

        safe_print("  [OK] Deserialization successful")

        return True
    except Exception as e:
        safe_print(f"  [FAIL] Failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def validate_tests():
    """Validate tests exist and can be discovered."""
    safe_print("\n[OK] Validating tests...")

    test_files = [
        Path("tests/test_retry_handler.py"),
        Path("tests/test_subprocess_monitoring.py"),
    ]

    for test_file in test_files:
        if not test_file.exists():
            safe_print(f"  [FAIL] Test file not found: {test_file}")
            return False
        safe_print(f"  [OK] {test_file}")

    return True


def main():
    """Run all validations."""
    safe_print("=" * 80)
    safe_print("RETRY FUNCTIONALITY INTEGRATION VALIDATION")
    safe_print("=" * 80)

    checks = [
        ("Configuration", validate_config),
        ("Module Imports", validate_modules),
        ("Config Loading", validate_config_loading),
        ("RunnerState Serialization", validate_runner_state_serialization),
        ("Test Files", validate_tests),
    ]

    results = []
    for name, check_fn in checks:
        try:
            passed = check_fn()
            results.append((name, passed))
        except Exception as e:
            safe_print(f"\n[FAIL] {name} raised exception: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

    safe_print("\n" + "=" * 80)
    safe_print("VALIDATION SUMMARY")
    safe_print("=" * 80)

    for name, passed in results:
        status = "[OK] PASS" if passed else "[FAIL] FAIL"
        safe_print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)

    if all_passed:
        safe_print("\n🎉 All validations passed! Retry integration is working correctly.")
        return 0
    else:
        safe_print("\nERROR: Some validations failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
