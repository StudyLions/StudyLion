import difflib
import discord
from cmdClient.checks import is_owner

from settings import UserInputError

from utils.lib import prop_tabulate

from .module import module


@module.cmd("botconfig",
            desc="Update global bot configuration.",
            flags=('add', 'remove'),
            group="Bot Admin")
@is_owner()
async def cmd_botconfig(ctx, flags):
    """
    Usage``
        {prefix}botconfig
        {prefix}botconfig info
        {prefix}botconfig <setting>
        {prefix}botconfig <setting> <value>
    Description:
        Usage directly follows the `config` command for guild configuration.
    """
    # Cache and map some info for faster access
    setting_displaynames = {setting.display_name.lower(): setting for setting in ctx.client.settings.settings.values()}
    appid = ctx.client.conf['data_appid']

    if not ctx.args or ctx.args.lower() in ('info', 'help'):
        # Fill the setting cats
        cats = {}
        for setting in ctx.client.settings.settings.values():
            cat = cats.get(setting.category, [])
            cat.append(setting)
            cats[setting.category] = cat

        # Format the cats
        sections = {}
        for catname, cat in cats.items():
            catprops = {
                setting.display_name: setting.get(appid).summary if not ctx.args else setting.desc
                for setting in cat
            }
            # TODO: Add cat description here
            sections[catname] = prop_tabulate(*zip(*catprops.items()))

        # Build the cat page
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title="App Configuration"
        )
        for name, section in sections.items():
            embed.add_field(name=name, value=section, inline=False)

        await ctx.reply(embed=embed)
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
                "Use `{}botconfig info` to see all the available settings.".format(
                    name,
                    "Maybe you meant {}?\n".format(match) if match else "",
                    ctx.best_prefix
                )
            )

        if len(parts) == 1 and not ctx.msg.attachments:
            # config <setting>
            # View config embed for provided setting
            await setting.get(appid).widget(ctx, flags=flags)
        else:
            # config <setting> <value>
            # Attempt to set config setting
            try:
                parsed = await setting.parse(appid, ctx, parts[1] if len(parts) > 1 else '')
                parsed.write(add_only=flags['add'], remove_only=flags['remove'])
            except UserInputError as e:
                await ctx.reply(embed=discord.Embed(
                    description="{} {}".format('❌', e.msg),
                    colour=discord.Colour.red()
                ))
            else:
                await ctx.reply(embed=discord.Embed(
                    description="{} {}".format('✅', setting.get(appid).success_response),
                    colour=discord.Colour.green()
                ))
