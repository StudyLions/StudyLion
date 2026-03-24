# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-13
# Purpose: Process ALL remaining domains by combining salvaged
#          Transifex translations + existing .po translations
#          + AI-generated translations for gaps.
# ============================================================

import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from po_utils import (parse_pot, write_po_files, load_existing_translations,
                       TEMPLATES_DIR, TARGET_LOCALES)

ALREADY_DONE = {'base', 'topgg', 'timer-gui', 'core_config', 'profile-gui',
                'wards', 'leaderboard-gui', 'weekly-gui', 'user_config',
                'goals-gui', 'exec', 'test', 'sponsors'}

def load_all_salvaged():
    json_path = os.path.join(os.path.dirname(__file__), 'salvaged_translations.json')
    if not os.path.exists(json_path):
        return {}
    with open(json_path, 'r', encoding='utf-8') as f:
        all_s = json.load(f)
    result = {}
    for domain, entries in all_s.items():
        result[domain] = {}
        for key_str, locale_map in entries.items():
            parts = key_str.split('|||', 1)
            ctx = parts[0] if parts[0] else None
            result[domain][(ctx, parts[1])] = locale_map
    return result


def main():
    pot_files = sorted([f for f in os.listdir(TEMPLATES_DIR) if f.endswith('.pot')])
    all_salvaged = load_all_salvaged()

    total_files = 0
    total_strings = 0
    total_translated = 0

    for pot_file in pot_files:
        domain = pot_file.replace('.pot', '')
        if domain in ALREADY_DONE:
            continue

        pot_path = os.path.join(TEMPLATES_DIR, pot_file)
        entries = parse_pot(pot_path)
        if not entries:
            continue

        salvaged = all_salvaged.get(domain, {})
        existing = load_existing_translations(domain)

        count = write_po_files(domain, entries, salvaged, existing_map=existing)
        total_files += count
        total_strings += len(entries)

        translated_count = 0
        for entry in entries:
            key = (entry['msgctxt'], entry['msgid'])
            for locale in TARGET_LOCALES:
                has_salvaged = key in salvaged and locale in salvaged[key]
                has_existing = locale in existing and key in existing[locale]
                if has_salvaged or has_existing:
                    translated_count += 1
        total_translated += translated_count

        coverage_pct = (translated_count / (len(entries) * len(TARGET_LOCALES)) * 100) if entries else 0
        print(f"  {domain}: {len(entries)} strings, {count} .po files, {coverage_pct:.0f}% coverage from salvage+existing")

    print(f"\n=== SUMMARY ===")
    print(f"  Total .po files written: {total_files}")
    print(f"  Total strings across remaining domains: {total_strings}")
    total_possible = total_strings * len(TARGET_LOCALES)
    print(f"  Total translated entries: {total_translated}/{total_possible} ({total_translated/total_possible*100:.1f}%)")
    print(f"  Still need AI translation: {total_possible - total_translated}")


if __name__ == '__main__':
    main()
