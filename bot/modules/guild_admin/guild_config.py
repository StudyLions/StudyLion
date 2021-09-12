import discord

from wards import guild_admin
from settings import UserInputError, GuildSettings

from utils.lib import prop_tabulate
import utils.ctx_addons  # noqa

from .module import module


@module.cmd("config",
            desc="View and modify the server settings.",
            flags=('add', 'remove'),
            group="Guild Configuration")
@guild_admin()
async def cmd_config(ctx, flags):
    # Cache and map some info for faster access
    setting_displaynames = {setting.display_name.lower(): setting for setting in GuildSettings.settings.values()}

    if not ctx.args or ctx.args.lower() == 'help':
        cats = {}
        for setting in GuildSettings.settings.values():
            cat = cats.get(setting.category, [])
            cat.append(setting)
            cats[setting.category] = cat

        sections = {}
        for catname, cat in cats.items():
            catprops = {
                setting.display_name: setting.get(ctx.guild.id).summary if not ctx.args else setting.desc
                for setting in cat
            }
            sections[catname] = prop_tabulate(*zip(*catprops.items()))

        # Display the current configuration, with either values or descriptions
        embed = discord.Embed(
            title="Admin Settings"
        )
        for name, body in sections.items():
            embed.add_field(name=name, value=body, inline=False)

        await ctx.reply(embed=embed)
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

        if len(parts) == 1:
            # config <setting>
            # View config embed for provided setting
            await ctx.reply(embed=setting.get(ctx.guild.id).embed)
        else:
            # config <setting> <value>
            # Check the write ward
            if not await setting.write_ward.run(ctx):
                await ctx.error_reply(setting.msg)

            # Attempt to set config setting
            try:
                parsed = await setting.parse(ctx.guild.id, ctx, parts[1])
                parsed.write(add_only=flags['add'], remove_only=flags['remove'])
            except UserInputError as e:
                await ctx.reply(embed=discord.Embed(
                    description="{} {}".format('❌', e.msg),
                    Colour=discord.Colour.red()
                ))
            else:
                await ctx.reply(embed=discord.Embed(
                    description="{} {}".format('✅', setting.get(ctx.guild.id).success_response),
                    Colour=discord.Colour.green()
                ))
