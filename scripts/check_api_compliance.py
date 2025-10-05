#!/usr/bin/env python3
"""
Mastodon API Compliance Checker

This script analyzes all Mastodon API calls in the codebase and compares them
against the official mastodon.py library to ensure 100% compliance.

Usage:
    python scripts/check_api_compliance.py
    python scripts/check_api_compliance.py --fix  # Auto-fix issues (future)
    python scripts/check_api_compliance.py --verbose  # Show all details
"""

import ast
import inspect
import sys
from pathlib import Path
from typing import Any

# Add backend to path so we can import mastodon
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from mastodon import Mastodon
except ImportError:
    print("ERROR: mastodon.py not installed. Run: pip install Mastodon.py")
    sys.exit(1)


class MastodonAPICallVisitor(ast.NodeVisitor):
    """AST visitor that extracts all Mastodon API method calls."""

    def __init__(self, filename: str):
        self.filename = filename
        self.calls: list[dict[str, Any]] = []
        self.current_function = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track which function we're in for better error reporting."""
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_Call(self, node: ast.Call) -> None:
        """Extract all calls to Mastodon client methods."""
        # Check for client.method_name(...) pattern
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                # Direct client calls: client.account_statuses(...)
                if node.func.value.id == "client":
                    self._record_call(node, node.func.attr, "direct")
            elif isinstance(node.func.value, ast.Attribute):
                # Service calls: mastodon_service.get_admin_client().account(...)
                # or self.client.account(...)
                if (
                    isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == "self"
                    and node.func.value.attr == "client"
                ):
                    self._record_call(node, node.func.attr, "self.client")

        self.generic_visit(node)

    def _record_call(self, node: ast.Call, method_name: str, call_type: str) -> None:
        """Record details about a Mastodon API call."""
        # Extract argument names and values
        args = []
        kwargs = {}

        for arg in node.args:
            args.append(self._get_arg_repr(arg))

        for keyword in node.keywords:
            # Skip **kwargs expansion (keyword.arg is None for **dict unpacking)
            if keyword.arg is not None:
                kwargs[keyword.arg] = self._get_arg_repr(keyword.value)

        self.calls.append(
            {
                "file": self.filename,
                "line": node.lineno,
                "function": self.current_function,
                "method": method_name,
                "call_type": call_type,
                "args": args,
                "kwargs": kwargs,
            }
        )

    def _get_arg_repr(self, node: ast.AST) -> str:
        """Get string representation of an argument."""
        if isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return ast.unparse(node)
        elif isinstance(node, ast.List):
            return f"[{len(node.elts)} items]"
        elif isinstance(node, ast.Dict):
            return f"{{{len(node.keys)} items}}"
        else:
            return ast.unparse(node)[:50]


class MastodonAPIChecker:
    """Main checker class that validates API calls against mastodon.py."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.issues: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.mastodon_methods = self._get_mastodon_methods()

    def _get_mastodon_methods(self) -> dict[str, inspect.Signature]:
        """Get all public methods from Mastodon class with their signatures."""
        methods = {}
        for name, method in inspect.getmembers(Mastodon, predicate=inspect.isfunction):
            if not name.startswith("_"):
                try:
                    methods[name] = inspect.signature(method)
                except (ValueError, TypeError):
                    # Some methods might not have inspectable signatures
                    pass
        return methods

    def scan_file(self, filepath: Path) -> list[dict[str, Any]]:
        """Scan a Python file for Mastodon API calls."""
        try:
            with open(filepath, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(filepath))

            visitor = MastodonAPICallVisitor(str(filepath))
            visitor.visit(tree)
            return visitor.calls
        except SyntaxError as e:
            print(f"⚠️  Syntax error in {filepath}: {e}")
            return []
        except Exception as e:
            print(f"⚠️  Error scanning {filepath}: {e}")
            return []

    def check_call(self, call: dict[str, Any]) -> None:
        """Validate a single API call against mastodon.py."""
        method_name = call["method"]

        # Check if method exists
        if method_name not in self.mastodon_methods:
            self.issues.append(
                {
                    "severity": "ERROR",
                    "type": "unknown_method",
                    "message": f"Method '{method_name}' does not exist in mastodon.py",
                    "file": call["file"],
                    "line": call["line"],
                    "function": call["function"],
                    "suggestion": self._suggest_similar_method(method_name),
                }
            )
            return

        # Get the signature
        signature = self.mastodon_methods[method_name]
        params = signature.parameters

        # Check for deprecated methods
        if method_name in DEPRECATED_METHODS:
            self.warnings.append(
                {
                    "severity": "WARNING",
                    "type": "deprecated",
                    "message": f"Method '{method_name}' is deprecated",
                    "file": call["file"],
                    "line": call["line"],
                    "function": call["function"],
                    "suggestion": DEPRECATED_METHODS[method_name],
                }
            )

        # Check for known API version issues
        if method_name in API_VERSION_ISSUES:
            self.issues.append(
                {
                    "severity": "ERROR",
                    "type": "api_version",
                    "message": API_VERSION_ISSUES[method_name]["message"],
                    "file": call["file"],
                    "line": call["line"],
                    "function": call["function"],
                    "suggestion": API_VERSION_ISSUES[method_name]["fix"],
                }
            )

        # Validate kwargs against signature
        for kwarg_name in call["kwargs"]:
            # Skip 'self' parameter
            param_names = [p for p in params.keys() if p != "self"]
            if kwarg_name not in param_names:
                self.issues.append(
                    {
                        "severity": "ERROR",
                        "type": "invalid_parameter",
                        "message": f"Parameter '{kwarg_name}' is not valid for {method_name}()",
                        "file": call["file"],
                        "line": call["line"],
                        "function": call["function"],
                        "valid_params": param_names,
                    }
                )

    def _suggest_similar_method(self, method_name: str) -> str:
        """Suggest similar method names based on fuzzy matching."""
        # Simple similarity check
        candidates = []
        for name in self.mastodon_methods.keys():
            if method_name.lower() in name.lower() or name.lower() in method_name.lower():
                candidates.append(name)

        if candidates:
            return f"Did you mean: {', '.join(candidates[:3])}?"
        return "No similar methods found"

    def scan_codebase(self, root_dir: Path) -> None:
        """Scan entire codebase for API calls."""
        print(f"🔍 Scanning {root_dir} for Mastodon API calls...\n")

        all_calls = []
        backend_dir = root_dir / "backend" / "app"

        # Scan all Python files
        for py_file in backend_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            calls = self.scan_file(py_file)
            all_calls.extend(calls)

        print(f"📊 Found {len(all_calls)} Mastodon API calls\n")

        # Check each call
        for call in all_calls:
            self.check_call(call)

            if self.verbose:
                self._print_call(call)

    def _print_call(self, call: dict[str, Any]) -> None:
        """Print details about a call."""
        file_short = Path(call["file"]).relative_to(Path.cwd())
        print(f"  {file_short}:{call['line']} in {call['function']}()")
        kwarg_names = [k for k in call["kwargs"].keys() if k is not None]
        print(f"    {call['method']}({', '.join(kwarg_names)})")

    def report(self) -> bool:
        """Print final report and return success status."""
        print("\n" + "=" * 80)
        print("MASTODON API COMPLIANCE REPORT")
        print("=" * 80 + "\n")

        # Print errors
        if self.issues:
            print(f"❌ {len(self.issues)} ERRORS FOUND:\n")
            for i, issue in enumerate(self.issues, 1):
                file_short = Path(issue["file"]).relative_to(Path.cwd())
                print(f"{i}. {issue['severity']}: {issue['type']}")
                print(f"   File: {file_short}:{issue['line']}")
                if issue["function"]:
                    print(f"   Function: {issue['function']}()")
                print(f"   Message: {issue['message']}")
                if "suggestion" in issue:
                    print(f"   💡 {issue['suggestion']}")
                if "valid_params" in issue:
                    print(f"   Valid parameters: {', '.join(issue['valid_params'])}")
                print()

        # Print warnings
        if self.warnings:
            print(f"⚠️  {len(self.warnings)} WARNINGS:\n")
            for i, warning in enumerate(self.warnings, 1):
                file_short = Path(warning["file"]).relative_to(Path.cwd())
                print(f"{i}. {warning['severity']}: {warning['type']}")
                print(f"   File: {file_short}:{warning['line']}")
                if warning["function"]:
                    print(f"   Function: {warning['function']}()")
                print(f"   Message: {warning['message']}")
                if "suggestion" in warning:
                    print(f"   💡 {warning['suggestion']}")
                print()

        # Summary
        if not self.issues and not self.warnings:
            print("✅ All Mastodon API calls are compliant!")
            print(f"   Checked {len(self.mastodon_methods)} available methods")
            return True
        else:
            print("📊 Summary:")
            print(f"   Errors: {len(self.issues)}")
            print(f"   Warnings: {len(self.warnings)}")
            print(f"   Available methods in mastodon.py: {len(self.mastodon_methods)}")
            return len(self.issues) == 0

    def list_available_methods(self) -> None:
        """List all available Mastodon methods (for reference)."""
        print("\n" + "=" * 80)
        print("AVAILABLE MASTODON.PY METHODS")
        print("=" * 80 + "\n")

        # Group by category
        categories = {
            "account": [],
            "admin": [],
            "status": [],
            "instance": [],
            "report": [],
            "oauth": [],
            "other": [],
        }

        for name in sorted(self.mastodon_methods.keys()):
            categorized = False
            for category in categories.keys():
                if name.startswith(category):
                    categories[category].append(name)
                    categorized = True
                    break
            if not categorized:
                categories["other"].append(name)

        for category, methods in categories.items():
            if methods:
                print(f"\n{category.upper()}:")
                for method in methods:
                    sig = self.mastodon_methods[method]
                    print(f"  • {method}{sig}")


# Known deprecated methods and their replacements
DEPRECATED_METHODS = {
    "admin_accounts": "Use admin_accounts_v2() instead - v1 may return incorrect data",
}

# Known API version issues
API_VERSION_ISSUES = {
    # Add specific known issues here
}


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Check Mastodon API compliance")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all API calls")
    parser.add_argument("--list-methods", "-l", action="store_true", help="List all available methods")
    parser.add_argument("--fix", action="store_true", help="Auto-fix issues (not implemented yet)")

    args = parser.parse_args()

    checker = MastodonAPIChecker(verbose=args.verbose)

    if args.list_methods:
        checker.list_available_methods()
        return 0

    # Scan codebase
    root_dir = Path(__file__).parent.parent
    checker.scan_codebase(root_dir)

    # Report results
    success = checker.report()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
