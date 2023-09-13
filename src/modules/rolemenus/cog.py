from typing import Optional
from collections import defaultdict
import asyncio
import json

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.ui.button import ButtonStyle
from discord.app_commands import Range, Transform
from discord.app_commands.transformers import AppCommandOptionType as cmdopt

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.errors import ResponseTimedOut, UserInputError, UserCancelled, SafeCancellation
from meta.sharding import THIS_SHARD
from utils.lib import utc_now, error_embed
from utils.ui import Confirm, ChoicedEnum, Transformed, AButton, AsComponents
from utils.transformers import DurationTransformer
from utils.monitor import TaskMonitor
from constants import MAX_COINS
from data import NULL

from wards import low_management_ward, equippable_role

from . import babel, logger
from .data import RoleMenuData, MenuType
from .rolemenu import RoleMenu, RoleMenuRole
from .ui.menueditor import MenuEditor
from .ui.menus import MenuList
from .templates import templates
from .menuoptions import RoleMenuOptions as RMOptions
from .roleoptions import RoleMenuRoleOptions as RMROptions


_p = babel._p


class MenuStyleParam(ChoicedEnum):
    REACTION = (
        _p('argtype:menu_style|opt:reaction', "Reaction Roles"),
        MenuType.REACTION
    )
    BUTTON = (
        _p('argtype:menu_style|opt:button', "Button Menu"),
        MenuType.BUTTON
    )
    DROPDOWN = (
        _p('argtype:menu_style|opt:dropdown', "Dropdown Menu"),
        MenuType.DROPDOWN
    )

    @property
    def choice_name(self):
        return self.value[0]

    @property
    def choice_value(self) -> str:
        return self.name

    @property
    def data(self) -> MenuType:
        return self.value[1]


# ----- Context Menu -----
@appcmds.context_menu(
    name=_p('ctxcmd:rolemenu', "Role Menu Editor")
)
@appcmds.guild_only
async def rolemenu_ctxcmd(interaction: discord.Interaction, message: discord.Message):
    bot: LionBot = interaction.client
    self: RoleMenuCog = bot.get_cog('RoleMenuCog')
    t = bot.translator.t

    # Ward for manage_roles
    if not interaction.user.guild_permissions.manage_roles:
        raise UserInputError(
            t(_p(
                'ctxcmd:rolemenu|error:author_perms',
                "You need the `MANAGE_ROLES` permission in order to manage the server role menus."
            ))
        )
    if not interaction.guild.me.guild_permissions.manage_roles:
        raise UserInputError(
            t(_p(
                'ctxcmd:rolemenus|error:my_perms',
                "I lack the `MANAGE_ROLES` permission required to offer roles from role menus."
            ))
        )

    await interaction.response.defer(thinking=True, ephemeral=True)
    # Lookup the rolemenu in the active message cache
    menuid = self.live_menus[interaction.guild.id].get(message.id, None)
    if menuid is None:
        # Create a new menu
        target_mine = (message.author == message.guild.me)

        # Default menu type is Button if we own the message, reaction otherwise
        if target_mine:
            menu_type = MenuType.BUTTON
        else:
            menu_type = MenuType.REACTION

        # TODO: Something to avoid duliplication
        # Also localise
        name = 'Untitled'

        message_data = {}
        message_data['content'] = message.content
        if message.embeds:
            message_data['embed'] = message.embeds[0].to_dict()
        rawmessage = json.dumps(message_data)

        # Create RoleMenu, set options if given
        menu = await RoleMenu.create(
            bot,
            guildid=message.guild.id,
            channelid=message.channel.id,
            messageid=message.id,
            name=name,
            enabled=True,
            menutype=menu_type,
            rawmessage=rawmessage,
        )
    else:
        menu = await RoleMenu.fetch(self.bot, menuid)
        menu._message = message

    # Open the editor
    editor = MenuEditor(self.bot, menu, callerid=interaction.user.id)
    await editor.run(interaction)
    await editor.wait()


class ExpiryMonitor(TaskMonitor):
    ...


class RoleMenuCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(RoleMenuData())

        # Menu caches
        self.live_menus = RoleMenu.attached_menus  # guildid -> messageid -> menuid

        # Expiry manage
        self.expiry_monitor = ExpiryMonitor(executor=self._expire)

    # ----- Initialisation -----
    async def cog_load(self):
        await self.data.init()

        self.bot.tree.add_command(rolemenu_ctxcmd)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        for menu in list(RoleMenu._menus.values()):
            menu.detach()
        self.live_menus.clear()
        if self.expiry_monitor._monitor_task:
            self.expiry_monitor._monitor_task.cancel()
        self.bot.tree.remove_command(rolemenu_ctxcmd)

    @LionCog.listener('on_ready')
    @log_wrap(action="Initialise Role Menus")
    async def initialise(self):
        self.expiry_monitor = ExpiryMonitor(executor=self._expire)
        self.expiry_monitor.start()

        guildids = [guild.id for guild in self.bot.guilds]
        if guildids:
            await self._initialise_guilds(*guildids)

    async def _initialise_guilds(self, *guildids):
        """
        Initialise the RoleMenus in the given guilds,
        and launch their expiry tasks if required.
        """
        # Fetch menu data from the guilds
        menu_rows = await self.data.RoleMenu.fetch_where(guildid=guildids)
        if not menu_rows:
            # Nothing to initialise
            return

        menuids = [row.menuid for row in menu_rows]
        guildids = {row.guildid for row in menu_rows}

        # Fetch menu roles from these menus
        role_rows = await self.data.RoleMenuRole.fetch_where(menuid=menuids).order_by('menuroleid')

        # Initialise MenuRoles and partition by menu
        role_menu_roles = defaultdict(dict)
        for row in role_rows:
            mrole = RoleMenuRole(self.bot, row)
            role_menu_roles[row.menuid][row.menuroleid] = mrole

        # Bulk fetch the Lion Guilds
        await self.bot.core.lions.fetch_guilds(*guildids)

        # Initialise and attach RoleMenus
        for menurow in menu_rows:
            menu = RoleMenu(self.bot, menurow, role_menu_roles[menurow.menuid])
            await menu.attach()

        # Fetch all unexpired expiring menu roles from these menus
        expiring = await self.data.RoleMenuHistory.fetch_expiring_where(menuid=menuids)
        if expiring:
            await self.schedule_expiring(*expiring)

    # ----- Cog API -----
    async def fetch_guild_menus(self, guildid):
        """
        Retrieve guild menus for the given guildid.
        Uses cache where possible.
        """
        # TODO: For efficiency, cache the guild menus as well
        # Current guild-key cache only caches the *active* guild menus, which is insufficent
        # But we actually keep all guild menus in the RoleMenu cache anyway,
        # so we just need to refine that cache a bit.
        # For now, we can live with every acmpl hitting the database.
        rows = await self.data.RoleMenu.fetch_where(guildid=guildid)
        menuids = [row.menuid for row in rows]

        menus = []
        for menuid in menuids:
            menus.append(await RoleMenu.fetch(self.bot, menuid))

        return menus

    async def schedule_expiring(self, *rows: RoleMenuData.RoleMenuHistory):
        """
        Schedule expiry of given equip rows.
        """
        tasks = [
            (row.equipid, row.expires_at.timestamp()) for row in rows if row.expires_at
        ]
        if tasks:
            self.expiry_monitor.schedule_tasks(*tasks)
            logger.debug(
                f"Scheduled rolemenu expiry tasks: {tasks}"
            )

    async def cancel_expiring_tasks(self, *equipids):
        """
        Cancel (task) expiry of given equipds, if they are scheduled.
        """
        self.expiry_monitor.cancel_tasks(*equipids)
        logger.debug(
            f"Cancelled rolemenu expiry tasks: {equipids}"
        )

    async def _expire(self, equipid: int):
        """
        Attempt to expire the given equipid.

        The equipid may no longer be valid, or may be unexpirable.
        If the bot is no longer in the server, ignores the expiry.
        If the member is no longer in the server, removes the role from persisted roles, if applicable.
        """
        logger.debug(f"Expiring RoleMenu equipped role {equipid}")
        rows = await self.data.RoleMenuHistory.fetch_expiring_where(equipid=equipid)
        if rows:
            equip_row = rows[0]
            menu = await self.data.RoleMenu.fetch(equip_row.menuid)
            guild = self.bot.get_guild(menu.guildid)
            if guild is not None:
                role = guild.get_role(equip_row.roleid)
                if role is not None:
                    lion = await self.bot.core.lions.fetch_member(guild.id, equip_row.userid)
                    await lion.remove_role(role)
                now = utc_now()
                await equip_row.update(removed_at=now)
        else:
            # equipid is no longer valid or is not expiring
            pass

    # ----- Private Utils -----
    async def _parse_msg(self, guild: discord.Guild, msgstr: str) -> discord.Message:
        """
        Parse a message reference link into a Message.
        """
        t = self.bot.translator.t

        error = None
        message = None
        splits = msgstr.strip().rsplit('/', maxsplit=2)[-2:]
        if len(splits) == 2 and splits[0].isdigit() and splits[1].isdigit():
            chid, mid = map(int, splits)
            channel = guild.get_channel(chid)
            if channel is not None:
                try:
                    message = await channel.fetch_message(mid)
                except discord.NotFound:
                    error = t(_p(
                        'parse:message_link|suberror:message_dne',
                        "Could not find the linked message, has it been deleted?"
                    ))
                except discord.Forbidden:
                    error = t(_p(
                        'parse:message_link|suberror:no_perms',
                        "Insufficient permissions! I need the `MESSAGE_HISTORY` permission in {channel}."
                    )).format(channel=channel.menion)
            else:
                error = t(_p(
                    'parse:message_link|suberror:channel_dne',
                    "The channel `{channelid}` could not be found in this server."
                )).format(channelid=chid)
        else:
            error = t(_p(
                'parse:message_link|suberror:malformed_link',
                "Malformed message link. Please copy the link by right clicking the target message."
            ))

        if message is None:
            raise UserInputError(
                t(_p(
                    'parse:message_link|error',
                    "Failed to resolve the provided message link.\n**ERROR:** {error}"
                )).format(error=error)
            )

        return message

    async def _parse_menu(self, menustr: str, create=False) -> RoleMenu:
        ...

    async def _acmpl_menu(self, interaction: discord.Interaction, partial: str, allow_new=False):
        ...

    async def _parse_role(self, menu, rolestr) -> RoleMenuRole:
        """
        Parse a provided role menu role.
        This can be given as 'rid-<id>', role mention, or role id.
        """
        ...

    async def _acmpl_role(self, interaction: discord.Interaction, partial: str):
        ...

    # ----- Event Handlers -----
    @LionCog.listener('on_raw_reaction_add')
    @LionCog.listener('on_raw_reaction_remove')
    async def on_reaction(self, payload: discord.RawReactionActionEvent):
        """
        Check the message is an active message.

        If so, fetch the associated menu and pass on the reaction event.
        """
        if payload.member and payload.member.bot:
            return

        menuid = self.live_menus[payload.guild_id].get(payload.message_id, None)
        if menuid is not None:
            menu = await RoleMenu.fetch(self.bot, menuid)
            if menu.data.menutype is MenuType.REACTION:
                await menu.handle_reaction(payload)

    # Message delete handler
    @LionCog.listener('on_message_delete')
    async def detach_menu(self, message: discord.Message):
        """
        Detach any associated menu.

        Set _message and messageid to None.
        """
        if not message.guild:
            return
        menuid = self.live_menus[message.guild.id].get(message.id, None)
        if menuid is not None:
            menu = await RoleMenu.fetch(self.bot, menuid)
            menu.detach()
            menu._message = None
            await menu.data.update(messageid=None)
            logger.info(
                f"RoleMenu <menuid:{menu.data.menuid}> attached message deleted."
            )

    # Role delete handler
    @LionCog.listener('on_role_delete')
    async def delete_menu_role(self, role: discord.Role):
        """
        Delete any rolemenuroles associated with the role.

        Set equip removed_at.
        Cancel any associated expiry tasks.
        """
        records = await self.data.RoleMenuRole.table.delete_where(roleid=role.id)
        if records:
            menuids = set(record['menuid'] for record in records)
            for menuid in menuids:
                menu = await RoleMenu.fetch(self.bot, menuid)
                await menu.reload_roles()
                await menu.update_message()
        equip_records = await self.data.RoleMenuHistory.table.update_where(
            (self.data.RoleMenuHistory.removed_at == NULL),
            roleid=role.id
        ).set(removed_at=utc_now())
        if equip_records:
            equipids = [equip_records['equipid'] for record in equip_records]
            await self.cancel_expiring_tasks(*equipids)

    # Guild leave handler (stop listening)
    @LionCog.listener('on_guild_leave')
    async def unload_guild_menus(self, guild: discord.Guild):
        """
        Detach any listening menus from this guild.
        Cancel any expiry tasks.
        """
        menu_data = await self.data.RoleMenu.fetch_where(guildid=guild.id)
        if menu_data:
            listening = list(self.live_menus[guild.id].values())
            for menu in listening:
                menu.detach()
            menuids = [row.menuid for row in menu_data]
            expiring = await self.data.RoleMenuHistory.fetch_expiring_where(menuid=menuids)
            if expiring:
                equipids = [row.equipid for row in expiring]
                await self.cancel_expiring_tasks(*equipids)

    # Guild join handler (start listening)
    @LionCog.listener('on_guild_join')
    async def load_guild_menus(self, guild: discord.Guild):
        """
        Run initialise for this guild.
        """
        await self._initialise_guilds(guild.id)

    # ----- Commands -----
    @cmds.hybrid_command(
        name=_p('cmd:rolemenus', "rolemenus"),
        description=_p(
            'cmd:rolemenus|desc',
            "View and configure the role menus in this server."
        )
    )
    @appcmds.guild_only
    @appcmds.default_permissions(manage_roles=True)
    async def rolemenus_cmd(self, ctx: LionContext):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        # Ward for manage_roles
        if not ctx.author.guild_permissions.manage_roles:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenus|error:author_perms',
                    "You need the `MANAGE_ROLES` permission in order to manage the server role menus."
                ))
            )
        if not ctx.guild.me.guild_permissions.manage_roles:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenus|error:my_perms',
                    "I lack the `MANAGE_ROLES` permission required to offer roles from role menus."
                ))
            )

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)
        menusui = MenuList(self.bot, ctx.guild, callerid=ctx.author.id)
        await menusui.run(ctx.interaction)
        await menusui.wait()

    async def _menu_acmpl(self, interaction: discord.Interaction, partial: str) -> list[appcmds.Choice]:
        """
        Generate a list of Choices matching the given menu string.

        Menus are matched by name.
        """
        # TODO: Make this more efficient so we aren't hitting data for every acmpl
        t = self.bot.translator.t
        guildid = interaction.guild.id

        guild_menus = await self.fetch_guild_menus(guildid)

        choices = []
        to_match = partial.strip().lower()
        for menu in guild_menus:
            if to_match in menu.data.name.lower():
                choice_name = menu.data.name
                choice_value = f"menuid:{menu.data.menuid}"
                choices.append(
                    appcmds.Choice(name=choice_name, value=choice_value)
                )

        if not choices:
            # Offer 'no menus matching' choice instead, with current partial
            choice_name = t(_p(
                'acmpl:menus|choice:no_choices|name',
                "No role menus matching '{partial}'"
            )).format(partial=partial)
            choice_value = partial
            choice = appcmds.Choice(
                name=choice_name, value=choice_value
            )
            choices.append(choice)

        return choices[:25]

    async def _role_acmpl(self, interaction: discord.Interaction, partial: str) -> list[appcmds.Choice]:
        """
        Generate a list of Choices representing menu roles matching the given partial.

        Roles are matched by label and role name. Role mentions are acceptable.
        Matches will only be given if the menu parameter has already been entered.
        """
        t = self.bot.translator.t
        menu_key = t(_p(
            'acmpl:menuroles|param:menu|keyname', "menu"
        ), locale=interaction.data.get('locale', 'en-US'))
        menu_name = interaction.namespace[menu_key] if menu_key in interaction.namespace else None
        if menu_name is None:
            choice_name = t(_p(
                'acmpl:menuroles|choice:no_menu|name',
                "Please select a menu first"
            ))
            choice_value = partial
            choices = [appcmds.Choice(name=choice_name, value=choice_value)]
        else:
            # Resolve the menu name
            menu: RoleMenu
            if menu_name.startswith('menuid:') and menu_name[7:].isdigit():
                # Assume autogenerated from acmpl of the form menuid:id
                menuid = int(menu_name[7:])
                menu = await RoleMenu.fetch(self.bot, menuid)
            else:
                # Assume it should match a menu name (case-insensitive)
                guild_menus = await self.fetch_guild_menus(interaction.guild.id)
                to_match = menu_name.strip().lower()
                menu = next(
                    (menu for menu in guild_menus if menu.data.name.lower() == to_match),
                    None
                )

            if menu is None:
                choice = appcmds.Choice(
                    name=t(_p(
                        'acmpl:menuroles|choice:invalid_menu|name',
                        "Menu '{name}' does not exist!"
                    )).format(name=menu_name),
                    value=partial
                )
                choices = [choice]
            else:
                # We have a menu and can match roles
                to_match = partial.strip().lower()
                choices = []
                for mrole in menu.roles:
                    matching = (to_match in mrole.config.label.value.lower())
                    role = interaction.guild.get_role(mrole.data.roleid)
                    if not matching and role:
                        matching = matching or (to_match in role.name.lower())
                        matching = matching or (to_match in role.mention)
                    if matching:
                        if role and (mrole.data.label != role.name):
                            name = f"{mrole.data.label} (@{role.name})"
                        else:
                            name = mrole.data.label
                        choice = appcmds.Choice(
                            name=name,
                            value=f"<@&{mrole.data.roleid}>"
                        )
                        choices.append(choice)
                if not choices:
                    choice = appcmds.Choice(
                        name=t(_p(
                            'acmpl:menuroles|choice:no_matching|name',
                            "No roles in this menu matching '{partial}'"
                        )).format(partial=partial),
                        value=partial
                    )
        return choices[:25]

    @cmds.hybrid_group(
        name=_p('group:rolemenu', "rolemenu"),
        description=_p(
            'group:rolemenu|desc',
            "Base command group for role menu configuration."
        )
    )
    @appcmds.guild_only()
    @appcmds.default_permissions(manage_roles=True)
    async def rolemenu_group(self, ctx: LionBot):
        ...

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_create', "newmenu"),
        description=_p(
            'cmd:rolemenu_create|desc',
            "Create a new role menu (optionally using an existing message)"
        )
    )
    @appcmds.choices(
        template=[
            template.as_choice() for template in templates.values()
        ],
    )
    @appcmds.rename(
        name=RMOptions.Name._display_name,
        sticky=RMOptions.Sticky._display_name,
        refunds=RMOptions.Refunds._display_name,
        obtainable=RMOptions.Obtainable._display_name,
        required_role=RMOptions.RequiredRole._display_name,
        message=_p('cmd:rolemenu_create|param:message', "message_link"),
        menu_style=_p('cmd:rolemenu_create|param:menu_style', "menu_style"),
        template=_p('cmd:rolemenu_create|param:remplate', "template"),
        rawmessage=_p('cmd:rolemenu_create|param:rawmessage', "custom_message"),
    )
    @appcmds.describe(
        name=RMOptions.Name._desc,
        sticky=RMOptions.Sticky._desc,
        refunds=RMOptions.Refunds._desc,
        obtainable=RMOptions.Obtainable._desc,
        required_role=RMOptions.RequiredRole._desc,
        message=_p(
            'cmd:rolemenu_create|param:message|desc',
            "Link to an existing message to turn it into a (reaction) role menu"
        ),
        menu_style=_p(
            'cmd:rolemenu_create|param:menu_style',
            "Selection style for this menu (using buttons, dropdowns, or reactions)"
        ),
        template=_p(
            'cmd:rolemenu_create|param:template',
            "Template to use for the menu message body"
        ),
        rawmessage=_p(
            'cmd:rolemenu_create|param:rawmessage',
            "Attach a custom menu message to use"
        ),
    )
    @appcmds.default_permissions(manage_roles=True)
    async def rolemenu_create_cmd(self, ctx: LionContext,
                                  name: appcmds.Range[str, 1, 64],
                                  message: Optional[str] = None,
                                  menu_style: Optional[Transformed[MenuStyleParam, cmdopt.string]] = None,
                                  sticky: Optional[bool] = None,
                                  refunds: Optional[bool] = None,
                                  obtainable: Optional[appcmds.Range[int, 1, 25]] = None,
                                  required_role: Optional[discord.Role] = None,
                                  template: Optional[appcmds.Choice[int]] = None,
                                  rawmessage: Optional[discord.Attachment] = None,
                                  ):
        # Type checking guards
        if ctx.guild is None:
            return
        if ctx.interaction is None:
            return

        t = self.bot.translator.t
        await ctx.interaction.response.defer(thinking=True)

        # Ward for manage_roles
        if not ctx.author.guild_permissions.manage_roles:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_create|error:author_perms',
                    "You need the `MANAGE_ROLES` permission in order to create new role menus."
                ))
            )
        if not ctx.guild.me.guild_permissions.manage_roles:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_create|error:my_perms',
                    "I lack the `MANAGE_ROLES` permission needed to offer roles from role menus."
                ))
            )

        # Parse provided target message if given
        if message is None:
            target_message = None
            target_mine = True
        else:
            # Parse provided message link into a Message
            target_message: discord.Message = await self._parse_msg(ctx.guild, message)
            target_mine = (target_message.author == ctx.guild.me)

            # Check that this message is not already attached to a role menu
            matching = await self.data.RoleMenu.fetch_where(messageid=target_message.id)
            if matching:
                raise UserInputError(
                    t(_p(
                        'cmd:rolemenu_create|error:message_exists',
                        "The message {link} already has a role menu! Use {edit_cmd} to edit it."
                    )).format(
                        link=target_message.jump_url,
                        edit_cmd=self.bot.core.mention_cache['rolemenu editmenu']
                    )
                )

        # Default menu type is Button if we own the message, reaction otherwise
        if menu_style is not None:
            menu_type = menu_style.data
        elif target_mine:
            menu_type = MenuType.BUTTON
        else:
            menu_type = MenuType.REACTION

        # Handle incompatible options from unowned target message
        if not target_mine:
            if menu_type is not MenuType.REACTION:
                raise UserInputError(
                    t(_p(
                        'cmd:rolemenu_create|error:style_notmine',
                        "I cannot create a `{style}` style menu on a message I didn't send! (Discord restriction)."
                    )).format(style=t(menu_style.value[0]))
                )
            if rawmessage is not None:
                raise UserInputError(
                    t(_p(
                        'cmd:rolemenu_create|error:rawmessage_notmine',
                        "Cannot apply a custom menu message to {message} because I do not own this message!"
                    )).format(
                        message=target_message.jump_url
                    )
                )
            if template is not None:
                raise UserInputError(
                    t(_p(
                        'cmd:rolemenu_create|error:template_notmine',
                        "Cannot apply a menu message template to {message} because I do not own this message!"
                    )).format(
                        message=target_message.jump_url
                    )
                )

        # Parse menu options if given
        name = name.strip()
        matching = await self.data.RoleMenu.fetch_where(name=name)
        if matching:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_create|error:name_exists',
                    "A rolemenu called `{name}` already exists! Use {edit_cmd} to edit it."
                )).format(name=name, edit_cmd=self.bot.core.mention_cache['rolemenu editmenu'])
            )

        templateid = template.value if template is not None else None
        if target_message:
            message_data = {}
            message_data['content'] = target_message.content
            if target_message.embeds:
                message_data['embed'] = target_message.embeds[0].to_dict()
            rawmessagedata = json.dumps(message_data)
        else:
            if rawmessage is not None:
                # Attempt to parse rawmessage
                rawmessagecontent = await RMOptions.Message.download_attachment(rawmessage)
                rawmessagedata = await RMOptions.Message._parse_string(0, rawmessagecontent)
            else:
                rawmessagedata = None
                if templateid is None:
                    templateid = 0

        # Create RoleMenu data, set options if given
        menu = await RoleMenu.create(
            self.bot,
            guildid=ctx.guild.id,
            channelid=target_message.channel.id if target_message else None,
            messageid=target_message.id if target_message else None,
            name=name,
            enabled=True,
            required_roleid=required_role.id if required_role else None,
            sticky=sticky,
            refunds=refunds,
            obtainable=obtainable,
            menutype=menu_type,
            templateid=templateid,
            rawmessage=rawmessagedata,
        )

        # If the message already exists and we own it, we may need to update it
        if target_message and target_mine:
            await menu.update_message()

        # Open editor, with preview if not a reaction role message
        editor = MenuEditor(self.bot, menu, callerid=ctx.author.id)
        await editor.run(ctx.interaction)
        await editor.wait()

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_edit', "editmenu"),
        description=_p(
            'cmd:rolemenu_edit|desc',
            "Edit an existing role menu."
        )
    )
    @appcmds.choices(
        template=[
            template.as_choice() for template in templates.values()
        ],
    )
    @appcmds.rename(
        name=_p('cmd:rolemenu_edit|param:name', "name"),
        new_name=_p('cmd:rolemenu_edit|param:new_name', "new_name"),
        channel=_p('cmd:rolemenu_edit|param:channel', "new_channel"),
        sticky=RMOptions.Sticky._display_name,
        refunds=RMOptions.Refunds._display_name,
        obtainable=RMOptions.Obtainable._display_name,
        required_role=RMOptions.RequiredRole._display_name,
        menu_style=_p('cmd:rolemenu_edit|param:menu_style', "menu_style"),
        template=_p('cmd:rolemenu_edit|param:remplate', "template"),
        rawmessage=_p('cmd:rolemenu_edit|param:rawmessage', "custom_message"),
    )
    @appcmds.describe(
        name=_p(
            'cmd:rolemenu_edit|param:name|desc',
            "Name of the menu to edit"
        ),
        channel=_p(
            'cmd:rolemenu_edit|param:channel|desc',
            "Server channel to move the menu to"
        ),
        new_name=RMOptions.Name._desc,
        sticky=RMOptions.Sticky._desc,
        refunds=RMOptions.Refunds._desc,
        obtainable=RMOptions.Obtainable._desc,
        required_role=RMOptions.RequiredRole._desc,
        menu_style=_p(
            'cmd:rolemenu_edit|param:menu_style',
            "Selection style for this menu (using buttons, dropdowns, or reactions)"
        ),
        template=_p(
            'cmd:rolemenu_edit|param:template',
            "Template to use for the menu message body"
        ),
        rawmessage=_p(
            'cmd:rolemenu_edit|param:rawmessage',
            "Attach a custom menu message to use"
        ),
    )
    async def rolemenu_edit_cmd(self, ctx: LionContext,
                                name: appcmds.Range[str, 1, 64],
                                new_name: Optional[appcmds.Range[str, 1, 64]] = None,
                                channel: Optional[discord.TextChannel | discord.VoiceChannel] = None,
                                menu_style: Optional[Transformed[MenuStyleParam, cmdopt.string]] = None,
                                sticky: Optional[bool] = None,
                                refunds: Optional[bool] = None,
                                obtainable: Optional[appcmds.Range[int, 1, 25]] = None,
                                required_role: Optional[discord.Role] = None,
                                template: Optional[appcmds.Choice[int]] = None,
                                rawmessage: Optional[discord.Attachment] = None,
                                ):
        # Type checking guards
        if ctx.guild is None:
            return
        if ctx.interaction is None:
            return

        t = self.bot.translator.t
        await ctx.interaction.response.defer(ephemeral=True, thinking=True)

        # Wards for manage_roles
        if not ctx.author.guild_permissions.manage_roles:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_edit|error:author_perms',
                    "You need the `MANAGE_ROLES` permission in order to edit role menus."
                ))
            )
        if not ctx.guild.me.guild_permissions.manage_roles:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_edit|error:my_perms',
                    "I lack the `MANAGE_ROLES` permission needed to offer roles from role menus."
                ))
            )

        # Parse target menu from name
        guild_menus = await self.fetch_guild_menus(ctx.guild.id)
        target: RoleMenu
        if name.startswith('menuid:') and name[7:].isdigit():
            # Assume autogenerated from acmpl of the form menuid:id
            menuid = int(name[7:])
            target = await RoleMenu.fetch(self.bot, menuid)
        else:
            # Assume it should match a menu name (case-insensitive)
            to_match = name.strip().lower()
            target = next(
                (menu for menu in guild_menus if menu.data.name.lower() == to_match),
                None
            )

        if target is None:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_edit|error:menu_not_found',
                    "This server does not have a role menu called `{name}`!"
                )).format(name=name)
            )
        await target.fetch_message()

        # Parse provided options
        reposting = channel is not None
        managed = target.managed

        update_args = {}
        ack_lines = []
        error_lines = []

        if new_name is not None:
            # Check whether the name already exists
            for menu in guild_menus:
                if menu.data.name.lower() == new_name.lower() and menu.data.menuid != target.data.menuid:
                    raise UserInputError(
                        t(_p(
                            'cmd:rolemenu_edit|parse:new_name|error:name_exists',
                            "A role menu with the name **{new_name}** already exists!"
                        )).format(new_name=new_name)
                    )
            name_config = target.config.name
            name_config.value = new_name
            update_args[name_config._column] = name_config.data
            ack_lines.append(name_config.update_message)

        if sticky is not None:
            sticky_config = target.config.sticky
            sticky_config.value = sticky
            update_args[sticky_config._column] = sticky_config.data
            ack_lines.append(sticky_config.update_message)

        if refunds is not None:
            refunds_config = target.config.refunds
            refunds_config.value = refunds
            update_args[refunds_config._column] = refunds_config.data
            ack_lines.append(refunds_config.update_message)

        if obtainable is not None:
            obtainable_config = target.config.obtainable
            obtainable_config.value = obtainable
            update_args[obtainable_config._column] = obtainable_config.data
            ack_lines.append(obtainable_config.update_message)

        if required_role is not None:
            required_role_config = target.config.required_role
            required_role_config.value = required_role
            update_args[required_role_config._column] = required_role_config.data
            ack_lines.append(required_role_config.update_message)

        if template is not None:
            if not managed and not reposting:
                raise UserInputError(
                    t(_p(
                        'cmd:rolemenu_edit|parse:template|error:not_managed',
                        "Cannot set a template message for a role menu attached to a message I did not send."
                    ))
                )
            templateid = template.value
            if templateid == -1:
                templateid = None
            update_args[self.data.RoleMenu.templateid.name] = templateid
            if templateid is not None:
                ack_lines.append(
                    t(_p(
                        'cmd:rolemenu_edit|parse:template|success:template',
                        "Now using the `{name}` menu message template."
                    )).format(name=t(templates[templateid].name))
                )
            else:
                ack_lines.append(
                    t(_p(
                        'cmd:rolemenu_edit|parse:template|success:custom',
                        "Now using a custom menu message."
                    ))
                )
                # TODO: Generate the custom message from the template if it doesn't exist

        if rawmessage is not None:
            msg_config = target.config.rawmessage
            content = await msg_config.download_attachment(rawmessage)
            data = await msg_config._parse_string(content)
            update_args[msg_config._column] = data
            if template is None:
                update_args[self.data.RoleMenu.templateid.name] = None
            ack_lines.append(msg_config.update_message)

        # Update the data, if applicable
        if update_args:
            await target.data.update(**update_args)

        # If we are reposting, do the repost
        if reposting:
            try:
                await target.repost_to(channel)
                ack_lines.append(
                    t(_p(
                        'cmd:rolemenu_edit|repost|success',
                        "The role menu is now available at {message}"
                    )).format(message=target.jump_link)
                )
                if target.data.menutype is MenuType.REACTION:
                    try:
                        await target.update_reactons()
                    except SafeCancellation as e:
                        error_lines.append(e.msg)
            except discord.Forbidden:
                error_lines.append(t(_p(
                    'cmd:rolemenu_edit|repost|error:forbidden',
                    "Cannot update channel! I lack the `EMBED_LINKS` or `SEND_MESSAGES` permission in {channel}."
                )).format(channel=channel.mention))
            except discord.HTTPException as e:
                error_lines.append(t(_p(
                    'cmd:rolemenu_edit|repost|error:unknown',
                    "An unknown error occurred trying to repost the menu to {channel}.\n"
                    "**Error:** `{exception}`"
                )).format(channel=channel.mention, exception=e.text))
        else:
            await target.update_message()

        # Ack the updates
        if ack_lines or error_lines:
            tick = self.bot.config.emojis.tick
            cross = self.bot.config.emojis.cancel
            await ctx.interaction.edit_original_response(
                embed=discord.Embed(
                    colour=discord.Colour.brand_green() if ack_lines else discord.Colour.brand_red(),
                    description='\n'.join((
                        *(f"{tick} {line}" for line in ack_lines),
                        *(f"{cross} {line}" for line in error_lines),
                    ))
                )
            )

        # Trigger listening MenuEditor update
        listen_key = (ctx.channel.id, ctx.author.id, target.data.menuid)
        if (listen_key) not in MenuEditor._listening or not (ack_lines or error_lines):
            ui = MenuEditor(self.bot, target, callerid=ctx.author.id)
            await ui.run(ctx.interaction)
            await ui.wait()
        else:
            ui = MenuEditor._listening[listen_key]
            await ui.refresh()
            await ui.update_preview()

    rolemenu_edit_cmd.autocomplete('name')(_menu_acmpl)

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_delete', "delmenu"),
        description=_p(
            'cmd:rolemenu_delete|desc',
            "Delete a role menu."
        )
    )
    @appcmds.rename(
        name=_p('cmd:rolemenu_delete|param:name', "menu")
    )
    @appcmds.describe(
        name=_p(
            'cmd:rolemenu_delete|param:name|desc',
            "Name of the rolemenu to delete."
        )
    )
    async def rolemenu_delete_cmd(self, ctx: LionContext, name: appcmds.Range[str, 1, 64]):
        if ctx.guild is None:
            return
        if ctx.interaction is None:
            return

        t = self.bot.translator.t

        if not ctx.author.guild_permissions.manage_roles:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_delete|error:author_perms',
                    "You need the `MANAGE_ROLES` permission in order to manage the server role menus."
                ))
            )

        # Parse target
        guild_menus = await self.fetch_guild_menus(ctx.guild.id)
        target: RoleMenu
        if name.startswith('menuid:') and name[7:].isdigit():
            # Assume autogenerated from acmpl of the form menuid:id
            menuid = int(name[7:])
            target = await RoleMenu.fetch(self.bot, menuid)
        else:
            # Assume it should match a menu name (case-insensitive)
            to_match = name.strip().lower()
            target = next(
                (menu for menu in guild_menus if menu.data.name.lower() == to_match),
                None
            )

        if target is None:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_delete|error:menu_not_found',
                    "This server does not have a role menu called `{name}`!"
                )).format(name=name)
            )
        await target.fetch_message()

        # Confirm
        confirm_msg = t(_p(
            'cmd:rolemenu_delete|confirm|title',
            "Are you sure you want to delete the role menu **{name}**? This is not reversible!"
        )).format(name=target.data.name)
        confirm = Confirm(confirm_msg, ctx.author.id)
        confirm.confirm_button.label = t(_p(
            'cmd:rolemenu_delete|confirm|button:yes',
            "Yes, Delete Now"
        ))
        confirm.confirm_button.style = ButtonStyle.red
        confirm.cancel_button.label = t(_p(
            'cmd:rolemenu_delete|confirm|button:no',
            "No, Cancel"
        ))
        confirm.cancel_button.style = ButtonStyle.green
        try:
            result = await confirm.ask(ctx.interaction, ephemeral=True)
        except ResponseTimedOut:
            result = False

        if result:
            old_name = target.data.name

            # Delete them menu
            await target.delete()

            # Close any menueditors that are listening
            listen_key = (ctx.channel.id, ctx.author.id, target.data.menuid)
            listening = MenuEditor._listening.get(listen_key, None)
            if listening is not None:
                await listening.quit()

            # Ack deletion
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:rolemenu_delete|success|desc',
                    "Successfully deleted the menu **{name}**"
                )).format(name=old_name)
            )
            await ctx.interaction.followup.send(embed=embed, ephemeral=False)

    rolemenu_delete_cmd.autocomplete('name')(_menu_acmpl)

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_addrole', "addrole"),
        description=_p(
            'cmd:rolemenu_addrole|desc',
            "Add a new role to an existing role menu."
        )
    )
    @appcmds.rename(
        menu=_p(
            'cmd:rolemenu_addrole|param:menu', "menu"
        ),
        role=_p(
            'cmd:rolemenu_addrole|param:role', "role"
        ),
        label=RMROptions.Label._display_name,
        emoji=RMROptions.Emoji._display_name,
        description=RMROptions.Description._display_name,
        price=RMROptions.Price._display_name,
        duration=RMROptions.Duration._display_name,
    )
    @appcmds.describe(
        menu=_p(
            'cmd:rolemenu_addrole|param:menu|desc',
            "Name of the menu to add a role to"
        ),
        role=_p(
            'cmd:rolemenu_addrole|param:role|desc',
            "Role to add to the menu"
        ),
        label=RMROptions.Label._desc,
        emoji=RMROptions.Emoji._desc,
        description=RMROptions.Description._desc,
        price=RMROptions.Price._desc,
        duration=_p(
            'cmd:rolemenu_addrole|param:duration|desc',
            "Lifetime of the role after selection in minutes."
        ),
    )
    async def rolemenu_addrole_cmd(self, ctx: LionContext,
                                   menu: appcmds.Range[str, 1, 64],
                                   role: discord.Role,
                                   label: Optional[appcmds.Range[str, 1, 100]] = None,
                                   emoji: Optional[appcmds.Range[str, 0, 100]] = None,
                                   description: Optional[appcmds.Range[str, 0, 100]] = None,
                                   price: Optional[appcmds.Range[int, 0, MAX_COINS]] = None,
                                   duration: Optional[Transform[int, DurationTransformer(60)]] = None,
                                   ):
        # Type checking guards
        if not ctx.interaction:
            return
        if not ctx.guild:
            return

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        # Permission ward
        # Will check if the author has permission to manage this role
        # Will check that the bot has permission to manage this role
        # Raises UserInputError on lack of permissions
        await equippable_role(self.bot, role, ctx.author)

        t = self.bot.translator.t

        # Parse target menu
        name = menu
        guild_menus = await self.fetch_guild_menus(ctx.guild.id)
        target: RoleMenu
        if name.startswith('menuid:') and name[7:].isdigit():
            # Assume autogenerated from acmpl of the form menuid:id
            menuid = int(name[7:])
            target = await RoleMenu.fetch(self.bot, menuid)
        else:
            # Assume it should match a menu name (case-insensitive)
            to_match = name.strip().lower()
            target = next(
                (menu for menu in guild_menus if menu.data.name.lower() == to_match),
                None
            )

        if target is None:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_addrole|error:menu_not_found',
                    "This server does not have a role menu called `{name}`!"
                )).format(name=name)
            )
        await target.fetch_message()
        target_is_reaction = (target.data.menutype is MenuType.REACTION)

        # Parse target role
        existing = next(
            (mrole for mrole in target.roles if mrole.data.roleid == role.id),
            None
        )
        parent_id = existing.data.menuroleid if existing is not None else role.id

        # Parse provided config
        data_args = {}
        ack_lines = []

        if not existing:
            # Creation args
            data_args = {
                'menuid': target.data.menuid,
                'roleid': role.id,
            }

        # label
        # Use role name if not existing and not given
        if (label is None) and (not existing):
            label = role.name[:100]
        if label is not None:
            setting_cls = RMROptions.Label
            data = setting_cls._data_from_value(parent_id, label)
            data_args[setting_cls._column] = data
            if existing:
                instance = setting_cls(existing.data.menuroleid, data)
                ack_lines.append(instance.update_message)

        # emoji
        # Autogenerate emoji if not exists and not given
        if (emoji is None) and (not existing):
            emoji = next(target.unused_emojis(include_defaults=target_is_reaction), None)
        if emoji is not None:
            setting_cls = RMROptions.Emoji
            data = await setting_cls._parse_string(parent_id, emoji, interaction=ctx.interaction)
            data_args[setting_cls._column] = data
            if existing:
                instance = setting_cls(existing.data.menuroleid, data)
                ack_lines.append(instance.update_message)

        # description
        if description is not None:
            setting_cls = RMROptions.Description
            data = setting_cls._data_from_value(parent_id, description or None)
            data_args[setting_cls._column] = data
            if existing:
                instance = setting_cls(existing.data.menuroleid, data)
                ack_lines.append(instance.update_message)

        # price
        if price is not None:
            setting_cls = RMROptions.Price
            data = setting_cls._data_from_value(parent_id, price or None)
            data_args[setting_cls._column] = data
            if existing:
                instance = setting_cls(existing.data.menuroleid, data)
                ack_lines.append(instance.update_message)

        # duration
        if duration is not None:
            setting_cls = RMROptions.Duration
            data = setting_cls._data_from_value(parent_id, duration or None)
            data_args[setting_cls._column] = data
            if existing:
                instance = setting_cls(existing.data.menuroleid, data)
                ack_lines.append(instance.update_message)

        # Create or edit RoleMenuRole
        if not existing:
            # Do create
            data = await self.data.RoleMenuRole.create(**data_args)

            # Ack creation
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'cmd:rolemenu_addrole|success:create|title',
                    "Added Menu Role"
                )),
                description=t(_p(
                    'cmd:rolemenu_addrole|success:create|desc',
                    "Add the role {role} to the menu **{menu}**."
                )).format(
                    role=role.mention,
                    menu=target.data.name
                )
            )
            # Update target roles
            await target.reload_roles()
        elif data_args:
            # Do edit
            await existing.data.update(**data_args)

            # Ack edit
            tick = self.bot.config.emojis.tick
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'cmd:rolemenu_addrole|success:edit|title',
                    "Menu Role updated"
                )),
                description='\n'.join(
                    f"{tick} {line}" for line in ack_lines
                )
            )
        else:
            # addrole was called on an existing role, but no options were modified
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                description=t(_p(
                    'cmd:rolemenu_addrole|error:role_exists',
                    "The role {role} is already selectable from the menu **{menu}**"
                )).format(
                    role=role.mention, menu=target.data.name
                )
            )

        listen_key = (ctx.channel.id, ctx.author.id, target.data.menuid)
        listening = MenuEditor._listening.get(listen_key, None)
        if data_args:
            # Update target and any listening editors
            await target.update_message()
            if target_is_reaction:
                try:
                    await self.menu.update_reactons()
                except SafeCancellation as e:
                    embed.add_field(
                        name=t(_p(
                            'cmd:rolemenu_addrole|success|error:reaction|name',
                            "Note"
                        )),
                        value=e.msg
                    )
            if listening is not None:
                await listening.refresh()
                await listening.update_preview()

        # Ack, with open editor button if there is no open editor already
        @AButton(
            label=t(_p(
                'cmd:rolemenu_addrole|success|button:editor|label',
                "Edit Menu"
            )),
            style=ButtonStyle.blurple
        )
        async def editor_button(press: discord.Interaction, pressed):
            ui = MenuEditor(self.bot, target, callerid=press.user.id)
            await ui.run(press)

        await ctx.interaction.followup.send(
            embed=embed,
            ephemeral=True,
            view=AsComponents(editor_button) if listening is None else discord.utils.MISSING
        )

    rolemenu_addrole_cmd.autocomplete('menu')(_menu_acmpl)

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_editrole', "editrole"),
        description=_p(
            'cmd:rolemenu_editrole|desc',
            "Edit role options in an existing role menu."
        )
    )
    @appcmds.rename(
        menu=_p(
            'cmd:rolemenu_editrole|param:menu', "menu"
        ),
        menu_role=_p(
            'cmd:rolemenu_editrole|param:menu_role', "menu_role"
        ),
        role=_p(
            'cmd:rolemenu_editrole|param:role', "new_role"
        ),
        label=RMROptions.Label._display_name,
        emoji=RMROptions.Emoji._display_name,
        description=RMROptions.Description._display_name,
        price=RMROptions.Price._display_name,
        duration=RMROptions.Duration._display_name,
    )
    @appcmds.describe(
        menu=_p(
            'cmd:rolemenu_editrole|param:menu|desc',
            "Name of the menu to edit the role for"
        ),
        menu_role=_p(
            'cmd:rolemenu_editrole|param:menu_role|desc',
            "Label, name, or mention of the menu role to edit."
        ),
        role=_p(
            'cmd:rolemenu_editrole|param:role|desc',
            "New server role this menu role should give."
        ),
        label=RMROptions.Label._desc,
        emoji=RMROptions.Emoji._desc,
        description=RMROptions.Description._desc,
        price=RMROptions.Price._desc,
        duration=_p(
            'cmd:rolemenu_editrole|param:duration|desc',
            "Lifetime of the role after selection in minutes."
        ),
    )
    async def rolemenu_editrole_cmd(self, ctx: LionContext,
                                    menu: appcmds.Range[str, 1, 64],
                                    menu_role: appcmds.Range[str, 1, 64],
                                    role: Optional[discord.Role] = None,
                                    label: Optional[appcmds.Range[str, 1, 100]] = None,
                                    emoji: Optional[appcmds.Range[str, 0, 100]] = None,
                                    description: Optional[appcmds.Range[str, 0, 100]] = None,
                                    price: Optional[appcmds.Range[int, 0, MAX_COINS]] = None,
                                    duration: Optional[Transform[int, DurationTransformer(60)]] = None,
                                    ):
        # Type checking wards
        if not ctx.interaction:
            return
        if not ctx.guild:
            return
        await ctx.interaction.response.defer(thinking=True, ephemeral=True)
        t = self.bot.translator.t

        # Parse target menu
        name = menu
        guild_menus = await self.fetch_guild_menus(ctx.guild.id)
        target_menu: RoleMenu
        if name.startswith('menuid:') and name[7:].isdigit():
            # Assume autogenerated from acmpl of the form menuid:id
            menuid = int(name[7:])
            target_menu = await RoleMenu.fetch(self.bot, menuid)
        else:
            # Assume it should match a menu name (case-insensitive)
            to_match = name.strip().lower()
            target_menu = next(
                (menu for menu in guild_menus if menu.data.name.lower() == to_match),
                None
            )

        if target_menu is None:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_editrole|error:menu_not_found',
                    "This server does not have a role menu called `{name}`!"
                )).format(name=name)
            )
        await target_menu.fetch_message()

        # Parse target role
        menu_roles = target_menu.roles
        target_role: RoleMenuRole
        if (maybe_id := menu_role.strip('<&@> ')).isdigit():
            # Assume given as role mention or id
            # Note that acmpl choices also provide mention
            roleid = int(maybe_id)
            target_role = next(
                (mrole for mrole in menu_roles if mrole.data.roleid == roleid),
                None
            )
        else:
            # Assume given as mrole label
            to_match = menu_role.strip().lower()
            target_role = next(
                (mrole for mrole in menu_roles if mrole.config.label.value.lower() == to_match),
                None
            )

        if target_role is None:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_editrole|error:role_not_found',
                    "The menu **{menu}** does not have the role **{name}**"
                )).format(menu=target_menu.data.name, name=menu_role)
            )

        # Check bot and author permissions
        if current_role := ctx.guild.get_role(target_role.data.roleid):
            await equippable_role(self.bot, current_role, ctx.author)
        if role is not None:
            await equippable_role(self.bot, role, ctx.author)

        # Parse role options
        data_args = {}
        ack_lines = []

        # new role
        if role is not None:
            config = target_role.config.role
            config.value = role
            data_args[config._column] = config.data
            ack_lines.append(config.update_message)

        # label
        if label is not None:
            config = target_role.config.label
            config.value = label
            data_args[config._column] = config.data
            ack_lines.append(config.update_message)

        # emoji
        if emoji is not None:
            config = target_role.config.emoji
            config.data = await config._parse_string(config.parent_id, emoji, interaction=ctx.interaction)
            data_args[config._column] = config.data
            ack_lines.append(config.update_message)

        # description
        if description is not None:
            config = target_role.config.description
            config.data = await config._parse_string(config.parent_id, description)
            data_args[config._column] = config.data
            ack_lines.append(config.update_message)

        # price
        if price is not None:
            config = target_role.config.price
            config.value = price or None
            data_args[config._column] = config.data
            ack_lines.append(config.update_message)

        # duration
        if duration is not None:
            config = target_role.config.duration
            config.data = duration or None
            data_args[config._column] = config.data
            ack_lines.append(config.update_message)

        if data_args:
            # Perform updates
            await target_role.data.update(**data_args)

            # Ack updates
            tick = self.bot.config.emojis.tick
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'cmd:rolemenu_editrole|success|title',
                    "Role menu role updated"
                )),
                description='\n'.join(
                    f"{tick} {line}" for line in ack_lines
                )
            )

            await target_menu.update_message()
            if target_menu.data.menutype is MenuType.REACTION and emoji is not None:
                try:
                    await target_menu.update_reactons()
                except SafeCancellation as e:
                    embed.add_field(
                        name=t(_p(
                            'cmd:rolemenu_editrole|success|error:reaction|name',
                            "Warning!"
                        )),
                        value=e.msg
                    )

            await ctx.interaction.followup.send(
                embed=embed,
                ephemeral=True
            )

        listen_key = (ctx.channel.id, ctx.author.id, target_menu.data.menuid)
        listening = MenuEditor._listening.get(listen_key, None)

        if (listening is None) or (not data_args):
            ui = MenuEditor(self.bot, target_menu, callerid=ctx.author.id)
            await ui.run(ctx.interaction)
            await ui.wait()
        else:
            await listening.refresh()
            await listening.update_preview()

    rolemenu_editrole_cmd.autocomplete('menu')(_menu_acmpl)
    rolemenu_editrole_cmd.autocomplete('menu_role')(_role_acmpl)

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_delrole', "delrole"),
        description=_p(
            'cmd:rolemenu_delrole|desc',
            "Remove a role from a role menu."
        )
    )
    @appcmds.rename(
        menu=_p('cmd:rolemenu_delrole|param:menu', "menu"),
        menu_role=_p('cmd:rolemenu_delrole|param:menu_role', "menu_role")
    )
    @appcmds.describe(
        menu=_p(
            'cmd:rolemenu_delrole|param:menu|desc',
            "Name of the menu to delete the role from."
        ),
        menu_role=_p(
            'cmd:rolemenu_delrole|param:menu_role|desc',
            "Name, label, or mention of the role to delete."
        )
    )
    async def rolemenu_delrole_cmd(self, ctx: LionContext,
                                   menu: appcmds.Range[str, 1, 64],
                                   menu_role: appcmds.Range[str, 1, 64]
                                   ):
        # Typechecking guards
        if ctx.guild is None:
            return
        if ctx.interaction is None:
            return
        t = self.bot.translator.t

        if not ctx.author.guild_permissions.manage_roles:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_delrole|error:author_perms',
                    "You need the `MANAGE_ROLES` permission in order to manage the server role menus."
                ))
            )

        # Parse target menu
        name = menu
        guild_menus = await self.fetch_guild_menus(ctx.guild.id)
        target_menu: RoleMenu
        if name.startswith('menuid:') and name[7:].isdigit():
            # Assume autogenerated from acmpl of the form menuid:id
            menuid = int(name[7:])
            target_menu = await RoleMenu.fetch(self.bot, menuid)
        else:
            # Assume it should match a menu name (case-insensitive)
            to_match = name.strip().lower()
            target_menu = next(
                (menu for menu in guild_menus if menu.data.name.lower() == to_match),
                None
            )

        if target_menu is None:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_delrole|error:menu_not_found',
                    "This server does not have a role menu called `{name}`!"
                )).format(name=name)
            )
        await target_menu.fetch_message()

        # Parse target role
        menu_roles = target_menu.roles
        target_role: RoleMenuRole
        if (maybe_id := menu_role.strip('<&@> ')).isdigit():
            # Assume given as role mention or id
            # Note that acmpl choices also provide mention
            roleid = int(maybe_id)
            target_role = next(
                (mrole for mrole in menu_roles if mrole.data.roleid == roleid),
                None
            )
        else:
            # Assume given as mrole label
            to_match = menu_role.strip().lower()
            target_role = next(
                (mrole for mrole in menu_roles if mrole.config.label.value.lower() == to_match),
                None
            )

        if target_role is None:
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_delrole|error:role_not_found',
                    "The menu **{menu}** does not have the role **{name}**"
                )).format(menu=target_menu.data.name, name=menu_role)
            )

        await ctx.interaction.response.defer(thinking=True)

        # Remove role and update target menu
        old_name = target_role.data.label
        await target_role.data.delete()
        await target_menu.reload_roles()
        await target_menu.update_message()

        # Ack deletion
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            description=t(_p(
                'cmd:rolemenu_delrole|success',
                "The role **{name}** was successfully removed from the menu **{menu}**."
            )).format(name=old_name, menu=target_menu.config.name.value)
        )
        await ctx.interaction.edit_original_response(embed=embed)

        # Update listening editor if it exists
        listen_key = (ctx.channel.id, ctx.author.id, target_menu.data.menuid)
        listening = MenuEditor._listening.get(listen_key, None)
        if listening is not None:
            await listening.refresh()
            await listening.update_preview()

    rolemenu_delrole_cmd.autocomplete('menu')(_menu_acmpl)
    rolemenu_delrole_cmd.autocomplete('menu_role')(_role_acmpl)
