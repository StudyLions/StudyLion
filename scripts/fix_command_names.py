# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-14
# Purpose: Fix translations that break Discord command sync:
#   1. Command/parameter NAMES must be lowercase ASCII only
#   2. Command descriptions must be <= 100 characters
#   3. Reset any invalid name translations to English
# ============================================================

import os
import re
import polib

LOCALES_DIR = "locales"


def is_name_entry(msgctxt):
    """Check if this entry is a command/param/group NAME (not a description)."""
    if not msgctxt:
        return False
    ctx = msgctxt

    if '|' not in ctx:
        if ctx.startswith(('cmd:', 'group:', 'command')):
            return True
    else:
        parts = ctx.split('|')
        last = parts[-1]
        if last.startswith('param:') and not last.endswith('desc'):
            return True

    return False


def is_description_entry(msgctxt):
    """Check if this entry is a command/param description (100 char limit)."""
    if not msgctxt:
        return False
    return msgctxt.endswith('|desc')


def is_valid_command_name(name):
    """Check if a string is a valid Discord command/parameter name."""
    if not name or len(name) > 32:
        return False
    return bool(re.match(r'^[-_\w]{1,32}$', name, re.UNICODE)) and name == name.lower()


def main():
    fixed_names = 0
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
                if not entry.msgstr or not entry.msgid:
                    continue

                if is_name_entry(entry.msgctxt):
                    if not is_valid_command_name(entry.msgstr):
                        if is_valid_command_name(entry.msgid):
                            entry.msgstr = entry.msgid
                            fixed_names += 1
                            modified = True
                        else:
                            entry.msgstr = entry.msgid.lower().replace(' ', '_')[:32]
                            fixed_names += 1
                            modified = True

                if is_description_entry(entry.msgctxt):
                    if len(entry.msgstr) > 100:
                        entry.msgstr = entry.msgstr[:97] + "..."
                        truncated_descs += 1
                        modified = True

            if modified:
                po.save()
                mo_path = po_path.replace('.po', '.mo')
                po.save_as_mofile(mo_path)
                files_modified += 1

    print(f"Fixed {fixed_names} invalid command/param names")
    print(f"Truncated {truncated_descs} descriptions over 100 chars")
    print(f"Modified {files_modified} files")


if __name__ == '__main__':
    main()
