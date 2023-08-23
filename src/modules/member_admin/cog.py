from typing import Optional
import asyncio

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.sharding import THIS_SHARD
from utils.lib import utc_now

from wards import low_management_ward, equippable_role, high_management_ward

from . import babel, logger
from .data import MemberAdminData
from .settings import MemberAdminSettings
from .settingui import MemberAdminUI

_p = babel._p


class MemberAdminCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

        self.data = bot.db.load_registry(MemberAdminData())
        self.settings = MemberAdminSettings()

        # Set of (guildid, userid) that are currently being added
        self._adding_roles = set()

    # ----- Initialisation -----
    async def cog_load(self):
        await self.data.init()

        for setting in self.settings.guild_model_settings:
            self.bot.core.guild_config.register_model_setting(setting)

        # Load the config command
        configcog = self.bot.get_cog('ConfigCog')
        if configcog is None:
            logger.warning(
                "Loading MemberAdminCog before ConfigCog. "
                "Configuration command cannot be crossloaded."
            )
        else:
            self.crossload_group(self.configure_group, configcog.configure_group)

    # ----- Cog API -----
    async def absent_remove_role(self, guildid, userid, roleid):
        """
        Idempotently remove a role from a member who is no longer in the guild.
        """
        return await self.data.past_roles.delete_where(guildid=guildid, userid=userid, roleid=roleid)

    # ----- Event Handlers -----
    @LionCog.listener('on_member_join')
    @log_wrap(action="Greetings")
    async def admin_greet_member(self, member: discord.Member):
        lion = await self.bot.core.lions.fetch_member(member.guild.id, member.id, member=member)

        if lion.data.first_joined and lion.data.first_joined > member.joined_at:
            # Freshly created member
            # At least we haven't seen them join before

            # Give them the welcome message
            welcome = lion.lguild.config.get(self.settings.GreetingMessage.setting_id)
            if welcome.data and not member.bot:
                channel = lion.lguild.config.get(self.settings.GreetingChannel.setting_id).value
                if not channel:
                    # If channel is unset, use direct message
                    channel = member

                formatter = await welcome.generate_formatter(self.bot, member)
                formatted = await formatter(welcome.value)
                args = welcome.value_to_args(member.guild.id, formatted)

                try:
                    await channel.send(**args.send_args)
                except discord.HTTPException as e:
                    logger.info(
                        f"Welcome message failed for <uid:{member.id}> in <gid:{member.guild.id}>: "
                        f"{e.text}"
                    )
                else:
                    logger.debug(
                        f"Welcome message sent to <uid:{member.id}> in <gid:{member.guild.id}>."
                    )

            # Give them their autoroles
            setting = self.settings.BotAutoroles if member.bot else self.settings.Autoroles
            autoroles = await setting.get(member.guild.id)
            # Filter non-existent roles
            roles = [member.guild.get_role(role.id) for role in autoroles.value]
            roles = [role for role in roles if role]
            roles = [role for role in roles if role and role.is_assignable()]
            if roles:
                try:
                    self._adding_roles.add((member.guild.id, member.id))
                    await member.add_roles(*roles, reason="Adding Configured Autoroles")
                except discord.HTTPException as e:
                    logger.info(
                        f"Autoroles failed for <uid:{member.id}> in <gid:{member.guild.id}>: {e.text}"
                    )
                else:
                    logger.debug(
                        f"Gave autoroles to <uid:{member.id}> in <gid:{member.guild.id}>"
                    )
                finally:
                    self._adding_roles.discard((member.guild.id, member.id))
        else:
            # Returning member

            # Give them the returning message
            returning = lion.lguild.config.get(self.settings.ReturningMessage.setting_id)
            if not returning.data:
                returning = lion.lguild.config.get(self.settings.GreetingMessage.setting_id)
            if returning.data and not member.bot:
                channel = lion.lguild.config.get(self.settings.GreetingChannel.setting_id).value
                if not channel:
                    # If channel is unset, use direct message
                    channel = member

                last_seen = lion.data.last_left or lion.data._timestamp
                formatter = await returning.generate_formatter(
                        self.bot, member, last_seen=last_seen.timestamp()
                )
                formatted = await formatter(returning.value)
                args = returning.value_to_args(member.guild.id, formatted)

                try:
                    await channel.send(**args.send_args)
                except discord.HTTPException as e:
                    logger.info(
                        f"Returning message failed for <uid:{member.id}> in <gid:{member.guild.id}>: "
                        f"{e.text}"
                    )
                else:
                    logger.debug(
                        f"Returning message sent to <uid:{member.id}> in <gid:{member.guild.id}>."
                    )

            # Give them their old roles if we have them, else autoroles
            persistence = lion.lguild.config.get(self.settings.RolePersistence.setting_id).value
            if persistence and not member.bot:
                rows = await self.data.past_roles.select_where(guildid=member.guild.id, userid=member.id)
                roles = [member.guild.get_role(row['roleid']) for row in rows]
                roles = [role for role in roles if role and role.is_assignable()]
                if roles:
                    try:
                        self._adding_roles.add((member.guild.id, member.id))
                        await member.add_roles(*roles, reason="Restoring Member Roles")
                    except discord.HTTPException as e:
                        logger.info(
                            f"Role restore failed for <uid:{member.id}> in <gid:{member.guild.id}>: {e.text}"
                        )
                    else:
                        logger.debug(
                            f"Restored roles to <uid:{member.id}> in <gid:{member.guild.id}>"
                        )
                    finally:
                        self._adding_roles.discard((member.guild.id, member.id))
            else:
                setting = self.settings.BotAutoroles if member.bot else self.settings.Autoroles
                autoroles = await setting.get(member.guild.id)
                roles = [member.guild.get_role(role.id) for role in autoroles.value]
                roles = [role for role in roles if role and role.is_assignable()]
                if roles:
                    try:
                        self._adding_roles.add((member.guild.id, member.id))
                        await member.add_roles(*roles, reason="Adding Configured Autoroles")
                    except discord.HTTPException as e:
                        logger.info(
                            f"Autoroles failed for <uid:{member.id}> in <gid:{member.guild.id}>: {e.text}"
                        )
                    else:
                        logger.debug(
                            f"Gave autoroles to <uid:{member.id}> in <gid:{member.guild.id}>"
                        )
                    finally:
                        self._adding_roles.discard((member.guild.id, member.id))

    @LionCog.listener('on_member_remove')
    @log_wrap(action="Farewell")
    async def admin_member_farewell(self, member: discord.Member):
        # Ignore members that just joined
        if (member.guild.id, member.id) in self._adding_roles:
            return

        # Set lion last_left, creating the lion_member if needed
        lion = await self.bot.core.lions.fetch_member(member.guild.id, member.id)
        await lion.data.update(last_left=utc_now())

        # Save member roles
        async with self.bot.db.connection() as conn:
            self.bot.db.conn = conn
            async with conn.transaction():
                await self.data.past_roles.delete_where(
                    guildid=member.guild.id,
                    userid=member.id
                )
                # Insert current member roles
                if member.roles:
                    await self.data.past_roles.insert_many(
                        ('guildid', 'userid', 'roleid'),
                        *((member.guild.id, member.id, role.id) for role in member.roles)
                    )
        logger.debug(
            f"Stored persisting roles for member <uid:{member.id}> in <gid:{member.guild.id}>."
        )

    @LionCog.listener('on_guild_join')
    async def admin_init_guild(self, guild: discord.Guild):
        ...

    @LionCog.listener('on_guild_leave')
    @log_wrap(action='Destroy Guild')
    async def admin_destroy_guild(self, guild: discord.Guild):
        # Clear persisted roles for this guild
        await self.data.past_roles.delete_where(guildid=guild.id)
        logger.info(f"Cleared persisting roles for guild <gid:{guild.id}> because we left the guild.")

    @LionCog.listener('on_guildset_role_persistence')
    async def clear_stored_roles(self, guildid, data):
        if data is False:
            await self.data.past_roles.delete_where(guildid=guildid)
            logger.info(
                    f"Cleared persisting roles for guild <gid:{guildid}> because they disabled persistence."
            )

    # ----- Cog Commands -----
    @cmds.hybrid_command(
        name=_p('cmd:resetmember', "resetmember"),
        description=_p(
            'cmd:resetmember|desc',
            "Reset (server-associated) member data for the target member or user."
        )
    )
    @appcmds.rename(
        target=_p('cmd:resetmember|param:target', "member_to_reset"),
        saved_roles=_p('cmd:resetmember|param:saved_roles', "saved_roles"),
    )
    @appcmds.describe(
        target=_p(
            'cmd:resetmember|param:target|desc',
            "Choose the member (current or past) you want to reset."
        ),
        saved_roles=_p(
            'cmd:resetmember|param:saved_roles|desc',
            "Clear the saved roles for this member, so their past roles are not restored on rejoin."
        ),
    )
    @high_management_ward
    @appcmds.default_permissions(administrator=True)
    async def cmd_resetmember(self, ctx: LionContext,
                              target: discord.User,
                              saved_roles: Optional[bool] = False,
                              # voice_activity: Optional[bool] = False,
                              # text_activity: Optional[bool] = False,
                              # coins: Optional[bool] = False,
                              # everything: Optional[bool] = False,
                              ):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        if saved_roles:
            await self.data.past_roles.delete_where(
                guildid=ctx.guild.id,
                userid=target.id,
            )
            await ctx.reply(
                t(_p(
                    'cmd:resetmember|reset:saved_roles|success',
                    "The saved roles for {target} have been reset. "
                    "They will not regain their roles if they rejoin."
                )).format(target=target.mention)
            )
        else:
            await ctx.error_reply(
                t(_p(
                    'cmd:resetmember|error:nothing_to_do',
                    "No reset operation selected, nothing to do."
                )),
                ephemeral=True
            )


    # ----- Config Commands -----
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        """
        Substitute configure command group.
        """
        pass

    @configure_group.command(
        name=_p('cmd:configure_welcome', "welcome"),
        description=_p(
            'cmd:configure_welcome|desc',
            "Configure new member greetings and roles."
        )
    )
    @appcmds.rename(
        greeting_channel=MemberAdminSettings.GreetingChannel._display_name,
        role_persistence=MemberAdminSettings.RolePersistence._display_name,
        welcome_message=MemberAdminSettings.GreetingMessage._display_name,
        returning_message=MemberAdminSettings.ReturningMessage._display_name,
    )
    @appcmds.describe(
        greeting_channel=MemberAdminSettings.GreetingChannel._desc,
        role_persistence=MemberAdminSettings.RolePersistence._desc,
        welcome_message=MemberAdminSettings.GreetingMessage._desc,
        returning_message=MemberAdminSettings.ReturningMessage._desc,
    )
    @low_management_ward
    async def configure_welcome(self, ctx: LionContext,
                                greeting_channel: Optional[discord.TextChannel|discord.VoiceChannel] = None,
                                role_persistence: Optional[bool] = None,
                                welcome_message: Optional[discord.Attachment] = None,
                                returning_message: Optional[discord.Attachment] = None,
                                ):
        # Type checking guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True)

        modified = []

        if greeting_channel is not None:
            setting = self.settings.GreetingChannel
            await setting._check_value(ctx.guild.id, greeting_channel)
            instance = setting(ctx.guild.id, None)
            instance.value = greeting_channel
            modified.append(instance)

        if role_persistence is not None:
            setting = self.settings.RolePersistence
            instance = setting(ctx.guild.id, role_persistence)
            modified.append(instance)

        if welcome_message is not None:
            setting = self.settings.GreetingMessage
            content = await setting.download_attachment(welcome_message)
            instance = await setting.from_string(ctx.guild.id, content)
            modified.append(instance)

        if returning_message is not None:
            setting = self.settings.ReturningMessage
            content = await setting.download_attachment(returning_message)
            instance = await setting.from_string(ctx.guild.id, content)
            modified.append(instance)

        if modified:
            ack_lines = []
            update_args = {}
            for instance in modified:
                ack_lines.append(instance.update_message)
                update_args[instance._column] = instance._data

            # Data update
            await ctx.lguild.data.update(**update_args)
            for instance in modified:
                instance.dispatch_update()

            # Ack modified
            tick = self.bot.config.emojis.tick
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description='\n'.join(f"{tick} {line}" for line in ack_lines),
            )
            await ctx.reply(embed=embed)

        if ctx.channel.id not in MemberAdminUI._listening or not modified:
            ui = MemberAdminUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()
