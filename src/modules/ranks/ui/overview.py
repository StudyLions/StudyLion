from typing import Optional
import asyncio

import discord
from discord.ui.select import select, Select, SelectOption, RoleSelect
from discord.ui.button import button, Button, ButtonStyle

from meta import conf, LionBot
from core.data import RankType
from data import ORDER

from utils.ui import MessageUI
from utils.lib import MessageArgs
from babel.translator import ctx_translator

from .. import babel, logger
from ..data import AnyRankData
from ..utils import rank_model_from_type, format_stat_range, stat_data_to_value
from .editor import RankEditor
from .preview import RankPreviewUI

_p = babel._p


class RankOverviewUI(MessageUI):
    def __init__(self, bot: LionBot, guild: discord.Guild, callerid: int, **kwargs):
        super().__init__(callerid=callerid, **kwargs)
        self.bot = bot
        self.guild = guild
        self.guildid = guild.id

        self.lguild = None
        # List of ranks rows in ASC order
        self.ranks: list[AnyRankData] = []
        self.rank_type: RankType = None

        self.rank_preview: Optional[RankPreviewUI] = None

    @property
    def rank_model(self):
        """
        Return the correct Rank model for the current rank type.
        """
        if self.rank_type is None:
            return None
        else:
            return rank_model_from_type(self.rank_type)

    # ----- API -----
    async def run(self, *args, **kwargs):
        await super().run(*args, **kwargs)

    # ----- UI Components -----
    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        """
        Quit the UI.
        """
        await press.response.defer()
        await self.quit()

    async def quit_button_refresh(self):
        pass

    @button(label="AUTO_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def auto_button(self, press: discord.Interaction, pressed: Button):
        """
        Automatically generate a set of activity ranks for the guild.

        Ranks are determined by rank type.
        """
        await press.response.send_message("Not Implemented Yet")

    async def auto_button_refresh(self):
        self.auto_button.label = self.bot.translator.t(_p(
            'ui:rank_overview|button:auto|label',
            "Auto Create"
        ))

    @button(label="REFRESH_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def refresh_button(self, press: discord.Interaction, pressed: Button):
        """
        Refresh the current ranks,
        ensuring that all members have the correct rank.
        """
        await press.response.send_message("Not Implemented Yet")

    async def refresh_button_refresh(self):
        self.refresh_button.label = self.bot.translator.t(_p(
            'ui:rank_overview|button:refresh|label',
            "Refresh Member Ranks"
        ))

    @button(label="CLEAR_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def clear_button(self, press: discord.Interaction, pressed: Button):
        """
        Clear the rank list.
        """
        await self.rank_model.table.delete_where(guildid=self.guildid)
        self.bot.get_cog('RankCog').flush_guild_ranks(self.guild.id)
        self.ranks = []
        await self.redraw()

    async def clear_button_refresh(self):
        self.clear_button.label = self.bot.translator.t(_p(
            'ui:rank_overview|button:clear|label',
            "Clear Ranks"
        ))

    @button(label="CREATE_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def create_button(self, press: discord.Interaction, pressed: Button):
        """
        Create a new rank, and role to go with it.

        Errors if the client does not have permission to create roles.
        """
        async def _create_callback(rank, submit: discord.Interaction):
            await submit.response.send_message(
                embed=discord.Embed(
                    colour=discord.Colour.brand_green(),
                    description="Rank Created!"
                ),
                ephemeral=True
            )
            await self.refresh()

        await RankEditor.create_rank(
            press,
            self.rank_type,
            self.guild,
            callback=_create_callback
        )

    async def create_button_refresh(self):
        self.create_button.label = self.bot.translator.t(_p(
            'ui:rank_overview|button:create|label',
            "Create Rank"
        ))

    @select(cls=RoleSelect, placeholder="ROLE_SELECT_PLACEHOLDER", min_values=1, max_values=1)
    async def role_menu(self, selection: discord.Interaction, selected):
        """
        Create a new rank based on the selected role,
        or edit an existing rank,
        or throw an error if the role is @everyone or not manageable by the client.
        """
        role: discord.Role = selected.values[0]
        if role >= selection.user.top_role:
            # Do not allow user to manage a role above their own top role
            t = self.bot.translator.t
            error = t(_p(
                'ui:rank_overview|menu:roles|error:above_caller',
                "You have insufficient permissions to assign {mention} as a rank role! "
                "You may only manage roles below your top role."
            ))
            embed = discord.Embed(
                title=t(_p(
                    'ui:rank_overview|menu:roles|error:above_caller|title',
                    "Insufficient permissions!"
                )),
                description=error,
                colour=discord.Colour.brand_red()
            )
            await selection.response.send_message(embed=embed, ephemeral=True)
        elif role.is_assignable():
            existing = next((rank for rank in self.ranks if rank.roleid == role.id), None)
            if existing:
                # Display and edit the given role
                await RankEditor.edit_rank(
                    selection,
                    self.rank_type,
                    existing,
                    role,
                    callback=self._editor_callback
                )
            else:
                # Create new rank based on role
                await RankEditor.create_rank(
                    selection,
                    self.rank_type,
                    self.guild,
                    role=role,
                    callback=self._editor_callback
                )
        else:
            # Ack with a complaint depending on the type of error
            t = self.bot.translator.t

            if role.is_default():
                error = t(_p(
                    'ui:rank_overview|menu:roles|error:not_assignable|suberror:is_default',
                    "The @everyone role cannot be removed, and cannot be a rank!"
                ))
            elif role.managed:
                error = t(_p(
                    'ui:rank_overview|menu:roles|error:not_assignable|suberror:is_managed',
                    "The role is managed by another application or integration, and cannot be a rank!"
                ))
            elif not self.guild.me.guild_permissions.manage_roles:
                error = t(_p(
                    'ui:rank_overview|menu:roles|error:not_assignable|suberror:no_permissions',
                    "I do not have the `MANAGE_ROLES` permission in this server, so I cannot manage ranks!"
                ))
            elif (role >= self.guild.me.top_role):
                error = t(_p(
                    'ui:rank_overview|menu:roles|error:not_assignable|suberror:above_me',
                    "This role is above my top role in the role hierarchy, so I cannot add or remove it!"
                ))
            else:
                # Catch all for other potential issues
                error = t(_p(
                    'ui:rank_overview|menu:roles|error:not_assignable|suberror:other',
                    "I am not able to manage the selected role, so it cannot be a rank!"
                ))

            embed = discord.Embed(
                title=t(_p(
                    'ui:rank_overview|menu:roles|error:not_assignable|title',
                    "Could not create rank!"
                )),
                description=error,
                colour=discord.Colour.brand_red()
            )
            await selection.response.send_message(embed=embed, ephemeral=True)

    async def _editor_callback(self, rank: AnyRankData, submit: discord.Interaction):
        asyncio.create_task(self.refresh())
        await self._open_preview(rank, submit)

    async def _open_preview(self, rank: AnyRankData, interaction: discord.Interaction):
        previewui = RankPreviewUI(
            self.bot, self.guild, self.rank_type, rank, callerid=self._callerid, parent=self
        )
        if self.rank_preview is not None:
            asyncio.create_task(self.rank_preview.quit())
        self.rank_preview = previewui
        self._slaves = [previewui]
        await previewui.run(interaction)

    async def role_menu_refresh(self):
        self.role_menu.placeholder = self.bot.translator.t(_p(
            'ui:rank_overview|menu:roles|placeholder',
            "Create from role"
        ))

    @select(cls=Select, placeholder="RANK_PLACEHOLDER", min_values=1, max_values=1)
    async def rank_menu(self, selection: discord.Interaction, selected):
        """
        Select a rank to open the preview UI for that rank.

        Replaces the previously opened preview ui, if open.
        """
        rankid = int(selected.values[0])
        rank = await self.rank_model.fetch(rankid)
        await self._open_preview(rank, selection)

    async def rank_menu_refresh(self):
        self.rank_menu.placeholder = self.bot.translator.t(_p(
            'ui:rank_overview|menu:ranks|placeholder',
            "View or edit rank"
        ))

        options = []
        for rank in self.ranks:
            role = self.guild.get_role(rank.roleid)
            name = role.name if role else "Unknown Role"
            option = SelectOption(
                value=str(rank.rankid),
                label=name,
                description=format_stat_range(self.rank_type, rank.required, short=False),
            )
            options.append(option)
        self.rank_menu.options = options

    # ----- UI Flow -----
    def _format_range(self, start: int, end: Optional[int] = None):
        """
        Appropriately format the given required amount for the current rank type.
        """
        if self.rank_type is RankType.VOICE:
            startval = stat_data_to_value(self.rank_type, start)
            if end:
                endval = stat_data_to_value(self.rank_type, end)
                string = f"{startval} - {endval} h"
            else:
                string = f"{startval} h"
        elif self.rank_type is RankType.XP:
            if end:
                string = f"{start} - {end} XP"
            else:
                string = f"{start} XP"
        elif self.rank_type is RankType.MESSAGE:
            if end:
                string = f"{start} - {end} msgs"
            else:
                string = f"{start} msgs"
        return string

    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t

        if self.ranks:
            # Format the ranks into a neat list
            # TODO: Error symbols for non-existent or permitted roles
            required = [rank.required for rank in self.ranks]
            ranges = list(zip(required, required[1:]))
            pad = 1 if len(ranges) < 10 else 2

            lines = []
            for i, rank in enumerate(self.ranks):
                if i == len(self.ranks) - 1:
                    reqstr = format_stat_range(self.rank_type, rank.required)
                    rangestr = f"≥ {reqstr}"
                else:
                    start, end = ranges[i]
                    rangestr = format_stat_range(self.rank_type, start, end)

                line = "`[{pos:<{pad}}]` | <@&{roleid}> **({rangestr})**".format(
                    pad=pad,
                    pos=i+1,
                    roleid=rank.roleid,
                    rangestr=rangestr
                )
                lines.append(line)
            desc = '\n'.join(reversed(lines))
        else:
            # No ranks, give hints about adding ranks
            desc = t(_p(
                'ui:rank_overview|embed:noranks|desc',
                "No activity ranks have been set up!\n"
                "Press 'AUTO' to automatically create a "
                "standard heirachy of voice | text | xp ranks, "
                "or select a role or press Create below!"
            ))
        if self.rank_type is RankType.VOICE:
            title = t(_p(
                'ui:rank_overview|embed|title|type:voice',
                "Voice Ranks in {guild_name}"
            ))
        elif self.rank_type is RankType.XP:
            title = t(_p(
                'ui:rank_overview|embed|title|type:xp',
                "XP ranks in {guild_name}"
            ))
        elif self.rank_type is RankType.MESSAGE:
            title = t(_p(
                'ui:rank_overview|embed|title|type:message',
                "Message ranks in {guild_name}"
            ))
        title = title.format(guild_name=self.guild.name)
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=title,
            description=desc
        )
        return MessageArgs(embed=embed)

    async def refresh_layout(self):
        if self.ranks:
            # If the guild has at least one rank setup
            await asyncio.gather(
                self.rank_menu_refresh(),
                self.role_menu_refresh(),
                self.refresh_button_refresh(),
                self.create_button_refresh(),
                self.clear_button_refresh(),
                self.quit_button_refresh(),
            )
            self.set_layout(
                (self.rank_menu,),
                (self.role_menu,),
                (self.refresh_button, self.create_button, self.clear_button, self.quit_button)
            )
        else:
            # If the guild has no ranks set up
            await asyncio.gather(
                self.role_menu_refresh(),
                self.auto_button_refresh(),
                self.create_button_refresh(),
                self.quit_button_refresh(),
            )
            self.set_layout(
                (self.role_menu,),
                (self.auto_button, self.create_button, self.quit_button)
            )

    async def reload(self):
        """
        Refresh the rank list and type from data.
        """
        self.lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        self.rank_type = self.lguild.config.get('rank_type').value
        self.ranks = await self.rank_model.fetch_where(
            guildid=self.guildid
        ).order_by('required', ORDER.ASC)
