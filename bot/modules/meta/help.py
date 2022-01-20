import discord
from cmdClient.checks import is_owner

from utils.lib import prop_tabulate
from utils import interactive, ctx_addons  # noqa
from wards import is_guild_admin

from .module import module


# Set the command groups to appear in the help
group_hints = {
    '🆕 Pomodoro': "*Stay in sync with your friends using our timers!*",
    'Productivity': "*Use these to help you stay focused and productive!*",
    'Statistics': "*StudyLion leaderboards and study statistics.*",
    'Economy': "*Buy, sell, and trade with your hard-earned coins!*",
    'Personal Settings': "*Tell me about yourself!*",
    'Guild Admin': "*Dangerous administration commands!*",
    'Guild Configuration': "*Control how I behave in your server.*",
    'Meta': "*Information about me!*"
}

standard_group_order = (
    ('🆕 Pomodoro', 'Productivity', 'Statistics', 'Economy', 'Personal Settings', 'Meta'),
)

mod_group_order = (
    ('Moderation', 'Meta'),
    ('🆕 Pomodoro', 'Productivity', 'Statistics', 'Economy', 'Personal Settings')
)

admin_group_order = (
    ('Guild Admin', 'Guild Configuration', 'Moderation', 'Meta'),
    ('🆕 Pomodoro', 'Productivity', 'Statistics', 'Economy', 'Personal Settings')
)

bot_admin_group_order = (
    ('Bot Admin', 'Guild Admin', 'Guild Configuration', 'Moderation', 'Meta'),
    ('🆕 Pomodoro', 'Productivity', 'Statistics', 'Economy', 'Personal Settings')
)

# Help embed format
# TODO: Add config fields for this
title = "StudyLion Command List"
header = """
[StudyLion](https://bot.studylions.com/) is a fully featured study assistant \
    that tracks your study time and offers productivity tools \
    such as to-do lists, task reminders, private study rooms, group accountability sessions, and much much more.\n
Use `{ctx.best_prefix}help <command>` (e.g. `{ctx.best_prefix}help send`) to learn how to use each command, \
    or [click here](https://discord.studylions.com/tutorial) for a comprehensive tutorial.
"""


@module.cmd("help",
            group="Meta",
            desc="StudyLion command list.")
async def cmd_help(ctx):
    """
    Usage``:
        {prefix}help [cmdname]
    Description:
        When used with no arguments, displays a list of commands with brief descriptions.
        Otherwise, shows documentation for the provided command.
    Examples:
        {prefix}help
        {prefix}help top
        {prefix}help timezone
    """
    if ctx.arg_str:
        # Attempt to fetch the command
        command = ctx.client.cmd_names.get(ctx.arg_str.strip(), None)
        if command is None:
            return await ctx.error_reply(
                ("Command `{}` not found!\n"
                 "Write `{}help` to see a list of commands.").format(ctx.args, ctx.best_prefix)
            )

        smart_help = getattr(command, 'smart_help', None)
        if smart_help is not None:
            return await smart_help(ctx)

        help_fields = command.long_help.copy()
        help_map = {field_name: i for i, (field_name, _) in enumerate(help_fields)}

        if not help_map:
            return await ctx.reply("No documentation has been written for this command yet!")

        field_pages = [[]]
        page_fields = field_pages[0]
        for name, pos in help_map.items():
            if name.endswith("``"):
                # Handle codeline help fields
                page_fields.append((
                    name.strip("`"),
                    "`{}`".format('`\n`'.join(help_fields[pos][1].splitlines()))
                ))
            elif name.endswith(":"):
                # Handle property/value help fields
                lines = help_fields[pos][1].splitlines()

                names = []
                values = []
                for line in lines:
                    split = line.split(":", 1)
                    names.append(split[0] if len(split) > 1 else "")
                    values.append(split[-1])

                page_fields.append((
                    name.strip(':'),
                    prop_tabulate(names, values)
                ))
            elif name == "Related":
                # Handle the related field
                names = [cmd_name.strip() for cmd_name in help_fields[pos][1].split(',')]
                names.sort(key=len)
                values = [
                    (getattr(ctx.client.cmd_names.get(cmd_name, None), 'desc', '') or '').format(ctx=ctx)
                    for cmd_name in names
                ]
                page_fields.append((
                    name,
                    prop_tabulate(names, values)
                ))
            elif name == "PAGEBREAK":
                page_fields = []
                field_pages.append(page_fields)
            else:
                page_fields.append((name, help_fields[pos][1]))

        # Build the aliases
        aliases = getattr(command, 'aliases', [])
        alias_str = "(Aliases `{}`.)".format("`, `".join(aliases)) if aliases else ""

        # Build the embeds
        pages = []
        for i, page_fields in enumerate(field_pages):
            embed = discord.Embed(
                title="`{}` command documentation. {}".format(
                    command.name,
                    alias_str
                ),
                colour=discord.Colour(0x9b59b6)
            )
            for fieldname, fieldvalue in page_fields:
                embed.add_field(
                    name=fieldname,
                    value=fieldvalue.format(ctx=ctx, prefix=ctx.best_prefix),
                    inline=False
                )

            embed.set_footer(
                text="{}\n[optional] and <required> denote optional and required arguments, respectively.".format(
                    "Page {} of {}".format(i + 1, len(field_pages)) if len(field_pages) > 1 else '',
                )
            )
            pages.append(embed)

        # Post the embed
        await ctx.pager(pages)
    else:
        # Build the command groups
        cmd_groups = {}
        for command in ctx.client.cmds:
            # Get the command group
            group = getattr(command, 'group', "Misc")
            cmd_group = cmd_groups.get(group, [])
            if not cmd_group:
                cmd_groups[group] = cmd_group

            # Add the command name and description to the group
            cmd_group.append((command.name, getattr(command, 'desc', '')))

            # Add any required aliases
            for alias, desc in getattr(command, 'help_aliases', {}).items():
                cmd_group.append((alias, desc))

        # Turn the command groups into strings
        stringy_cmd_groups = {}
        for group_name, cmd_group in cmd_groups.items():
            cmd_group.sort(key=lambda tup: len(tup[0]))
            stringy_cmd_groups[group_name] = prop_tabulate(*zip(*cmd_group))

        # Now put everything into a bunch of embeds
        if await is_owner.run(ctx):
            group_order = bot_admin_group_order
        elif ctx.guild:
            if is_guild_admin(ctx.author):
                group_order = admin_group_order
            elif ctx.guild_settings.mod_role.value in ctx.author.roles:
                group_order = mod_group_order
            else:
                group_order = standard_group_order
        else:
            group_order = admin_group_order

        help_embeds = []
        for page_groups in group_order:
            embed = discord.Embed(
                description=header.format(ctx=ctx),
                colour=discord.Colour(0x9b59b6),
                title=title
            )
            for group in page_groups:
                group_hint = group_hints.get(group, '').format(ctx=ctx)
                group_str = stringy_cmd_groups.get(group, None)
                if group_str:
                    embed.add_field(
                        name=group,
                        value="{}\n{}".format(group_hint, group_str).format(ctx=ctx),
                        inline=False
                    )
            help_embeds.append(embed)

        # Add the page numbers
        for i, embed in enumerate(help_embeds):
            embed.set_footer(text="Page {}/{}".format(i+1, len(help_embeds)))

        # Send the embeds
        if help_embeds:
            await ctx.pager(help_embeds)
        else:
            await ctx.reply(
                embed=discord.Embed(description=header, colour=discord.Colour(0x9b59b6))
            )
