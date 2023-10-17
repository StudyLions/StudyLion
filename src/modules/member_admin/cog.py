from io import StringIO
from typing import Optional
import asyncio

import discord
from discord.ext import commands as cmds
from discord.enums import AppCommandOptionType
from discord import app_commands as appcmds
from psycopg import sql
from data.queries import NULLS, ORDER

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.sharding import THIS_SHARD
from meta.errors import UserInputError, SafeCancellation
from babel.translator import ctx_locale
from utils.lib import utc_now, parse_time_static, write_records
from utils.ui import ChoicedEnum, Transformed
from utils.ratelimits import Bucket, BucketFull, BucketOverFull
from data import RawExpr, NULL

from wards import low_management_ward, equippable_role, high_management_ward

from . import babel, logger
from .data import MemberAdminData
from .settings import MemberAdminSettings
from .settingui import MemberAdminUI

_p = babel._p


class DownloadableData(ChoicedEnum):
    VOICE_LEADERBOARD = _p('cmd:admin_data|param:data_type|choice:voice_leaderboard', "Voice Leaderboard")
    MSG_LEADERBOARD = _p('cmd:admin_data|param:data_type|choice:msg_leaderboard', "Message Leaderboard")
    XP_LEADERBOARD = _p('cmd:admin_data|param:data_type|choice:xp_leaderboard', "XP Leaderboard")
    ROLEMENU_EQUIP = _p('cmd:admin_data|param:data_type|choice:rolemenu_equip', "Rolemenu Roles Equipped")
    TRANSACTIONS = _p('cmd:admin_data|param:data_type|choice:transactions', "Economy Transactions (Incomplete)")
    BALANCES = _p('cmd:admin_data|param:data_type|choice:balances', "Economy Balances")
    VOICE_SESSIONS = _p('cmd:admin_data|param:data_type|choice:voice_sessions', "Voice Sessions")

    @property
    def choice_name(self):
        return self.value


    @property
    def choice_value(self):
        return self.name

class MemberAdminCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

        self.data = bot.db.load_registry(MemberAdminData())
        self.settings = MemberAdminSettings()

        # Set of (guildid, userid) that are currently being added
        self._adding_roles = set()

        # Map of guildid -> Bucket
        self._data_request_buckets: dict[int, Bucket] = {}

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
            self.crossload_group(self.configure_group, configcog.config_group)
            self.crossload_group(self.admin_group, configcog.admin_group)

    # ----- Cog API -----
    async def absent_remove_role(self, guildid, userid, roleid):
        """
        Idempotently remove a role from a member who is no longer in the guild.
        """
        return await self.data.past_roles.delete_where(guildid=guildid, userid=userid, roleid=roleid)

    def data_bucket_req(self, guildid: int):
        bucket = self._data_request_buckets.get(guildid, None)
        if bucket is None:
            bucket = self._data_request_buckets[guildid] = Bucket(10, 10)
        bucket.request()

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

            t = self.bot.translator.t
            ctx_locale.set(lion.lguild.locale)
            lion.lguild.log_event(
                title=t(_p(
                    'eventlog|event:welcome|title',
                    "New Member Joined"
                )),
                name=t(_p(
                    'eventlog|event:welcome|desc',
                    "{member} joined the server for the first time.",
                )).format(
                    member=member.mention
                ),
                roles_given='\n'.join(role.mention for role in roles) if roles else None,
                balance=lion.data.coins,
            )
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

            t = self.bot.translator.t
            ctx_locale.set(lion.lguild.locale)
            lion.lguild.log_event(
                title=t(_p(
                    'eventlog|event:returning|title',
                    "Member Rejoined"
                )),
                name=t(_p(
                    'eventlog|event:returning|desc',
                    "{member} rejoined the server.",
                )).format(
                    member=member.mention
                ),
                balance=lion.data.coins,
                roles_given='\n'.join(role.mention for role in roles) if roles else None,
                fields={
                    t(_p(
                        'eventlog|event:returning|field:first_joined',
                        "First Joined"
                    )): (
                        discord.utils.format_dt(lion.data.first_joined) if lion.data.first_joined else 'Unknown',
                        True
                    ),
                    t(_p(
                        'eventlog|event:returning|field:last_seen',
                        "Last Seen"
                    )): (
                        discord.utils.format_dt(lion.data.last_left) if lion.data.last_left else 'Unknown',
                        True
                    ),
                },
            )

    @LionCog.listener('on_raw_member_remove')
    @log_wrap(action="Farewell")
    async def admin_member_farewell(self, payload: discord.RawMemberRemoveEvent):
        # Ignore members that just joined
        guildid = payload.guild_id
        userid = payload.user.id
        if (guildid, userid) in self._adding_roles:
            return

        # Set lion last_left, creating the lion_member if needed
        lion = await self.bot.core.lions.fetch_member(guildid, userid)
        await lion.data.update(last_left=utc_now())

        # Save member roles
        roles = None
        async with self.bot.db.connection() as conn:
            self.bot.db.conn = conn
            async with conn.transaction():
                await self.data.past_roles.delete_where(
                    guildid=guildid,
                    userid=userid
                )
                # Insert current member roles
                print(type(payload.user))
                if isinstance(payload.user, discord.Member) and payload.user.roles:
                    member = payload.user
                    roles = member.roles
                    await self.data.past_roles.insert_many(
                        ('guildid', 'userid', 'roleid'),
                        *((guildid, userid, role.id) for role in member.roles)
                    )
        logger.debug(
            f"Stored persisting roles for member <uid:{userid}> in <gid:{guildid}>."
        )

        t = self.bot.translator.t
        ctx_locale.set(lion.lguild.locale)
        lion.lguild.log_event(
            title=t(_p(
                'eventlog|event:left|title',
                "Member Left"
            )),
            name=t(_p(
                'eventlog|event:left|desc',
                "{member} left the server.",
            )).format(
                member=f"<@{userid}>"
            ),
            balance=lion.data.coins,
            fields={
                t(_p(
                    'eventlog|event:left|field:stored_roles',
                    "Stored Roles"
                )): (
                    '\n'.join(role.mention for role in roles) if roles is not None else 'None',
                    True
                ),
                t(_p(
                    'eventlog|event:left|field:first_joined',
                    "First Joined"
                )): (
                    discord.utils.format_dt(lion.data.first_joined) if lion.data.first_joined else 'Unknown',
                    True
                ),
            },
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
    async def clear_stored_roles(self, guildid, setting: MemberAdminSettings.RolePersistence):
        data = setting.data
        if data is False:
            await self.data.past_roles.delete_where(guildid=guildid)
            logger.info(
                    f"Cleared persisting roles for guild <gid:{guildid}> because they disabled persistence."
            )

    # ----- Cog Commands -----
    @LionCog.placeholder_group
    @cmds.hybrid_group('admin', with_app_command=False)
    async def admin_group(self, ctx: LionContext):
        """
        Substitute configure command group.
        """
        pass

    @admin_group.command(
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

    @admin_group.command(
        name=_p('cmd:admin_data', "data"),
        description=_p(
            'cmd:admin_data|desc',
            "Download various raw data for external analysis and backup."
        )
    )
    @appcmds.rename(
        data_type=_p('cmd:admin_data|param:data_type', "type"),
        target=_p('cmd:admin_data|param:target', "target"),
        start=_p('cmd:admin_data|param:start', "after"),
        end=_p('cmd:admin_data|param:end', "before"),
        limit=_p('cmd:admin_data|param:limit', "limit"),
    )
    @appcmds.describe(
        data_type=_p(
            'cmd:admin_data|param:data_type|desc',
            "Select the type of data you want to download"
        ),
        target=_p(
            'cmd:admin_data|param:target|desc',
            "Filter the data by selecting a user or role"
        ),
        start=_p(
            'cmd:admin_data|param:start|desc',
            "Retrieve records created after this date and time in server timezone (YYYY-MM-DD HH:MM)"
        ),
        end=_p(
            'cmd:admin_data|param:end|desc',
            "Retrieve records created before this date and time in server timezone (YYYY-MM-DD HH:MM)"
        ),
        limit=_p(
            'cmd:admin_data|param:limit|desc',
            "Maximum number of records to retrieve."
        )
    )
    @high_management_ward
    async def cmd_data(self, ctx: LionContext,
                       data_type: Transformed[DownloadableData, AppCommandOptionType.string],
                       target: Optional[discord.User | discord.Member | discord.Role] = None,
                       start: Optional[str] = None,
                       end: Optional[str] = None,
                       limit: appcmds.Range[int, 1, 100000] = 1000,
                       ):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        t = self.bot.translator.t

        # Parse arguments

        userids: Optional[list[int]] = None
        if target is None:
            # All guild members
            userids = None
        elif isinstance(target, discord.Role):
            # Members of the given role
            userids = [member.id for member in target.members]
        else:
            # target is a user or member
            userids = [target.id]

        if start:
            start_time = await parse_time_static(start, ctx.lguild.timezone)
        else:
            start_time = ctx.guild.created_at

        if end:
            end_time = await parse_time_static(end, ctx.lguild.timezone)
        else:
            end_time = utc_now()
            
        # Form query
        if data_type is DownloadableData.VOICE_LEADERBOARD:
            query = self.bot.core.data.Member.table.select_where()
            query.select(
                'guildid',
                'userid',
                total_time=RawExpr(
                    sql.SQL("study_time_between(guildid, userid, %s, %s)"),
                    (start_time, end_time)
                )
            )
            query.order_by('total_time', ORDER.DESC, NULLS.LAST)
        elif data_type is DownloadableData.MSG_LEADERBOARD:
            from tracking.text.data import TextTrackerData as Data

            query = Data.TextSessions.table.select_where()
            query.select(
                'guildid',
                'userid',
                total_messages="SUM(messages)"
            )
            query.where(
                Data.TextSessions.start_time >= start_time,
                Data.TextSessions.start_time < end_time,
            )
            query.group_by('guildid', 'userid')
            query.order_by('total_messages', ORDER.DESC, NULLS.LAST)
        elif data_type is DownloadableData.XP_LEADERBOARD:
            from modules.statistics.data import StatsData as Data

            query = Data.MemberExp.table.select_where()
            query.select(
                'guildid',
                'userid',
                total_xp="SUM(amount)"
            )
            query.where(
                Data.MemberExp.earned_at >= start_time,
                Data.MemberExp.earned_at < end_time,
            )
            query.group_by('guildid', 'userid')
            query.order_by('total_xp', ORDER.DESC, NULLS.LAST)
        elif data_type is DownloadableData.ROLEMENU_EQUIP:
            from modules.rolemenus.data import RoleMenuData as Data

            query = Data.RoleMenuHistory.table.select_where().leftjoin('role_menus', using=('menuid',))
            query.select(
                guildid=Data.RoleMenu.guildid,
                userid=Data.RoleMenuHistory.userid,
                menuid=Data.RoleMenu.menuid,
                menu_messageid=Data.RoleMenu.messageid,
                menu_name=Data.RoleMenu.name,
                equipid=Data.RoleMenuHistory.equipid,
                roleid=Data.RoleMenuHistory.roleid,
                obtained_at=Data.RoleMenuHistory.obtained_at,
                expires_at=Data.RoleMenuHistory.expires_at,
                removed_at=Data.RoleMenuHistory.removed_at,
                transactionid=Data.RoleMenuHistory.transactionid,
            )
            query.where(
                Data.RoleMenuHistory.obtained_at >= start_time,
                Data.RoleMenuHistory.obtained_at < end_time,
            )
            query.order_by(Data.RoleMenuHistory.obtained_at, ORDER.DESC)
        elif data_type is DownloadableData.TRANSACTIONS:
            raise SafeCancellation("Transaction data is not yet available")
        elif data_type is DownloadableData.BALANCES:
            raise SafeCancellation("Member balance data is not yet available")
        elif data_type is DownloadableData.VOICE_SESSIONS:
            raise SafeCancellation("Raw voice session data is not yet available")
        else:
            raise ValueError(f"Unknown data type requested {data_type}")

        query.where(guildid=ctx.guild.id)
        if userids:
            query.where(userid=userids)
        query.limit(limit)
        query.with_no_adapter()

        # Request bucket
        try:
            self.data_bucket_req(ctx.guild.id)
        except BucketOverFull:
            # Don't do anything, even respond to the interaction
            raise SafeCancellation()
        except BucketFull:
            raise SafeCancellation(t(_p(
                'cmd:admin_data|error:ratelimited',
                "Too many requests! Please wait a few minutes before using this command again."
            )))

        # Run query
        await ctx.interaction.response.defer(thinking=True)
        results = await query

        if results:
            with StringIO() as stream:
                write_records(results, stream)
                stream.seek(0)
                file = discord.File(stream, filename='data.csv')
                await ctx.reply(file=file)
        else:
            await ctx.error_reply(
                t(_p(
                    'cmd:admin_data|error:no_results',
                    "Your query had no results! Try relaxing your filters."
                ))
            )

    @cmd_data.autocomplete('start')
    @cmd_data.autocomplete('end')
    async def cmd_data_acmpl_time(self, interaction: discord.Interaction, partial: str):
        if not interaction.guild:
            return []

        lguild = await self.bot.core.lions.fetch_guild(interaction.guild.id)
        timezone = lguild.timezone

        t = self.bot.translator.t
        try:
            timestamp = await parse_time_static(partial, timezone)
            choice = appcmds.Choice(
                name=timestamp.strftime('%Y-%m-%d %H:%M'),
                value=partial
            )
        except UserInputError:
            choice = appcmds.Choice(
                name=t(_p(
                    'cmd:admin_data|acmpl:time|error:parse',
                    "Cannot parse \"{partial}\" as a time. Try the format YYYY-MM-DD HH:MM"
                )).format(partial=partial)[:100],
                value=partial
            )
        return [choice]

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
