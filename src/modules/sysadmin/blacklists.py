from typing import Optional, List
import asyncio
import logging

from data import Table, Registry, ORDER

import discord
from discord.abc import Messageable
from discord.ext import commands as cmds
from discord.app_commands.transformers import AppCommandOptionType
from discord.ui.select import select, Select, SelectOption
from discord.ui.button import button
from discord.ui.text_input import TextStyle, TextInput

from meta import LionCog, LionBot, LionContext
from meta.logger import logging_context, log_wrap, set_logging_context
from meta.errors import UserInputError
from meta.app import shard_talk

from utils.ui import ChoicedEnum, Transformed, FastModal, LeoUI, error_handler_for, ModalRetryUI
from utils.lib import EmbedField, tabulate, MessageArgs, parse_ids, error_embed

from wards import sys_admin_ward

logger = logging.getLogger(__name__)


class BlacklistData(Registry, name="blacklists"):
    guild_blacklist = Table('global_guild_blacklist')
    user_blacklist = Table('global_user_blacklist')


class BlacklistAction(ChoicedEnum):
    ADD_USER = "Blacklist Users"
    RM_USER = "UnBlacklist Users"
    ADD_GUILD = "Blacklist Guilds"
    RM_GUILD = "UnBlacklist Guilds"

    @property
    def choice_name(self):
        return self.value


class Blacklists(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = self.bot.db.load_registry(BlacklistData())

        self.user_blacklist: set[int] = set()
        self.guild_blacklist: set[int] = set()

        self.talk_user_blacklist = shard_talk.register_route("user blacklist")(self.load_user_blacklist)
        self.talk_guild_blacklist = shard_talk.register_route("guild blacklist")(self.load_guild_blacklist)

    async def cog_load(self):
        await self.data.init()
        await self.load_user_blacklist()
        await self.load_guild_blacklist()

    async def load_user_blacklist(self):
        """Populate the user blacklist."""
        rows = await self.data.user_blacklist.select_where()
        self.user_blacklist = {row['userid'] for row in rows}
        logger.info(
            f"Loaded {len(self.user_blacklist)} blacklisted users."
        )

    async def load_guild_blacklist(self):
        """Populate the guild blacklist."""
        rows = await self.data.guild_blacklist.select_where()
        self.guild_blacklist = {row['guildid'] for row in rows}
        logger.info(
            f"Loaded {len(self.guild_blacklist)} blacklisted guilds."
        )
        if self.bot.is_ready():
            await self.leave_blacklisted_guilds()

    @LionCog.listener('on_ready')
    @log_wrap(action="Guild Blacklist")
    async def leave_blacklisted_guilds(self):
        """Leave any blacklisted guilds we are in on this shard."""
        to_leave = [
            guild for guild in self.bot.guilds
            if guild.id in self.guild_blacklist
        ]
        if to_leave:
            tasks = [asyncio.create_task(guild.leave()) for guild in to_leave]
            await asyncio.gather(*tasks)

        logger.info(
            "Left {} blacklisted guilds.".format(len(to_leave)),
        )

    @LionCog.listener('on_guild_join')
    @log_wrap(action="Check Guild Blacklist")
    async def check_guild_blacklist(self, guild):
        """Check if the given guild is in the blacklist, and leave if so."""
        if guild.id in self.guild_blacklist:
            set_logging_context(context=f"gid: {guild.id}")
            await guild.leave()
            logger.info(
                "Automatically left blacklisted guild '{}' (gid:{}) upon join.".format(guild.name, guild.id)
            )

    async def bot_check_once(self, ctx: LionContext) -> bool:  # type:ignore
        if ctx.author.id in self.user_blacklist:
            logger.debug(
                f"Ignoring command from blacklisted user <uid: {ctx.author.id}>.",
                extra={'action': 'User Blacklist'}
            )
            return False
        else:
            return True

    @log_wrap(action="User Blacklist")
    async def blacklist_users(self, actorid, userids, reason):
        await self.data.user_blacklist.insert_many(
            ('userid', 'ownerid', 'reason'),
            *((userid, actorid, reason) for userid in userids)
        )
        self.user_blacklist.update(userids)
        await self.talk_user_blacklist().broadcast()

        uid_str = ', '.join(f"<uid: {userid}>" for userid in userids)
        logger.info(
            f"Owner <aid: {actorid}> blacklisted {uid_str} with reason: \"{reason}\""
        )

    @log_wrap(action="User Blacklist")
    async def unblacklist_users(self, actorid, userids):
        await self.data.user_blacklist.delete_where(userid=userids)
        self.user_blacklist.difference_update(userids)

        await self.talk_user_blacklist().broadcast()

        uid_str = ', '.join(f"<uid: {userid}>" for userid in userids)
        logger.info(
            f"Owner <aid: {actorid}> removed blacklist for user(s) {uid_str}."
        )

    @log_wrap(action="Guild Blacklist")
    async def blacklist_guilds(self, actorid, guildids, reason):
        await self.data.guild_blacklist.insert_many(
            ('guildid', 'ownerid', 'reason'),
            *((guildid, actorid, reason) for guildid in guildids)
        )
        self.guild_blacklist.update(guildids)
        await self.talk_guild_blacklist().broadcast()

        gid_str = ', '.join(f"<gid: {guildid}>" for guildid in guildids)
        logger.info(
            f"Owner <aid: {actorid}> blacklisted {gid_str} with reason: \"{reason}\""
        )

    @log_wrap(action="Guild Blacklist")
    async def unblacklist_guilds(self, actorid, guildids):
        await self.data.guild_blacklist.delete_where(guildid=guildids)
        self.guild_blacklist.difference_update(guildids)

        await self.talk_guild_blacklist().broadcast()

        gid_str = ', '.join(f"<gid: {guildid}>" for guildid in guildids)
        logger.info(
            f"Owner <aid: {actorid}> removed blacklist for guild(s) {gid_str}."
        )

    @cmds.hybrid_command(
        name="blacklist",
        description="Display and modify the user and guild blacklists."
    )
    @sys_admin_ward
    async def blacklist_cmd(
        self,
        ctx: LionContext,
        action: Optional[Transformed[BlacklistAction, AppCommandOptionType.string]] = None,
        targets: Optional[str] = None,
        reason: Optional[str] = None
    ):
        """
        Display and modify the user and guild blacklists.

        With no arguments, just displays the Blacklist UI.

        If `targets` are provided, they should be a comma separated list of user or guild ids.
        If `action` is not specified, they are assumed to be users to blacklist.
        `reason` is the reason for the blacklist.
        If `targets` are provided, but `reason` is not, it will be prompted for.
        """
        UI = BlacklistUI(ctx.bot, ctx, auth=[ctx.author.id])
        if not ctx.interaction:
            return await ctx.error_reply("This command cannot be used as a text command.")

        if (action is None and targets is not None) or action is BlacklistAction.ADD_USER:
            await UI.spawn_add_users(ctx.interaction, targets, reason)
        elif action is BlacklistAction.ADD_GUILD:
            await UI.spawn_add_guilds(ctx.interaction, targets, reason)
        elif action is BlacklistAction.RM_USER:
            if targets is None:
                UI._show_remove = True
                await UI.spawn()
            else:
                try:
                    userids = parse_ids(targets)
                except UserInputError as ex:
                    await ctx.error_reply("Could not extract user id from {item}".format(**ex.info))
                else:
                    await UI.do_rm_users(ctx.interaction, userids)
        elif action is BlacklistAction.RM_GUILD:
            if targets is None:
                UI._show_remove = True
                UI.guild_mode = True
                await UI.spawn()
            else:
                try:
                    guildids = parse_ids(targets)
                except UserInputError as ex:
                    await ctx.error_reply("Could not extract guild id from {item}".format(**ex.info))
                else:
                    await UI.do_rm_guilds(ctx.interaction, guildids)
        elif action is None and targets is None:
            await UI.spawn()


class BlacklistInput(FastModal):
    targets: TextInput = TextInput(
        label="Userids to blacklist.",
        placeholder="Comma separated ids.",
        max_length=4000,
        required=True
    )

    reason: TextInput = TextInput(
        label="Reason for the blacklist.",
        style=TextStyle.long,
        max_length=4000,
        required=True
    )

    @error_handler_for(UserInputError)
    async def rerequest(self, interaction: discord.Interaction, error: UserInputError):
        await ModalRetryUI(self, error.msg).respond_to(interaction)


class BlacklistUI(LeoUI):
    block_len = 5  # Number of entries to show per page

    def __init__(self, bot: LionBot, dest: Messageable, auth: Optional[List[int]] = None):
        super().__init__()
        # Client information
        self.bot = bot
        self.cog: Blacklists = bot.get_cog('Blacklists')  # type: ignore
        if self.cog is None:
            raise ValueError("Cannot run BlacklistUI without the 'Blacklists' cog.")

        # State
        self.guild_mode = False  # Whether we are showing guild blacklist or user blacklist
        # List of current pages, as (page args, data slice) tuples
        self.pages: Optional[List[tuple[MessageArgs, tuple[int, int]]]] = None
        self.page_no: int = 0  # Current page we are on
        self.data = None  # List of data rows for this mode

        # Discord State
        self.dest = dest  # The destination to send or resend the UI
        self.message: Optional[discord.Message] = None  # Message holding the UI

        # UI State
        # This is better handled by a general abstract "_extra" or layout modi interface.
        # For now, just a flag for whether we show the extra remove menu.
        self._show_remove = False
        self.auth = auth  # List of userids authorised to use the UI

    async def interaction_check(self, interaction):
        if self.auth and interaction.user.id not in self.auth:
            await interaction.response.send_message(
                embed=error_embed("You are not authorised to use this interface!"),
                ephemeral=True
            )
            return False
        else:
            return True

    async def cleanup(self):
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    @button(label="ADD", row=2)
    async def press_add(self, interaction, pressed):
        if self.guild_mode:
            await self.spawn_add_guilds(interaction)
        else:
            await self.spawn_add_users(interaction)

    @button(label="RM", row=2)
    async def press_rm(self, interaction, pressed):
        await interaction.response.defer()
        self._show_remove = not self._show_remove
        await self.show()

    @button(label="Switch", row=2)
    async def press_switch(self, interaction, pressed):
        await interaction.response.defer()
        if self.guild_mode:
            await self.set_user_mode()
        else:
            await self.set_guild_mode()

    @button(label="<", row=1)
    async def press_previous(self, interaction, pressed):
        await interaction.response.defer()
        self.page_no -= 1
        await self.show()

    @button(label="x", row=1)
    async def press_cancel(self, interaction, pressed):
        await interaction.response.defer()
        if self.message:
            try:
                await self.message.delete()
            except discord.HTTPException:
                pass
        await self.close()

    @button(label=">", row=1)
    async def press_next(self, interaction, pressed):
        await interaction.response.defer()
        self.page_no += 1
        await self.show()

    @select(cls=Select)
    async def select_remove(self, interaction, selected):
        self._show_remove = False
        if not selected.values:
            # Treat this as a cancel
            await interaction.response.defer()
        else:
            # Parse the values and pass straight to the appropriate do method
            # Aside from race states, should be impossible for this to raise a handled exception
            # (So no need to catch UserInputError)
            ids = map(int, selected.values)
            if self.guild_mode:
                await self.do_rm_guilds(interaction, ids)
            else:
                await self.do_rm_users(interaction, ids)

    @property
    def current_page(self):
        if not self.pages:
            raise ValueError("Cannot get the current page without pages!")
        self.page_no %= len(self.pages)
        return self.pages[self.page_no]

    async def spawn(self):
        """
        Run the UI.
        """
        if self.guild_mode:
            await self.set_guild_mode()
        else:
            await self.set_user_mode()

    async def update_data(self):
        """
        Updated stored data for the current mode.
        """
        if self.guild_mode:
            query = self.cog.data.guild_blacklist.select_where()
            query.leftjoin('guild_config', using=('guildid',))
            query.select('guildid', 'ownerid', 'reason', 'name', 'created_at')
        else:
            query = self.cog.data.user_blacklist.select_where()
            query.leftjoin('user_config', using=('userid',))
            query.select('userid', 'ownerid', 'reason', 'name', 'created_at')

        query.order_by('created_at', ORDER.DESC)
        self.data = await query
        return self.data

    async def set_guild_mode(self):
        """
        Change UI to guild blacklist mode.
        """
        self.guild_mode = True
        self.press_add.label = "Blacklist Guilds"
        self.press_rm.label = "Un-Blacklist Guilds"
        self.press_switch.label = "Show User List"
        self.select_remove.placeholder = "Select User id to remove"

        if not self.guild_mode:
            self._show_remove = False

        self.page_no = 0
        await self.refresh()

    async def set_user_mode(self):
        """
        Change UI to user blacklist mode.
        """
        self.press_add.label = "Blacklist Users"
        self.press_rm.label = "Un-Blacklist Users"
        self.press_switch.label = "Show Guild List"
        self.select_remove.placeholder = "Select Guild id to remove"

        if self.guild_mode:
            self._show_remove = False

        self.guild_mode = False
        self.page_no = 0
        await self.refresh()

    async def show(self):
        """
        Show the Blacklist UI, creating a new message if required.
        """
        if len(self.pages) > 1:
            self.set_layout(
                (self.press_previous, self.press_cancel, self.press_next),
                (self.press_add, self.press_rm, self.press_switch)
            )
        else:
            self.set_layout(
                (self.press_add, self.press_rm, self.press_switch, self.press_cancel)
            )
        page, slice = self.current_page
        if self._show_remove and self.data:
            key = 'guildid' if self.guild_mode else 'userid'
            self.select_remove._underlying.options = [
                SelectOption(label=str(row[key]), value=str(row[key]))
                for row in self.data[slice[0]:slice[1]]
            ]
            self.set_layout(*self._layout, (self.select_remove,))

        self.press_rm.disabled = (not self.data)

        if self.message is not None:
            self.message = await self.message.edit(**page.edit_args, view=self)
        else:
            self.message = await self.dest.send(**page.send_args, view=self)

    def format_user_rows(self, *rows):
        fields = []
        for row in rows:
            userid = row['userid']
            name = row['name']
            if user := self.bot.get_user(userid):
                name = f"({user.name})"
            elif oldname := row['name']:
                name = f"({oldname})"
            else:
                name = ''
            reason = row['reason']
            if len(reason) > 900:
                reason = reason[:900] + '...'
            table = '\n'.join(tabulate(
                ("User", f"<@{userid}> {name}"),
                ("Blacklisted by", f"<@{row['ownerid']}>"),
                ("Blacklisted at", f"<t:{int(row['created_at'].timestamp())}:F>"),
                ("Reason", reason)
            ))
            fields.append(EmbedField(name=str(userid), value=table, inline=False))
        return fields

    def format_guild_rows(self, *rows):
        fields = []
        for row in rows:
            guildid = row['guildid']

            name = row['name']
            if guild := self.bot.get_guild(guildid):
                name = f"({guild.name})"
            elif oldname := row['name']:
                name = f"({oldname})"
            else:
                name = ''

            reason = row['reason']
            table = '\n'.join(tabulate(
                ("Guild", f"`{guildid}` {name}"),
                ("Blacklisted by", f"<@{row['ownerid']}>"),
                ("Blacklisted at", f"<t:{int(row['created_at'].timestamp())}:F>"),
                ("Reason", reason)
            ))
            fields.append(EmbedField(name=str(guildid), value=table, inline=False))
        return fields

    async def make_pages(self):
        """
        Format the data in `self.data`, respecting the current mode.
        """
        if self.data is None:
            raise ValueError("Cannot make pages without initialising first!")

        embeds = []
        slices = []
        if self.guild_mode:
            title = "Guild Blacklist"
            no_desc = "There are no blacklisted guilds"
            formatter = self.format_guild_rows
        else:
            title = "User Blacklist"
            no_desc = "There are no blacklisted users"
            formatter = self.format_user_rows

        base_embed = discord.Embed(
            title=title,
            colour=discord.Colour.dark_orange()
        )
        if len(self.data) == 0:
            base_embed.description = no_desc
            embeds.append(base_embed)
            slices.append((0, 0))
        else:
            fields = formatter(*self.data)
            bl = self.block_len
            blocks = [(fields[i:i+bl], (i, i+bl)) for i in range(0, len(fields), bl)]
            n = len(blocks)
            for i, (block, slice) in enumerate(blocks):
                embed = base_embed.copy()
                embed._fields = [field._asdict() for field in block]
                if n > 1:
                    embed.title += f" (Page {i + 1}/{n})"
                embeds.append(embed)
                slices.append(slice)

        pages = [MessageArgs(embed=embed) for embed in embeds]
        self.pages = list(zip(pages, slices))
        return self.pages

    async def refresh(self):
        """
        Refresh the current UI message, if it exists.
        Takes into account the current mode and page number.
        """
        await self.update_data()
        await self.make_pages()
        await self.show()

    async def spawn_add_users(self, interaction: discord.Interaction,
                              userids: Optional[str] = None, reason: Optional[str] = None):
        """Spawn the add_users modal, optionally with fields pre-filled."""
        modal = BlacklistInput(title="Blacklist users")
        modal.targets.default = userids
        modal.reason.default = reason

        @modal.submit_callback()
        async def add_users_submit(interaction):
            await self.parse_add_users(interaction, modal.targets.value, modal.reason.value)

        await interaction.response.send_modal(modal)

    async def parse_add_users(self, interaction, useridstr: str, reason: str):
        """
        Parse provided userid string and reason, and pass onto do_add_users.
        If they are invalid, instead raise a UserInputError.
        """
        try:
            userids = parse_ids(useridstr)
        except UserInputError as ex:
            raise UserInputError("Could not extract a user id from `$item`", info=ex.info) from None

        await self.do_add_users(interaction, userids, reason)

    async def do_add_users(self, interaction: discord.Interaction, userids: list[int], reason: str):
        """
        Actually blacklist the given users and send an ack.
        To be run after initial argument validation.
        Updates the UI, or posts one if it doesn't exist.
        """
        remaining = set(userids).difference(self.cog.user_blacklist)
        if not remaining:
            raise UserInputError("All provided users are already blacklisted!")
        await self.cog.blacklist_users(interaction.user.id, list(remaining), reason)
        embed = discord.Embed(
            title="Users Blacklisted",
            description=(
                "You have blacklisted the following users:\n"
                + (', '.join(f"`{uid}`" for uid in remaining))
            ),
            colour=discord.Colour.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        if self.message is not None:
            await self.set_user_mode()

    async def do_rm_users(self, interaction: discord.Interaction, userids: list[int]):
        remaining = self.cog.user_blacklist.intersection(userids)
        if not remaining:
            raise UserInputError("None of these users are blacklisted")
        await self.cog.unblacklist_users(interaction.user.id, list(remaining))
        embed = discord.Embed(
            title="Users removed from Blacklist",
            description=(
                "You have removed the following users from the blacklist:\n"
                + (', '.join(f"`{uid}`" for uid in remaining))
            ),
            colour=discord.Colour.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        if self.message is not None:
            await self.set_user_mode()

    async def spawn_add_guilds(self, interaction: discord.Interaction,
                               guildids: Optional[str] = None, reason: Optional[str] = None):
        """Spawn the add_guilds modal, optionally with fields pre-filled."""
        modal = BlacklistInput(title="Blacklist guilds")
        modal.targets.default = guildids
        modal.reason.default = reason

        @modal.submit_callback()
        async def add_guilds_submit(interaction):
            await self.parse_add_guilds(interaction, modal.targets.value, modal.reason.value)

        await interaction.response.send_modal(modal)

    async def parse_add_guilds(self, interaction, guildidstr: str, reason: str):
        """
        Parse provided guildid string and reason, and pass onto do_add_guilds.
        If they are invalid, instead raise a UserInputError.
        """
        try:
            guildids = parse_ids(guildidstr)
        except UserInputError as ex:
            raise UserInputError("Could not extract a guild id from `$item`", info=ex.info) from None

        await self.do_add_guilds(interaction, guildids, reason)

    async def do_add_guilds(self, interaction: discord.Interaction, guildids: list[int], reason: str):
        """
        Actually blacklist the given guilds and send an ack.
        To be run after initial argument validation.
        Updates the UI, or posts one if it doesn't exist.
        """
        remaining = set(guildids).difference(self.cog.guild_blacklist)
        if not remaining:
            raise UserInputError("All provided guilds are already blacklisted!")
        await self.cog.blacklist_guilds(interaction.user.id, list(remaining), reason)
        embed = discord.Embed(
            title="Guilds Blacklisted",
            description=(
                "You have blacklisted the following guilds:\n"
                + (', '.join(f"`{gid}`" for gid in remaining))
            ),
            colour=discord.Colour.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        if self.message is not None:
            await self.set_guild_mode()

    async def do_rm_guilds(self, interaction: discord.Interaction, guildids: list[int]):
        remaining = self.cog.guild_blacklist.intersection(guildids)
        if not remaining:
            raise UserInputError("None of these guilds are blacklisted")
        await self.cog.unblacklist_guilds(interaction.user.id, list(remaining))
        embed = discord.Embed(
            title="Guilds removed from Blacklist",
            description=(
                "You have removed the following guilds from the blacklist:\n"
                + (', '.join(f"`{gid}`" for gid in remaining))
            ),
            colour=discord.Colour.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        if self.message is not None:
            await self.set_guild_mode()
