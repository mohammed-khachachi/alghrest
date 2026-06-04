#!/usr/bin/env python3
"""
ALGHREST Test Runner
===================

Comprehensive test runner for the ALGHREST trading system.
Supports multiple test types, coverage reporting, and CI/CD integration.

Usage:
    python scripts/run_tests.py --help
    python scripts/run_tests.py unit
    python scripts/run_tests.py integration
    python scripts/run_tests.py all --coverage --html-report
    python scripts/run_tests.py integration --parallel --verbose
    python scripts/run_tests.py unit --fast --no-cov
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ROOT_LINT_EXCLUDED_PREFIXES = (
    "HMM_Trading/",
    "alghrest-test/HMM_Trading/",
)


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"


class TestRunner:
    """Main test runner with support for different test types and configurations."""

    def __init__(self):
        self.project_root = PROJECT_ROOT
        self.test_dir = self.project_root / "tests"
        self.results = {}

    def env_flag(self, name: str) -> bool:
        """Return true when an environment flag is set to a common truthy value."""
        return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

    def should_lint_changed_files(self, args) -> bool:
        """Use changed-file linting for PRs or explicit local simulation."""
        if args.all_files:
            return False

        if args.changed_only or self.env_flag("ALGHREST_LINT_CHANGED_ONLY"):
            return True

        return os.getenv("GITHUB_EVENT_NAME") == "pull_request"

    def git_output(self, args: list[str]) -> str | None:
        """Run a git command and return stripped stdout when it succeeds."""
        result = subprocess.run(
            ["git", *args],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def lint_base_candidates(self, args) -> list[str]:
        """Build an ordered list of refs that can identify the PR base."""
        raw_candidates = [
            args.base_ref,
            os.getenv("ALGHREST_LINT_BASE_REF"),
        ]

        event_path = os.getenv("GITHUB_EVENT_PATH")
        if event_path:
            event_file = Path(event_path)
            if event_file.exists():
                try:
                    event = json.loads(event_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    event = {}

                pull_request = event.get("pull_request", {})
                base = pull_request.get("base", {}) if isinstance(pull_request, dict) else {}
                if isinstance(base, dict):
                    raw_candidates.append(base.get("sha"))
                    base_ref = base.get("ref")
                    if base_ref:
                        raw_candidates.extend([f"origin/{base_ref}", base_ref])

        github_base_ref = os.getenv("GITHUB_BASE_REF")
        if github_base_ref:
            raw_candidates.extend([f"origin/{github_base_ref}", github_base_ref])

        raw_candidates.extend(["origin/main", "origin/develop", "main", "develop"])

        candidates = []
        for candidate in raw_candidates:
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return candidates

    def python_files_from_diff(self, diff_output: str) -> list[str]:
        """Filter a git diff file list down to existing Python files."""
        files = []
        for line in diff_output.splitlines():
            rel_path = line.strip()
            normalized_path = rel_path.replace("\\", "/")
            if not normalized_path or Path(normalized_path).suffix != ".py":
                continue
            if normalized_path.startswith(ROOT_LINT_EXCLUDED_PREFIXES):
                continue
            if (self.project_root / normalized_path).is_file():
                files.append(normalized_path)
        return sorted(set(files))

    def changed_python_files(self, args) -> list[str] | None:
        """Find changed Python files relative to a merge base."""
        for base_ref in self.lint_base_candidates(args):
            merge_base = self.git_output(["merge-base", "HEAD", base_ref])
            if not merge_base:
                continue

            diff_output = self.git_output(
                ["diff", "--name-only", "--diff-filter=ACMRTUXB", merge_base, "--"]
            )
            if diff_output is None:
                continue

            self.print_info(f"Changed-file lint base: {base_ref} ({merge_base[:12]})")
            return self.python_files_from_diff(diff_output)

        if os.getenv("GITHUB_EVENT_NAME") == "pull_request":
            return None

        self.print_warning("No merge base found; using staged and unstaged local changes")
        local_files = []
        for diff_args in (
            ["diff", "--name-only", "--diff-filter=ACMRTUXB", "--cached", "--"],
            ["diff", "--name-only", "--diff-filter=ACMRTUXB", "--"],
        ):
            diff_output = self.git_output(diff_args)
            if diff_output:
                local_files.extend(self.python_files_from_diff(diff_output))
        return sorted(set(local_files))

    def lint_targets(self, args) -> list[str] | None:
        """Return Ruff/Black targets for the selected linting mode."""
        if not self.should_lint_changed_files(args):
            self.print_info("Lint target mode: full repository")
            return ["."]

        changed_files = self.changed_python_files(args)
        if changed_files is None:
            self.print_error("Changed-file lint requested, but no PR base could be resolved")
            return None

        if not changed_files:
            self.print_info("No changed Python files found; skipping Ruff and Black checks")
            return []

        self.print_info("Lint target mode: changed Python files")
        for file_path in changed_files:
            self.print_info(f"  {file_path}")
        return changed_files

    def print_banner(self, text: str):
        """Print a styled banner."""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 60}")
        print(f"{text.center(60)}")
        print(f"{'=' * 60}{Colors.RESET}\n")

    def print_success(self, text: str):
        """Print success message."""
        print(f"{Colors.GREEN}{Colors.BOLD}✓ {text}{Colors.RESET}")

    def print_error(self, text: str):
        """Print error message."""
        print(f"{Colors.RED}{Colors.BOLD}✗ {text}{Colors.RESET}")

    def print_warning(self, text: str):
        """Print warning message."""
        print(f"{Colors.YELLOW}{Colors.BOLD}⚠ {text}{Colors.RESET}")

    def print_info(self, text: str):
        """Print info message."""
        print(f"{Colors.BLUE}INFO {text}{Colors.RESET}")

    def build_pytest_command(
        self,
        test_paths: list[str],
        markers: list[str] | None = None,
        coverage: bool = True,
        parallel: bool = False,
        verbose: bool = False,
        html_report: bool = False,
        junit_xml: bool = False,
        fast: bool = False,
    ) -> list[str]:
        """Build pytest command with various options."""

        cmd = [sys.executable, "-m", "pytest"]

        # Add test paths
        cmd.extend(test_paths)

        # Add markers
        if markers:
            for marker in markers:
                cmd.extend(["-m", marker])

        # Verbosity
        if verbose:
            cmd.append("-v")
        elif fast:
            cmd.append("-q")
        else:
            cmd.append("-v")

        # Coverage options
        if coverage and not fast:
            cmd.extend(
                [
                    "--cov=agents",
                    "--cov=core",
                    "--cov=connectors",
                    "--cov-report=term-missing",
                ]
            )

            if html_report:
                cmd.append("--cov-report=html:htmlcov")

        # Parallel execution
        if parallel:
            if importlib.util.find_spec("pytest_xdist") is not None:
                cmd.extend(["-n", "auto"])
            else:
                self.print_warning("pytest-xdist not installed, running sequentially")

        # JUnit XML for CI
        if junit_xml:
            cmd.extend(["--junit-xml=test-results.xml"])

        # Fast mode optimizations
        if fast:
            cmd.extend(
                [
                    "--tb=short",
                    "--no-cov",
                    "--disable-warnings",
                ]
            )

        return cmd

    def run_command(
        self,
        cmd: list[str],
        description: str,
        cwd: Path | None = None,
    ) -> tuple[bool, float, str]:
        """Run a command and return success status, duration, and output."""

        if cwd is None:
            cwd = self.project_root

        self.print_info(f"Running: {description}")
        print(f"{Colors.CYAN}Command: {' '.join(cmd)}{Colors.RESET}")

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minute timeout
            )

            duration = time.time() - start_time

            # Print real-time output
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(f"{Colors.YELLOW}{result.stderr}{Colors.RESET}")

            success = result.returncode == 0

            if success:
                self.print_success(f"{description} completed in {duration:.1f}s")
            else:
                self.print_error(
                    f"{description} failed after {duration:.1f}s "
                    f"(exit code {result.returncode})"
                )

            return success, duration, result.stdout + result.stderr

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            self.print_error(f"{description} timed out after {duration:.1f}s")
            return False, duration, "Command timed out"

        except Exception as e:
            duration = time.time() - start_time
            self.print_error(f"{description} failed with exception: {e}")
            return False, duration, str(e)

    def run_unit_tests(self, args) -> bool:
        """Run unit tests."""
        self.print_banner("Running Unit Tests")

        test_paths = [str(self.test_dir / "unit")]

        cmd = self.build_pytest_command(
            test_paths=test_paths,
            markers=["unit"] if not args.fast else None,
            coverage=args.coverage and not args.no_cov,
            parallel=args.parallel,
            verbose=args.verbose,
            html_report=args.html_report,
            junit_xml=args.junit_xml,
            fast=args.fast,
        )

        success, duration, output = self.run_command(cmd, "Unit Tests")

        self.results["unit"] = {
            "success": success,
            "duration": duration,
            "output": output,
        }

        return success

    def run_integration_tests(self, args) -> bool:
        """Run integration tests."""
        self.print_banner("Running Integration Tests")

        # Check if infrastructure is required
        if not args.no_infra_check:
            self.print_info("Checking infrastructure dependencies...")
            # In a real implementation, check Docker containers, Redis, Kafka etc.
            self.print_warning("Infrastructure check skipped (mock mode)")

        test_paths = [str(self.test_dir / "integration")]

        cmd = self.build_pytest_command(
            test_paths=test_paths,
            markers=["integration"] if not args.fast else None,
            coverage=args.coverage and not args.no_cov,
            parallel=args.parallel,
            verbose=args.verbose,
            html_report=args.html_report,
            junit_xml=args.junit_xml,
            fast=args.fast,
        )

        success, duration, output = self.run_command(cmd, "Integration Tests")

        self.results["integration"] = {
            "success": success,
            "duration": duration,
            "output": output,
        }

        return success

    def run_backtest_tests(self, args) -> bool:
        """Run backtesting tests."""
        self.print_banner("Running Backtesting Tests")

        test_paths = [str(self.test_dir)]

        cmd = self.build_pytest_command(
            test_paths=test_paths,
            markers=["backtest"],
            coverage=False,  # Backtests don't need coverage
            parallel=args.parallel,
            verbose=args.verbose,
            html_report=False,
            junit_xml=args.junit_xml,
            fast=args.fast,
        )

        success, duration, output = self.run_command(cmd, "Backtesting Tests")

        self.results["backtest"] = {
            "success": success,
            "duration": duration,
            "output": output,
        }

        return success

    def run_live_tests(self, args) -> bool:
        """Run live trading tests (with extra safety checks)."""
        self.print_banner("Running Live Tests")

        # Safety check for live tests
        if not args.confirm_live:
            self.print_error("Live tests require --confirm-live flag for safety")
            return False

        env_check = os.getenv("ENVIRONMENT", "development")
        if env_check == "live":
            self.print_error("Cannot run live tests in ENVIRONMENT=live mode")
            return False

        self.print_warning("Running live tests in paper trading mode")

        test_paths = [str(self.test_dir)]

        cmd = self.build_pytest_command(
            test_paths=test_paths,
            markers=["live"],
            coverage=False,
            parallel=False,  # Live tests run sequentially for safety
            verbose=True,
            html_report=False,
            junit_xml=args.junit_xml,
            fast=False,
        )

        success, duration, output = self.run_command(cmd, "Live Tests")

        self.results["live"] = {
            "success": success,
            "duration": duration,
            "output": output,
        }

        return success

    def run_linting(self, args) -> bool:
        """Run code quality checks."""
        self.print_banner("Running Code Quality Checks")

        checks = []
        lint_targets = self.lint_targets(args)
        if lint_targets is None:
            self.results["linting"] = {
                "success": False,
                "checks": [("changed-files", False)],
            }
            return False

        # Ruff
        if lint_targets:
            self.print_info("Running Ruff (linting)")
            success, _, _ = self.run_command(
                [sys.executable, "-m", "ruff", "check", *lint_targets],
                "Ruff Linting",
            )
            checks.append(("ruff", success))

        # Black (formatting check)
        if lint_targets and not args.skip_format:
            self.print_info("Running Black (format check)")
            success, _, _ = self.run_command(
                [sys.executable, "-m", "black", "--check", *lint_targets],
                "Black Format Check",
            )
            checks.append(("black", success))

        # MyPy (type checking)
        if not args.skip_mypy:
            self.print_info("Running MyPy (type checking)")
            success, _, _ = self.run_command(
                [sys.executable, "-m", "mypy", "agents/", "core/"],
                "MyPy Type Checking",
            )
            checks.append(("mypy", success))

        all_passed = all(success for _, success in checks)

        self.results["linting"] = {
            "success": all_passed,
            "checks": checks,
        }

        return all_passed

    def generate_report(self, args):
        """Generate test report."""
        self.print_banner("Test Results Summary")

        total_duration = sum(
            result.get("duration", 0)
            for result in self.results.values()
            if isinstance(result, dict)
        )

        passed_tests = sum(
            1
            for result in self.results.values()
            if isinstance(result, dict) and result.get("success", False)
        )

        total_tests = len(
            [r for r in self.results.values() if isinstance(r, dict) and "success" in r]
        )

        print(f"Total Duration: {total_duration:.1f}s")
        print(f"Tests Passed: {passed_tests}/{total_tests}")

        # Detailed results
        for test_type, result in self.results.items():
            if isinstance(result, dict) and "success" in result:
                status = "PASS" if result["success"] else "FAIL"
                color = Colors.GREEN if result["success"] else Colors.RED
                duration = result.get("duration", 0)
                print(f"{color}{status:>6}{Colors.RESET} {test_type:<15} ({duration:.1f}s)")

        # Coverage report
        if args.coverage and not args.no_cov:
            print(f"\n{Colors.CYAN}Coverage Report:{Colors.RESET}")
            if args.html_report:
                coverage_path = self.project_root / "htmlcov" / "index.html"
                if coverage_path.exists():
                    print(f"HTML coverage report: file://{coverage_path}")

        # Save JSON report if requested
        if args.json_report:
            report_path = self.project_root / "test-report.json"
            with open(report_path, "w") as f:
                json.dump(self.results, f, indent=2, default=str)
            self.print_info(f"JSON report saved to {report_path}")

        return passed_tests == total_tests


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ALGHREST Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_tests.py unit                    # Run unit tests only
  python scripts/run_tests.py integration --parallel  # Run integration tests in parallel
  python scripts/run_tests.py all --coverage         # Run all tests with coverage
  python scripts/run_tests.py unit --fast --no-cov   # Fast unit tests without coverage
  python scripts/run_tests.py lint --skip-mypy       # Run linting without type checking
  python scripts/run_tests.py lint --changed-only --base-ref origin/main
        """,
    )

    # Test type selection
    parser.add_argument(
        "test_type",
        choices=["unit", "integration", "backtest", "live", "lint", "all"],
        help="Type of tests to run",
    )

    # Coverage options
    parser.add_argument(
        "--coverage", action="store_true", default=True, help="Enable coverage reporting"
    )
    parser.add_argument("--no-cov", action="store_true", help="Disable coverage reporting")
    parser.add_argument("--html-report", action="store_true", help="Generate HTML coverage report")

    # Execution options
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--fast", action="store_true", help="Fast mode (reduced output, no coverage)"
    )
    parser.add_argument("--junit-xml", action="store_true", help="Generate JUnit XML for CI")

    # Safety options
    parser.add_argument("--confirm-live", action="store_true", help="Confirm running live tests")
    parser.add_argument("--no-infra-check", action="store_true", help="Skip infrastructure checks")

    # Linting options
    parser.add_argument("--skip-format", action="store_true", help="Skip formatting checks")
    parser.add_argument("--skip-mypy", action="store_true", help="Skip type checking")
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Run Ruff and Black only on changed Python files",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Force full-repository Ruff and Black checks, even in PR contexts",
    )
    parser.add_argument(
        "--base-ref",
        help="Base git ref or SHA used by --changed-only; defaults to PR base when available",
    )

    # Report options
    parser.add_argument("--json-report", action="store_true", help="Generate JSON test report")

    args = parser.parse_args()

    runner = TestRunner()

    # Override coverage if no-cov is specified
    if args.no_cov:
        args.coverage = False

    all_passed = True

    try:
        if args.test_type == "unit":
            all_passed = runner.run_unit_tests(args)

        elif args.test_type == "integration":
            all_passed = runner.run_integration_tests(args)

        elif args.test_type == "backtest":
            all_passed = runner.run_backtest_tests(args)

        elif args.test_type == "live":
            all_passed = runner.run_live_tests(args)

        elif args.test_type == "lint":
            all_passed = runner.run_linting(args)

        elif args.test_type == "all":
            runner.print_banner("Running All Tests")

            # Run in order of importance
            results = []
            results.append(runner.run_linting(args))
            results.append(runner.run_unit_tests(args))
            results.append(runner.run_integration_tests(args))

            if not args.fast:
                results.append(runner.run_backtest_tests(args))

            all_passed = all(results)

    except KeyboardInterrupt:
        runner.print_error("Tests interrupted by user")
        all_passed = False

    except Exception as e:
        runner.print_error(f"Test runner failed: {e}")
        all_passed = False

    finally:
        # Always generate report
        runner.generate_report(args)

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
