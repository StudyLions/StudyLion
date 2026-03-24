# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-13
# Purpose: Utility functions for parsing .pot templates and
#          generating .po translation files for all locales.
# ============================================================

import os
import re
from datetime import datetime, timezone

LOCALES_DIR = "locales"
TEMPLATES_DIR = os.path.join(LOCALES_DIR, "templates")

TARGET_LOCALES = [
    'bg', 'cs', 'da', 'de', 'el', 'es_ES', 'fi', 'fr', 'hi', 'hr',
    'hu', 'id', 'it', 'ja', 'ko', 'lt', 'nl', 'no', 'pl', 'pt_BR',
    'ro', 'ru', 'sv_SE', 'th', 'tr', 'uk', 'vi', 'zh_CN', 'zh_TW', 'he_IL'
]

LANGUAGE_NAMES = {
    'bg': 'Bulgarian', 'cs': 'Czech', 'da': 'Danish', 'de': 'German',
    'el': 'Greek', 'es_ES': 'Spanish', 'fi': 'Finnish', 'fr': 'French',
    'hi': 'Hindi', 'hr': 'Croatian', 'hu': 'Hungarian', 'id': 'Indonesian',
    'it': 'Italian', 'ja': 'Japanese', 'ko': 'Korean', 'lt': 'Lithuanian',
    'nl': 'Dutch', 'no': 'Norwegian', 'pl': 'Polish', 'pt_BR': 'Portuguese (Brazil)',
    'ro': 'Romanian', 'ru': 'Russian', 'sv_SE': 'Swedish', 'th': 'Thai',
    'tr': 'Turkish', 'uk': 'Ukrainian', 'vi': 'Vietnamese',
    'zh_CN': 'Chinese (Simplified)', 'zh_TW': 'Chinese (Traditional)',
    'he_IL': 'Hebrew',
}

PLURAL_FORMS = {
    'bg': 'nplurals=2; plural=(n != 1);',
    'cs': 'nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;',
    'da': 'nplurals=2; plural=(n != 1);',
    'de': 'nplurals=2; plural=(n != 1);',
    'el': 'nplurals=2; plural=(n != 1);',
    'es_ES': 'nplurals=2; plural=(n != 1);',
    'fi': 'nplurals=2; plural=(n != 1);',
    'fr': 'nplurals=2; plural=(n > 1);',
    'hi': 'nplurals=2; plural=(n != 1);',
    'hr': 'nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);',
    'hu': 'nplurals=2; plural=(n != 1);',
    'id': 'nplurals=1; plural=0;',
    'it': 'nplurals=2; plural=(n != 1);',
    'ja': 'nplurals=1; plural=0;',
    'ko': 'nplurals=1; plural=0;',
    'lt': 'nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2);',
    'nl': 'nplurals=2; plural=(n != 1);',
    'no': 'nplurals=2; plural=(n != 1);',
    'pl': 'nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);',
    'pt_BR': 'nplurals=2; plural=(n > 1);',
    'ro': 'nplurals=3; plural=(n==1 ? 0 : (n==0 || (n%100>0 && n%100<20)) ? 1 : 2);',
    'ru': 'nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);',
    'sv_SE': 'nplurals=2; plural=(n != 1);',
    'th': 'nplurals=1; plural=0;',
    'tr': 'nplurals=2; plural=(n != 1);',
    'uk': 'nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);',
    'vi': 'nplurals=1; plural=0;',
    'zh_CN': 'nplurals=1; plural=0;',
    'zh_TW': 'nplurals=1; plural=0;',
    'he_IL': 'nplurals=4; plural=(n == 1 && n % 1 == 0) ? 0 : (n == 2 && n % 1 == 0) ? 1: (n % 10 == 0 && n % 1 == 0 && n > 10) ? 2 : 3;',
}


def parse_pot(pot_path):
    """Parse a .pot file and return a list of entries.
    Each entry is a dict with keys: comments, flags, msgctxt, msgid, msgid_plural.
    The header entry (empty msgid) is excluded.
    """
    with open(pot_path, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = []
    blocks = re.split(r'\n(?=#[:\.,~]|\nmsgctxt|\nmsgid)', content)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        comments = []
        flags = []
        msgctxt = None
        msgid = None
        msgid_plural = None

        lines = block.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith('#:') or line.startswith('#.'):
                comments.append(line)
            elif line.startswith('#,'):
                flags.append(line)
            elif line.startswith('msgctxt '):
                msgctxt = _extract_string(lines, i)
                i = _skip_continuation(lines, i)
            elif line.startswith('msgid_plural '):
                msgid_plural = _extract_string(lines, i)
                i = _skip_continuation(lines, i)
            elif line.startswith('msgid '):
                msgid = _extract_string(lines, i)
                i = _skip_continuation(lines, i)
            elif line.startswith('msgstr'):
                pass
            i += 1

        if msgid is not None and msgid != "":
            entries.append({
                'comments': comments,
                'flags': flags,
                'msgctxt': msgctxt,
                'msgid': msgid,
                'msgid_plural': msgid_plural,
            })

    return entries


def parse_po(po_path):
    """Parse a .po file and return a dict of (msgctxt, msgid) -> msgstr."""
    if not os.path.exists(po_path):
        return {}

    with open(po_path, 'r', encoding='utf-8') as f:
        content = f.read()

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
                msgctxt = _extract_string(lines, i)
                i = _skip_continuation(lines, i)
            elif line.startswith('msgid_plural '):
                i = _skip_continuation(lines, i)
            elif line.startswith('msgid '):
                msgid = _extract_string(lines, i)
                i = _skip_continuation(lines, i)
            elif line.startswith('msgstr ') or line.startswith('msgstr['):
                if msgstr is None:
                    msgstr = _extract_string(lines, i)
                i = _skip_continuation(lines, i)
            i += 1

        if msgid and msgstr:
            translations[(msgctxt, msgid)] = msgstr

    return translations


def _extract_string(lines, start_idx):
    """Extract a quoted string value, handling multi-line continuations."""
    line = lines[start_idx]
    match = re.search(r'"(.*)"', line)
    if not match:
        return ""
    result = match.group(1)

    i = start_idx + 1
    while i < len(lines) and lines[i].startswith('"'):
        match = re.match(r'^"(.*)"', lines[i])
        if match:
            result += match.group(1)
        i += 1

    return _unescape(result)


def _skip_continuation(lines, start_idx):
    """Return the index of the last continuation line."""
    i = start_idx + 1
    while i < len(lines) and lines[i].startswith('"'):
        i += 1
    return i - 1


def _unescape(s):
    """Unescape .po string escapes."""
    s = s.replace('\\n', '\n')
    s = s.replace('\\t', '\t')
    s = s.replace('\\"', '"')
    s = s.replace('\\\\', '\\')
    return s


def _escape(s):
    """Escape a string for .po format."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\t', '\\t')
    return s


def _format_msgstr(s):
    """Format a msgstr value, using multi-line format for strings with newlines."""
    escaped = _escape(s)
    if '\n' in s:
        parts = s.split('\n')
        lines = ['msgstr ""']
        for i, part in enumerate(parts):
            part_escaped = _escape(part)
            if i < len(parts) - 1:
                lines.append(f'"{part_escaped}\\n"')
            elif part:
                lines.append(f'"{part_escaped}"')
        return '\n'.join(lines)
    else:
        return f'msgstr "{escaped}"'


def _format_msgid(s):
    """Format a msgid value, using multi-line format for strings with newlines."""
    escaped = _escape(s)
    if '\n' in s:
        parts = s.split('\n')
        lines = ['msgid ""']
        for i, part in enumerate(parts):
            part_escaped = _escape(part)
            if i < len(parts) - 1:
                lines.append(f'"{part_escaped}\\n"')
            elif part:
                lines.append(f'"{part_escaped}"')
        return '\n'.join(lines)
    else:
        return f'msgid "{escaped}"'


# --- AI-MODIFIED (2026-03-13) ---
# Purpose: Add plural support helpers for msgid_plural / msgstr[N]
def _format_msgid_plural(s):
    """Format a msgid_plural value, using multi-line format for strings with newlines."""
    escaped = _escape(s)
    if '\n' in s:
        parts = s.split('\n')
        lines = ['msgid_plural ""']
        for i, part in enumerate(parts):
            part_escaped = _escape(part)
            if i < len(parts) - 1:
                lines.append(f'"{part_escaped}\\n"')
            elif part:
                lines.append(f'"{part_escaped}"')
        return '\n'.join(lines)
    else:
        return f'msgid_plural "{escaped}"'


def _format_indexed_msgstr(idx, s):
    """Format a msgstr[N] value, using multi-line format for strings with newlines."""
    if '\n' in s:
        parts = s.split('\n')
        lines = [f'msgstr[{idx}] ""']
        for i, part in enumerate(parts):
            part_escaped = _escape(part)
            if i < len(parts) - 1:
                lines.append(f'"{part_escaped}\\n"')
            elif part:
                lines.append(f'"{part_escaped}"')
        return '\n'.join(lines)
    else:
        return f'msgstr[{idx}] "{_escape(s)}"'


def _get_nplurals(locale):
    """Get the number of plural forms for a locale."""
    pf = PLURAL_FORMS.get(locale, 'nplurals=2; plural=(n != 1);')
    m = re.match(r'nplurals=(\d+)', pf)
    return int(m.group(1)) if m else 2
# --- END AI-MODIFIED ---


def generate_po_header(locale, domain):
    """Generate a .po file header."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M+0000')
    lang_name = LANGUAGE_NAMES.get(locale, locale)
    plural = PLURAL_FORMS.get(locale, 'nplurals=2; plural=(n != 1);')

    return f'''# {lang_name} translation for LionBot - {domain}
# AI-translated with human Transifex contributions where available.
#
msgid ""
msgstr ""
"Project-Id-Version: LionBot\\n"
"Report-Msgid-Bugs-To: \\n"
"POT-Creation-Date: 2023-10-24 14:37+0300\\n"
"PO-Revision-Date: {now}\\n"
"Last-Translator: AI (Claude)\\n"
"Language-Team: {lang_name}\\n"
"Language: {locale}\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: {plural}\\n"
'''


def generate_po_file(domain, locale, entries, translations, existing=None):
    """Generate a complete .po file content.

    Args:
        domain: The translation domain name
        locale: The target locale
        entries: List of entries from parse_pot()
        translations: Dict of (msgctxt, msgid) -> {locale: translated_string}
        existing: Optional dict of (msgctxt, msgid) -> msgstr from existing .po file
    """
    lines = [generate_po_header(locale, domain)]

    for entry in entries:
        for comment in entry['comments']:
            lines.append(comment)
        for flag in entry['flags']:
            lines.append(flag)

        if entry['msgctxt'] is not None:
            lines.append(f'msgctxt "{_escape(entry["msgctxt"])}"')

        lines.append(_format_msgid(entry['msgid']))

        key = (entry['msgctxt'], entry['msgid'])

        # --- AI-MODIFIED (2026-03-13) ---
        # Purpose: Handle plural entries (msgid_plural / msgstr[N])
        if entry['msgid_plural'] is not None:
            lines.append(_format_msgid_plural(entry['msgid_plural']))
            nplurals = _get_nplurals(locale)

            translation = None
            if existing and key in existing:
                translation = existing[key]
            elif key in translations and locale in translations[key]:
                translation = translations[key][locale]

            if isinstance(translation, (list, tuple)):
                for i in range(nplurals):
                    val = translation[i] if i < len(translation) else (translation[-1] if translation else "")
                    lines.append(_format_indexed_msgstr(i, val))
            elif isinstance(translation, str):
                lines.append(_format_indexed_msgstr(0, translation))
                for i in range(1, nplurals):
                    lines.append(f'msgstr[{i}] ""')
            else:
                for i in range(nplurals):
                    lines.append(f'msgstr[{i}] ""')
        else:
            msgstr = ""
            if existing and key in existing:
                msgstr = existing[key]
            elif key in translations and locale in translations[key]:
                msgstr = translations[key][locale]
            lines.append(_format_msgstr(msgstr))
        # --- END AI-MODIFIED ---
        lines.append("")

    return '\n'.join(lines)


def write_po_files(domain, entries, translations, locales=None, existing_map=None):
    """Write .po files for all target locales for a given domain.

    Args:
        domain: The translation domain name
        entries: List of entries from parse_pot()
        translations: Dict of (msgctxt, msgid) -> {locale: translated_string}
        locales: List of locales to generate (defaults to TARGET_LOCALES)
        existing_map: Optional dict of {locale: {(msgctxt, msgid): msgstr}}
    """
    if locales is None:
        locales = TARGET_LOCALES

    written = 0
    for locale in locales:
        locale_dir = os.path.join(LOCALES_DIR, locale, "LC_MESSAGES")
        os.makedirs(locale_dir, exist_ok=True)

        existing = None
        if existing_map and locale in existing_map:
            existing = existing_map[locale]

        content = generate_po_file(domain, locale, entries, translations, existing)

        po_path = os.path.join(locale_dir, f"{domain}.po")
        with open(po_path, 'w', encoding='utf-8') as f:
            f.write(content)
        written += 1

    return written


def load_existing_translations(domain, locales=None):
    """Load existing .po translations for a domain across all locales."""
    if locales is None:
        locales = TARGET_LOCALES

    existing_map = {}
    for locale in locales:
        po_path = os.path.join(LOCALES_DIR, locale, "LC_MESSAGES", f"{domain}.po")
        trans = parse_po(po_path)
        if trans:
            existing_map[locale] = trans

    return existing_map
