import asyncio
from typing import Optional, TYPE_CHECKING
from collections import defaultdict

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, Select, SelectOption

from meta import LionBot, conf
from utils.lib import MessageArgs
from utils.ui import MessageUI

from .. import babel
from ..rolemenu import RoleMenu

from .menueditor import MenuEditor

if TYPE_CHECKING:
    from ..cog import RoleMenuCog

_p = babel._p


class MenuList(MessageUI):
    blocklen = 20

    def __init__(self, bot: LionBot, guild: discord.Guild, **kwargs):
        super().__init__(**kwargs)

        self.bot = bot
        self.guild = guild
        self.cog: 'RoleMenuCog' = bot.get_cog('RoleMenuCog')

        self.pagen = 0
        self.menus = []
        self.menu_blocks = [[]]

        self._menu_editor: Optional[MenuEditor] = None

    @property
    def page(self):
        self.pagen %= self.page_count
        return self.menu_blocks[self.pagen]

    @property
    def page_count(self):
        return len(self.menu_blocks)

    # ----- UI API -----

    # ----- Components -----
    # Quit Button
    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        """
        Close the UI. This should also close all children.
        """
        await press.response.defer(thinking=False)
        await self.quit()

    # Page Buttons
    @button(emoji=conf.emojis.forward)
    async def next_page_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        self.pagen += 1
        await self.refresh()

    @button(emoji=conf.emojis.backward)
    async def prev_page_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        self.pagen -= 1
        await self.refresh()

    @button(emoji=conf.emojis.refresh)
    async def refresh_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        await self.refresh()

    # Menu selector
    @select(cls=Select, placeholder="EDITMENU_MENU_PLACEHOLDER", min_values=0, max_values=1)
    async def editmenu_menu(self, selection: discord.Interaction, selected: Select):
        """
        Opens the menu editor for the selected menu.

        Replaces the existing editor, if it exists.
        """
        if selected.values:
            await selection.response.defer(thinking=True, ephemeral=True)
            if self._menu_editor is not None and not self._menu_editor.is_finished():
                await self._menu_editor.quit()
            menuid = int(selected.values[0])
            menu = await RoleMenu.fetch(self.bot, menuid)
            editor = MenuEditor(self.bot, menu, callerid=self._callerid)
            self._menu_editor = editor
            self._slaves.append(editor)
            await editor.run(selection)
        else:
            await selection.response.defer()

    async def editmenu_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.editmenu_menu
        menu.placeholder = t(_p(
            'ui:menu_list|menu:editmenu|placeholder',
            "Select Menu to Edit"
        ))
        menus = self.page
        if menus:
            menu.options = [
                self._format_menu_option(m) for m in menus
            ]
            menu.disabled = False
        else:
            menu.options = [
                SelectOption(label='DUMMY')
            ]
            menu.disabled = True

    # ----- UI Flow -----
    def _format_menu_line(self, menu: RoleMenu) -> str:
        """
        Format a provided RoleMenu into a pretty display line.
        """
        t = self.bot.translator.t
        jump_link = menu.jump_link
        if jump_link is not None:
            line = t(_p(
                'ui:menu_list|menu_line:attached',
                "[`{name}`]({jump_url}) with `{count}` roles."
            )).format(
                name=menu.config.name.value,
                jump_url=jump_link,
                count=len(menu.roles)
            )
        else:
            line = t(_p(
                'ui:menu_list|menu_line:unattached',
                "`{name}` with `{count}` roles."
            )).format(
                name=menu.config.name.value,
                count=len(menu.roles)
            )
        return line

    def _format_menu_option(self, menu: RoleMenu) -> SelectOption:
        """
        Format a provided RoleMenu into a SelectOption.
        """
        option = SelectOption(
            value=str(menu.data.menuid),
            label=menu.config.name.value[:100],
        )
        return option

    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        menus = self.page

        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=t(_p(
                'ui:menu_list|embed|title',
                "Role Menus in {guild}"
            )).format(guild=self.guild.name)
        )

        if not menus:
            # Empty page message
            # Add tips to create menus
            tips_name = t(_p(
                'ui:menu_list|embed|field:tips|name',
                "Tips"
            ))
            tips_value = t(_p(
                'ui:menu_list|embed|field:tips|value',
                "Right click an existing message or use the `newmenu` command to create a new menu."
            ))
            embed.add_field(name=tips_name, value=tips_value)
            # TODO: Guide image
        else:
            # Partition menus by channel, without breaking the order
            channel_lines = defaultdict(list)
            for menu in menus:
                channel_lines[menu.data.channelid].append(self._format_menu_line(menu))

            for channelid, lines in channel_lines.items():
                name = f"<#{channelid}>" if channelid else t(_p(
                    'ui:menu_list|embed|field:unattached|name',
                    "Unattached Menus"
                ))
                value = '\n'.join(lines)
                # Precaution in case all the menu names are really long
                value = value[:1024]
                embed.add_field(
                    name=name, value=value, inline=False
                )

            embed.set_footer(
                text=t(_p(
                    'ui:menu_list|embed|footer:text',
                    "Click a menu name to jump to the message."
                ))
            )

        return MessageArgs(embed=embed)

    async def refresh_layout(self):
        refresh_tasks = (
            self.editmenu_menu_refresh(),
        )
        await asyncio.gather(*refresh_tasks)

        if len(self.menu_blocks) > 1:
            self.prev_page_button.disabled = False
            self.next_page_button.disabled = False
        else:
            self.prev_page_button.disabled = True
            self.next_page_button.disabled = True

        self.set_layout(
            (self.prev_page_button, self.refresh_button, self.next_page_button, self.quit_button,),
            (self.editmenu_menu,),
        )

    def _sort_key(self, menu_data):
        message_exists = int(bool(menu_data.messageid))
        channel = self.guild.get_channel(menu_data.channelid) if menu_data.channelid else None
        channel_position = channel.position if channel is not None else 0
        # Unattached menus will be ordered by their creation id
        messageid = menu_data.messageid or menu_data.menuid
        return (message_exists, channel_position, messageid)

    async def reload(self):
        # Fetch menu data for this guild
        menu_data = await self.cog.data.RoleMenu.fetch_where(guildid=self.guild.id)

        # Order menu data by (message_exists, channel_position, messageid)
        sorted_menu_data = sorted(menu_data, key=self._sort_key)

        # Fetch associated menus, load into self.menus
        menus = []
        for data in sorted_menu_data:
            menu = await RoleMenu.fetch(self.bot, data.menuid)
            menus.append(menu)

        self.menus = menus

        self.menu_blocks = [menus[i:i+self.blocklen] for i in range(0, len(menus), self.blocklen)] or [[]]
