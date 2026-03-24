# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-13
# Purpose: Compile all .po files to .mo files for gettext.
# ============================================================

import os
import polib

LOCALES_DIR = "locales"


def main():
    total = 0
    errors = 0

    for locale_dir in sorted(os.listdir(LOCALES_DIR)):
        lc_path = os.path.join(LOCALES_DIR, locale_dir, "LC_MESSAGES")
        if not os.path.isdir(lc_path):
            continue

        for po_file in sorted(os.listdir(lc_path)):
            if not po_file.endswith('.po'):
                continue

            po_path = os.path.join(lc_path, po_file)
            mo_path = po_path.replace('.po', '.mo')

            try:
                po = polib.pofile(po_path)
                po.save_as_mofile(mo_path)
                total += 1
            except Exception as e:
                print(f"  ERROR: {po_path}: {e}")
                errors += 1

    print(f"Compiled {total} .mo files ({errors} errors)")


if __name__ == '__main__':
    main()
