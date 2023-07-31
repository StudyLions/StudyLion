from typing import Optional
from collections import defaultdict
import asyncio
import json

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.app_commands import Range
from discord.app_commands.transformers import AppCommandOptionType as cmdopt

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.errors import ResponseTimedOut, UserInputError, UserCancelled
from meta.sharding import THIS_SHARD
from utils.lib import utc_now, error_embed
from utils.ui import Confirm, ChoicedEnum, Transformed
from constants import MAX_COINS

from wards import low_management_ward

from . import babel, logger
from .data import RoleMenuData, MenuType
from .rolemenu import RoleMenu, RoleMenuRole
from .ui.menueditor import MenuEditor
from .templates import templates


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


class RoleMenuCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(RoleMenuData())

        # Menu caches
        self.guild_menus = defaultdict(dict)  # guildid -> menuid -> RoleMenu
        self.guild_menu_messages = defaultdict(dict)  # guildid -> messageid -> RoleMenu

    # ----- Initialisation -----
    async def cog_load(self):
        await self.data.init()

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        ...

    @LionCog.listener('on_ready')
    @log_wrap(action="Initialise Role Menus")
    async def initialise(self):
        ...

    # ----- Cog API -----
    async def register_menus(*menus):
        ...

    async def deregister_menus(*menus):
        ...

    # ----- Private Utils -----
    async def _parse_msg(self, guild: discord.Guild, msgstr: str) -> discord.Message:
        """
        Parse a message reference link into a Message.
        """
        t = self.bot.translator.t

        error = None
        message = None
        splits = msgstr.strip().rsplit('/', maxsplit=2)
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
    # Message delete handler
    # Role delete handler
    # Reaction handler
    # Guild leave handler (stop listening)
    # Guild join handler (start listening)

    # ----- Context Menu -----

    # ----- Commands -----

    @cmds.hybrid_command(
        name=_p('cmd:rolemenus', "rolemenus"),
        description=_p(
            'cmd:rolemenus|desc',
            "View and configure the role menus in this server."
        )
    )
    async def rolemenus_cmd(self, ctx: LionContext):
        # Spawn the menus UI
        # Maybe accept a channel here to restrict the menus
        ...

    @cmds.hybrid_group(
        name=_p('group:rolemenu', "rolemenu"),
        description=_p(
            'group:rolemenu|desc',
            "Base command group for role menu configuration."
        )
    )
    @appcmds.guild_only()
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
        ]
    )
    async def rolemenu_create_cmd(self, ctx: LionContext,
                                  name: appcmds.Range[str, 1, 64],
                                  message: Optional[str] = None,
                                  menu_style: Optional[Transformed[MenuStyleParam, cmdopt.string]] = None,
                                  required_role: Optional[discord.Role] = None,
                                  sticky: Optional[bool] = None,
                                  refunds: Optional[bool] = None,
                                  obtainable: Optional[appcmds.Range[int, 1, 25]] = None,
                                  template: Optional[appcmds.Choice[int]] = None,
                                  ):
        # Type checking guards
        if ctx.guild is None:
            return
        if ctx.interaction is None:
            return

        t = self.bot.translator.t
        await ctx.interaction.response.defer(thinking=True)

        # Parse provided target message if given
        if message is None:
            target_message = None
            target_mine = True
        else:
            # Parse provided message link into a Message
            target_message: discord.Message = await self._parse_msg(message)
            target_mine = (target_message.author == ctx.guild.me)

            # Check that this message is not already attached to a role menu
            if target_message.id in (menu.data.messageid for menu in self.guild_menus[ctx.guild.id].values()):
                raise UserInputError(
                    t(_p(
                        'cmd:rolemenu_create|error:message_exists',
                        "The message {link} already has a role menu! Use {edit_cmd} to edit it."
                    )).format(
                        link=target_message.jump_url,
                        edit_cmd=self.bot.core.mention_cache['rolemenu edit']
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
                        'cmd:rolemenu_create|error:incompatible_style',
                        "I cannot create a `{style}` style menu on a message I didn't send (Discord restriction)."
                    )).format(style=t(menu_style.value[0]))
                )

        # Parse menu options if given
        name = name.strip()
        if name.lower() in (menu.data.name.lower() for menu in self.guild_menus[ctx.guild.id].values()):
            raise UserInputError(
                t(_p(
                    'cmd:rolemenu_create|error:name_exists',
                    "A rolemenu called `{name}` already exists! Use {edit_cmd} to edit it."
                )).format(name=name, edit_cmd=self.bot.core.mention_cache['rolemenu edit'])
            )

        templateid = template.value if template is not None else None
        if target_message:
            message_data = {}
            message_data['content'] = target_message.content
            if target_message.embeds:
                message_data['embed'] = target_message.embeds[0].to_dict()
            rawmessage = json.dumps(message_data)
        else:
            rawmessage = None
            if templateid is None:
                templateid = 0

        # Create RoleMenu data, set options if given
        data = await self.data.RoleMenu.create(
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
            rawmessage=rawmessage,
        )
        # Create RoleMenu
        menu = RoleMenu(self.bot, data, [])

        # Open editor, with preview if not a reaction role message
        editor = MenuEditor(self.bot, menu, callerid=ctx.author.id)
        await editor.run(ctx.interaction)
        await editor.wait()

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_edit', "editmenu"),
        description=_p(
            'cmd:rolemenu_edit|desc',
            "Edit an existing (or in-creation) role menu."
        )
    )
    async def rolemenu_edit_cmd(self, ctx: LionContext):
        # Parse target
        # Parse provided options
        # Set options if provided
        # Open editor with preview
        ...

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_delete', "delmenu"),
        description=_p(
            'cmd:rolemenu_delete|desc',
            "Delete a role menu."
        )
    )
    async def rolemenu_delete_cmd(self, ctx: LionContext):
        # Parse target
        # Delete target
        ...

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_addrole', "addrole"),
        description=_p(
            'cmd:rolemenu_addrole|desc',
            "Add a new role to a new or existing role menu."
        )
    )
    async def rolemenu_addrole_cmd(self, ctx: LionContext,
                                   role: discord.Role,
                                   message: Optional[str] = None,
                                   ):
        # Parse target menu, may need to create here
        # Parse target role
        # Check author permissions
        # Parse role options
        # Create RoleMenuRole
        # Ack, with open editor button
        ...

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_editrole', "editrole"),
        description=_p(
            'cmd:rolemenu_editrole|desc',
            "Edit role options in a role menu (supports in-creation menus)"
        )
    )
    async def rolemenu_editrole_cmd(self, ctx: LionContext):
        # Parse target menu
        # Parse target role
        # Check author permissions
        # Parse role options
        # Either ack changes or open the RoleEditor
        ...

    @rolemenu_group.command(
        name=_p('cmd:rolemenu_delrole', "delrole"),
        description=_p(
            'cmd:rolemenu_delrole|desc',
            "Remove a role from a role menu."
        )
    )
    async def rolemenu_delrole_cmd(self, ctx: LionContext):
        # Parse target menu
        # Parse target role
        # Remove role
        ...
