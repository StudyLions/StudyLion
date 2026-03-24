# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: Parse PM2 log output for Python tracebacks, errors,
#          and recurring patterns. Can read from stdin (piped
#          SSH output) or from a local log file.
#
# Usage examples:
#   # Pipe live/test bot logs directly:
#   ssh -i ~/.ssh/lionbot_ed25519 root@65.109.163.156 \
#       "su - leo -c 'pm2 logs test-leo --lines 5000 --nostream'" \
#       | python scripts/mine_logs.py
#
#   # Or from a saved file:
#   python scripts/mine_logs.py --file saved_logs.txt
#
#   # Adjust minimum occurrences to show:
#   python scripts/mine_logs.py --min-count 2 --file saved_logs.txt
# ============================================================

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TextIO


@dataclass
class Traceback:
    lines: list[str] = field(default_factory=list)
    exception_line: str = ""
    source_file: str = ""
    source_lineno: str = ""
    command_context: str = ""

    @property
    def signature(self) -> str:
        """Unique signature for deduplication: exception class + message + location."""
        exc_class = self.exception_line.split(":")[0].strip() if self.exception_line else "Unknown"
        return f"{exc_class} @ {self.source_file}:{self.source_lineno}"


@dataclass
class ErrorEntry:
    level: str
    message: str
    timestamp: str = ""
    context: str = ""

    @property
    def signature(self) -> str:
        msg_short = self.message[:120].strip()
        return f"[{self.level}] {msg_short}"


TRACEBACK_START = re.compile(r"Traceback \(most recent call last\)")
EXCEPTION_LINE = re.compile(r"^(\w+(?:\.\w+)*(?:Error|Exception|Warning|Failure))\b")
FILE_LINE = re.compile(r'^\s+File "([^"]+)", line (\d+)')
LOG_ERROR = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?.*?"
    r"\b(ERROR|CRITICAL|FATAL)\b[:\s]*(.*)",
    re.IGNORECASE,
)
DISCORD_ERROR = re.compile(r"discord\.errors\.(\w+)")
COMMAND_CONTEXT = re.compile(r"(?:Run|Acmp)\s+([\w.]+)")


def parse_logs(stream: TextIO) -> tuple[list[Traceback], list[ErrorEntry], Counter]:
    tracebacks: list[Traceback] = []
    errors: list[ErrorEntry] = []
    discord_errors: Counter = Counter()

    current_tb: Traceback | None = None
    last_file = ""
    last_lineno = ""
    recent_context = ""

    for raw_line in stream:
        line = raw_line.rstrip("\n\r")

        ctx_match = COMMAND_CONTEXT.search(line)
        if ctx_match:
            recent_context = ctx_match.group(1)

        disc_match = DISCORD_ERROR.search(line)
        if disc_match:
            discord_errors[disc_match.group(1)] += 1

        if TRACEBACK_START.search(line):
            current_tb = Traceback(command_context=recent_context)
            current_tb.lines.append(line)
            continue

        if current_tb is not None:
            current_tb.lines.append(line)
            fm = FILE_LINE.match(line)
            if fm:
                last_file = fm.group(1)
                last_lineno = fm.group(2)
            if EXCEPTION_LINE.match(line.strip()):
                current_tb.exception_line = line.strip()
                current_tb.source_file = last_file
                current_tb.source_lineno = last_lineno
                tracebacks.append(current_tb)
                current_tb = None
                last_file = ""
                last_lineno = ""
            elif not line.strip() or (not line.startswith(" ") and "File" not in line and "Traceback" not in line):
                if len(current_tb.lines) > 1:
                    current_tb.exception_line = current_tb.lines[-1].strip() if current_tb.lines else "Unknown"
                    current_tb.source_file = last_file
                    current_tb.source_lineno = last_lineno
                    tracebacks.append(current_tb)
                current_tb = None
                last_file = ""
                last_lineno = ""
            continue

        err_match = LOG_ERROR.search(line)
        if err_match:
            errors.append(ErrorEntry(
                level=err_match.group(2).upper(),
                message=err_match.group(3),
                timestamp=err_match.group(1) or "",
                context=recent_context,
            ))

    return tracebacks, errors, discord_errors


def print_report(
    tracebacks: list[Traceback],
    errors: list[ErrorEntry],
    discord_errors: Counter,
    min_count: int = 1,
):
    print("=" * 72)
    print("  LIONBOT LOG ANALYSIS REPORT")
    print("=" * 72)

    # --- Tracebacks grouped by signature ---
    tb_groups: dict[str, list[Traceback]] = defaultdict(list)
    for tb in tracebacks:
        tb_groups[tb.signature].append(tb)

    sorted_tb = sorted(tb_groups.items(), key=lambda x: len(x[1]), reverse=True)
    filtered_tb = [(sig, tbs) for sig, tbs in sorted_tb if len(tbs) >= min_count]

    print(f"\n--- TRACEBACKS ({len(tracebacks)} total, {len(tb_groups)} unique) ---\n")
    if not filtered_tb:
        print("  (none matching filter)\n")
    for sig, tbs in filtered_tb:
        print(f"  [{len(tbs)}x] {sig}")
        if tbs[0].command_context:
            print(f"       Command context: {tbs[0].command_context}")
        exc_line = tbs[0].exception_line
        if len(exc_line) > 200:
            exc_line = exc_line[:200] + "..."
        print(f"       Exception: {exc_line}")
        print()

    # --- Error log entries ---
    err_groups: Counter = Counter()
    for e in errors:
        err_groups[e.signature] += 1

    sorted_err = err_groups.most_common()
    filtered_err = [(sig, cnt) for sig, cnt in sorted_err if cnt >= min_count]

    print(f"--- ERROR/CRITICAL LOG ENTRIES ({len(errors)} total, {len(err_groups)} unique) ---\n")
    if not filtered_err:
        print("  (none matching filter)\n")
    for sig, cnt in filtered_err:
        print(f"  [{cnt}x] {sig}")
    print()

    # --- Discord-specific errors ---
    print(f"--- DISCORD API ERRORS ({sum(discord_errors.values())} total) ---\n")
    if not discord_errors:
        print("  (none found)\n")
    for err_name, cnt in discord_errors.most_common():
        if cnt >= min_count:
            print(f"  [{cnt}x] discord.errors.{err_name}")
    print()

    # --- Summary ---
    print("--- SUMMARY ---\n")
    print(f"  Total tracebacks:       {len(tracebacks)}")
    print(f"  Unique tracebacks:      {len(tb_groups)}")
    print(f"  Total error log lines:  {len(errors)}")
    print(f"  Unique error patterns:  {len(err_groups)}")
    print(f"  Discord API errors:     {sum(discord_errors.values())}")
    print()

    if filtered_tb:
        top_sig, top_tbs = filtered_tb[0]
        print(f"  Most common traceback ({len(top_tbs)}x):")
        print(f"    {top_sig}")
        print()
        print("  Full traceback of most recent occurrence:")
        print("  " + "-" * 60)
        for line in top_tbs[-1].lines:
            print(f"    {line}")
        print("  " + "-" * 60)
    print()


def main():
    parser = argparse.ArgumentParser(description="Parse PM2 logs for errors and tracebacks")
    parser.add_argument("--file", "-f", help="Read from file instead of stdin")
    parser.add_argument("--min-count", "-m", type=int, default=1,
                        help="Only show errors occurring at least this many times (default: 1)")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as f:
            tracebacks, errors, discord_errors = parse_logs(f)
    else:
        tracebacks, errors, discord_errors = parse_logs(sys.stdin)

    print_report(tracebacks, errors, discord_errors, min_count=args.min_count)


if __name__ == "__main__":
    main()
