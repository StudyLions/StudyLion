# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-14
# Purpose: Fix v2 - smarter detection of name vs description entries.
#          Uses the msgid content to determine if it's a name or description.
#          Names are short, no spaces/punctuation. Descriptions have spaces.
# ============================================================

import os
import re
import polib

LOCALES_DIR = "locales"


def looks_like_name(msgid):
    """A command/param name is short, lowercase, no spaces or punctuation (except _ and -)."""
    if not msgid or len(msgid) > 32:
        return False
    return bool(re.match(r'^[a-z0-9_-]+$', msgid))


def is_name_context(msgctxt):
    """Check if msgctxt is a name-type context (not description)."""
    if not msgctxt:
        return False
    if '|' not in msgctxt:
        return msgctxt.startswith(('cmd:', 'group:', 'command'))
    parts = msgctxt.split('|')
    last = parts[-1]
    if last.startswith('param:') and 'desc' not in last:
        return True
    return False


def is_valid_discord_name(name):
    """Check if a string is valid for Discord command/parameter name."""
    if not name or len(name) > 32:
        return False
    return bool(re.match(r'^[-_\w]{1,32}$', name, re.UNICODE)) and name == name.lower()


def main():
    fixed_names = 0
    restored_descs = 0
    truncated_descs = 0
    files_modified = 0

    for locale_dir in sorted(os.listdir(LOCALES_DIR)):
        lc_path = os.path.join(LOCALES_DIR, locale_dir, "LC_MESSAGES")
        if not os.path.isdir(lc_path):
            continue

        for po_file in sorted(os.listdir(lc_path)):
            if not po_file.endswith('.po'):
                continue

            po_path = os.path.join(lc_path, po_file)
            try:
                po = polib.pofile(po_path)
            except Exception:
                continue

            modified = False
            for entry in po:
                if not entry.msgid:
                    continue

                if is_name_context(entry.msgctxt):
                    if looks_like_name(entry.msgid):
                        if entry.msgstr and not is_valid_discord_name(entry.msgstr):
                            entry.msgstr = entry.msgid
                            fixed_names += 1
                            modified = True
                    else:
                        mangled = entry.msgid.lower().replace(' ', '_')[:32]
                        if entry.msgstr == mangled or entry.msgstr == mangled[:31]:
                            entry.msgstr = ""
                            restored_descs += 1
                            modified = True

                if entry.msgctxt and entry.msgctxt.endswith('|desc'):
                    if entry.msgstr and len(entry.msgstr) > 100:
                        entry.msgstr = entry.msgstr[:97] + "..."
                        truncated_descs += 1
                        modified = True

            if modified:
                po.save()
                mo_path = po_path.replace('.po', '.mo')
                po.save_as_mofile(mo_path)
                files_modified += 1

    print(f"Fixed {fixed_names} invalid command/param names")
    print(f"Restored {restored_descs} mangled descriptions (reset to empty for English fallback)")
    print(f"Truncated {truncated_descs} descriptions over 100 chars")
    print(f"Modified {files_modified} files")

    os.chdir(os.path.join(os.path.dirname(__file__), '..'))
    problems = []
    for loc_dir in sorted(os.listdir('locales')):
        lc = os.path.join('locales', loc_dir, 'LC_MESSAGES')
        if not os.path.isdir(lc):
            continue
        for f in sorted(os.listdir(lc)):
            if not f.endswith('.po'):
                continue
            try:
                p = polib.pofile(os.path.join(lc, f))
            except:
                continue
            for e in p:
                if not e.msgctxt or not e.msgstr:
                    continue
                if is_name_context(e.msgctxt) and looks_like_name(e.msgid):
                    if not is_valid_discord_name(e.msgstr):
                        problems.append(f"{loc_dir}/{f}: [{e.msgctxt}] '{e.msgid}' => '{e.msgstr}'")
    if problems:
        print(f"\nRemaining {len(problems)} invalid names:")
        for p in problems[:10]:
            print(f"  {p}")
    else:
        print("\nNo remaining invalid name entries!")


if __name__ == '__main__':
    os.chdir(os.path.join(os.path.dirname(__file__), '..'))
    main()
