import json
from typing import Optional, TYPE_CHECKING
import datetime as dt
from collections import defaultdict

import discord
from discord.ui.select import Select, SelectOption
from discord.ui.button import Button, ButtonStyle

from meta import LionBot
from meta.errors import UserInputError, SafeCancellation
from utils.ui import MessageArgs, HookedItem, AsComponents
from utils.lib import utc_now, jumpto, emojikey
from babel.translator import ctx_locale

from modules.economy.cog import Economy, EconomyData, TransactionType

from .data import RoleMenuData as Data
from .data import MenuType
from .menuoptions import RoleMenuConfig
from .roleoptions import RoleMenuRoleConfig
from .templates import templates
from . import logger, babel

if TYPE_CHECKING:
    from .cog import RoleMenuCog

_p = babel._p

MISSING = object()

DEFAULT_EMOJIS = "🍏 🍎 🍐 🍊 🍋 🍌 🍉 🍇 🫐 🍓 🍈 🍒 🍑 🥭 🍍 🥥 🥝 🍅 🍆 🥑 🫒 🥦 🥬 🫑 🥒".split()
DEFAULT_EMOJIS_PARTIALS = [discord.PartialEmoji(name=string) for string in DEFAULT_EMOJIS]


class MenuDropdown(HookedItem, Select):
    ...


class MenuButton(HookedItem, Button):
    ...


class RoleMenuRole:
    def __init__(self, bot: LionBot, data: Data.RoleMenuRole):
        self.bot = bot
        self.data = data
        self.config = RoleMenuRoleConfig(data.menuroleid, data)

    @property
    def custom_id(self):
        return f"rmrid:{self.data.menuroleid}"

    @property
    def as_option(self):
        return SelectOption(
            emoji=self.config.emoji.data or None,
            label=self.config.label.value,
            value=str(self.data.menuroleid),
            description=self.config.description.value,
        )

    @property
    def as_button(self):
        @MenuButton(
            emoji=self.config.emoji.data or None,
            label=self.config.label.value,
            custom_id=self.custom_id,
            style=ButtonStyle.grey
        )
        async def menu_button(press: discord.Interaction, pressed: Button):
            await press.response.defer(thinking=True, ephemeral=True)
            menu = await RoleMenu.fetch(self.bot, self.data.menuid)
            await menu.interactive_selection(press, self.data.menuroleid)

        return menu_button


class RoleMenu:
    # Cache of messages with listening menus attached
    attached_menus = defaultdict(dict)  # guildid -> messageid -> menuid

    # Registry of persistent Views for given menus
    menu_views = {}  # menuid -> View

    # Persistent cache of menus
    _menus = {}  # menuid -> Menu

    def __init__(self, bot: LionBot, data: Data.RoleMenu, rolemap):
        self.bot = bot
        self.cog: 'RoleMenuCog' = bot.get_cog('RoleMenuCog')
        self.data = data
        self.config = RoleMenuConfig(data.menuid, data)
        self.rolemap: dict[int, RoleMenuRole] = rolemap
        self.roles = list(rolemap.values())

        self._message = MISSING

    @property
    def _view(self) -> Optional[discord.ui.View]:
        """
        Active persistent View for this menu.
        """
        return self.menu_views.get(self.data.menuid, None)

    @property
    def message(self):
        if self._message is MISSING:
            raise ValueError("Cannot access menu message before fetch")
        else:
            return self._message

    @property
    def jump_link(self):
        if self.data.messageid:
            link = jumpto(
                self.data.guildid,
                self.data.channelid,
                self.data.messageid
            )
        else:
            link = None
        return link

    @property
    def managed(self):
        """
        Whether the menu message is owned by the bot.

        Returns True if the menu is unattached.
        """
        if self._message is MISSING:
            # Unknown, but send falsey value
            managed = None
        elif self._message is None:
            managed = True
        elif self._message.author is self._message.guild.me:
            managed = True
        else:
            managed = False
        return managed

    @classmethod
    async def fetch(cls, bot: LionBot, menuid: int):
        """
        Fetch the requested menu by id, applying registry cache where possible.
        """
        if (menu := cls._menus.get(menuid, None)) is None:
            cog = bot.get_cog('RoleMenuCog')
            data = await cog.data.RoleMenu.fetch(menuid)
            role_rows = await cog.data.RoleMenuRole.fetch_where(menuid=menuid).order_by('menuroleid')
            rolemap = {row.menuroleid: RoleMenuRole(bot, row) for row in role_rows}
            menu = cls(bot, data, rolemap)
            cls._menus[menuid] = menu
        return menu

    @classmethod
    async def create(cls, bot: LionBot, **data_args):
        cog = bot.get_cog('RoleMenuCog')
        data = await cog.data.RoleMenu.create(
            **data_args
        )
        menu = cls(bot, data, {})
        cls._menus[data.menuid] = menu
        await menu.attach()
        return menu

    async def fetch_message(self, refresh=False):
        """
        Fetch the message the menu is attached to.
        """
        if refresh or self._message is MISSING:
            if self.data.messageid is None:
                _message = None
            else:
                _message = None
                channelid = self.data.channelid
                channel = self.bot.get_channel(channelid)
                if channel is not None:
                    try:
                        _message = await channel.fetch_message(self.data.messageid)
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        pass
                    except discord.HTTPException:
                        # Something unexpected went wrong, leave the data alone for now
                        logger.exception("Something unexpected occurred while fetching the menu message")
                        raise
                if _message is None:
                    await self.data.update(messageid=None)
            self._message = _message
        return self._message

    def emoji_map(self):
        emoji_map = {}
        for mrole in self.roles:
            emoji = mrole.config.emoji.as_partial
            if emoji is not None:
                emoji_map[emoji] = mrole.data.menuroleid
        return emoji_map

    async def attach(self):
        """
        Start listening for menu selection events.
        """
        if self.data.messageid:
            self.attached_menus[self.data.guildid][self.data.messageid] = self.data.menuid
        if self.data.menutype is not MenuType.REACTION:
            view = await self.make_view()
            if view is not None:
                self.menu_views[self.data.menuid] = view
                self.bot.add_view(view)
        elif self.data.menutype is MenuType.REACTION:
            pass

    def detach(self):
        """
        Stop listening for menu selection events.
        """
        view = self.menu_views.pop(self.data.menuid, None)
        if view is not None:
            view.stop()
        if (mid := self.data.messageid) is not None:
            self.attached_menus[self.data.guildid].pop(mid, None)

    async def delete(self):
        self.detach()
        self._menus.pop(self.data.menuid, None)

        # Delete the menu, along with the message if it is self-managed.
        message = await self.fetch_message()
        if message and message.author is message.guild.me:
            try:
                await message.delete()
            except discord.HTTPException:
                # This should never really fail since we own the message
                # But it is possible the message was externally deleted and we never updated message cache
                # So just ignore quietly
                pass

        # Cancel any relevant expiry tasks (before we delete data which will delete the equip rows)
        expiring = await self.cog.data.RoleMenuHistory.fetch_expiring_where(menuid=self.data.menuid)
        if expiring:
            await self.cog.cancel_expiring_tasks(*(row.equipid for row in expiring))
        await self.data.delete()

    async def reload_roles(self):
        """
        Fetches and re-initialises the MenuRoles for this Menu.
        """
        roledata = self.bot.get_cog('RoleMenuCog').data.RoleMenuRole
        role_rows = await roledata.fetch_where(menuid=self.data.menuid).order_by('menuroleid')
        self.rolemap = {row.menuroleid: RoleMenuRole(self.bot, row) for row in role_rows}
        self.roles = list(self.rolemap.values())

    async def update_message(self):
        """
        Update the (managed) message the menu is attached to.

        Does nothing if there is not message or it is not bot-managed.
        """
        self.detach()
        message = await self.fetch_message()
        if message is not None and self.managed:
            args = await self.make_args()
            view = await self.make_view()
            try:
                await message.edit(**args.edit_args, view=view)
                await self.attach()
            except discord.NotFound:
                await self.data.update(messageid=None)
                self._message = None
            except discord.HTTPException as e:
                t = self.bot.translator.t
                error = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'rolemenu|menu_message|error|title',
                        'ROLE MENU DISPLAY ERROR'
                    )),
                    description=t(_p(
                        'rolemenu|menu_message|error|desc',
                        "A critical error occurred trying to display this role menu.\n"
                        "Error: `{error}`."
                    )).format(error=e.text)
                )
                try:
                    await message.edit(
                        embed=error
                    )
                except discord.HTTPException:
                    # There's really something wrong
                    # Nothing we can safely do.
                    pass
                pass

    async def update_reactons(self):
        """
        Attempt to update the reactions on a REACTION type menu.

        Does nothing if the menu is not REACTION type.
        Will raise `SafeCancellation` and stop if a reaction fails.
        """
        message = await self.fetch_message()
        if message is not None and self.data.menutype is MenuType.REACTION:
            # First remove any of my reactions that are no longer relevant
            required = {
                emojikey(mrole.config.emoji.as_partial) for mrole in self.roles if mrole.data.emoji
            }
            for reaction in message.reactions:
                if reaction.me and (emojikey(reaction.emoji) not in required):
                    try:
                        await message.remove_reaction(reaction.emoji, message.guild.me)
                    except discord.HTTPException:
                        pass
            
            # Then add any extra reactions that are missing
            existing_mine = {
                emojikey(reaction.emoji) for reaction in message.reactions if reaction.me
            }
            existing = {
                emojikey(reaction.emoji) for reaction in message.reactions
            }
            for mrole in self.roles:
                emoji = mrole.config.emoji.as_partial
                if emoji is not None and emojikey(emoji) not in existing_mine:
                    try:
                        await message.add_reaction(emoji)
                    except discord.HTTPException:
                        if emojikey(emoji) not in existing:
                            t = self.bot.translator.t
                            raise SafeCancellation(
                                t(_p(
                                    'rolemenu|update_reactions|error',
                                    "Could not add the {emoji} reaction, perhaps I do not "
                                    "have access to this emoji! Reactions will need to be added "
                                    "manually."
                                )).format(emoji=emoji)
                            )
                        else:
                            # We can't react with this emoji, but it does exist on the message
                            # Just ignore the error and continue
                            continue

    async def repost_to(self, destination):
        # Set the current message to be deleted if it is a managed message.
        # Don't delete until after we have successfully moved the menu though.
        if self.managed and (message := self.message):
            to_delete = message
        else:
            to_delete = None

        # Now try and post the message in the new channel
        args = await self.make_args()
        view = await self.make_view()
        new_message = await destination.send(**args.send_args, view=view or discord.utils.MISSING)

        # Stop listening to events on the current message (if it exists)
        self.detach()
        await self.data.update(channelid=destination.id, messageid=new_message.id)
        self._message = new_message
        await self.attach()

        if to_delete:
            # Attempt to delete the original message
            try:
                await to_delete.delete()
            except discord.HTTPException:
                pass

    async def _make_button_view(self):
        buttons = [mrole.as_button for mrole in self.roles]
        return AsComponents(*buttons, timeout=None)

    async def _make_dropdown_view(self):
        t = self.bot.translator.t

        placeholder = t(_p(
            'ui:rolemenu_dropdown|placeholder',
            "Select Roles"
        ))
        options = [mrole.as_option for mrole in self.roles]

        @MenuDropdown(
            custom_id=f"menuid:{self.data.menuid}",
            placeholder=placeholder,
            options=options,
            min_values=0, max_values=1
        )
        async def menu_dropdown(selection: discord.Interaction, selected: Select):
            if selected.values:
                await selection.response.defer(thinking=True, ephemeral=True)
                menuroleid = int(selected.values[0])
                menu = await self.fetch(self.bot, self.data.menuid)
                await menu.interactive_selection(selection, menuroleid)
            else:
                await selection.response.defer(thinking=False)

        return AsComponents(menu_dropdown, timeout=None)

    async def make_view(self) -> Optional[discord.ui.View]:
        """
        Create the appropriate discord.View for this menu.

        May be None if the menu has no roles or is a REACTION menu.
        """
        lguild = await self.bot.core.lions.fetch_guild(self.data.guildid)
        ctx_locale.set(lguild.locale)
        if not self.roles:
            view = None
        elif self.data.menutype is MenuType.REACTION:
            view = None
        elif self.data.menutype is MenuType.DROPDOWN:
            view = await self._make_dropdown_view()
        elif self.data.menutype is MenuType.BUTTON:
            view = await self._make_button_view()
        return view

    async def make_args(self) -> MessageArgs:
        """
        Generate the message arguments for this menu.
        """
        if (tid := self.data.templateid) is not None:
            # Apply template
            template = templates[tid]
            args = await template.render_menu(self)
        else:
            raw = self.data.rawmessage
            data = json.loads(raw)
            args = MessageArgs(
                content=data.get('content', ''),
                embed=discord.Embed.from_dict(data['embed']) if 'embed' in data else None
            )
        return args

    def unused_emojis(self, include_defaults=True):
        """
        Fetch the next emoji on the message that is not already assigned to a role.
        Checks custom emojis by PartialEmoji equality (i.e. by id).

        If no reaction exists, uses a default emoji.
        """
        if self.message:
            message_emojis = [reaction.emoji for reaction in self.message.reactions]
        else:
            message_emojis = []
        if self.data.menutype is MenuType.REACTION:
            valid_emojis = (*message_emojis, *DEFAULT_EMOJIS_PARTIALS)
        else:
            valid_emojis = message_emojis
        menu_emojis = {emojikey(mrole.config.emoji.as_partial) for mrole in self.roles}
        for emoji in valid_emojis:
            if emojikey(emoji) not in menu_emojis:
                yield str(emoji)

    async def _handle_selection(self, lion, member: discord.Member, menuroleid: int):
        mrole = self.rolemap.get(menuroleid, None)
        if mrole is None:
            raise ValueError(f"Attempt to process event for invalid menuroleid {menuroleid}, THIS SHOULD NOT HAPPEN.")

        guild = member.guild

        t = self.bot.translator.t

        role = guild.get_role(mrole.data.roleid)
        if role is None:
            # This role no longer exists, nothing we can do
            raise UserInputError(
                t(_p(
                    'rolemenu|error:role_gone',
                    "This role no longer exists!"
                ))
            )
        if role in member.roles:
            # Member already has the role, deselection case.
            if self.config.sticky.value:
                # Cannot deselect
                raise UserInputError(
                    t(_p(
                        'rolemenu|deselect|error:sticky',
                        "{role} is a sticky role, you cannot remove it with this menu!"
                    )).format(role=role.mention)
                )

            conn = await self.bot.db.get_connection()
            async with conn.transaction():
                # Remove the role
                try:
                    await member.remove_roles(role)
                except discord.Forbidden:
                    raise UserInputError(
                        t(_p(
                            'rolemenu|deselect|error:perms',
                            "I don't have enough permissions to remove this role from you!"
                        ))
                    )
                except discord.HTTPException:
                    raise UserInputError(
                        t(_p(
                            'rolemenu|deselect|error:discord',
                            "An unknown error occurred removing your role! Please try again later."
                        ))
                    )

                # Update history
                now = utc_now()
                history = await self.cog.data.RoleMenuHistory.table.update_where(
                    menuid=self.data.menuid,
                    roleid=role.id,
                    userid=member.id,
                    removed_at=None,
                ).set(removed_at=now)
                await self.cog.cancel_expiring_tasks(*(row.equipid for row in history))

                # Refund if required
                transactionids = [row['transactionid'] for row in history]
                if self.config.refunds.value and any(transactionids):
                    transactionids = [tid for tid in transactionids if tid]
                    economy: Economy = self.bot.get_cog('Economy')
                    refunded = await economy.data.Transaction.refund_transactions(*transactionids)
                    total_refund = sum(row.amount + row.bonus for row in refunded)
                else:
                    total_refund = 0

                # Ack the removal
                embed = discord.Embed(
                    colour=discord.Colour.brand_green(),
                    title=t(_p(
                        'rolemenu|deslect|success|title',
                        "Role removed"
                    ))
                )
                if total_refund:
                    embed.description = t(_p(
                        'rolemenu|deselect|success:refund|desc',
                        "You have removed {role}, and been refunded {coin} **{amount}**."
                    )).format(role=role.mention, coin=self.bot.config.emojis.coin, amount=total_refund)
                else:
                    embed.description = t(_p(
                        'rolemenu|deselect|success:norefund|desc',
                        "You have unequipped {role}."
                    )).format(role=role.mention)
                return embed
        else:
            # Member does not have the role, selection case.
            required = self.config.required_role.value
            if required is not None:
                # Check member has the required role
                if required not in member.roles:
                    raise UserInputError(
                        t(_p(
                            'rolemenu|select|error:required_role',
                            "You need to have the {role} role to use this!"
                        )).format(role=required.mention)
                    )

            obtainable = self.config.obtainable.value
            if obtainable is not None:
                # Check shared roles
                menu_roleids = {mrole.data.roleid for mrole in self.roles}
                member_roleids = {role.id for role in member.roles}
                common = len(menu_roleids.intersection(member_roleids))
                if common >= obtainable:
                    raise UserInputError(
                        t(_p(
                            'rolemenu|select|error:max_obtainable',
                            "You already have the maximum of {obtainable} roles from this menu!"
                        )).format(obtainable=obtainable)
                    )

            price = mrole.config.price.value
            if price:
                # Check member balance
                # TODO: More transaction safe (or rather check again after transaction)
                await lion.data.refresh()
                balance = lion.data.coins
                if balance < price:
                    raise UserInputError(
                        t(_p(
                            'rolemenu|select|error:insufficient_funds',
                            "The role {role} costs {coin}**{cost}**,"
                            "but you only have {coin}**{balance}**!"
                        )).format(
                            role=role.mention,
                            coin=self.bot.config.emojis.coin,
                            cost=price,
                            balance=balance,
                        )
                    )

            conn = await self.bot.db.get_connection()
            async with conn.transaction():
                try:
                    await member.add_roles(role)
                except discord.Forbidden:
                    raise UserInputError(
                        t(_p(
                            'rolemenu|select|error:perms',
                            "I don't have enough permissions to give you this role!"
                        ))
                    )
                except discord.HTTPException:
                    raise UserInputError(
                        t(_p(
                            'rolemenu|select|error:discord',
                            "An unknown error occurred while assigning your role! "
                            "Please try again later."
                        ))
                    )

                now = utc_now()

                # Create transaction if applicable
                if price:
                    economy: Economy = self.bot.get_cog('Economy')
                    tx = await economy.data.Transaction.execute_transaction(
                        transaction_type=TransactionType.OTHER,
                        guildid=guild.id, actorid=member.id,
                        from_account=member.id, to_account=None,
                        amount=price
                    )
                    tid = tx.transactionid
                else:
                    tid = None

                # Calculate expiry
                duration = mrole.config.duration.value
                if duration is not None:
                    expiry = now + dt.timedelta(seconds=duration)
                else:
                    expiry = None

                # Add to equip history
                equip = await self.cog.data.RoleMenuHistory.create(
                    menuid=self.data.menuid, roleid=role.id,
                    userid=member.id,
                    obtained_at=now,
                    transactionid=tid,
                    expires_at=expiry
                )
                await self.cog.schedule_expiring(equip)

            # Ack the selection
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'rolemenu|select|success|title',
                    "Role equipped"
                ))
            )
            if price > 0:
                embed.description = t(_p(
                    'rolemenu|select|success:purchase|desc',
                    "You have purchased the role {role} for {coin}**{amount}**"
                )).format(role=role.mention, coin=self.bot.config.emojis.coin, amount=price)
            else:
                embed.description = t(_p(
                    'rolemenu|select|success:nopurchase|desc',
                    "You have equipped the role {role}"
                )).format(role=role.mention)

            if expiry is not None:
                embed.description += '\n' + t(_p(
                    'rolemenu|select|expires_at',
                    "The role will expire at {timestamp}."
                )).format(
                    timestamp=discord.utils.format_dt(expiry)
                )
            return embed

    async def interactive_selection(self, interaction: discord.Interaction, menuroleid: int):
        """
        Handle a component interaction callback for this menu.

        Assumes the interaction has already been responded to (ephemerally).
        """
        member = interaction.user
        guild = interaction.guild
        if not isinstance(member, discord.Member):
            # Occasionally Discord drops the ball on user type. This manually fetches the guild member.
            member = await guild.fetch_member(member.id)

        # Localise to the member's locale
        lion = await self.bot.core.lions.fetch_member(guild.id, member.id, member=member)
        ctx_locale.set(lion.private_locale(interaction))
        result = await self._handle_selection(lion, member, menuroleid)
        await interaction.edit_original_response(embed=result)

    async def handle_reaction(self, reaction_payload: discord.RawReactionActionEvent):
        """
        Handle a raw reaction event on a message the menu is attached to.

        Ignores the event if it is not relevant.
        """
        guild = self.bot.get_guild(reaction_payload.guild_id)
        channel = self.bot.get_channel(reaction_payload.channel_id)
        if guild and channel:
            emoji_map = self.emoji_map()
            menuroleid = emoji_map.get(reaction_payload.emoji, None)
            if menuroleid is not None:
                member = reaction_payload.member
                if not member:
                    member = await guild.fetch_member(reaction_payload.user_id)
                if member.bot:
                    return
                lion = await self.bot.core.lions.fetch_member(guild.id, member.id, member=member)
                ctx_locale.set(lion.private_locale())
                try:
                    embed = await self._handle_selection(lion, member, menuroleid)
                except UserInputError as e:
                    embed = discord.Embed(
                        colour=discord.Colour.brand_red(),
                        description=e.msg
                    )
                t = self.bot.translator.t
                content = t(_p(
                    'rolemenu|content:reactions',
                    "[Click here]({jump_link}) to jump back."
                )).format(jump_link=jumpto(guild.id, channel.id, reaction_payload.message_id))
                try:
                    await member.send(content=content, embed=embed)
                except discord.HTTPException:
                    pass
