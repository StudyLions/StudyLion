# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-13
# Purpose: Extract translations from Transifex git branches
#          and save matching entries as JSON for reuse.
# ============================================================

import os
import sys
import json
import subprocess
import re

sys.path.insert(0, os.path.dirname(__file__))
from po_utils import parse_pot, TEMPLATES_DIR

BRANCH_PREFIX = "remotes/origin/translations_79b2d482755244ef9bc86b9951a1ebc2_"

BRANCH_TO_LOCALE = {
    'ar': 'ar',
    'de': 'de',
    'es_419': 'es_ES',
    'fr': 'fr',
    'hi': 'hi',
    'ja': 'ja',
    'ko': 'ko',
    'pl': 'pl',
    'pt_BR': 'pt_BR',
    'tr': 'tr',
    'vi_VN': 'vi',
}


def git_show(branch, path):
    """Get file content from a git branch."""
    try:
        result = subprocess.run(
            ['git', 'show', f'{branch}:{path}'],
            capture_output=True, text=True, encoding='utf-8'
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except Exception:
        return None


def git_ls_tree(branch, path):
    """List files in a directory on a git branch."""
    try:
        result = subprocess.run(
            ['git', 'ls-tree', '--name-only', branch, path],
            capture_output=True, text=True, encoding='utf-8'
        )
        if result.returncode == 0:
            return [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        return []
    except Exception:
        return []


def parse_po_content(content):
    """Parse .po file content and return dict of (msgctxt, msgid) -> msgstr."""
    translations = {}
    blocks = re.split(r'\n\n+', content)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        msgctxt = None
        msgid = None
        msgstr = None

        lines = block.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith('msgctxt '):
                msgctxt = extract_string(lines, i)
                i = skip_continuation(lines, i)
            elif line.startswith('msgid_plural '):
                i = skip_continuation(lines, i)
            elif line.startswith('msgid '):
                msgid = extract_string(lines, i)
                i = skip_continuation(lines, i)
            elif line.startswith('msgstr ') or line.startswith('msgstr['):
                if msgstr is None:
                    msgstr = extract_string(lines, i)
                i = skip_continuation(lines, i)
            i += 1

        if msgid and msgstr:
            translations[(msgctxt, msgid)] = msgstr

    return translations


def extract_string(lines, start_idx):
    line = lines[start_idx]
    match = re.search(r'"(.*)"', line)
    if not match:
        return ""
    result = match.group(1)
    i = start_idx + 1
    while i < len(lines) and lines[i].startswith('"'):
        m = re.match(r'^"(.*)"', lines[i])
        if m:
            result += m.group(1)
        i += 1
    return unescape(result)


def skip_continuation(lines, start_idx):
    i = start_idx + 1
    while i < len(lines) and lines[i].startswith('"'):
        i += 1
    return i - 1


def unescape(s):
    s = s.replace('\\n', '\n')
    s = s.replace('\\t', '\t')
    s = s.replace('\\"', '"')
    s = s.replace('\\\\', '\\')
    return s


def main():
    pot_files = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith('.pot')]
    pot_strings = {}
    for pot_file in pot_files:
        domain = pot_file.replace('.pot', '')
        entries = parse_pot(os.path.join(TEMPLATES_DIR, pot_file))
        pot_strings[domain] = {(e['msgctxt'], e['msgid']) for e in entries}

    print(f"Loaded {len(pot_files)} .pot templates with {sum(len(s) for s in pot_strings.values())} total strings")

    salvaged = {}
    stats = {}

    for branch_locale, our_locale in BRANCH_TO_LOCALE.items():
        branch = f"{BRANCH_PREFIX}{branch_locale}"
        print(f"\n--- Branch: {branch_locale} -> locale: {our_locale} ---")

        locale_dir = f"locales/{branch_locale}/LC_MESSAGES"
        if branch_locale == 'vi_VN':
            locale_dir = f"locales/vi_VN/LC_MESSAGES"
        elif branch_locale == 'es_419':
            locale_dir = f"locales/es_419/LC_MESSAGES"

        files = git_ls_tree(branch, locale_dir + '/')
        if not files:
            locale_dir = f"locales/{branch_locale}/LC_MESSAGES"
            files = git_ls_tree(branch, locale_dir + '/')

        if not files:
            print(f"  No .po files found, trying alternate paths...")
            for alt_dir in [f"locales/{branch_locale}", f"locales/{our_locale}/LC_MESSAGES"]:
                files = git_ls_tree(branch, alt_dir + '/')
                if files:
                    locale_dir = alt_dir
                    break

        po_files = [f for f in files if f.endswith('.po')]
        if not po_files:
            alt_files = git_ls_tree(branch, locale_dir)
            po_files = [f for f in alt_files if f.endswith('.po')]

        print(f"  Found {len(po_files)} .po files")

        branch_total = 0
        branch_matched = 0

        for po_path in po_files:
            if '/' not in po_path:
                po_path = f"{locale_dir}/{po_path}"
            content = git_show(branch, po_path)
            if not content:
                continue

            domain = os.path.basename(po_path).replace('.po', '')
            if domain not in pot_strings:
                continue

            trans = parse_po_content(content)
            valid_keys = pot_strings[domain]

            matched = 0
            for key, value in trans.items():
                if key in valid_keys:
                    if domain not in salvaged:
                        salvaged[domain] = {}
                    ctx_key = f"{key[0]}|||{key[1]}" if key[0] else f"|||{key[1]}"
                    if ctx_key not in salvaged[domain]:
                        salvaged[domain][ctx_key] = {}
                    salvaged[domain][ctx_key][our_locale] = value
                    matched += 1

            branch_total += len(trans)
            branch_matched += matched
            if matched > 0:
                print(f"  {domain}: {matched}/{len(trans)} strings matched current templates")

        stats[our_locale] = {'total': branch_total, 'matched': branch_matched}
        print(f"  TOTAL: {branch_matched}/{branch_total} strings salvaged")

    output_path = os.path.join('scripts', 'salvaged_translations.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(salvaged, f, ensure_ascii=False, indent=2)

    print(f"\n=== SUMMARY ===")
    total_salvaged = 0
    for locale, s in sorted(stats.items()):
        print(f"  {locale}: {s['matched']} strings salvaged")
        total_salvaged += s['matched']
    print(f"  TOTAL: {total_salvaged} translations salvaged across all languages")
    print(f"  Saved to: {output_path}")


if __name__ == '__main__':
    main()
