from typing import Optional
import asyncio
import time
import datetime as dt
from collections import defaultdict

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from meta import LionBot, LionCog, LionContext, conf
from meta.errors import UserInputError
from meta.logger import log_wrap, logging_context
from meta.sharding import THIS_SHARD
from meta.app import appname
from meta.monitor import ComponentMonitor, ComponentStatus, StatusLevel
from utils.lib import utc_now, error_embed

from wards import low_management_ward, sys_admin_ward, low_management_iward
from . import babel, logger
from .data import TextTrackerData

from .session import TextSession
from .settings import TextTrackerSettings, TextTrackerGlobalSettings
from .ui import TextTrackerConfigUI


_p = babel._p


class TextTrackerCog(LionCog):
    """
    LionCog module controlling and configuring the text tracking system.
    """
    # Maximum number of completed sessions to batch before processing
    batchsize = conf.text_tracker.getint('batchsize')

    # Maximum time to processing for a completed session
    batchtime = conf.text_tracker.getint('batchtime')

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(TextTrackerData())
        self.settings = TextTrackerSettings()
        self.global_settings = TextTrackerGlobalSettings()
        self.monitor = ComponentMonitor('TextTracker', self._monitor)
        self.babel = babel

        self.sessionq = asyncio.Queue(maxsize=0)

        self.ready = asyncio.Event()
        self.errors = 0

        # Map of ongoing text sessions
        # guildid -> (userid -> TextSession)
        self.ongoing = defaultdict(dict)

        self._consumer_task = None

        self.untracked_channels = self.settings.UntrackedTextChannels._cache

    async def _monitor(self):
        state = (
            "<"
                "TextTracker"
                " ready={ready}"
                " queued={queued}"
                " errors={errors}"
                " running={running}"
                " consumer={consumer}"
                ">"
        )
        data = dict(
            ready=self.ready.is_set(),
            queued=self.sessionq.qsize(),
            errors=self.errors,
            running=sum(len(usessions) for usessions in self.ongoing.values()),
            consumer="'Running'" if (self._consumer_task and not self._consumer_task.done()) else "'Not Running'",
        )
        if not self.ready.is_set():
            level = StatusLevel.STARTING
            info = f"(STARTING) Not initialised. {state}"
        elif not self._consumer_task:
            level = StatusLevel.ERRORED
            info = f"(ERROR) Consumer task not running. {state}"
        elif self.errors > 1:
            level = StatusLevel.UNSURE
            info = f"(UNSURE) Errors occurred while consuming. {state}"
        else:
            level = StatusLevel.OKAY
            info = f"(OK) Message tracking operational. {state}"

        return ComponentStatus(level, info, info, data)

    async def cog_load(self):
        self.bot.system_monitor.add_component(self.monitor)
        await self.data.init()

        self.bot.core.guild_config.register_model_setting(self.settings.XPPerPeriod)
        self.bot.core.guild_config.register_model_setting(self.settings.WordXP)
        self.bot.core.guild_config.register_setting(self.settings.UntrackedTextChannels)

        self.global_xp_per_period = await self.global_settings.XPPerPeriod.get(appname)
        self.global_word_xp = await self.global_settings.WordXP.get(appname)

        leo_setting_cog = self.bot.get_cog('LeoSettings')
        leo_setting_cog.bot_setting_groups.append(self.global_settings)
        self.crossload_group(self.leo_configure_group, leo_setting_cog.leo_configure_group)

        # Update the untracked text channel cache
        await self.settings.UntrackedTextChannels.setup(self.bot)

        configcog = self.bot.get_cog('ConfigCog')
        if configcog is None:
            logger.critical(
                "Attempting to load the TextTrackerCog before ConfigCog! Failed to crossload configuration group."
            )
        else:
            self.crossload_group(self.configure_group, configcog.config_group)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        self.ready.clear()
        if self._consumer_task is not None:
            self._consumer_task.cancel()

    @log_wrap(stack=['Text Sessions', 'Finished'])
    async def session_handler(self, session: TextSession):
        """
        Callback used to process a completed session.

        Places the session into the completed queue and removes it from the session cache.
        """
        cached = self.ongoing[session.guildid].pop(session.userid, None)
        if cached is not session:
            raise ValueError("Sync error, completed session does not match cached session!")
        logger.debug(
            "Ending text session: {session!r}".format(
                session=session
            )
        )
        await self.bot.core.lions.fetch_member(session.guildid, session.userid)
        self.sessionq.put_nowait(session)

    @log_wrap(stack=['Text Sessions', 'Consumer'])
    async def _session_consumer(self):
        """
        Process completed sessions in batches of length `batchsize`.
        """
        # Number of sessions in the batch
        counter = 0
        batch = []
        last_time = time.monotonic()

        closing = False
        while not closing:
            try:
                session = await self.sessionq.get()
                batch.append(session)
                counter += 1
            except asyncio.CancelledError:
                # Attempt to process the rest of the batch, then close
                closing = True

            if counter >= self.batchsize or time.monotonic() - last_time > self.batchtime or closing:
                if batch:
                    try:
                        await self._process_batch(batch)
                    except Exception:
                        logger.exception(
                            "Unknown exception processing batch of text sessions! Discarding and continuing."
                        )
                        self.errors += 1
                    batch = []
                    counter = 0
                    last_time = time.monotonic()

    async def _process_batch(self, batch):
        """
        Process a batch of completed text sessions.

        Handles economy calculations.
        """
        if not batch:
            raise ValueError("Cannot process empty batch!")

        logger.info(
            f"Saving batch of {len(batch)} completed text sessions."
        )
        if self.bot.core is None or self.bot.core.lions is None:
            # Currently unloading, nothing we can do
            logger.warning(
                "Skipping text session batch due to unloaded modules."
            )
            return

        # Batch-fetch lguilds
        lguilds = await self.bot.core.lions.fetch_guilds(*{session.guildid for session in batch})
        await self.bot.core.lions.fetch_members(
            *((session.guildid, session.userid) for session in batch)
        )

        # Build data
        rows = []
        for sess in batch:
            # TODO: XP and coin calculations from settings
            # Note that XP is calculated here rather than directly through the DB
            # to support both XP and economy dynamic bonuses.

            globalxp = (
                sess.total_periods * self.global_xp_per_period.value
                + self.global_word_xp.value * sess.total_words / 100
            )

            lguild = lguilds[sess.guildid]
            periodxp = lguild.config.get('xp_per_period').value
            wordxp = lguild.config.get('word_xp').value
            xpcoins = lguild.config.get('coins_per_xp').value
            guildxp = (
                sess.total_periods * periodxp
                + wordxp * sess.total_words / 100
            )
            coins = xpcoins * guildxp / 100
            rows.append((
                sess.guildid, sess.userid,
                sess.start_time, sess.duration,
                sess.total_messages, sess.total_words, sess.total_periods,
                int(guildxp), int(globalxp),
                int(coins)
            ))

        # Submit to batch data handler
        # TODO: error handling
        await self.data.TextSessions.end_sessions(self.bot.db, *rows)
        rank_cog = self.bot.get_cog('RankCog')
        if rank_cog:
            await rank_cog.on_message_session_complete(
                *((rows[0], rows[1], rows[4], rows[7]) for rows in rows)
            )

    @LionCog.listener('on_ready')
    @log_wrap(action='Init Text Sessions')
    async def initialise(self):
        """
        Launch the session consumer.
        """
        self.ready.clear()
        if self._consumer_task and not self._consumer_task.cancelled():
            self._consumer_task.cancel()
        self._consumer_task = asyncio.create_task(self._session_consumer(), name='text-session-consumer')
        self.ready.set()
        logger.info("Launched text session consumer.")

    @LionCog.listener('on_message')
    @log_wrap(stack=['Text Sessions', 'Message Event'])
    async def text_message_handler(self, message: discord.Message):
        """
        Message event handler for the text session tracker.

        Process the handled message through a text session,
        creating it if required.
        """
        # Initial wards
        if message.author.bot:
            return
        if not message.guild:
            return
        # TODO: Blacklisted ward

        guildid = message.guild.id
        channel = message.channel
        try:
            channel.category_id
        except discord.ClientException:
            logger.debug(f"Ignoring message from channel with no parent: {message.channel}")
            return

        # Untracked channel ward
        untracked = self.untracked_channels.get(guildid, [])
        if channel.id in untracked or (channel.category_id and channel.category_id in untracked):
            return

        # Identify whether a session already exists for this member
        guild_sessions = self.ongoing[guildid]
        if (session := guild_sessions.get(message.author.id, None)) is None:
            with logging_context(context=f"mid: {message.id}"):
                session = TextSession.from_message(message)
                session.on_finish(self.session_handler)
                guild_sessions[message.author.id] = session
                logger.debug(
                    "Launched new text session: {session!r}".format(
                        session=session
                    )
                )
        session.process(message)

    # -------- Configuration Commands --------
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        # Placeholder group method, not used
        pass

    @configure_group.command(
        name=_p('cmd:configure_message_exp', "message_exp"),
        description=_p(
            'cmd:configure_message_exp|desc',
            "Configure Message Tracking & Experience"
        )
    )
    @appcmds.rename(
        xp_per_period=TextTrackerSettings.XPPerPeriod._display_name,
        word_xp=TextTrackerSettings.WordXP._display_name,
    )
    @appcmds.describe(
        xp_per_period=TextTrackerSettings.XPPerPeriod._desc,
        word_xp=TextTrackerSettings.WordXP._desc,
    )
    @low_management_ward
    async def configure_text_tracking_cmd(self, ctx: LionContext,
                                          xp_per_period: Optional[appcmds.Range[int, 0, 2**15]] = None,
                                          word_xp: Optional[appcmds.Range[int, 0, 2**15]] = None):
        """
        Guild configuration command to view and configure the text tracker settings.
        """
        # Standard type checking guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # Retrieve and initialise settings
        setting_xp_period = ctx.lguild.config.get('xp_per_period')
        setting_word_xp = ctx.lguild.config.get('word_xp')

        modified = []
        if xp_per_period is not None and setting_xp_period._data != xp_per_period:
            setting_xp_period.data = xp_per_period
            await setting_xp_period.write()
            modified.append(setting_xp_period)
        if word_xp is not None and setting_word_xp._data != word_xp:
            setting_word_xp.data = word_xp
            await setting_word_xp.write()
            modified.append(setting_word_xp)

        # Send update ack if required
        if modified:
            desc = '\n'.join(f"{conf.emojis.tick} {setting.update_message}" for setting in modified)
            await ctx.reply(
                embed=discord.Embed(
                    colour=discord.Colour.green(),
                    description=desc
                )
            )

        if ctx.channel.id not in TextTrackerConfigUI._listening or not modified:
            # Display setting group UI
            configui = TextTrackerConfigUI(self.bot, ctx.guild.id, ctx.channel.id)
            await configui.run(ctx.interaction)
            await configui.wait()

    # -------- Global Configuration Commands --------
    @LionCog.placeholder_group
    @cmds.hybrid_group('leo_configure', with_app_command=False)
    async def leo_configure_group(self, ctx: LionContext):
        # Placeholder group method, not used
        pass

    @leo_configure_group.command(
        name=_p('cmd:leo_configure_exp_rates', "experience_rates"),
        description=_p(
            'cmd:leo_configure_exp_rates|desc',
            "Global experience rate configuration"
        )
    )
    @appcmds.rename(
        xp_per_period=TextTrackerGlobalSettings.XPPerPeriod._display_name,
        word_xp=TextTrackerGlobalSettings.WordXP._display_name,
    )
    @appcmds.describe(
        xp_per_period=TextTrackerGlobalSettings.XPPerPeriod._desc,
        word_xp=TextTrackerGlobalSettings.WordXP._desc,
    )
    @sys_admin_ward
    async def leo_configure_text_tracking_cmd(self, ctx: LionContext,
                                              xp_per_period: Optional[appcmds.Range[int, 0, 2**15]] = None,
                                              word_xp: Optional[appcmds.Range[int, 0, 2**15]] = None):
        """
        Global configuration panel for text tracking global XP.
        """
        setting_xp_period = self.global_xp_per_period
        setting_word_xp = self.global_word_xp

        modified = []
        if word_xp is not None and word_xp != setting_word_xp._data:
            setting_word_xp.value = word_xp
            await setting_word_xp.write()
            modified.append(setting_word_xp)
        if xp_per_period is not None and xp_per_period != setting_xp_period._data:
            setting_xp_period.value = xp_per_period
            await setting_xp_period.write()
            modified.append(setting_xp_period)

        if modified:
            desc = '\n'.join(f"{conf.emojis.tick} {setting.update_message}" for setting in modified)
            await ctx.reply(
                embed=discord.Embed(
                    colour=discord.Colour.green(),
                    description=desc
                )
            )
        else:
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                title="Configure Global XP"
            )
            embed.add_field(**setting_xp_period.embed_field, inline=False)
            embed.add_field(**setting_word_xp.embed_field, inline=False)
            await ctx.reply(embed=embed)
