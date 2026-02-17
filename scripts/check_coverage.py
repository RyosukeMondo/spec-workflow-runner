#!/usr/bin/env python3
"""
Check per-file coverage thresholds.

Usage:
    python scripts/check_coverage.py

This script parses the coverage report and enforces per-file minimum coverage
requirements for critical modules. It's intended to be run after pytest with
coverage collection.

Exit codes:
    0 - All coverage thresholds met
    1 - One or more thresholds not met
    2 - Coverage data not found or error
"""

import sys
from pathlib import Path

# Per-file minimum coverage requirements (percentage)
FILE_THRESHOLDS: dict[str, float] = {
    "src/spec_workflow_runner/tui/state.py": 90.0,
    "src/spec_workflow_runner/tui/runner_manager.py": 90.0,
}


def load_coverage_json() -> dict:
    """Load coverage data from .coverage.json file."""
    coverage_file = Path(".coverage")
    if not coverage_file.exists():
        print("Error: No coverage data found. Run pytest with --cov first.", file=sys.stderr)
        sys.exit(2)

    # Try to use coverage API
    try:
        import coverage

        cov = coverage.Coverage(data_file=str(coverage_file))
        cov.load()

        # Get file coverage data
        file_coverage = {}
        for filename in cov.get_data().measured_files():
            analysis = cov.analysis(filename)
            executed = len(analysis[1])
            missing = len(analysis[2])
            total = executed + missing
            if total > 0:
                file_coverage[filename] = (executed / total) * 100.0
            else:
                file_coverage[filename] = 100.0

        return file_coverage
    except ImportError:
        print("Error: coverage package not installed", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error loading coverage data: {e}", file=sys.stderr)
        sys.exit(2)


def normalize_path(path: str) -> str:
    """Normalize file path to match coverage data format."""
    # Coverage data uses absolute paths, so resolve our relative paths
    return str(Path(path).resolve())


def check_thresholds(file_coverage: dict) -> bool:
    """Check if all files meet their coverage thresholds."""
    all_passed = True

    print("\n=== Per-File Coverage Check ===\n")

    for file_path, threshold in FILE_THRESHOLDS.items():
        # Try both relative and absolute paths
        normalized_path = normalize_path(file_path)

        # Find matching coverage entry
        coverage_pct = None
        for cov_file, pct in file_coverage.items():
            if cov_file.endswith(file_path) or cov_file == normalized_path:
                coverage_pct = pct
                break

        if coverage_pct is None:
            print(f"❌ {file_path}")
            print("   ERROR: File not found in coverage data")
            all_passed = False
            continue

        status = "✅" if coverage_pct >= threshold else "❌"
        print(f"{status} {file_path}")
        print(f"   Coverage: {coverage_pct:.2f}% (threshold: {threshold:.2f}%)")

        if coverage_pct < threshold:
            print("   FAILED: Coverage below threshold")
            all_passed = False

    print()
    return all_passed


def main() -> int:
    """Main entry point."""
    file_coverage = load_coverage_json()

    if not file_coverage:
        print("Error: No coverage data available", file=sys.stderr)
        return 2

    passed = check_thresholds(file_coverage)

    if passed:
        print("✅ All per-file coverage thresholds met!")
        return 0
    else:
        print("❌ Some per-file coverage thresholds not met")
        return 1


if __name__ == "__main__":
    sys.exit(main())
