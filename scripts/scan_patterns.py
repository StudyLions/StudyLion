# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: Scan the StudyLion codebase for common discord.py
#          anti-patterns and potential bugs. Runs locally on
#          the source tree (no server access needed).
#
# Usage:
#   python scripts/scan_patterns.py [--src-dir src]
# ============================================================

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    severity: str  # "error", "warning", "info"
    message: str
    code_line: str


SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

CHECKS: list[tuple[str, str, str, re.Pattern]] = []


def register_check(rule_id: str, severity: str, message: str, pattern: str, flags: int = 0):
    CHECKS.append((rule_id, severity, message, re.compile(pattern, flags)))


# --- Registered checks ---

register_check(
    "RESP-DOUBLE",
    "error",
    "Possible double interaction response (response.send_message called after defer/send). "
    "This will raise InteractionResponded at runtime.",
    r"interaction\.response\.\w+\(.*\).*\n.*interaction\.response\.\w+\(",
    re.MULTILINE,
)

register_check(
    "MISSING-AWAIT-RESP",
    "error",
    "Missing 'await' before interaction.response method call. "
    "The response will silently fail without await.",
    r"(?<!await\s)(?<!await  )interaction\.response\.(?:send_message|defer|send_modal)\(",
)

register_check(
    "MISSING-AWAIT-FOLLOWUP",
    "warning",
    "Missing 'await' before interaction.followup.send(). "
    "The message will not be sent.",
    r"(?<!await\s)(?<!await  )interaction\.followup\.send\(",
)

register_check(
    "MISSING-AWAIT-EDIT",
    "warning",
    "Missing 'await' before interaction.edit_original_response(). ",
    r"(?<!await\s)(?<!await  )interaction\.edit_original_response\(",
)

register_check(
    "BARE-EXCEPT",
    "warning",
    "Bare 'except:' catches everything including KeyboardInterrupt and SystemExit. "
    "Use 'except Exception:' instead.",
    r"^\s*except\s*:\s*$",
    re.MULTILINE,
)

register_check(
    "UNBOUNDED-QUERY",
    "info",
    "SQL SELECT without LIMIT. Could return unbounded result sets on large tables.",
    r"""(?:execute|fetch)\s*\(\s*['"]?\s*SELECT\s+(?!.*LIMIT\s+\d).*(?:FROM|from)\s+\w+(?!\s+LIMIT)""",
    re.IGNORECASE | re.DOTALL,
)

register_check(
    "MISSING-AWAIT-CTX",
    "error",
    "Missing 'await' before ctx.reply() or ctx.send(). The message will not be sent.",
    r"(?<!await\s)(?<!await  )ctx\.(?:reply|send)\(",
)

register_check(
    "BROAD-PERMISSION-CHECK",
    "info",
    "Using administrator permission check. Consider if a more granular permission is appropriate.",
    r"\.administrator\b",
)

register_check(
    "HARDCODED-ID",
    "info",
    "Hardcoded Discord snowflake ID. Consider moving to config.",
    r"(?<!\d)\d{17,20}(?!\d)(?!.*(?:#|config|admin|shard_count|prefix|version|DATA_VERSION|application_id))",
)

register_check(
    "DEPRECATED-DATETIME",
    "warning",
    "Using datetime.utcnow() which is deprecated in Python 3.12+. Use datetime.now(timezone.utc) instead.",
    r"datetime\.utcnow\(\)",
)

register_check(
    "SYNC-SLEEP",
    "warning",
    "Using time.sleep() in async code. This blocks the event loop. Use asyncio.sleep() instead.",
    r"^\s*[^#\n]*time\.sleep\(",
    re.MULTILINE,
)

register_check(
    "RAW-SQL-FSTRING",
    "warning",
    "Possible SQL injection: f-string or .format() used in SQL query. Use parameterized queries.",
    r"""(?:execute|fetch)\s*\(\s*f['"]+.*(?:SELECT|INSERT|UPDATE|DELETE)""",
    re.IGNORECASE,
)


def scan_file(filepath: Path, src_root: Path) -> list[Finding]:
    findings = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    rel_path = str(filepath.relative_to(src_root.parent))
    lines = content.split("\n")

    for rule_id, severity, message, pattern in CHECKS:
        for match in pattern.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            code_line = lines[line_num - 1].strip() if line_num <= len(lines) else ""

            if rule_id == "HARDCODED-ID":
                if any(skip in code_line for skip in [
                    "# ", "logger", "log", "print", "version", "DATA_VERSION",
                    "shard", "prefix", "config", "import", "emoji", "EMOJI",
                    "Colour(", "Color(", "0x", "getint", "getintlist",
                ]):
                    continue

            findings.append(Finding(
                file=rel_path,
                line=line_num,
                rule=rule_id,
                severity=severity,
                message=message,
                code_line=code_line,
            ))

    return findings


def scan_directory(src_dir: Path) -> list[Finding]:
    findings = []
    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        findings.extend(scan_file(py_file, src_dir))
    return findings


def print_report(findings: list[Finding]):
    print("=" * 72)
    print("  LIONBOT ANTI-PATTERN SCAN REPORT")
    print("=" * 72)

    by_severity: dict[str, list[Finding]] = {"error": [], "warning": [], "info": []}
    for f in findings:
        by_severity[f.severity].append(f)

    for severity in ["error", "warning", "info"]:
        items = by_severity[severity]
        label = severity.upper()
        print(f"\n--- {label} ({len(items)} findings) ---\n")
        if not items:
            print("  (none)\n")
            continue

        by_rule: dict[str, list[Finding]] = {}
        for f in items:
            by_rule.setdefault(f.rule, []).append(f)

        for rule, rule_findings in sorted(by_rule.items()):
            print(f"  [{rule}] {rule_findings[0].message}")
            print(f"  Occurrences ({len(rule_findings)}):")
            for f in rule_findings[:15]:
                print(f"    {f.file}:{f.line}  |  {f.code_line[:100]}")
            if len(rule_findings) > 15:
                print(f"    ... and {len(rule_findings) - 15} more")
            print()

    print("--- SUMMARY ---\n")
    print(f"  Errors:   {len(by_severity['error'])}")
    print(f"  Warnings: {len(by_severity['warning'])}")
    print(f"  Info:     {len(by_severity['info'])}")
    print(f"  Total:    {len(findings)}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Scan StudyLion source for anti-patterns")
    parser.add_argument("--src-dir", default="src", help="Source directory to scan (default: src)")
    args = parser.parse_args()

    src_dir = Path(args.src_dir).resolve()
    if not src_dir.is_dir():
        print(f"Error: '{src_dir}' is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {src_dir} ...\n")
    findings = scan_directory(src_dir)
    print_report(findings)


if __name__ == "__main__":
    main()
