from typing import Optional

import discord

from meta import LionBot, conf

from . import babel

_p = babel._p


cmd_map = {
    "cmd_my": "my",
    "cmd_my_timezone": "my timezone",
    "cmd_my_language": "my language",
    "cmd_ranks": "ranks",
    "cmd_leaderboard": "leaderboard",
    "cmd_me": "me",
    "cmd_stats": "stats",
    "cmd_send": "send",
    "cmd_shop": "shop open",
    "cmd_room": "room rent",
    "cmd_reminders": "remindme in",
    "cmd_tasklist": "tasklist open",
    "cmd_timers": "timers list",
    "cmd_schedule": "schedule book",
    "cmd_dashboard": "dashboard"
}

emojis = {
    'config_emoji': conf.emojis.config,
    'stats_emoji': conf.emojis.stats,
    'coin': conf.emojis.coin,
    'utility_emoji': conf.emojis.utility
}


member_study = _p(
    'helptext|level:member|mode:study',
    """
    {config_emoji} Personal Configuration
    *View or adjust personal settings with the {cmd_my} command.*
    {cmd_my_timezone}: Timezone used to display your stats and set reminders.
    {cmd_my_language}: Your preferred language for commands and interactions.


    {stats_emoji} Statistics
    *Study in voice channels to earn activity ranks and compete on the leaderboard!*
    {cmd_me}: View your personal study profile and set your profile tags.
    {cmd_stats}: View study statistics for the current and past weeks or months.
    {cmd_ranks}: See the list of activity ranks.
    {cmd_leaderboard}: Compete with other members on the server leaderboards.


    {coin} Economy
    *Earn coins through studying, then spend them on some well deserved rewards!*
    {cmd_send}: Send your {coin} to another member.
    {cmd_shop}: Purchase server roles with your {coin}.
    {cmd_room}: Rent a private voice channel for you and your friends.


    {utility_emoji} Utilities
    *Some other utilities to help you stay productive while studying!*
    {cmd_reminders}: Ask me to remind you about that important task!
    {cmd_tasklist}: Create tasks and feel the satisfaction of checking them off.
    {cmd_timers}: Stay productive using the classic *pomodoro technique*!
    {cmd_schedule}: Schedule a shared study session and keep yourself accountable!
    """
)

admin_extra = _p(
    'helptext|page:admin',
    """
    Use {cmd_dashboard} to see an overview of the server configuration, \
    and quickly jump to the feature configuration panels to modify settings.

    Configuration panels are also accessible directly through the `/configure` commands \
    and most settings can be set with these commands.

    Other relevant commands for guild configuration below:
    `/editshop`: Add/Edit/Remove colour roles from the {coin} shop.
    `/ranks`: Add/Edit/Remove activity ranks.
    `/timer admin`: Add/Edit/Remove Pomodoro timers in voice channels.
    """
)


async def make_member_page(bot: LionBot, user: discord.User, guild: Optional[discord.Guild]) -> discord.Embed:
    """
    Create the member-oriented help section, with user and optional guild context.

    Takes into account the guild mode, if provided.
    """
    t = bot.translator.t

    mention_cmd = bot.core.mention_cmd
    cmd_mentions = {
        key: mention_cmd(name) for key, name in cmd_map.items()
    }
    format_args = {**emojis, **cmd_mentions}

    # TODO: Take into account lguild mode
    text = t(member_study).format(**format_args)
    sections = text.split('\n\n\n')

    embed = discord.Embed(
        colour=discord.Colour.orange(),
        title=t(_p(
            'helptext|level:member|title',
            "Command Summary (for members)"
        ))
    )
    for section in sections:
        title, _, body = section.strip().partition('\n')
        embed.add_field(name=title, value=body, inline=False)

    return embed


async def make_admin_page(bot: LionBot, user: discord.User, guild: Optional[discord.Guild]) -> discord.Embed:
    """
    Create the admin-oriented help section, with user or member context.
    """
    t = bot.translator.t

    mention_cmd = bot.core.mention_cmd
    cmd_mentions = {
        key: mention_cmd(name) for key, name in cmd_map.items()
    }
    format_args = {**emojis, **cmd_mentions}

    text = t(admin_extra).format(**format_args)

    embed = discord.Embed(
        colour=discord.Colour.orange(),
        title=t(_p(
            'helptext|level:admin|title',
            "Command Summary (for server admins)"
        ))
    )
    embed.description = text

    return embed
