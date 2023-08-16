from typing import Optional
import asyncio
import logging
from string import Template

import discord
from discord.ext import commands as cmds
import discord.app_commands as appcmds
from discord.app_commands.transformers import AppCommandOptionType

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.app import shard_talk, appname
from utils.ui import ChoicedEnum, Transformed
from utils.lib import tabulate

from data import RowModel, Registry, RegisterEnum
from data.columns import String, Column

from settings.data import ModelData
from settings.setting_types import EnumSetting, StringSetting
from settings.groups import SettingGroup

from wards import sys_admin_ward

from . import babel

_p = babel._p

logger = logging.getLogger(__name__)


class AppActivityType(ChoicedEnum):
    """
    Schema
    ------
    CREATE TYPE ActivityType AS ENUM(
        'PLAYING',
        'WATCHING',
        'LISTENING',
        'STREAMING'
    );
    """
    playing = ('PLAYING', 'Playing', discord.ActivityType.playing)
    watching = ('WATCHING', 'Watching', discord.ActivityType.watching)
    listening = ('LISTENING', 'Listening', discord.ActivityType.listening)
    streaming = ('STREAMING', 'Streaming', discord.ActivityType.streaming)

    @property
    def choice_name(self):
        return self.value[1]

    @property
    def choice_value(self):
        return self.value[1]


class AppStatus(ChoicedEnum):
    """
    Schema
    ------
    CREATE TYPE OnlineStatus AS ENUM(
        'ONLINE',
        'IDLE',
        'DND',
        'OFFLINE'
    );
    """
    online = ('ONLINE', 'Online', discord.Status.online)
    idle = ('IDLE', 'Idle', discord.Status.idle)
    dnd = ('DND', 'Do Not Disturb', discord.Status.dnd)
    offline = ('OFFLINE', 'Offline/Invisible', discord.Status.offline)

    @property
    def choice_name(self):
        return self.value[1]

    @property
    def choice_value(self):
        return self.value[1]


class PresenceData(Registry, name='presence'):
    class AppPresence(RowModel):
        """
        Schema
        ------
        CREATE TABLE bot_config_presence(
            appname TEXT PRIMARY KEY REFERENCES bot_config(appname) ON DELETE CASCADE,
            online_status OnlineStatus,
            activity_type ActivityType,
            activity_name Text
        );
        """
        _tablename_ = 'bot_config_presence'
        _cache_ = {}

        appname = String(primary=True)
        online_status: Column[AppStatus] = Column()
        activity_type: Column[AppActivityType] = Column()
        activity_name = String()

    AppActivityType = RegisterEnum(AppActivityType, name="ActivityType")
    AppStatus = RegisterEnum(AppStatus, name='OnlineStatus')


class PresenceSettings(SettingGroup):
    """
    Control the bot status and activity.
    """
    _title = "Presence Settings ({bot.core.mention_cache[presence]})"

    class PresenceStatus(ModelData, EnumSetting[str, AppStatus]):
        setting_id = 'presence_status'

        _display_name = _p('botset:presence_status', 'online_status')
        _desc = _p('botset:presence_status|desc', "Bot status indicator")
        _long_desc = _p(
            'botset:presence_status|long_desc',
            "Whether the bot account displays as online, idle, dnd, or offline."
        )
        _accepts = _p(
            'botset:presence_status|accepts',
            "Online/Idle/Dnd/Offline"
        )

        _model = PresenceData.AppPresence
        _column = PresenceData.AppPresence.online_status.name
        _create_row = True

        _enum = AppStatus
        _outputs = {
            AppStatus.online: _p('botset:presence_status|output:online', "**Online**"),
            AppStatus.idle: _p('botset:presence_status|output:idle', "**Idle**"),
            AppStatus.dnd: _p('botset:presence_status|output:dnd', "**Do Not Disturb**"),
            AppStatus.offline: _p('botset:presence_status|output:offline', "**Offline**"),
        }
        _input_formatted = {
            AppStatus.online: _p('botset:presence_status|input_format:online', "Online"),
            AppStatus.idle: _p('botset:presence_status|input_format:idle', "Idle"),
            AppStatus.dnd: _p('botset:presence_status|input_format:dnd', "DND"),
            AppStatus.offline: _p('botset:presence_status|input_format:offline', "Offline"),
        }
        _input_patterns = {
            AppStatus.online: _p('botset:presence_status|input_pattern:online', "on|online"),
            AppStatus.idle: _p('botset:presence_status|input_pattern:idle', "idle"),
            AppStatus.dnd: _p('botset:presence_status|input_pattern:dnd', "do not disturb|dnd"),
            AppStatus.offline: _p('botset:presence_status|input_pattern:offline', "off|offline|invisible"),
        }
        _default = AppStatus.online

    class PresenceType(ModelData, EnumSetting[str, AppActivityType]):
        setting_id = 'presence_type'

        _display_name = _p('botset:presence_type', 'activity_type')
        _desc = _p('botset:presence_type|desc', "Type of presence activity")
        _long_desc = _p(
            'botset:presence_type|long_desc',
            "Whether the bot activity is shown as 'Listening', 'Playing', or 'Watching'."
        )
        _accepts = _p(
            'botset:presence_type|accepts',
            "Listening/Playing/Watching/Streaming"
        )

        _model = PresenceData.AppPresence
        _column = PresenceData.AppPresence.activity_type.name
        _create_row = True

        _enum = AppActivityType
        _outputs = {
            AppActivityType.watching: _p('botset:presence_type|output:watching', "**Watching**"),
            AppActivityType.listening: _p('botset:presence_type|output:listening', "**Listening**"),
            AppActivityType.playing: _p('botset:presence_type|output:playing', "**Playing**"),
            AppActivityType.streaming: _p('botset:presence_type|output:streaming', "**Streaming**"),
        }
        _input_formats = {
            AppActivityType.watching: _p('botset:presence_type|input_format:watching', "Watching"),
            AppActivityType.listening: _p('botset:presence_type|input_format:listening', "Listening"),
            AppActivityType.playing: _p('botset:presence_type|input_format:playing', "Playing"),
            AppActivityType.streaming: _p('botset:presence_type|input_format:streaming', "Streaming"),
        }
        _input_patterns = {
            AppActivityType.watching: _p('botset:presence_type|input_pattern:watching', "watching"),
            AppActivityType.listening: _p('botset:presence_type|input_pattern:listening', "listening"),
            AppActivityType.playing: _p('botset:presence_type|input_pattern:playing', "playing"),
            AppActivityType.streaming: _p('botset:presence_type|input_pattern:streaming', "streaming"),
        }
        _default = AppActivityType.watching

    class PresenceName(ModelData, StringSetting[str]):
        setting_id = 'presence_name'

        _display_name = _p('botset:presence_name', 'activity_name')
        _desc = _p("botset:presence_name|desc", "Name of the presence activity")
        _long_desc = _p("botset:presence_name|long_desc", "Presence activity name.")
        _accepts = _p('botset:presence_name|accepts', "The name of the activity to show.")

        _model = PresenceData.AppPresence
        _column = PresenceData.AppPresence.activity_name.name
        _create_row = True
        _default = "$in_vc students in $voice_channels study rooms!"


class PresenceCtrl(LionCog):
    depends = {'CoreCog', 'LeoSettings'}

    # Only update every 60 seconds at most
    ratelimit = 60

    # Update at least every 300 seconds regardless of events
    interval = 300

    # Possible substitution keys, and the events that listen to them
    keys = {
        '$in_vc': {'on_voice_state_update'},
        '$voice_channels': {'on_channel_add', 'on_channel_remove'},
        '$shard_members': {'on_member_join', 'on_member_leave'},
        '$shard_guilds': {'on_guild_join', 'on_guild_leave'}
    }

    default_format = "$in_vc students in $voice_channels study rooms!"
    default_activity = discord.ActivityType.watching
    default_status = discord.Status.online

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(PresenceData())
        self.settings = PresenceSettings()

        self.activity_type: discord.ActivityType = self.default_activity
        self.activity_format: str = self.default_format
        self.status: discord.Status = self.default_status

        self._listening: set = set()
        self._tick = asyncio.Event()
        self._loop_task: Optional[asyncio.Task] = None

        self.talk_reload_presence = shard_talk.register_route("reload presence")(self.reload_presence)

    async def cog_load(self):
        await self.data.init()
        if (leo_setting_cog := self.bot.get_cog('LeoSettings')) is not None:
            leo_setting_cog.bot_setting_groups.append(self.settings)

        await self.reload_presence()
        self.update_listeners()
        self._loop_task = asyncio.create_task(self.presence_loop())
        await self.tick()

    async def cog_unload(self):
        """
        De-register the event listeners, and cancel the presence update loop.
        """
        if (leo_setting_cog := self.bot.get_cog('LeoSettings')) is not None:
            leo_setting_cog.bot_setting_groups.remove(self.settings)

        if self._loop_task is not None and not self._loop_task.done():
            self._loop_task.cancel("Unloading")

        for event in self._listening:
            self.bot.remove_listener(self.tick, event)
            self._listening.discard(event)

    def update_listeners(self):
        # Build the list of events that should trigger status updates
        # Un-register any current listeners we don't need
        # Re-register any new listeners we need
        new_listeners = set()
        for key, events in self.keys.items():
            if key in self.activity_format:
                new_listeners.update(events)
        to_remove = self._listening.difference(new_listeners)
        to_add = new_listeners.difference(self._listening)

        for event in to_remove:
            self.bot.remove_listener(self.tick, event)
        for event in to_add:
            self.bot.add_listener(self.tick, event)

        self._listening = new_listeners

    async def reload_presence(self) -> None:
        # Reload the presence information from the appconfig table
        # TODO: When botconfig is done, these should load from settings, instead of directly from data
        self.data.AppPresence._cache_.pop(appname, None)
        self.activity_type = (await self.settings.PresenceType.get(appname)).value.value[2]
        self.activity_format = (await self.settings.PresenceName.get(appname)).value
        self.status = (await self.settings.PresenceStatus.get(appname)).value.value[2]

    async def set_presence(self, activity: Optional[discord.BaseActivity], status: Optional[discord.Status]):
        """
        Globally change the client presence and save the new presence information.
        """
        # TODO: Waiting on botconfig settings
        self.activity_type = activity.type if activity else None
        self.activity_name = activity.name if activity else None
        self.status = status or self.status
        await self.talk_reload_presence().broadcast(except_self=False)

    async def format_activity(self, form: str) -> str:
        """
        Format the given string.
        """
        subs = {
            'shard_members': sum(1 for _ in self.bot.get_all_members()),
            'shard_guilds': sum(1 for _ in self.bot.guilds)
        }
        if '$in_vc' in form:
            # TODO: Waiting on study module data
            subs['in_vc'] = sum(1 for m in self.bot.get_all_members() if m.voice and m.voice.channel)
        if '$voice_channels' in form:
            # TODO: Waiting on study module data
            subs['voice_channels'] = sum(1 for c in self.bot.get_all_channels() if c.type == discord.ChannelType.voice)

        return Template(form).safe_substitute(subs)

    async def tick(self, *args, **kwargs):
        """
        Request a presence update when next possible.
        Arbitrary arguments allow this to be used as a generic event listener.
        """
        self._tick.set()

    @log_wrap(action="Presence Update")
    async def _do_presence_update(self):
        try:
            activity_name = await self.format_activity(self.activity_format)
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=self.activity_type,
                    name=activity_name
                ),
                status=self.status
            )
            logger.debug(
                "Set status to '%s' with activity '%s' \"%s\"",
                str(self.status), str(self.activity_type), str(activity_name)
            )
        except Exception:
            logger.exception(
                "Unhandled exception occurred while updating client presence. Ignoring."
            )

    @log_wrap(stack=["Presence", "Loop"])
    async def presence_loop(self):
        """
        Request a client presence update when possible.
        """
        await self.bot.wait_until_ready()
        logger.debug("Launching presence update loop.")
        try:
            while True:
                # Wait for the wakeup event
                try:
                    await asyncio.wait_for(self._tick.wait(), timeout=self.interval)
                except asyncio.TimeoutError:
                    pass

                # Clear the wakeup event
                self._tick.clear()

                # Run the presence update
                await self._do_presence_update()

                # Wait for the delay
                await asyncio.sleep(self.ratelimit)
        except asyncio.CancelledError:
            logger.debug("Closing client presence update loop.")
        except Exception:
            logger.exception(
                "Unhandled exception occurred running client presence update loop. Closing loop."
            )

    @cmds.hybrid_command(
        name="presence",
        description="Globally set the bot status and activity."
    )
    @appcmds.describe(
        status="Online status (online | idle | dnd | offline)",
        type="Activity type (watching | listening | playing | streaming)",
        string="Activity name, supports substitutions $in_vc, $voice_channels, $shard_guilds, $shard_members"
    )
    @sys_admin_ward
    async def presence_cmd(
        self,
        ctx: LionContext,
        status: Optional[Transformed[AppStatus, AppCommandOptionType.string]] = None,
        type: Optional[Transformed[AppActivityType, AppCommandOptionType.string]] = None,
        string: Optional[str] = None
    ):
        """
        Modify the client online status and activity.

        Discord makes no guarantees as to which combination of activity type and arguments actually work.
        """
        colours = {
            discord.Status.online: discord.Colour.green(),
            discord.Status.idle: discord.Colour.orange(),
            discord.Status.dnd: discord.Colour.red(),
            discord.Status.offline: discord.Colour.light_grey()
        }

        if any((status, type, string)):
            # TODO: Batch?
            if status is not None:
                await self.settings.PresenceStatus(appname, status).write()
            if type is not None:
                await self.settings.PresenceType(appname, type).write()
            if string is not None:
                await self.settings.PresenceName(appname, string).write()

            await self.talk_reload_presence().broadcast(except_self=False)
            await self._do_presence_update()

        current_name = await self.format_activity(self.activity_format)
        table = '\n'.join(
            tabulate(
                ('Status', self.status.name),
                ('Activity', f"{self.activity_type.name} {current_name}"),
            )
        )
        await ctx.reply(
            embed=discord.Embed(
                title="Current Presence",
                description=table,
                colour=colours[self.status]
            )
        )
