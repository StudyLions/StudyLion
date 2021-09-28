from cmdClient.checks import in_guild

import data
from data import tables
from core import Lion
from utils import interactive  # noqa

from .module import module


first_emoji = "🥇"
second_emoji = "🥈"
third_emoji = "🥉"


@module.cmd(
    "cointop",
    group="Economy",
    desc="View the LionCoin leaderboard.",
    aliases=('topc', 'ctop', 'topcoins', 'topcoin', 'cointop100'),
    help_aliases={'cointop100': "View the LionCoin top 100."}
)
@in_guild()
async def cmd_topcoin(ctx):
    """
    Usage``:
        {prefix}cointop
        {prefix}cointop 100
    Description:
        Display the LionCoin leaderboard, or top 100.

        Use the paging reactions or send `p<n>` to switch pages (e.g. `p11` to switch to page 11).
    """
    # Handle args
    if ctx.args and not ctx.args == "100":
        return await ctx.error_reply(
            "**Usage:**`{prefix}topcoin` or `{prefix}topcoin100`.".format(prefix=ctx.best_prefix)
        )
    top100 = (ctx.args == "100" or ctx.alias == "cointop100")

    # Flush any pending coin transactions
    Lion.sync()

    # Fetch the leaderboard
    exclude = set(m.id for m in ctx.guild_settings.unranked_roles.members)
    exclude.update(ctx.client.objects['blacklisted_users'])
    exclude.update(ctx.client.objects['ignored_members'][ctx.guild.id])

    if exclude:
        user_data = tables.lions.select_where(
            guildid=ctx.guild.id,
            userid=data.NOT(list(exclude)),
            select_columns=('userid', 'coins'),
            _extra="AND coins > 0 ORDER BY coins DESC " + ("LIMIT 100" if top100 else "")
        )
    else:
        user_data = tables.lions.select_where(
            guildid=ctx.guild.id,
            select_columns=('userid', 'coins'),
            _extra="AND coins > 0 ORDER BY coins DESC " + ("LIMIT 100" if top100 else "")
        )

    # Quit early if the leaderboard is empty
    if not user_data:
        return await ctx.reply("No leaderboard entries yet!")

    # Extract entries
    author_index = None
    entries = []
    for i, (userid, coins) in enumerate(user_data):
        member = ctx.guild.get_member(userid)
        name = member.display_name if member else str(userid)
        name = name.replace('*', ' ').replace('_', ' ')

        num_str = "{}.".format(i+1)

        coin_str = "{} LC".format(coins)

        if ctx.author.id == userid:
            author_index = i

        entries.append((num_str, name, coin_str))

    # Extract blocks
    blocks = [entries[i:i+20] for i in range(0, len(entries), 20)]
    block_count = len(blocks)

    # Build strings
    header = "LionCoin Top 100" if top100 else "LionCoin Leaderboard"
    if block_count > 1:
        header += " (Page {{page}}/{})".format(block_count)

    # Build pages
    pages = []
    for i, block in enumerate(blocks):
        max_num_l, max_name_l, max_coin_l = [max(len(e[i]) for e in block) for i in (0, 1, 2)]
        body = '\n'.join(
            "{:>{}} {:<{}} \t {:>{}} {} {}".format(
                entry[0], max_num_l,
                entry[1], max_name_l + 2,
                entry[2], max_coin_l + 1,
                first_emoji if i == 0 and j == 0 else (
                    second_emoji if i == 0 and j == 1 else (
                        third_emoji if i == 0 and j == 2 else ''
                    )
                ),
                "⮜" if author_index is not None and author_index == i * 20 + j else ""
            )
            for j, entry in enumerate(block)
        )
        title = header.format(page=i+1)
        line = '='*len(title)
        pages.append(
            "```md\n{}\n{}\n{}```".format(title, line, body)
        )

    # Finally, page the results
    await ctx.pager(pages, start_at=(author_index or 0)//20 if not top100 else 0)
