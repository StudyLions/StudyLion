import asyncio
import logging
import traceback
import datetime
from collections import defaultdict
from typing import List, Mapping, Optional
from cachetools import LFUCache

import discord
from discord import PartialEmoji

from meta import client
from core import Lion
from data import Row
from utils.lib import utc_now
from settings import GuildSettings

from ..module import module
from .data import reaction_role_messages, reaction_role_reactions
from .settings import RoleMessageSettings, ReactionSettings
from .expiry import schedule_expiry, cancel_expiry


class ReactionRoleReaction:
    """
    Light data class representing a reaction role reaction.
    """
    __slots__ = ('reactionid', '_emoji', '_message', '_role')

    def __init__(self, reactionid, message=None, **kwargs):
        self.reactionid = reactionid
        self._message: ReactionRoleMessage = None
        self._role = None
        self._emoji = None

    @classmethod
    def create(cls, messageid, roleid, emoji: PartialEmoji, message=None, **kwargs) -> 'ReactionRoleReaction':
        """
        Create a new ReactionRoleReaction with the provided attributes.
        `emoji` sould be provided as a PartialEmoji.
        `kwargs` are passed transparently to the `insert` method.
        """
        row = reaction_role_reactions.create_row(
            messageid=messageid,
            roleid=roleid,
            emoji_name=emoji.name,
            emoji_id=emoji.id,
            emoji_animated=emoji.animated,
            **kwargs
        )
        return cls(row.reactionid, message=message)

    @property
    def emoji(self) -> PartialEmoji:
        if self._emoji is None:
            data = self.data
            self._emoji = PartialEmoji(
                name=data.emoji_name,
                animated=data.emoji_animated,
                id=data.emoji_id,
            )
        return self._emoji

    @property
    def data(self) -> Row:
        return reaction_role_reactions.fetch(self.reactionid)

    @property
    def settings(self) -> ReactionSettings:
        return ReactionSettings(self.reactionid)

    @property
    def reaction_message(self):
        if self._message is None:
            self._message = ReactionRoleMessage.fetch(self.data.messageid)
        return self._message

    @property
    def role(self):
        if self._role is None:
            guild = self.reaction_message.guild
            if guild:
                self._role = guild.get_role(self.data.roleid)
        return self._role


class ReactionRoleMessage:
    """
    Light data class representing a reaction role message.
    Primarily acts as an interface to the corresponding Settings.
    """
    __slots__ = ('messageid', '_message')

    # Full live messageid cache for this client. Should always be up to date.
    _messages: Mapping[int, 'ReactionRoleMessage'] = {}  # messageid -> associated Reaction message

    # Reaction cache for the live messages. Least frequently used, will be fetched on demand.
    _reactions: Mapping[int, List[ReactionRoleReaction]] = LFUCache(1000)  # messageid -> List of Reactions

    # User-keyed locks so we only handle one reaction per user at a time
    _locks: Mapping[int, asyncio.Lock] = defaultdict(asyncio.Lock)  # userid -> Lock

    def __init__(self, messageid):
        self.messageid = messageid
        self._message = None

    @classmethod
    def fetch(cls, messageid) -> 'ReactionRoleMessage':
        """
        Fetch the ReactionRoleMessage for the provided messageid.
        Returns None if the messageid is not registered.
        """
        # Since the cache is assumed to be always up to date, just pass to fetch-from-cache.
        return cls._messages.get(messageid, None)

    @classmethod
    def create(cls, messageid, guildid, channelid, **kwargs) -> 'ReactionRoleMessage':
        """
        Create a ReactionRoleMessage with the given `messageid`.
        Other `kwargs` are passed transparently to `insert`.
        """
        # Insert the data
        reaction_role_messages.create_row(
            messageid=messageid,
            guildid=guildid,
            channelid=channelid,
            **kwargs
        )

        # Create the ReactionRoleMessage
        rmsg = cls(messageid)

        # Add to the global cache
        cls._messages[messageid] = rmsg

        # Return the constructed ReactionRoleMessage
        return rmsg

    def delete(self):
        """
        Delete this ReactionRoleMessage.
        """
        # Remove message from cache
        self._messages.pop(self.messageid, None)

        # Remove reactions from cache
        reactionids = [reaction.reactionid for reaction in self.reactions]
        [self._reactions.pop(reactionid, None) for reactionid in reactionids]

        # Remove message from data
        reaction_role_messages.delete_where(messageid=self.messageid)

    @property
    def data(self) -> Row:
        """
        Data row associated with this Message.
        Passes directly to the RowTable cache.
        Should not generally be used directly, use the settings interface instead.
        """
        return reaction_role_messages.fetch(self.messageid)

    @property
    def settings(self):
        """
        RoleMessageSettings associated to this Message.
        """
        return RoleMessageSettings(self.messageid)

    def refresh(self):
        """
        Refresh the reaction cache for this message.
        Returns the generated `ReactionRoleReaction`s for convenience.
        """
        # Fetch reactions and pre-populate reaction cache
        rows = reaction_role_reactions.fetch_rows_where(messageid=self.messageid)
        reactions = [ReactionRoleReaction(row.reactionid) for row in rows]
        self._reactions[self.messageid] = reactions
        return reactions

    @property
    def reactions(self) -> List[ReactionRoleReaction]:
        """
        Returns the list of active reactions for this message, as `ReactionRoleReaction`s.
        Lazily fetches the reactions from data if they have not been loaded.
        """
        reactions = self._reactions.get(self.messageid, None)
        if reactions is None:
            reactions = self.refresh()
        return reactions

    @property
    def enabled(self) -> bool:
        """
        Whether this Message is enabled.
        Passes directly to data for efficiency.
        """
        return self.data.enabled

    @enabled.setter
    def enabled(self, value: bool):
        self.data.enabled = value

    # Discord properties
    @property
    def guild(self) -> discord.Guild:
        return client.get_guild(self.data.guildid)

    @property
    def channel(self) -> discord.TextChannel:
        return client.get_channel(self.data.channelid)

    async def fetch_message(self) -> discord.Message:
        if self._message:
            return self._message

        channel = self.channel
        if channel:
            try:
                self._message = await channel.fetch_message(self.messageid)
                return self._message
            except discord.NotFound:
                # The message no longer exists
                # TODO: Cache and data cleanup? Or allow moving after death?
                pass

    @property
    def message(self) -> Optional[discord.Message]:
        return self._message

    @property
    def message_link(self) -> str:
        """
        Jump link tho the reaction message.
        """
        return 'https://discord.com/channels/{}/{}/{}'.format(
            self.data.guildid,
            self.data.channelid,
            self.messageid
        )

    # Event handlers
    async def process_raw_reaction_add(self, payload):
        """
        Process a general reaction add payload.
        """
        event_log = GuildSettings(self.guild.id).event_log
        async with self._locks[payload.user_id]:
            reaction = next((reaction for reaction in self.reactions if reaction.emoji == payload.emoji), None)
            if reaction:
                # User pressed a live reaction. Process!
                member = payload.member
                lion = Lion.fetch(member.guild.id, member.id)
                role = reaction.role
                if reaction.role and (role not in member.roles):
                    # Required role check, make sure the user has the required role, if set.
                    required_role = self.settings.required_role.value
                    if required_role and required_role not in member.roles:
                        # Silently remove their reaction
                        try:
                            message = await self.fetch_message()
                            await message.remove_reaction(
                                payload.emoji,
                                member
                            )
                        except discord.HTTPException:
                            pass
                        return

                    # Maximum check, check whether the user already has too many roles from this message.
                    maximum = self.settings.maximum.value
                    if maximum is not None:
                        # Fetch the number of applicable roles the user has
                        roleids = set(reaction.data.roleid for reaction in self.reactions)
                        member_roleids = set(role.id for role in member.roles)
                        if len(roleids.intersection(member_roleids)) > maximum:
                            # Notify the user
                            embed = discord.Embed(
                                title="Maximum group roles reached!",
                                description=(
                                    "Couldn't give you **{}**, "
                                    "because you already have `{}` roles from this group!".format(
                                        role.name,
                                        maximum
                                    )
                                )
                            )
                            # Silently try to notify the user
                            try:
                                await member.send(embed=embed)
                            except discord.HTTPException:
                                pass
                            # Silently remove the reaction
                            try:
                                message = await self.fetch_message()
                                await message.remove_reaction(
                                    payload.emoji,
                                    member
                                )
                            except discord.HTTPException:
                                pass

                            return

                    # Economy hook, check whether the user can pay for the role.
                    price = reaction.settings.price.value
                    if price and price > lion.coins:
                        # They can't pay!
                        # Build the can't pay embed
                        embed = discord.Embed(
                            title="Insufficient funds!",
                            description="Sorry, **{}** costs `{}` coins, but you only have `{}`.".format(
                                role.name,
                                price,
                                lion.coins
                            ),
                            colour=discord.Colour.red()
                        ).set_footer(
                            icon_url=self.guild.icon_url,
                            text=self.guild.name
                        ).add_field(
                            name="Jump Back",
                            value="[Click here]({})".format(self.message_link)
                        )
                        # Try to send them the embed, ignore errors
                        try:
                            await member.send(
                                embed=embed
                            )
                        except discord.HTTPException:
                            pass

                        # Remove their reaction, ignore errors
                        try:
                            message = await self.fetch_message()
                            await message.remove_reaction(
                                payload.emoji,
                                member
                            )
                        except discord.HTTPException:
                            pass

                        return

                    # Add the role
                    try:
                        await member.add_roles(
                            role,
                            atomic=True,
                            reason="Adding reaction role."
                        )
                    except discord.Forbidden:
                        event_log.log(
                            "Insufficient permissions to give {} the [reaction role]({}) {}".format(
                                member.mention,
                                self.message_link,
                                role.mention,
                            ),
                            title="Failed to add reaction role",
                            colour=discord.Colour.red()
                        )
                    except discord.HTTPException:
                        event_log.log(
                            "Something went wrong while adding the [reaction role]({}) "
                            "{} to {}.".format(
                                self.message_link,
                                role.mention,
                                member.mention
                            ),
                            title="Failed to add reaction role",
                            colour=discord.Colour.red()
                        )
                        client.log(
                            "Unexpected HTTPException encountered while adding '{}' (rid:{}) to "
                            "user '{}' (uid:{}) in guild '{}' (gid:{}).\n{}".format(
                                role.name,
                                role.id,
                                member,
                                member.id,
                                member.guild.name,
                                member.guild.id,
                                traceback.format_exc()
                            ),
                            context="REACTION_ROLE_ADD",
                            level=logging.WARNING
                        )
                    else:
                        # Charge the user and notify them, if the price is set
                        if price:
                            lion.addCoins(-price)
                            # Notify the user of their purchase
                            embed = discord.Embed(
                                title="Purchase successful!",
                                description="You have purchased **{}** for `{}` coins!".format(
                                    role.name,
                                    price
                                ),
                                colour=discord.Colour.green()
                            ).set_footer(
                                icon_url=self.guild.icon_url,
                                text=self.guild.name
                            ).add_field(
                                name="Jump Back",
                                value="[Click Here]({})".format(self.message_link)
                            )
                            try:
                                await member.send(embed=embed)
                            except discord.HTTPException:
                                pass

                        # Schedule the expiry, if required
                        duration = reaction.settings.duration.value
                        if duration:
                            expiry = utc_now() + datetime.timedelta(seconds=duration)
                            schedule_expiry(self.guild.id, member.id, role.id, expiry, reaction.reactionid)
                        else:
                            expiry = None

                        # Log the role modification if required
                        if self.settings.log.value:
                            event_log.log(
                                "Added [reaction role]({}) {} "
                                "to {}{}.{}".format(
                                    self.message_link,
                                    role.mention,
                                    member.mention,
                                    " for `{}` coins.".format(price) if price else '',
                                    "\nThis role will expire at <t:{:.0f}>.".format(
                                        expiry.timestamp()
                                    ) if expiry else ''
                                ),
                                title="Reaction Role Added"
                            )

    async def process_raw_reaction_remove(self, payload):
        """
        Process a general reaction remove payload.
        """
        if self.settings.removable.value:
            event_log = GuildSettings(self.guild.id).event_log
            async with self._locks[payload.user_id]:
                reaction = next((reaction for reaction in self.reactions if reaction.emoji == payload.emoji), None)
                if reaction:
                    # User removed a live reaction. Process!
                    member = self.guild.get_member(payload.user_id)
                    role = reaction.role
                    if member and not member.bot and role and (role in member.roles):
                        # Check whether they have the required role, if set
                        required_role = self.settings.required_role.value
                        if required_role and required_role not in member.roles:
                            # Ignore the reaction removal
                            return

                        try:
                            await member.remove_roles(
                                role,
                                atomic=True,
                                reason="Removing reaction role."
                            )
                        except discord.Forbidden:
                            event_log.log(
                                "Insufficient permissions to remove "
                                "the [reaction role]({}) {} from {}".format(
                                    self.message_link,
                                    role.mention,
                                    member.mention,
                                ),
                                title="Failed to remove reaction role",
                                colour=discord.Colour.red()
                            )
                        except discord.HTTPException:
                            event_log.log(
                                "Something went wrong while removing the [reaction role]({}) "
                                "{} from {}.".format(
                                    self.message_link,
                                    role.mention,
                                    member.mention
                                ),
                                title="Failed to remove reaction role",
                                colour=discord.Colour.red()
                            )
                            client.log(
                                "Unexpected HTTPException encountered while removing '{}' (rid:{}) from "
                                "user '{}' (uid:{}) in guild '{}' (gid:{}).\n{}".format(
                                    role.name,
                                    role.id,
                                    member,
                                    member.id,
                                    member.guild.name,
                                    member.guild.id,
                                    traceback.format_exc()
                                ),
                                context="REACTION_ROLE_RM",
                                level=logging.WARNING
                            )
                        else:
                            # Economy hook, handle refund if required
                            price = reaction.settings.price.value
                            refund = self.settings.refunds.value
                            if price and refund:
                                # Give the user the refund
                                lion = Lion.fetch(self.guild.id, member.id)
                                lion.addCoins(price)

                                # Notify the user
                                embed = discord.Embed(
                                    title="Role sold",
                                    description=(
                                        "You sold the role **{}** for `{}` coins.".format(
                                            role.name,
                                            price
                                        )
                                    ),
                                    colour=discord.Colour.green()
                                ).set_footer(
                                    icon_url=self.guild.icon_url,
                                    text=self.guild.name
                                ).add_field(
                                    name="Jump Back",
                                    value="[Click Here]({})".format(self.message_link)
                                )
                                try:
                                    await member.send(embed=embed)
                                except discord.HTTPException:
                                    pass

                            # Log role removal if required
                            if self.settings.log.value:
                                event_log.log(
                                    "Removed [reaction role]({}) {} "
                                    "from {}.".format(
                                        self.message_link,
                                        role.mention,
                                        member.mention
                                    ),
                                    title="Reaction Role Removed"
                                )

                            # Cancel any existing expiry
                            cancel_expiry(self.guild.id, member.id, role.id)


# TODO: Make all the embeds a bit nicer, and maybe make a consistent interface for them
# TODO: Handle RawMessageDelete event
# TODO: Handle permission errors when fetching message in config

@client.add_after_event('raw_reaction_add')
async def reaction_role_add(client, payload):
    reaction_message = ReactionRoleMessage.fetch(payload.message_id)
    if not payload.member.bot and reaction_message and reaction_message.enabled:
        try:
            await reaction_message.process_raw_reaction_add(payload)
        except Exception:
            # Unknown exception, catch and log it.
            client.log(
                "Unhandled exception while handling reaction message payload: {}\n{}".format(
                    payload,
                    traceback.format_exc()
                ),
                context="REACTION_ROLE_ADD",
                level=logging.ERROR
            )


@client.add_after_event('raw_reaction_remove')
async def reaction_role_remove(client, payload):
    reaction_message = ReactionRoleMessage.fetch(payload.message_id)
    if reaction_message and reaction_message.enabled:
        try:
            await reaction_message.process_raw_reaction_remove(payload)
        except Exception:
            # Unknown exception, catch and log it.
            client.log(
                "Unhandled exception while handling reaction message payload: {}\n{}".format(
                    payload,
                    traceback.format_exc()
                ),
                context="REACTION_ROLE_RM",
                level=logging.ERROR
            )


@module.init_task
def load_reaction_roles(client):
    """
    Load the ReactionRoleMessages.
    """
    rows = reaction_role_messages.fetch_rows_where()
    ReactionRoleMessage._messages = {row.messageid: ReactionRoleMessage(row.messageid) for row in rows}
