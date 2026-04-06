# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-01
# Updated: 2026-04-01
# Purpose: Parse .po files and generate an enriched JSON string
#          catalog for the Text Branding dashboard. Extracts all
#          translatable strings with their keys, defaults,
#          placeholders, domain groupings, plus computed fields:
#          string_type, safety, breadcrumb, context_type/region,
#          and popular flag. Blocks internal/dangerous strings.
# ============================================================
"""
Build the string catalog JSON from .po translation files.

Usage:
    python scripts/build_string_catalog.py [--locales-dir LOCALES_DIR] [--output OUTPUT]

Scans all .po files under locales/<locale>/LC_MESSAGES/<domain>.po,
extracts msgctxt (key) + msgid (default English) + msgid_plural,
auto-detects {placeholders}, and outputs a categorized JSON file.

The output JSON is consumed by the website dashboard Text Branding page.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


PLACEHOLDER_RE = re.compile(r'\{(\w+)\}')

BLOCKED_DOMAINS = {
    'sysadmin',
    'exec',
    'sponsors',
    'test',
    'premium',
    'customskins',
    'core_config',
}

BLOCKED_KEY_PATTERNS = [
    re.compile(r'regex:'),
    re.compile(r'input_pattern:'),
    re.compile(r'parse:truthy_values'),
    re.compile(r'parse:falsey_values'),
    re.compile(r'^formatstring:'),
    re.compile(r'row_format'),
    re.compile(r'input_format:'),
    re.compile(r'output:'),
]

POPULAR_KEYS = {
    'guildset:greeting_message|default',
    'guildset:returning_message|default',
    'event:rank_update|embed:notify',
    'timer|status|stage:focus|statusline',
    'timer|status|stage:break|statusline',
    'skin:leaderboard|mode:study|header_text',
    'skin:profile|header:achievements',
    'skin:stats|mode:study|header:col2',
    'cmd:economy_balance|embed:single|desc',
    'cmd:tasks_edit|resp:success|desc',
    'timer|status|warningline',
    'ui:reminderlist|button:new|modal|title',
}

DOMAIN_DISPLAY_NAMES = {
    'ranks': 'Rank Notifications',
    'economy': 'Economy & Coins',
    'reminders': 'Reminders',
    'schedule': 'Study Sessions & Schedule',
    'statistics': 'Profile & Statistics',
    'tasklist': 'Tasks & To-Do',
    'Pomodoro': 'Pomodoro Timer',
    'moderation': 'Moderation',
    'rooms': 'Private Rooms',
    'shop': 'Shop',
    'rolemenus': 'Role Menus',
    'config': 'Server Configuration',
    'user_config': 'User Settings',
    'member_admin': 'Member Administration',
    'meta': 'Bot Meta & Help',
    'video': 'Video Channels',
    'topgg': 'Voting & Top.gg',
    'screen': 'Screen Channels',
    'liongotchi': 'LionGotchi Pet',
    'sticky_messages': 'Sticky Messages',
    'leaderboard_autopost': 'Leaderboard Autopost',
    'shared_tasklist': 'Shared Task Boards',
    'base': 'Core Bot',
    'wards': 'Permissions',
    'babel': 'Language Settings',
    'lion-core': 'Core Bot',
    'settings_base': 'Settings Framework',
    'utils': 'Utilities',
    'voice-tracker': 'Voice Tracking',
    'text-tracker': 'Text Tracking',
    'timer-gui': 'Timer Cards',
    'goals-gui': 'Goals Cards',
    'weekly-gui': 'Weekly Cards',
    'profile-gui': 'Profile Cards',
    'monthly-gui': 'Monthly Cards',
    'leaderboard-gui': 'Leaderboard Cards',
    'stats-gui': 'Stats Cards',
}

CATEGORY_FROM_KEY_PREFIX = {
    'cmd:': 'Commands',
    'ui:': 'UI Elements',
    'embed:': 'Embeds',
    'error:': 'Error Messages',
    'event:': 'Events & Notifications',
    'eventlog': 'Event Log',
    'setting:': 'Settings',
    'acmpl:': 'Autocomplete',
}

PREFIX_LABELS = {
    'cmd': '',
    'ui': '',
    'skin': '',
    'guildset': '',
    'userset': '',
    'timerset': '',
    'menuset': '',
    'roleset': '',
    'botset': '',
    'dash': '',
    'modal': '',
    'settype': '',
    'formatstring': '',
    'argtype': '',
    'acmpl': '',
    'timer': 'Timer',
    'session': 'Session',
    'room': 'Room',
    'shop': 'Shop',
    'ticket': 'Ticket',
    'achievement': 'Achievement',
    'ward': 'Permission',
    'button': 'Button',
    'embed': 'Embed',
    'event': 'Event',
    'group': 'Group',
    'template': 'Template',
    'reminder': 'Reminder',
    'eventlog': 'Event Log',
}

SEGMENT_LABELS = {
    'desc': 'Description',
    'long_desc': 'Long Description',
    'label': 'Label',
    'title': 'Title',
    'name': 'Name',
    'placeholder': 'Placeholder',
    'footer': 'Footer',
    'author': 'Author',
    'header': 'Header',
    'accepts': 'Accepted Input',
    'default': 'Default',
    'formatted': 'Formatted',
    'success': 'Success',
    'statusline': 'Status Line',
    'warningline': 'Warning Line',
}


def _humanize(s: str) -> str:
    return s.replace('_', ' ').replace('-', ' ').title()


def guess_category(key: str) -> str:
    for prefix, cat in CATEGORY_FROM_KEY_PREFIX.items():
        if key.startswith(prefix):
            return cat
    if '|button:' in key or '|select:' in key:
        return 'UI Elements'
    if '|desc' in key:
        return 'Commands'
    if '|title' in key or '|field:' in key:
        return 'Embeds'
    return 'General'


def is_bare_command_name(key: str, default: str) -> bool:
    """Bare command names are keys like 'cmd:economy' where the default
    is a single word (the slash command name). Changing these breaks
    command registration."""
    if not key.startswith('cmd:') or '|' in key:
        return False
    return ' ' not in default.strip() and len(default.strip()) < 40


def is_blocked_key(key: str, default: str) -> bool:
    for pattern in BLOCKED_KEY_PATTERNS:
        if pattern.search(key):
            return True
    if is_bare_command_name(key, default):
        return True
    return False


def compute_string_type(key: str, domain: str) -> str:
    if domain.endswith('-gui'):
        return 'gui'
    if '|modal' in key or '|input:' in key:
        return 'modal'
    if '|embed' in key or key.startswith('embed:') or key.startswith('dash:'):
        return 'embed'
    if '|button:' in key:
        return 'button'
    if '|select:' in key or '|menu:' in key:
        return 'select'
    if key.startswith('eventlog'):
        return 'notification'
    if key.startswith('guildset:') or key.startswith('userset:') or \
       key.startswith('timerset:') or key.startswith('menuset:') or \
       key.startswith('roleset:') or key.startswith('botset:'):
        return 'setting'
    if key.startswith('cmd:') and '|' in key:
        return 'command'
    return 'text'


def compute_safety(placeholders: list[dict]) -> str:
    required = sum(1 for p in placeholders if p.get('required'))
    if required == 0:
        return 'safe'
    if required <= 2:
        return 'caution'
    return 'restricted'


def compute_context(key: str, domain: str) -> tuple[str, str]:
    """Returns (context_type, context_region)."""
    if domain.endswith('-gui'):
        ct = 'card'
        if '|header' in key:
            cr = 'header'
        elif '|footer' in key:
            cr = 'footer'
        elif '|field:' in key:
            cr = 'field'
        else:
            cr = 'field'
        return ct, cr

    if '|modal' in key:
        if '|title' in key:
            return 'modal', 'title'
        if '|field' in key or '|label' in key:
            return 'modal', 'field_label'
        return 'modal', 'title'

    if '|button:' in key:
        return 'button', 'label'

    if '|select:' in key or '|menu:' in key:
        if '|placeholder' in key:
            return 'select', 'placeholder'
        return 'select', 'option'

    if '|embed' in key or key.startswith('embed:') or key.startswith('dash:'):
        if '|title' in key:
            cr = 'title'
        elif '|desc' in key:
            cr = 'desc'
        elif '|footer' in key:
            cr = 'footer'
        elif '|author' in key:
            cr = 'author'
        elif '|field:' in key:
            if '|name' in key:
                cr = 'field_name'
            else:
                cr = 'field_value'
        elif '|header' in key:
            cr = 'title'
        else:
            cr = 'desc'
        return 'embed', cr

    return 'message', 'body'


def compute_breadcrumb(key: str) -> str:
    """Parse key structure into a human-readable breadcrumb path."""
    segments = key.split('|')
    parts = []

    first = segments[0]
    if ':' in first:
        prefix, identifier = first.split(':', 1)
        prefix_label = PREFIX_LABELS.get(prefix, '')
        ident_label = _humanize(identifier)
        if prefix_label:
            parts.append(f"{prefix_label}: {ident_label}")
        else:
            parts.append(ident_label)
    else:
        parts.append(_humanize(first))

    for seg in segments[1:]:
        if seg in SEGMENT_LABELS:
            parts.append(SEGMENT_LABELS[seg])
            continue

        if ':' in seg:
            seg_type, seg_value = seg.split(':', 1)
            seg_type_h = _humanize(seg_type)
            seg_value_h = _humanize(seg_value)

            if seg_type in ('mode', 'stage', 'type'):
                parts.append(f"{seg_value_h} {seg_type_h}")
            elif seg_type in ('button', 'select', 'menu'):
                parts.append(f"{seg_value_h} {seg_type_h}")
            elif seg_type in ('embed', 'modal', 'field', 'param'):
                parts.append(seg_value_h)
            elif seg_type in ('error', 'resp', 'check_value'):
                parts.append(seg_value_h)
            elif seg_type in ('event',):
                parts.append(seg_value_h)
            else:
                parts.append(f"{seg_type_h}: {seg_value_h}")
        else:
            parts.append(_humanize(seg))

    return ' > '.join(parts)


def extract_placeholders(text: str) -> list[dict]:
    matches = PLACEHOLDER_RE.findall(text)
    seen = set()
    result = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append({
                'name': m,
                'required': True,
            })
    return result


def parse_po_file(filepath: str) -> list[dict]:
    entries = []
    current = {}
    last_field = None

    def flush():
        if current.get('msgctxt') and current.get('msgid'):
            entries.append(dict(current))

    with open(filepath, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.rstrip('\n')

            if line.startswith('#'):
                continue
            if not line.strip():
                flush()
                current = {}
                last_field = None
                continue

            if line.startswith('msgctxt '):
                val = line[len('msgctxt '):]
                current['msgctxt'] = _unquote(val)
                last_field = 'msgctxt'
            elif line.startswith('msgid_plural '):
                val = line[len('msgid_plural '):]
                current['msgid_plural'] = _unquote(val)
                last_field = 'msgid_plural'
            elif line.startswith('msgid '):
                val = line[len('msgid '):]
                current['msgid'] = _unquote(val)
                last_field = 'msgid'
            elif line.startswith('msgstr'):
                last_field = 'msgstr'
            elif line.startswith('"') and last_field:
                val = _unquote(line)
                if last_field in current:
                    current[last_field] += val
                else:
                    current[last_field] = val

    flush()
    return entries


def _unquote(s: str) -> str:
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    s = s.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
    return s


def build_catalog(locales_dir: str) -> dict:
    catalog = {}
    locales_path = Path(locales_dir)

    po_files = list(locales_path.glob('*/LC_MESSAGES/*.po'))
    if not po_files:
        print(f"No .po files found in {locales_dir}", file=sys.stderr)
        return catalog

    seen_keys = {}
    blocked_count = 0

    for po_file in sorted(po_files):
        domain = po_file.stem

        if domain in BLOCKED_DOMAINS:
            continue

        entries = parse_po_file(str(po_file))

        for entry in entries:
            key = entry.get('msgctxt', '')
            msgid = entry.get('msgid', '')

            if not key or not msgid:
                continue
            if key in seen_keys:
                continue
            seen_keys[key] = True

            if is_blocked_key(key, msgid):
                blocked_count += 1
                continue

            if domain not in catalog:
                catalog[domain] = {
                    'display_name': DOMAIN_DISPLAY_NAMES.get(
                        domain,
                        domain.replace('_', ' ').replace('-', ' ').title()
                    ),
                    'strings': [],
                }

            placeholders = extract_placeholders(msgid)
            category = guess_category(key)
            has_plural = 'msgid_plural' in entry
            string_type = compute_string_type(key, domain)
            safety = compute_safety(placeholders)
            breadcrumb = compute_breadcrumb(key)
            context_type, context_region = compute_context(key, domain)

            string_entry = {
                'key': key,
                'default': msgid,
                'category': category,
                'has_plural': has_plural,
                'string_type': string_type,
                'safety': safety,
                'breadcrumb': breadcrumb,
                'context_type': context_type,
                'context_region': context_region,
            }

            if placeholders:
                string_entry['placeholders'] = placeholders
            if has_plural:
                string_entry['default_plural'] = entry['msgid_plural']
            if key in POPULAR_KEYS:
                string_entry['popular'] = True

            catalog[domain]['strings'].append(string_entry)

    for domain_data in catalog.values():
        domain_data['count'] = len(domain_data['strings'])
        domain_data['strings'].sort(key=lambda s: s['key'])

    if blocked_count:
        print(f"Blocked {blocked_count} dangerous key patterns", file=sys.stderr)

    return catalog


def main():
    parser = argparse.ArgumentParser(description='Build string catalog from .po files')
    parser.add_argument('--locales-dir', default='locales',
                        help='Path to the locales directory')
    parser.add_argument('--output', '-o', default=None,
                        help='Output JSON file path (default: stdout)')
    args = parser.parse_args()

    catalog = build_catalog(args.locales_dir)

    total_strings = sum(d['count'] for d in catalog.values())
    total_domains = len(catalog)

    output = {
        'version': '2.0',
        'generated_at': __import__('datetime').datetime.now().isoformat(),
        'total_strings': total_strings,
        'total_domains': total_domains,
        'domains': catalog,
    }

    json_str = json.dumps(output, indent=2, ensure_ascii=False)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_str, encoding='utf-8')
        print(f"Catalog written to {args.output}: {total_strings} strings across {total_domains} domains",
              file=sys.stderr)
    else:
        print(json_str)


if __name__ == '__main__':
    main()
