import discord
from cmdClient.checks import is_owner

from utils.lib import prop_tabulate
from utils import interactive, ctx_addons  # noqa
from wards import is_guild_admin

from .module import module


# Set the command groups to appear in the help
group_hints = {
    'Productivity': "*Various productivity tools.*",
    'Statistics': "*StudyLion leaderboards and study statistics.*",
    'Economy': "*Buy, sell, and trade with your hard-earned coins!*",
    'Personal Settings': "*Tell me about yourself!*",
    'Guild Configuration': "*Control how I behave in your server.*",
    'Meta': "*Information about me!*"
}

standard_group_order = (
    ('Productivity', 'Statistics', 'Economy', 'Personal Settings', 'Meta'),
)

mod_group_order = (
    ('Moderation', 'Meta'),
    ('Productivity', 'Statistics', 'Economy', 'Personal Settings')
)

admin_group_order = (
    ('Guild Configuration', 'Moderation', 'Meta'),
    ('Productivity', 'Statistics', 'Economy', 'Personal Settings')
)

bot_admin_group_order = (
    ('Bot Admin', 'Guild Configuration', 'Moderation', 'Meta'),
    ('Productivity', 'Statistics', 'Economy', 'Personal Settings')
)

# Help embed format
# TODO: Add config fields for this
title = "LionBot Command List"
header = """
Use `{ctx.best_prefix}help <cmd>` (e.g. `{ctx.best_prefix}help send`) to see how to use each command.
"""


@module.cmd("help",
            group="Meta",
            desc="LionBot command list.")
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
            await ctx.reply("No documentation has been written for this command yet!")

        for name, pos in help_map.items():
            if name.endswith("``"):
                # Handle codeline help fields
                help_fields[pos] = (
                    name.strip("`"),
                    "`{}`".format('`\n`'.join(help_fields[pos][1].splitlines()))
                )
            elif name.endswith(":"):
                # Handle property/value help fields
                lines = help_fields[pos][1].splitlines()

                names = []
                values = []
                for line in lines:
                    split = line.split(":", 1)
                    names.append(split[0] if len(split) > 1 else "")
                    values.append(split[-1])

                help_fields[pos] = (
                    name.strip(':'),
                    prop_tabulate(names, values)
                )
            elif name == "Related":
                # Handle the related field
                names = [cmd_name.strip() for cmd_name in help_fields[pos][1].split(',')]
                names.sort(key=len)
                values = [
                    (getattr(ctx.client.cmd_names.get(cmd_name, None), 'desc', '') or '').format(ctx=ctx)
                    for cmd_name in names
                ]
                help_fields[pos] = (
                    name,
                    prop_tabulate(names, values)
                )

        aliases = getattr(command, 'aliases', [])
        alias_str = "(Aliases `{}`.)".format("`, `".join(aliases)) if aliases else ""

        # Build the embed
        embed = discord.Embed(
            title="`{}` command documentation. {}".format(command.name, alias_str),
            colour=discord.Colour(0x9b59b6)
        )
        for fieldname, fieldvalue in help_fields:
            embed.add_field(
                name=fieldname,
                value=fieldvalue.format(ctx=ctx, prefix=ctx.best_prefix),
                inline=False
            )

        embed.set_footer(
            text="[optional] and <required> denote optional and required arguments, respectively."
        )

        # Post the embed
        await ctx.reply(embed=embed)
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
