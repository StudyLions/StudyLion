from typing import Optional
import asyncio

import discord
from discord.ext import commands as cmds
import discord.app_commands as appcmds
from cachetools import LRUCache
from bidict import bidict
from frozendict import frozendict


from meta import LionCog, LionBot, LionContext
from meta.errors import UserInputError
from meta.logger import log_wrap
from utils.lib import MISSING, utc_now
from wards import sys_admin_ward, low_management_ward
from gui.base import AppSkin
from babel.translator import ctx_locale

from . import logger, babel
from .data import CustomSkinData
from .skinlib import appskin_as_choice, FrozenCustomSkin, CustomSkin
from .settings import GlobalSkinSettings
from .settingui import GlobalSkinSettingUI
from .userskinui import UserSkinUI
from .editor.skineditor import CustomSkinEditor

_p = babel._p


class CustomSkinCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data: CustomSkinData = bot.db.load_registry(CustomSkinData())
        self.bot_settings = GlobalSkinSettings()

        # Cache of app skin id -> app skin name
        # After initialisation, contains all the base skins available for this app
        self.appskin_names: bidict[int, str] = bidict()

        # Bijective cache of skin property ids <-> (card_id, property_name) tuples
        self.skin_properties: bidict[int, tuple[str, str]] = bidict()

        # Cache of currently active user skins
        # Invalidation handled by local event handler
        self.active_user_skinids: LRUCache[int, Optional[int]] = LRUCache(maxsize=5000)

        # Cache of custom skin id -> frozen custom skin
        self.custom_skins: LRUCache[int, FrozenCustomSkin] = LRUCache(maxsize=1000)

        self.current_default: Optional[str] = None

    async def cog_load(self):
        await self.data.init()

        if (leo_setting_cog := self.bot.get_cog('LeoSettings')) is not None:
            leo_setting_cog.bot_setting_groups.append(self.bot_settings)
            self.crossload_group(self.leo_group, leo_setting_cog.leo_group)

        if (config_cog := self.bot.get_cog('ConfigCog')) is not None:
            self.crossload_group(self.admin_group, config_cog.admin_group)

        if (user_cog := self.bot.get_cog('UserConfigCog')) is not None:
            self.crossload_group(self.my_group, user_cog.userconfig_group)

        await self._reload_appskins()
        await self._reload_property_map()
        await self.get_default_skin()

    async def _reload_property_map(self):
        """
        Reload the skin property id to (card_id, property_name) bijection.
        """
        records = await self.data.skin_property_map.select_where()
        cache = self.skin_properties

        cache.clear()
        for record in records:
            cache[record['property_id']] = (record['card_id'], record['property_name'])

        logger.info(
            f"Loaded '{len(cache)}' custom skin properties."
        )

    async def _reload_appskins(self):
        """
        Reload the global_available_skin id to the appskin name.
        Create global_available_skins that don't already exist.
        """
        cache = self.appskin_names
        available = list(AppSkin.skins_data['skin_map'].keys())
        rows = await self.data.GlobalSkin.fetch_where(skin_name=available)

        cache.clear()
        for row in rows:
            cache[row.skin_id] = row.skin_name

        # Not caring about efficiency here because this essentially needs to happen once ever
        missing = [name for name in available if name not in cache.values()]
        for name in missing:
            row = await self.data.GlobalSkin.create(skin_name=name)
            cache[row.skin_id] = row.skin_name

        logger.info(
            f"Loaded '{len(cache)}' global base skins."
        )

    # ----- Internal API -----
    def get_base(self, base_skin_id: int) -> AppSkin:
        """
        Initialise a localised AppSkin for the given base skin id.
        """
        if base_skin_id not in self.appskin_names:
            raise ValueError(f"Unknown app skin id '{base_skin_id}'")

        return AppSkin.get(
            skin_id=self.appskin_names[base_skin_id],
            locale=ctx_locale.get(),
            use_cache=True,
        )

    async def get_default_skin(self) -> Optional[str]:
        """
        Get the current app-default skin, and return it as a skin name.

        May be None if there is no app-default set.
        This should almost always hit cache.
        """
        setting = self.bot_settings.DefaultSkin
        instance = await setting.get(self.bot.appname)
        self.current_default = instance.value
        return instance.value

    async def fetch_property_ids(self, *card_properties: tuple[str, str]) -> list[int]:
        """
        Fetch the skin property ids for the given (card_id, property_name) tuples.

        Creates any missing properties.
        """
        mapper = self.skin_properties.inverse
        missing = [prop for prop in card_properties if prop not in mapper]
        if missing:
            # First insert missing properties
            await self.data.skin_property_map.insert_many(
                ('card_id', 'property_name'),
                *missing
            )
        await self._reload_property_map()
        return [mapper[prop] for prop in card_properties]

    async def get_guild_skinid(self, guildid: int) -> Optional[int]:
        """
        Fetch the custom_skin_id associated to the current guild.

        Returns None if the guild is not premium or has no custom skin set.
        Usually hits cache (Specifically the PremiumGuild cache).
        """
        cog = self.bot.get_cog('PremiumCog')
        if not cog:
            logger.error(
                "Trying to get guild skinid without loaded premium cog!"
            )
            return None
        row = await cog.data.PremiumGuild.fetch(guildid)
        return row.custom_skin_id if row else None

    async def get_user_skinid(self, userid: int) -> Optional[int]:
        """
        Fetch the custom_skin_id of the active skin in the given user's skin inventory.

        Returns None if the user does not have an active skin.
        Should usually be cached by `self.active_user_skinids`.
        """
        skinid = self.active_user_skinids.get(userid, MISSING)
        if skinid is MISSING:
            rows = await self.data.UserSkin.fetch_where(userid=userid, active=True)
            skinid = rows[0].custom_skin_id if rows else None
            self.active_user_skinids[userid] = skinid
        return skinid

    async def args_for_skin(self, skinid: int, cardid: str) -> dict[str, str]:
        """
        Fetch the skin argument dictionary for the given custom_skin_id.

        Should usually be cached by `self.custom_skin_args`.
        """
        skin = self.custom_skins.get(skinid, None)
        if skin is None:
            custom_skin = await CustomSkin.fetch(self.bot, skinid)
            skin = custom_skin.freeze()
            self.custom_skins[skinid] = skin
        return skin.args_for(cardid)

    # ----- External API -----
    async def get_skinargs_for(self,
        guildid: Optional[int], userid: Optional[int], card_id: str
    ) -> dict[str, str]:
        """
        Get skin arguments for a standard GUI render with the given guild, user, and for the given card.

        Takes into account the global defaults, guild custom skin, and user active skin.
        """
        args = {}

        if userid and (skinid := await self.get_user_skinid(userid)):
            skin_args = await self.args_for_skin(skinid, card_id)
            args.update(skin_args)
        elif guildid and (skinid := await self.get_guild_skinid(guildid)):
            skin_args = await self.args_for_skin(skinid, card_id)
            args.update(skin_args)

        default = self.current_default
        if default:
            args.setdefault("base_skin_id", default)

        return args

    # ----- Event Handlers -----
    @LionCog.listener('on_userset_skin')
    async def refresh_user_skin(self, userid: int):
        """
        Update cached user active skinid.
        """
        self.active_user_skinids.pop(userid, None)
        await self.get_user_skinid(userid)

    @LionCog.listener('on_skin_updated')
    async def refresh_custom_skin(self, skinid: int):
        """
        Update cached args for given custom skin id.
        """
        self.custom_skins.pop(skinid, None)
        custom_skin = await CustomSkin.fetch(self.bot, skinid)
        if custom_skin is not None:
            skin = custom_skin.freeze()
            self.custom_skins[skinid] = skin

    @LionCog.listener('on_botset_skin')
    async def handle_botset_skin(self, appname, instance):
        await self.bot.global_dispatch('global_botset_skin', appname)

    @LionCog.listener('on_global_botset_skin')
    async def refresh_default_skin(self, appname):
        await self.bot.core.data.BotConfig.fetch(appname, cached=False)
        await self.get_default_skin()

    # ----- Userspace commands -----
    @LionCog.placeholder_group
    @cmds.hybrid_group("my", with_app_command=False)
    async def my_group(self, ctx: LionContext):
        ...

    @my_group.command(
        name=_p('cmd:my_skin', "skin"),
        description=_p(
            'cmd:my_skin|desc',
            "Change the colours of your interface"
        )
    )
    async def cmd_my_skin(self, ctx: LionContext):
        if not ctx.interaction:
            return
        ui = UserSkinUI(self.bot, ctx.author.id, ctx.author.id)
        await ui.run(ctx.interaction, ephemeral=True)
        await ui.wait()

    # ----- Adminspace commands -----
    @LionCog.placeholder_group
    @cmds.hybrid_group("admin", with_app_command=False)
    async def admin_group(self, ctx: LionContext):
        ...

    @admin_group.command(
        name=_p('cmd:admin_brand', "brand"),
        description=_p(
            'cmd:admin_brand|desc',
            "Fully customise my default interface for your members!"
        )
    )
    @low_management_ward
    async def cmd_admin_brand(self, ctx: LionContext):
        if not ctx.interaction:
            return
        if not ctx.guild:
            return
        t = self.bot.translator.t

        # Check guild premium status
        premiumcog = self.bot.get_cog('PremiumCog')
        guild_row = await premiumcog.data.PremiumGuild.fetch(ctx.guild.id, cached=False)

        if not guild_row:
            raise UserInputError(
                t(_p(
                    'cmd:admin_brand|error:not_premium',
                    "Only premium servers can modify their interface theme! "
                    "Use the {premium} command to upgrade your server."
                )).format(premium=self.bot.core.mention_cmd('premium'))
            )

        await ctx.interaction.response.defer(thinking=True, ephemeral=False)

        if guild_row.custom_skin_id is None:
            # Create new custom skin
            skin_data = await self.data.CustomisedSkin.create(
                base_skin_id=self.appskin_names.inverse[self.current_default] if self.current_default else None
            )
            await guild_row.update(custom_skin_id=skin_data.custom_skin_id)

        skinid = guild_row.custom_skin_id
        custom_skin = await CustomSkin.fetch(self.bot, skinid)
        if custom_skin is None:
            raise ValueError("Invalid custom skin id")

        # Open the CustomSkinEditor with this skin
        ui = CustomSkinEditor(custom_skin, callerid=ctx.author.id)
        await ui.send(ctx.channel)
        await ctx.interaction.delete_original_response()
        await ui.wait()

    # ----- Owner commands -----
    @LionCog.placeholder_group
    @cmds.hybrid_group("leo", with_app_command=False)
    async def leo_group(self, ctx: LionContext):
        ...

    @leo_group.command(
        name=_p('cmd:leo_skin', "skin"),
        description=_p(
            'cmd:leo_skin|desc',
            "View and update the global skin settings"
        )
    )
    @appcmds.rename(
        default_skin=_p('cmd:leo_skin|param:default_skin', "default_skin"),
    )
    @appcmds.describe(
        default_skin=_p(
            'cmd:leo_skin|param:default_skin|desc',
            "Set the global default skin."
        )
    )
    @sys_admin_ward
    async def cmd_leo_skin(self, ctx: LionContext,
                           default_skin: Optional[str] = None):
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True)
        modified = []

        if default_skin is not None:
            setting = self.bot_settings.DefaultSkin
            instance = await setting.from_string(self.bot.appname, default_skin)
            modified.append(instance)

        for instance in modified:
            await instance.write()

        # No update_str, just show the config window
        ui = GlobalSkinSettingUI(self.bot, self.bot.appname, ctx.channel.id)
        await ui.run(ctx.interaction)
        await ui.wait()
            

    @cmd_leo_skin.autocomplete('default_skin')
    async def cmd_leo_skin_acmpl_default_skin(self, interaction: discord.Interaction, partial: str):
        babel = self.bot.get_cog('BabelCog')
        ctx_locale.set(await babel.get_user_locale(interaction.user.id))

        choices = []
        for skinid in self.appskin_names:
            appskin = self.get_base(skinid)
            match = partial.lower()
            if match in appskin.skin_id.lower() or match in appskin.display_name.lower():
                choices.append(appskin_as_choice(appskin))
        if not choices:
            t = self.bot.translator.t
            choices = [
                appcmds.Choice(
                    name=t(_p(
                        'cmd:leo_skin|acmpl:default_skin|error:no_match',
                        "No app skins matching {partial}"
                        )).format(partial=partial)[:100],
                    value=partial
                )
            ]
        return choices
