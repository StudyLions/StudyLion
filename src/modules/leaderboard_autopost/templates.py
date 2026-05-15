# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-21
# Purpose: Template rendering and presets for leaderboard auto-post
# ============================================================
import re
from typing import Dict, List, Optional, Any

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Add Babel localization for text branding support
# LazyStr (from babel._p) is not JSON-serializable; resolve to plain str.
from . import babel
def _p(context, message):
    return str(babel._p(context, message))
# --- END AI-MODIFIED ---

DISCORD_LIMITS = {
    'content': 2000,
    'embed_title': 256,
    'embed_description': 4096,
    'embed_footer': 2048,
    'embed_field_name': 256,
    'embed_field_value': 1024,
    'embed_fields_max': 6,
    'embed_author_name': 256,
}

BLOCKED_MENTIONS = re.compile(r'@(everyone|here)', re.IGNORECASE)

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Add Babel localization for text branding support
TYPE_LABELS = {
    'study': _p('labels:type|study', "Productive Time"),
    'messages': _p('labels:type|messages', "Messages"),
    'coins': _p('labels:type|coins', "LionCoins"),
}
# --- END AI-MODIFIED ---

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Add Babel localization for text branding support
TYPE_UNITS = {
    'study': _p('labels:unit|study', "hours"),
    'messages': _p('labels:unit|messages', "messages"),
    'coins': _p('labels:unit|coins', "coins"),
}
# --- END AI-MODIFIED ---

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Add Babel localization for text branding support
FREQUENCY_LABELS = {
    'daily': _p('labels:frequency|daily', "Daily"),
    'weekly': _p('labels:frequency|weekly', "Weekly"),
    'monthly': _p('labels:frequency|monthly', "Monthly"),
    'seasonal': _p('labels:frequency|seasonal', "Seasonal"),
}
# --- END AI-MODIFIED ---


def render_template(template: Optional[str], variables: Dict[str, str]) -> Optional[str]:
    """Render a template string by substituting {variable} placeholders."""
    if not template:
        return None
    result = template
    for key, value in variables.items():
        result = result.replace('{' + key + '}', str(value))
    return result


def truncate(text: Optional[str], max_len: int) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + '...'


def validate_template(text: Optional[str], field_name: str) -> Optional[str]:
    """Return error message if template is invalid, else None."""
    if text is None:
        return None
    limit = DISCORD_LIMITS.get(field_name)
    if limit and len(text) > limit:
        return f"{field_name} exceeds {limit} character limit ({len(text)} chars)"
    if BLOCKED_MENTIONS.search(text):
        return f"{field_name} contains @everyone or @here which is not allowed"
    return None


def build_reward_summary(reward_tiers: List[Dict[str, Any]]) -> str:
    """Build a human-readable reward summary from tier config."""
    if not reward_tiers:
        return ''
    lines = []
    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Add Babel localization for text branding support
    for tier in sorted(reward_tiers, key=lambda t: t.get('from', 0)):
        fr = tier.get('from', 1)
        to = tier.get('to', fr)
        coins = tier.get('coins', 0)
        if fr == to:
            lines.append(
                _p('ui:rewards|tier_single', "Top {rank} \u2013 {coins} LionCoins")
                .format(rank=fr, coins=f"{coins:,}")
            )
        else:
            lines.append(
                _p('ui:rewards|tier_range', "Top {rank_from}-{rank_to} \u2013 {coins} LionCoins")
                .format(rank_from=fr, rank_to=to, coins=f"{coins:,}")
            )
    # --- END AI-MODIFIED ---
    return '\n'.join(lines)


def build_winner_list(
    winners: List[Dict[str, Any]],
    unit: str = 'hours',
) -> str:
    """Build a numbered list of winners."""
    lines = []
    for w in winners:
        rank = w.get('rank', '?')
        name = w.get('name', 'Unknown')
        value = w.get('value', 0)
        if isinstance(value, float):
            value = f"{value:.1f}"
        lines.append(f"{rank}. {name} – {value} {unit}")
    return '\n'.join(lines)


def build_variables(
    server_name: str,
    frequency: str,
    lb_type: str,
    top_count: int,
    period_str: str,
    winners: List[Dict[str, Any]],
    reward_tiers: List[Dict[str, Any]],
    top1_role_ids: Optional[List[int]] = None,
    topn_role_ids: Optional[List[int]] = None,
) -> Dict[str, str]:
    """Build the full variable dictionary for template rendering."""
    unit = TYPE_UNITS.get(lb_type, 'hours')
    top1 = winners[0] if winners else {}

    topn_mentions = ' '.join(f"<@&{rid}>" for rid in (topn_role_ids or []))
    top1_mentions = ' '.join(f"<@&{rid}>" for rid in (top1_role_ids or []))

    return {
        'server_name': server_name,
        'frequency': FREQUENCY_LABELS.get(frequency, frequency.title()),
        'type': TYPE_LABELS.get(lb_type, lb_type.title()),
        'type_unit': unit,
        'top_count': str(top_count),
        'period': period_str,
        'top1_name': top1.get('name', 'N/A'),
        'top1_mention': f"<@{top1['userid']}>" if top1.get('userid') else 'N/A',
        'top1_value': str(top1.get('value', 0)),
        'topn_role': topn_mentions,
        'top1_role': top1_mentions,
        'reward_summary': build_reward_summary(reward_tiers),
        'winner_list': build_winner_list(winners, unit),
    }


def build_dm_variables(
    base_vars: Dict[str, str],
    userid: int,
    rank: int,
    value: Any,
    coins_awarded: int,
) -> Dict[str, str]:
    """Extend base variables with per-user DM variables."""
    dm_vars = dict(base_vars)
    dm_vars['mention'] = f"<@{userid}>"
    dm_vars['rank'] = str(rank)
    dm_vars['value'] = str(value)
    dm_vars['coins'] = str(coins_awarded)
    return dm_vars


# Default presets used by the dashboard to pre-fill config forms
PRESETS = {
    'weekly_study_buddies': {
        'config_name': 'Weekly Study Buddies',
        'lb_type': 'study',
        'frequency': 'weekly',
        'top_count': 10,
        'post_day': 6,
        'post_hour': 20,
        'post_minute': 0,
        'week_starts_on': 'monday',
        'embed_color': 16766720,
        'include_image': True,
        'announce_content': (
            '{topn_role} The following LionCoins are awarded to you!\n'
            '{reward_summary}'
        ),
        'embed_title': 'TOP {top_count} MOST PRODUCTIVE THIS WEEK',
        'embed_description': 'Here are our {topn_role} for the week of **{period}**:',
        'embed_footer': '{server_name}',
        'embed_fields': [
            {
                'name': 'Note:',
                'value': (
                    'The users below will hold the role for one (1) week. '
                    'If you wish to have the role removed, please contact a Server Moderator.'
                ),
                'inline': False,
            }
        ],
        'reward_tiers': [
            {'from': 1, 'to': 1, 'coins': 3000},
            {'from': 2, 'to': 2, 'coins': 2000},
            {'from': 3, 'to': 3, 'coins': 1500},
            {'from': 4, 'to': 10, 'coins': 1000},
        ],
    },
    'daily_grind': {
        'config_name': 'Daily Grind',
        'lb_type': 'study',
        'frequency': 'daily',
        'top_count': 5,
        'post_hour': 22,
        'post_minute': 0,
        'embed_color': 3447003,
        'include_image': True,
        'embed_title': 'DAILY TOP {top_count} STUDY LEADERBOARD',
        'embed_description': 'Top studiers for **{period}**:',
        'embed_footer': '{server_name}',
        'reward_tiers': [
            {'from': 1, 'to': 1, 'coins': 500},
            {'from': 2, 'to': 5, 'coins': 200},
        ],
    },
    'monthly_champions': {
        'config_name': 'Monthly Champions',
        'lb_type': 'study',
        'frequency': 'monthly',
        'top_count': 10,
        'post_day': 1,
        'post_hour': 12,
        'post_minute': 0,
        'embed_color': 10181046,
        'include_image': True,
        'embed_title': 'MONTHLY CHAMPIONS',
        'embed_description': 'Our top {top_count} studiers for **{period}**:',
        'embed_footer': '{server_name}',
        'reward_tiers': [
            {'from': 1, 'to': 1, 'coins': 10000},
            {'from': 2, 'to': 3, 'coins': 5000},
            {'from': 4, 'to': 10, 'coins': 2000},
        ],
    },
}
