import discord

from wards import guild_admin
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
@guild_admin()
async def cmd_config(ctx, flags):
    # Cache and map some info for faster access
    setting_displaynames = {setting.display_name.lower(): setting for setting in GuildSettings.settings.values()}

    if not ctx.args or ctx.args.lower() == 'help':
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
                        "View brief setting descriptions with `{prefix}config help`.\n"
                        "See `{prefix}help config` for more general usage.".format(prefix=ctx.best_prefix)
                    )
                )
                for name, value in page.items():
                    embed.add_field(name=name, value=value, inline=False)

                pages.append(embed)

        if len(pages) > 1:
            [
                embed.set_footer(text="Page {}/{}".format(i+1, len(pages)))
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
            return await ctx.error_reply(
                "Server setting `{}` doesn't exist! Use `{}config` to see all server settings".format(
                    name, ctx.best_prefix
                )
            )

        if len(parts) == 1 and not ctx.msg.attachments:
            # config <setting>
            # View config embed for provided setting
            await setting.get(ctx.guild.id).widget(ctx, flags=flags)
        else:
            # config <setting> <value>
            # Check the write ward
            if not await setting.write_ward.run(ctx):
                await ctx.error_reply(setting.write_ward.msg)

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
