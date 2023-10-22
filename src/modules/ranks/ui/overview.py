from typing import Optional
import asyncio

import discord
from discord.ui.select import select, Select, SelectOption, RoleSelect
from discord.ui.button import button, Button, ButtonStyle

from meta import conf, LionBot
from meta.errors import ResponseTimedOut, SafeCancellation
from core.data import RankType
from data import ORDER

from utils.ui import MessageUI, Confirm
from utils.lib import MessageArgs
from wards import equippable_role
from babel.translator import ctx_translator

from .. import babel, logger
from ..data import AnyRankData, RankData
from ..utils import rank_model_from_type, format_stat_range, stat_data_to_value
from .editor import RankEditor
from .preview import RankPreviewUI
from .templates import get_guild_template

_p = babel._p


class RankOverviewUI(MessageUI):
    block_len = 25

    def __init__(self, bot: LionBot, guild: discord.Guild, callerid: int, **kwargs):
        super().__init__(callerid=callerid, **kwargs)
        self.bot = bot
        self.guild = guild
        self.guildid = guild.id
        self.cog = bot.get_cog('RankCog')

        self.lguild = None

        # List of ranks rows in ASC order
        self.ranks: list[AnyRankData] = []
        self.rank_type: RankType = None

        self.pagen = 0
        self.blocks = [[]]

        self.rank_preview: Optional[RankPreviewUI] = None

    @property
    def page_count(self):
        return len(self.blocks)

    @property
    def rank_block(self):
        self.pagen %= self.page_count
        return self.blocks[self.pagen]

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
        t = self.bot.translator.t

        # Prevent role creation spam
        if await self.rank_model.table.select_where(guildid=self.guild.id):
            return await press.response.send_message(content=t(_p(
                'ui:rank_overview|button:auto|error:already_created',
                "The rank roles have already been created!"
            )), ephemeral=True)

        await press.response.defer(thinking=True)

        if not self.guild.me.guild_permissions.manage_roles:
            raise SafeCancellation(t(_p(
                'ui:rank_overview|button:auto|error:my_permissions',
                "I lack the 'Manage Roles' permission required to create rank roles!"
            )))

        # Get rank role template based on set RankType and VoiceMode
        template = get_guild_template(self.rank_type, self.lguild.guild_mode.voice)
        if not template:
            # Safely error if rank type or voice mode isn't an expected value
            raise SafeCancellation(t(_p(
                'ui:rank_overview|button:auto|error:invalid_template',
                "Unable to determine rank role template!")))

        roles = []
        async with self.cog.ranklock(self.guild.id):
            for rank in reversed(template):
                try:
                    colour = discord.Colour.from_str(rank.colour)
                    role = await self.guild.create_role(name=t(rank.name), colour=colour)
                    roles.append(role)
                    await self.rank_model.create(
                        roleid=role.id,
                        guildid=self.guild.id,
                        required=rank.required,
                        reward=rank.reward,
                        message=t(rank.message)
                    )
                    self.cog.flush_guild_ranks(self.guild.id)

                # Error if manage roles is lost during the process. This shouldn't happen
                except discord.Forbidden:
                    self.cog.flush_guild_ranks(self.guild.id)
                    raise SafeCancellation(t(_p(
                        'ui:rank_overview|button|auto|role_creation|error:forbidden',
                        "An error occurred while autocreating rank roles!\n"
                        "I lack the 'Manage Roles' permission required to create rank roles!"
                        )))

                except discord.HTTPException:
                    self.cog.flush_guild_ranks(self.guild.id)
                    raise SafeCancellation(t(_p(
                        'ui:rank_overview|button:auto|role_creation|error:unknown',
                        "An error occurred while autocreating rank roles!\n"
                        "Please check the server has enough space for new roles "
                        "and try again."
                    )))

            success_msg = t(_p(
                'ui:rank_overview|button:auto|role_creation|success',
                "Successfully created the following rank roles:\n{roles}"
                )).format(roles="\n".join(role.mention for role in roles))
            embed = discord.Embed(
                    colour=discord.Colour.brand_green(),
                    description=success_msg)
            await press.edit_original_response(embed=embed)

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
        await press.response.defer(thinking=True)
        async with self.cog.ranklock(self.guild.id):
            await self.cog.interactive_rank_refresh(press, self.guild)

    async def refresh_button_refresh(self):
        self.refresh_button.label = self.bot.translator.t(_p(
            'ui:rank_overview|button:refresh|label',
            "Refresh Member Ranks"
        ))

    @button(label="CLEAR_BUTTON_PLACEHOLDER", style=ButtonStyle.red)
    async def clear_button(self, press: discord.Interaction, pressed: Button):
        """
        Clear the rank list.
        """
        # Confirm deletion
        t = self.bot.translator.t
        confirm_msg = t(_p(
            'ui:rank_overview|button:clear|confirm',
            "Are you sure you want to **delete all activity ranks** in this server?"
        ))
        confirmui = Confirm(confirm_msg, self._callerid)
        confirmui.confirm_button.label = t(_p(
            'ui:rank_overview|button:clear|confirm|button:yes',
            "Yes, clear ranks"
        ))
        confirmui.confirm_button.style = ButtonStyle.red
        confirmui.cancel_button.style = ButtonStyle.green
        confirmui.cancel_button.label = t(_p(
            'ui:rank_overview|button:clear|confirm|button:no',
            "Cancel"
        ))
        try:
            result = await confirmui.ask(press, ephemeral=True)
        except ResponseTimedOut:
            result = False
        if result:
            async with self.cog.ranklock(self.guild.id):
                await self.rank_model.table.delete_where(guildid=self.guildid)
                self.cog.flush_guild_ranks(self.guild.id)
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
        t = self.bot.translator.t
        if not self.guild.me.guild_permissions.manage_roles:
            raise SafeCancellation(t(_p(
                'ui:rank_overview|button:create|error:my_permissions',
                "I lack the 'Manage Roles' permission required to create rank roles!"
            )))

        async def _create_callback(rank, submit: discord.Interaction):
            await submit.response.send_message(
                embed=discord.Embed(
                    colour=discord.Colour.brand_green(),
                    description=t(_p(
                        'ui:rank_overview|button:create|success',
                        "Created a new rank {role}"
                    )).format(role=f"<@&{rank.roleid}>")
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

        if role.is_assignable():
            # Create or edit the selected role
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
                # Need to check the calling author has authority to manage this role
                await equippable_role(self.bot, role, selection.user)
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
        for rank in self.rank_block:
            role = self.guild.get_role(rank.roleid)
            name = role.name if role else "Unknown Role"
            option = SelectOption(
                value=str(rank.rankid),
                label=name,
                description=format_stat_range(self.rank_type, rank.required, short=False),
            )
            options.append(option)
        self.rank_menu.options = options

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

    async def make_message(self, show_note=True) -> MessageArgs:
        t = self.bot.translator.t

        if self.ranks:
            # Format the ranks into a neat list
            # TODO: Error symbols for non-existent or permitted roles
            required = [rank.required for rank in self.ranks]
            ranges = list(zip(required, required[1:]))
            pad = 1 if len(self.ranks) < 10 else 2

            lines = []
            for i, rank in enumerate(self.ranks):
                if i == len(self.ranks) - 1:
                    reqstr = format_stat_range(self.rank_type, rank.required)
                    rangestr = f"≥ {reqstr}"
                else:
                    start, end = ranges[i]
                    rangestr = format_stat_range(self.rank_type, start, end)

                line = "`[{pos:>{pad}}]` | <@&{roleid}> **({rangestr})**".format(
                    pad=pad,
                    pos=i+1,
                    roleid=rank.roleid,
                    rangestr=rangestr
                )
                lines.append(line)
            line_blocks = [
                lines[i:i+self.block_len] for i in range(0, len(lines), self.block_len)
            ] or [[]]
            lines = line_blocks[self.pagen]
            desc = '\n'.join(reversed(lines))
        else:
            # No ranks, give hints about adding ranks
            desc = t(_p(
                'ui:rank_overview|embed:noranks|desc',
                "No activity ranks have been set up!"
            ))
            if show_note:
                auto_addendum = t(_p(
                    'ui:rank_overview|embed:noranks|desc|admin_addendum',
                    "Press 'Auto Create' to automatically create a "
                    "standard heirachy of ranks.\n"
                    "To manually create ranks, press 'Create Rank' below, or select a role!"
                ))
                desc = "\n".join((desc, auto_addendum))

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
        if show_note:
            # Add note about season start
            note_name = t(_p(
                'ui:rank_overview|embed|field:note|name',
                "Note"
            ))
            season_start = self.lguild.data.season_start
            if season_start:
                season_str = t(_p(
                    'ui:rank_overview|embed|field:note|value:with_season',
                    "Ranks are determined by activity since {timestamp}."
                )).format(
                    timestamp=discord.utils.format_dt(season_start)
                )
            else:
                season_str = t(_p(
                    'ui:rank_overview|embed|field:note|value:without_season',
                    "Ranks are determined by *all-time* statistics.\n"
                    "To reward ranks from a later time (e.g. to have monthly/quarterly/yearly ranks) "
                    "set the `season_start` with {stats_cmd}"
                )).format(stats_cmd=self.bot.core.mention_cmd('admin config statistics'))
            if self.rank_type is RankType.VOICE:
                addendum = t(_p(
                    'ui:rank_overview|embed|field:note|value|voice_addendum',
                    "Also note that ranks will only be updated when a member leaves a tracked voice channel! "
                    "Use the **Refresh Member Ranks** button below to update all members manually."
                ))
                season_str = '\n'.join((season_str, addendum))
            embed.add_field(
                name=note_name,
                value=season_str,
                inline=False
            )

        return MessageArgs(embed=embed)

    async def refresh_layout(self):
        if len(self.blocks) > 1:
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
                (self.refresh_button, self.create_button, self.clear_button),
                (self.prev_page_button, self.quit_button, self.next_page_button)
            )
        elif self.rank_block:
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
        ranks = self.ranks = await self.rank_model.fetch_where(
            guildid=self.guildid
        ).order_by('required', ORDER.ASC)
        self.blocks = [ranks[i:i + self.block_len] for i in range(0, len(ranks), self.block_len)] or [[]]
