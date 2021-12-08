import difflib
import discord
from cmdClient.lib import SafeCancellation

from wards import guild_admin, guild_moderator
from settings import UserInputError, GuildSettings

from utils.lib import prop_tabulate
import utils.ctx_addons  # noqa

from .module import module


# Pages of configuration categories to display
cat_pages = {
    'Administration': ('Meta', 'Guild Roles', 'New Members'),
    'Moderation': ('Moderation', 'Video Channels'),
    'Productivity': ('Study Tracking', 'TODO List', 'Workout'),
    'Study Rooms': ('Rented Rooms', 'Accountability Rooms'),
}

# Descriptions of each configuration category
descriptions = {
}


@module.cmd("config",
            desc="View and modify the server settings.",
            flags=('add', 'remove'),
            group="Guild Configuration")
@guild_moderator()
async def cmd_config(ctx, flags):
    """
    Usage``:
        {prefix}config
        {prefix}config info
        {prefix}config <setting>
        {prefix}config <setting> <value>
    Description:
        Display the server configuration panel, and view/modify the server settings.

        Use `{prefix}config` to see the settings with their current values, or `{prefix}config info` to \
            show brief descriptions instead.
        Use `{prefix}config <setting>` (e.g. `{prefix}config event_log`) to view a more detailed description for each setting, \
            including the possible values.
        Finally, use `{prefix}config <setting> <value>` to set the setting to the given value.
        To unset a setting, or set it to the default, use `{prefix}config <setting> None`.

    Additional usage for settings which accept a list of values:
        `{prefix}config <setting> <value1>, <value2>, ...`
        `{prefix}config <setting> --add <value1>, <value2>, ...`
        `{prefix}config <setting> --remove <value1>, <value2>, ...`
        Note that the first form *overwrites* the setting completely,\
            while the second two will only *add* and *remove* values, respectively.
    Examples``:
        {prefix}config event_log
        {prefix}config event_log {ctx.ch.name}
        {prefix}config autoroles Member, Level 0, Level 10
        {prefix}config autoroles --remove Level 10
    """
    # Cache and map some info for faster access
    setting_displaynames = {setting.display_name.lower(): setting for setting in GuildSettings.settings.values()}

    if not ctx.args or ctx.args.lower() in ('info', 'help'):
        # Fill the setting cats
        cats = {}
        for setting in GuildSettings.settings.values():
            cat = cats.get(setting.category, [])
            cat.append(setting)
            cats[setting.category] = cat

        # Format the cats
        sections = {}
        for catname, cat in cats.items():
            catprops = {
                setting.display_name: setting.get(ctx.guild.id).summary if not ctx.args else setting.desc
                for setting in cat
            }
            # TODO: Add cat description here
            sections[catname] = prop_tabulate(*zip(*catprops.items()))

        # Put the cats on the correct pages
        pages = []
        for page_name, cat_names in cat_pages.items():
            page = {
                cat_name: sections[cat_name] for cat_name in cat_names if cat_name in sections
            }
            if page:
                embed = discord.Embed(
                    colour=discord.Colour.orange(),
                    title=page_name,
                    description=(
                        "View brief setting descriptions with `{prefix}config info`.\n"
                        "Use e.g. `{prefix}config event_log` to see more details.\n"
                        "Modify a setting with e.g. `{prefix}config event_log {ctx.ch.name}`.\n"
                        "See the [Online Tutorial]({tutorial}) for a complete setup guide.".format(
                            prefix=ctx.best_prefix,
                            ctx=ctx,
                            tutorial="https://discord.studylions.com/tutorial"
                        )
                    )
                )
                for name, value in page.items():
                    embed.add_field(name=name, value=value, inline=False)

                pages.append(embed)

        if len(pages) > 1:
            [
                embed.set_footer(text="Page {} of {}".format(i+1, len(pages)))
                for i, embed in enumerate(pages)
            ]
            await ctx.pager(pages)
        elif pages:
            await ctx.reply(embed=pages[0])
        else:
            await ctx.reply("No configuration options set up yet!")
    else:
        # Some args were given
        parts = ctx.args.split(maxsplit=1)

        name = parts[0]
        setting = setting_displaynames.get(name.lower(), None)
        if setting is None:
            matches = difflib.get_close_matches(name, setting_displaynames.keys(), n=2)
            match = "`{}`".format('` or `'.join(matches)) if matches else None
            return await ctx.error_reply(
                "Couldn't find a setting called `{}`!\n"
                "{}"
                "Use `{}config info` to see all the server settings.".format(
                    name,
                    "Maybe you meant {}?\n".format(match) if match else "",
                    ctx.best_prefix
                )
            )

        if len(parts) == 1 and not ctx.msg.attachments:
            # config <setting>
            # View config embed for provided setting
            await setting.get(ctx.guild.id).widget(ctx, flags=flags)
        else:
            # config <setting> <value>
            # Ignoring the write ward currently and just enforcing admin
            # Check the write ward
            # if not await setting.write_ward.run(ctx):
            #     raise SafeCancellation(setting.write_ward.msg)
            if not await guild_admin.run(ctx):
                raise SafeCancellation("You need to be a server admin to modify settings!")

            # Attempt to set config setting
            try:
                parsed = await setting.parse(ctx.guild.id, ctx, parts[1] if len(parts) > 1 else '')
                parsed.write(add_only=flags['add'], remove_only=flags['remove'])
            except UserInputError as e:
                await ctx.reply(embed=discord.Embed(
                    description="{} {}".format('❌', e.msg),
                    colour=discord.Colour.red()
                ))
            else:
                await ctx.reply(embed=discord.Embed(
                    description="{} {}".format('✅', setting.get(ctx.guild.id).success_response),
                    colour=discord.Colour.green()
                ))
