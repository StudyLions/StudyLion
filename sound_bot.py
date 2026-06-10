# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-22
# Purpose: SoundBot — a lightweight discord.Client that joins
#          voice channels and plays looped ambient audio,
#          driven by database configuration from the dashboard.
# ============================================================

import asyncio
import datetime
import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import discord
from discord import app_commands
import psycopg
from psycopg.rows import dict_row

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

try:
    import mutagen
except ImportError:
    mutagen = None

from audio_manager import AudioLibrary

logger = logging.getLogger(__name__)

SOUND_LABELS = {
    'rain': ('Rain', '\U0001f327\ufe0f'),
    'campfire': ('Campfire', '\U0001f525'),
    'ocean': ('Ocean Waves', '\U0001f30a'),
    'brown_noise': ('Brown Noise', '\U0001f7e4'),
    'white_noise': ('White Noise', '\u26aa'),
    'lofi': ('LoFi', '\U0001f3b5'),
}

DEFAULT_NICK_TEMPLATE = '{emoji} {sound}'

CONNECT_GRACE_S = 5
DISCONNECT_GRACE_S = 60
# --- AI-REPLACED (2026-05-19) ---
# Reason: 5-minute force-disconnect cooldown is too long. Most voice
# disconnects are transient (region change, voice server hiccup); users
# notice the bot is silent within seconds and have to manually toggle the
# dashboard to force a reconnect. 60s lets the bot auto-recover within
# a minute of a typical disconnect.
# --- Original code (commented out for rollback) ---
# FORCE_DC_COOLDOWN_S = 300
# --- AI-MODIFIED (2026-06-10) ---
# Purpose: total grace window for deciding whether a channel=None voice state
#   is a transient blip (discord.py auto-reconnect in progress) or a real
#   force-disconnect. Live logs showed reconnects to far media edges
#   (japan/hkg/sin) taking well over the old single 5s wait, so the handler
#   declared "force-disconnected" mid-reconnect and fought discord.py
#   (overlapping handshakes, "Timed out connecting", 60s cooldowns while
#   actually connected).
FORCE_DC_GRACE_TOTAL_S = 30
FORCE_DC_GRACE_STEP_S = 3
# --- END AI-MODIFIED ---
# --- End original code ---
FORCE_DC_COOLDOWN_S = 60
# --- END AI-REPLACED ---
POLL_INTERVAL_S = 15
STAGGER_CONNECT_S = 0.4


@dataclass
class GuildConfig:
    guildid: int
    bot_number: int
    sound_type: Optional[str]
    channelid: Optional[int]
    volume: int
    enabled: bool
    status: str
    error_msg: Optional[str]
    is_premium: bool
    nickname_template: Optional[str] = None
    voting_enabled: bool = False
    vote_cooldown_minutes: int = 30


class SoundBot(discord.Client):
    def __init__(
        self,
        bot_number: int,
        db_dsn: str,
        audio_lib: AudioLibrary,
        lofi_dir: str | None = None,
        **kwargs,
    ):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.voice_states = True
        super().__init__(intents=intents, **kwargs)

        self.bot_number = bot_number
        self.db_dsn = db_dsn
        self.audio_lib = audio_lib

        self._configs: dict[int, GuildConfig] = {}
        self._disconnect_tasks: dict[int, asyncio.Task] = {}
        self._connect_tasks: dict[int, asyncio.Task] = {}
        self._cooldowns: dict[int, float] = {}
        self._reconnect_attempts: dict[int, int] = {}
        # --- AI-MODIFIED (2026-06-10) ---
        # Purpose: single-flight guards. _grace_pending stops concurrent
        #   channel=None events from spawning parallel grace checks (logs showed
        #   "force-disconnected" firing 3x in 3s for one guild); _connect_locks
        #   stops overlapping _voice_connect runs racing each other and
        #   discord.py's own reconnect (logs showed two simultaneous voice
        #   handshakes followed by "Timed out connecting to voice").
        self._grace_pending: set[int] = set()
        self._connect_locks: dict[int, asyncio.Lock] = {}
        # --- END AI-MODIFIED ---
        self._db: Optional[psycopg.AsyncConnection] = None

        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: State for analytics, voting, and rentals
        self._usage_ids: dict[int, int] = {}
        self._votes: dict[int, dict[int, str]] = {}
        self._vote_message_ids: dict[int, int] = {}
        self._vote_last_switch: dict[int, float] = {}
        self._rental_configs: dict[int, GuildConfig] = {}
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: LoFi state — mutagen metadata, dedup, sub-moods, reliability, now-playing
        self._lofi_dir = lofi_dir
        self._lofi_meta: dict[str, tuple[str, str, float]] = {}
        self._lofi_pools: dict[str, list[str]] = {}
        self._lofi_playlists: dict[int, list[str]] = {}
        self._lofi_indices: dict[int, int] = {}
        self._lofi_gen: dict[int, int] = {}
        self._lofi_current: dict[int, tuple[str, str]] = {}
        self._np_message_ids: dict[int, int] = {}
        self._last_presence_update: float = 0
        self._lofi_error_counts: dict[int, int] = {}
        self._lofi_blacklists: dict[int, set[str]] = {}
        # --- AI-MODIFIED (2026-06-10) ---
        # Purpose: (size, mtime) cache so periodic rescans only re-parse files
        #   that actually changed, instead of running mutagen over the whole
        #   library every 5 minutes (see _scan_lofi).
        self._lofi_stats: dict[str, tuple[int, float]] = {}
        # --- END AI-MODIFIED ---
        if lofi_dir:
            self._scan_lofi(lofi_dir)
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-03) ---
        # Purpose: Unified sticky control panel state
        self._control_msg_ids: dict[int, int] = {}
        self._control_channel_ids: dict[int, int] = {}
        self._control_last_refresh: dict[int, float] = {}
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-05) ---
        # Purpose: Cache slow-changing poll data (schedules, timezones, blacklists)
        # and throttle heartbeat writes to reduce DB load
        self._cached_schedules: dict[int, list[dict]] = {}
        self._cached_tz_map: dict[int, str] = {}
        self._slow_cache_updated: float = 0
        self._heartbeat_updated: float = 0
        SLOW_CACHE_TTL_S = 60
        HEARTBEAT_INTERVAL_S = 90
        self._SLOW_CACHE_TTL_S = SLOW_CACHE_TTL_S
        self._HEARTBEAT_INTERVAL_S = HEARTBEAT_INTERVAL_S
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-04) ---
        # Purpose: Slash command tree and uptime tracking
        self.tree = app_commands.CommandTree(self)
        self._ready_at: float = 0
        self._register_commands()
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-05-19) ---
        # Purpose: Track which non-premium gids have already had the warning
        # logged this process, so the poll loop doesn't spam the log every
        # cycle for guilds that lost premium but kept their config row.
        self._logged_non_premium: set[int] = set()
        # --- END AI-MODIFIED ---

    # ------------------------------------------------------------------
    #  Slash commands
    # ------------------------------------------------------------------

    # --- AI-MODIFIED (2026-04-04) ---
    # Purpose: Register all slash commands on the CommandTree

    def _register_commands(self):
        """Register all slash commands. Called once from __init__."""
        bot = self

        async def _guard(interaction: discord.Interaction):
            """Common guard — returns (gid, cfg) or sends error and returns None."""
            gid = interaction.guild_id
            if not gid:
                await interaction.response.send_message(
                    "This command can only be used in a server.", ephemeral=True,
                )
                return None
            cfg = bot._configs.get(gid)
            if not cfg or not cfg.enabled:
                await interaction.response.send_message(
                    "\u274c Sound bot is not active in this server.", ephemeral=True,
                )
                return None
            return gid, cfg

        # ---- /nowplaying ----

        @bot.tree.command(name='nowplaying', description="Show what's currently playing")
        async def cmd_nowplaying(interaction: discord.Interaction):
            result = await _guard(interaction)
            if not result:
                return
            gid, cfg = result

            is_lofi = cfg.sound_type and cfg.sound_type.startswith('lofi')
            label, emoji = SOUND_LABELS.get(cfg.sound_type or '', (cfg.sound_type or 'None', '\U0001f3b5'))

            embed = discord.Embed(color=0x5865F2)
            if is_lofi:
                current = bot._lofi_current.get(gid)
                if current:
                    artist, title = current
                    embed.title = '\U0001f3b5 Now Playing'
                    embed.description = f'**{title}**\nby {artist}'
                else:
                    embed.title = f'{emoji} {label}'
                    embed.description = 'Waiting for playback\u2026'
            else:
                embed.title = f'{emoji} {label}'
                embed.description = 'Ambient sound is playing'

            vol_pct = cfg.volume or 50
            filled = round(vol_pct / 10)
            vol_bar = '\u2588' * filled + '\u2591' * (10 - filled)
            embed.add_field(name='Volume', value=f'\U0001f50a {vol_bar} {vol_pct}%', inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ---- /skip ----

        @bot.tree.command(name='skip', description='Skip the current LoFi track')
        @app_commands.default_permissions(manage_guild=True)
        async def cmd_skip(interaction: discord.Interaction):
            result = await _guard(interaction)
            if not result:
                return
            gid, cfg = result

            if not cfg.sound_type or not cfg.sound_type.startswith('lofi'):
                await interaction.response.send_message(
                    "Not in LoFi mode \u2014 nothing to skip.", ephemeral=True,
                )
                return

            vc = interaction.guild.voice_client
            if not vc or not vc.is_connected() or not vc.is_playing():
                await interaction.response.send_message("Nothing is playing.", ephemeral=True)
                return

            bot._stop_lofi(gid)
            vc.stop()
            await bot._play_lofi(gid, cfg)

            current = bot._lofi_current.get(gid)
            if current:
                embed = discord.Embed(
                    title='\u23ed\ufe0f Skipped!',
                    description=f'Now playing: **{current[1]}**\nby {current[0]}',
                    color=0x5865F2,
                )
            else:
                embed = discord.Embed(title='\u23ed\ufe0f Skipped!', color=0x5865F2)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            channel = interaction.channel
            if channel:
                await bot._post_control_panel(gid, channel, cfg)

        # ---- /volume ----

        @bot.tree.command(name='volume', description='Set the playback volume')
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.describe(level='Volume level')
        @app_commands.choices(level=[
            app_commands.Choice(name='\U0001f509 25%', value=25),
            app_commands.Choice(name='\U0001f509 50%', value=50),
            app_commands.Choice(name='\U0001f50a 75%', value=75),
            app_commands.Choice(name='\U0001f50a 100%', value=100),
        ])
        async def cmd_volume(interaction: discord.Interaction, level: int):
            result = await _guard(interaction)
            if not result:
                return
            gid, cfg = result

            cfg.volume = level
            try:
                await bot._db_exec(
                    "UPDATE ambient_sounds_config SET volume = %s, updated_at = NOW() "
                    "WHERE guildid = %s AND bot_number = %s",
                    (level, gid, bot.bot_number),
                )
            except Exception as exc:
                logger.error("Volume update failed: %s", exc)

            vc = interaction.guild.voice_client
            if vc and vc.is_connected() and vc.is_playing():
                await bot._voice_swap_source(gid, cfg)

            filled = round(level / 10)
            vol_bar = '\u2588' * filled + '\u2591' * (10 - filled)
            embed = discord.Embed(
                title='\U0001f50a Volume Updated',
                description=f'{vol_bar} **{level}%**',
                color=0x5865F2,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

            channel = interaction.channel
            if channel:
                await bot._post_control_panel(gid, channel, cfg)

        # ---- /sound (autocomplete) ----

        async def sound_autocomplete(
            interaction: discord.Interaction, current: str,
        ) -> list[app_commands.Choice[str]]:
            choices = []
            for sid, (name, em) in SOUND_LABELS.items():
                if current.lower() in name.lower() or current.lower() in sid.lower():
                    choices.append(app_commands.Choice(name=f'{em} {name}', value=sid))
            return choices[:25]

        @bot.tree.command(name='sound', description='Change the sound type')
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.describe(type='Sound to play')
        @app_commands.autocomplete(type=sound_autocomplete)
        async def cmd_sound(interaction: discord.Interaction, type: str):
            result = await _guard(interaction)
            if not result:
                return
            gid, cfg = result

            if type not in SOUND_LABELS:
                await interaction.response.send_message("Unknown sound type.", ephemeral=True)
                return

            if getattr(cfg, 'voting_enabled', False):
                if gid not in bot._votes:
                    bot._votes[gid] = {}
                bot._votes[gid][interaction.user.id] = type

                tally: dict[str, int] = {}
                for uid, sid in bot._votes[gid].items():
                    tally[sid] = tally.get(sid, 0) + 1

                current_type = cfg.sound_type
                current_votes = tally.get(current_type, 0)
                best_sound = max(tally, key=lambda s: tally[s])
                best_votes = tally[best_sound]

                cooldown_min = getattr(cfg, 'vote_cooldown_minutes', 30)
                last_switch = bot._vote_last_switch.get(gid, 0)
                cooldown_ok = (time.monotonic() - last_switch) >= cooldown_min * 60

                label, emoji = SOUND_LABELS.get(type, (type, '\U0001f3b5'))
                if best_sound != current_type and best_votes > current_votes and cooldown_ok:
                    cfg.sound_type = best_sound
                    try:
                        await bot._db_exec(
                            "UPDATE ambient_sounds_config SET sound_type = %s, updated_at = NOW() "
                            "WHERE guildid = %s AND bot_number = %s",
                            (best_sound, gid, bot.bot_number),
                        )
                    except Exception:
                        pass
                    vc = interaction.guild.voice_client
                    if vc and vc.is_connected():
                        await bot._voice_swap_source(gid, cfg)
                    bot._vote_last_switch[gid] = time.monotonic()
                    bot._votes[gid] = {}
                    bl, be = SOUND_LABELS.get(best_sound, (best_sound, '\U0001f3b5'))
                    embed = discord.Embed(
                        title=f'{be} Sound Changed by Vote!',
                        description=f'Now playing: **{bl}**',
                        color=0x5865F2,
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=False)
                else:
                    embed = discord.Embed(
                        title=f'{emoji} Vote Registered',
                        description=f'Voted for **{label}**',
                        color=0x5865F2,
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                cfg.sound_type = type
                try:
                    await bot._db_exec(
                        "UPDATE ambient_sounds_config SET sound_type = %s, updated_at = NOW() "
                        "WHERE guildid = %s AND bot_number = %s",
                        (type, gid, bot.bot_number),
                    )
                except Exception:
                    pass
                vc = interaction.guild.voice_client
                if vc and vc.is_connected():
                    await bot._voice_swap_source(gid, cfg)
                label, emoji = SOUND_LABELS.get(type, (type, '\U0001f3b5'))
                embed = discord.Embed(
                    title=f'{emoji} Sound Changed',
                    description=f'Now playing: **{label}**',
                    color=0x5865F2,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

            channel = interaction.channel
            if channel:
                await bot._post_control_panel(gid, channel, cfg)

        # ---- /panel ----

        @bot.tree.command(name='panel', description='Re-post the control panel')
        @app_commands.default_permissions(manage_guild=True)
        async def cmd_panel(interaction: discord.Interaction):
            result = await _guard(interaction)
            if not result:
                return
            gid, cfg = result

            await interaction.response.send_message('\u2705 Control panel posted!', ephemeral=True)
            channel = interaction.channel
            if channel:
                await bot._post_control_panel(gid, channel, cfg, force_new=True)

        # ---- /history ----

        @bot.tree.command(name='history', description='Show recently played LoFi tracks')
        async def cmd_history(interaction: discord.Interaction):
            result = await _guard(interaction)
            if not result:
                return
            gid, cfg = result

            if not cfg.sound_type or not cfg.sound_type.startswith('lofi'):
                await interaction.response.send_message(
                    "Not in LoFi mode right now.", ephemeral=True,
                )
                return

            try:
                rows = await bot._db_fetch(
                    "SELECT song_title, song_artist, played_at "
                    "FROM lofi_play_history "
                    "WHERE guildid = %s AND bot_number = %s "
                    "ORDER BY played_at DESC LIMIT 10",
                    (gid, bot.bot_number),
                )
            except Exception:
                rows = []

            if not rows:
                await interaction.response.send_message("No play history yet.", ephemeral=True)
                return

            lines = []
            for i, row in enumerate(rows, 1):
                title = row['song_title'] or 'Unknown'
                artist = row['song_artist'] or 'Unknown'
                played = row['played_at']
                if played:
                    ts = int(played.timestamp())
                    lines.append(f'`{i}.` **{title}** \u2014 {artist} \u00b7 <t:{ts}:R>')
                else:
                    lines.append(f'`{i}.` **{title}** \u2014 {artist}')

            embed = discord.Embed(
                title='\U0001f4dc Recently Played',
                description='\n'.join(lines),
                color=0x5865F2,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ---- /queue ----

        @bot.tree.command(name='queue', description='Show upcoming LoFi tracks')
        async def cmd_queue(interaction: discord.Interaction):
            result = await _guard(interaction)
            if not result:
                return
            gid, cfg = result

            if not cfg.sound_type or not cfg.sound_type.startswith('lofi'):
                await interaction.response.send_message(
                    "Not in LoFi mode right now.", ephemeral=True,
                )
                return

            playlist = bot._lofi_playlists.get(gid)
            idx = bot._lofi_indices.get(gid, 0)

            if not playlist:
                await interaction.response.send_message(
                    "No playlist loaded yet.", ephemeral=True,
                )
                return

            current = bot._lofi_current.get(gid)
            lines = []
            if current:
                lines.append(f'\u25b6\ufe0f **{current[1]}** \u2014 {current[0]}')
                lines.append('')

            upcoming = []
            blacklist = bot._lofi_blacklists.get(gid, set())
            check_idx = idx
            while len(upcoming) < 5 and check_idx < len(playlist):
                path = playlist[check_idx]
                if os.path.basename(path) not in blacklist:
                    meta = bot._lofi_meta.get(path)
                    if meta:
                        artist, title, _ = meta
                    else:
                        artist, title = bot._parse_filename(path)
                    upcoming.append((title, artist))
                check_idx += 1

            if upcoming:
                lines.append('**Up Next:**')
                for i, (title, artist) in enumerate(upcoming, 1):
                    lines.append(f'`{i}.` {title} \u2014 {artist}')
            else:
                lines.append('*Playlist will reshuffle soon*')

            remaining = max(0, len(playlist) - idx)
            embed = discord.Embed(
                title='\U0001f3b6 Queue',
                description='\n'.join(lines),
                color=0x5865F2,
            )
            embed.set_footer(text=f'{remaining} tracks remaining in shuffle')
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ---- /status ----

        @bot.tree.command(name='status', description='Show sound bot status')
        async def cmd_status(interaction: discord.Interaction):
            gid = interaction.guild_id
            if not gid:
                await interaction.response.send_message(
                    "Use this in a server.", ephemeral=True,
                )
                return

            cfg = bot._configs.get(gid)
            guild = interaction.guild
            vc = guild.voice_client if guild else None

            embed = discord.Embed(title='\U0001f4ca Sound Bot Status', color=0x5865F2)

            if not cfg or not cfg.enabled:
                embed.description = 'Not active in this server.'
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if vc and vc.is_connected() and vc.channel:
                channel = vc.channel
                humans = bot._humans(channel)
                embed.add_field(name='Channel', value=f'\U0001f50a {channel.mention}', inline=True)
                embed.add_field(name='Listeners', value=f'\U0001f465 {humans}', inline=True)
            else:
                embed.add_field(name='Channel', value='Not connected', inline=True)

            label, emoji = SOUND_LABELS.get(
                cfg.sound_type or '', (cfg.sound_type or 'None', '\U0001f3b5'),
            )
            is_lofi = cfg.sound_type and cfg.sound_type.startswith('lofi')
            embed.add_field(name='Sound', value=f'{emoji} {label}', inline=True)

            if is_lofi:
                current = bot._lofi_current.get(gid)
                if current:
                    embed.add_field(
                        name='Now Playing',
                        value=f'\U0001f3b5 **{current[1]}** \u2014 {current[0]}',
                        inline=False,
                    )

            vol_pct = cfg.volume or 50
            filled = round(vol_pct / 10)
            vol_bar = '\u2588' * filled + '\u2591' * (10 - filled)
            embed.add_field(name='Volume', value=f'{vol_bar} {vol_pct}%', inline=True)

            if bot._ready_at > 0:
                uptime_s = int(time.monotonic() - bot._ready_at)
                hours, remainder = divmod(uptime_s, 3600)
                minutes, _ = divmod(remainder, 60)
                embed.add_field(name='Uptime', value=f'{hours}h {minutes}m', inline=True)

            if vc and vc.is_playing():
                embed.add_field(name='Status', value='\u25b6\ufe0f Playing', inline=True)
            elif vc and vc.is_connected():
                embed.add_field(name='Status', value='\u23f8\ufe0f Idle', inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ---- /blacklist group ----

        blacklist_group = app_commands.Group(
            name='blacklist',
            description='Manage the LoFi song blacklist',
            default_permissions=discord.Permissions(manage_guild=True),
        )

        @blacklist_group.command(name='add', description='Block the currently playing song')
        async def bl_add(interaction: discord.Interaction):
            result = await _guard(interaction)
            if not result:
                return
            gid, cfg = result

            current = bot._lofi_current.get(gid)
            if not current:
                await interaction.response.send_message(
                    "No LoFi track is currently playing.", ephemeral=True,
                )
                return

            artist, title = current
            song_filename = None
            playlist = bot._lofi_playlists.get(gid)
            idx = bot._lofi_indices.get(gid, 0)
            if playlist and idx > 0:
                song_filename = os.path.basename(playlist[idx - 1])

            if not song_filename:
                for path, (a, t, _) in bot._lofi_meta.items():
                    if a == artist and t == title:
                        song_filename = os.path.basename(path)
                        break

            if not song_filename:
                await interaction.response.send_message(
                    "Could not identify the current song file.", ephemeral=True,
                )
                return

            bl = bot._lofi_blacklists.get(gid, set())
            if song_filename in bl:
                await interaction.response.send_message(
                    f'**{title}** is already blacklisted.', ephemeral=True,
                )
                return

            try:
                await bot._db_exec(
                    "INSERT INTO lofi_blacklist (guildid, song_filename, blacklisted_by) "
                    "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (gid, song_filename, interaction.user.id),
                )
            except Exception as exc:
                logger.error("Blacklist insert failed: %s", exc)
                await interaction.response.send_message(
                    "Failed to blacklist song.", ephemeral=True,
                )
                return

            bot._lofi_blacklists.setdefault(gid, set()).add(song_filename)

            vc = interaction.guild.voice_client
            if vc and vc.is_connected() and vc.is_playing():
                bot._stop_lofi(gid)
                vc.stop()
                await bot._play_lofi(gid, cfg)

            new_current = bot._lofi_current.get(gid)
            embed = discord.Embed(
                title='\U0001f6ab Song Blacklisted',
                description=(
                    f'**{title}** by {artist} will no longer play in this server.'
                ),
                color=0x5865F2,
            )
            if new_current:
                embed.add_field(
                    name='Now Playing',
                    value=f'\U0001f3b5 **{new_current[1]}** \u2014 {new_current[0]}',
                    inline=False,
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

            channel = interaction.channel
            if channel:
                await bot._post_control_panel(gid, channel, cfg)

        async def bl_remove_autocomplete(
            interaction: discord.Interaction, current: str,
        ) -> list[app_commands.Choice[str]]:
            gid = interaction.guild_id
            if not gid:
                return []
            bl = bot._lofi_blacklists.get(gid, set())
            choices = []
            for fname in sorted(bl):
                display = fname
                for path, (artist, title, _) in bot._lofi_meta.items():
                    if os.path.basename(path) == fname:
                        display = f'{title} \u2014 {artist}'
                        break
                if current.lower() in display.lower() or current.lower() in fname.lower():
                    choices.append(app_commands.Choice(name=display[:100], value=fname))
            return choices[:25]

        @blacklist_group.command(name='remove', description='Unblock a blacklisted song')
        @app_commands.describe(song='Song to remove from blacklist')
        @app_commands.autocomplete(song=bl_remove_autocomplete)
        async def bl_remove(interaction: discord.Interaction, song: str):
            result = await _guard(interaction)
            if not result:
                return
            gid, cfg = result

            bl = bot._lofi_blacklists.get(gid, set())
            if song not in bl:
                await interaction.response.send_message(
                    "That song is not blacklisted.", ephemeral=True,
                )
                return

            try:
                await bot._db_exec(
                    "DELETE FROM lofi_blacklist WHERE guildid = %s AND song_filename = %s",
                    (gid, song),
                )
            except Exception as exc:
                logger.error("Blacklist remove failed: %s", exc)
                await interaction.response.send_message(
                    "Failed to remove from blacklist.", ephemeral=True,
                )
                return

            bl.discard(song)

            display = song
            for path, (artist, title, _) in bot._lofi_meta.items():
                if os.path.basename(path) == song:
                    display = f'**{title}** by {artist}'
                    break

            embed = discord.Embed(
                title='\u2705 Song Unblocked',
                description=f'{display} can play again.',
                color=0x5865F2,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @blacklist_group.command(name='list', description='Show all blocked songs')
        async def bl_list(interaction: discord.Interaction):
            gid = interaction.guild_id
            if not gid:
                await interaction.response.send_message(
                    "Use this in a server.", ephemeral=True,
                )
                return

            bl = bot._lofi_blacklists.get(gid, set())
            if not bl:
                embed = discord.Embed(
                    title='\U0001f6ab Blacklist',
                    description='No songs are blacklisted in this server.',
                    color=0x5865F2,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            lines = []
            for i, fname in enumerate(sorted(bl), 1):
                display = fname
                for path, (artist, title, _) in bot._lofi_meta.items():
                    if os.path.basename(path) == fname:
                        display = f'**{title}** \u2014 {artist}'
                        break
                lines.append(f'`{i}.` {display}')

            embed = discord.Embed(
                title=f'\U0001f6ab Blacklist ({len(bl)} songs)',
                description='\n'.join(lines),
                color=0x5865F2,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        bot.tree.add_command(blacklist_group)

    async def setup_hook(self):
        """Sync slash commands with Discord after login."""
        await self.tree.sync()
        logger.info(
            "Bot #%d synced %d commands", self.bot_number, len(self.tree.get_commands()),
        )

    # --- END AI-MODIFIED ---

    # ------------------------------------------------------------------
    #  Database helpers
    # ------------------------------------------------------------------

    async def _get_db(self) -> psycopg.AsyncConnection:
        if self._db is None or self._db.closed:
            self._db = await psycopg.AsyncConnection.connect(
                self.db_dsn, autocommit=True,
            )
        return self._db

    async def _db_fetch(self, query: str, params=None) -> list[dict]:
        conn = await self._get_db()
        try:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params)
                return await cur.fetchall()
        except Exception:
            self._db = None
            raise

    async def _db_exec(self, query: str, params=None) -> None:
        conn = await self._get_db()
        try:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
        except Exception:
            self._db = None
            raise

    async def _update_status(
        self, guild_id: int, status: str, error_msg: str | None = None,
    ) -> None:
        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: Integrate usage analytics tracking with status transitions
        cfg = self._configs.get(guild_id)
        if status == 'active' and guild_id not in self._usage_ids:
            if cfg and cfg.sound_type and cfg.channelid:
                await self._start_usage(guild_id, cfg.sound_type, cfg.channelid)
        elif status != 'active' and guild_id in self._usage_ids:
            await self._end_usage(guild_id)
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-05-19) ---
        # Purpose: Keep the in-memory cfg in sync so the control panel can
        # show the latest status/error_msg immediately, instead of waiting
        # up to POLL_INTERVAL_S seconds for the next poll cycle to refresh it.
        if cfg is not None:
            cfg.status = status
            cfg.error_msg = error_msg
        # --- END AI-MODIFIED ---
        try:
            await self._db_exec(
                "UPDATE ambient_sounds_config "
                "SET status = %s, error_msg = %s, updated_at = NOW() "
                "WHERE guildid = %s AND bot_number = %s",
                (status, error_msg, guild_id, self.bot_number),
            )
        except Exception as exc:
            logger.error("Status update failed for guild %s: %s", guild_id, exc)

    # --- AI-MODIFIED (2026-03-23) ---
    # Purpose: Analytics — track play session start/stop and peak listeners
    async def _start_usage(self, guild_id: int, sound_type: str, channelid: int):
        try:
            rows = await self._db_fetch(
                "INSERT INTO ambient_sounds_usage (guildid, bot_number, sound_type, channelid) "
                "VALUES (%s, %s, %s, %s) RETURNING usage_id",
                (guild_id, self.bot_number, sound_type, channelid),
            )
            if rows:
                self._usage_ids[guild_id] = rows[0]['usage_id']
                logger.debug("Usage session %d started for guild %s", rows[0]['usage_id'], guild_id)
        except Exception as exc:
            logger.debug("Usage start failed for %s: %s", guild_id, exc)

    async def _end_usage(self, guild_id: int):
        usage_id = self._usage_ids.pop(guild_id, None)
        if usage_id is None:
            return
        try:
            await self._db_exec(
                "UPDATE ambient_sounds_usage SET ended_at = NOW() WHERE usage_id = %s",
                (usage_id,),
            )
            logger.debug("Usage session %d ended for guild %s", usage_id, guild_id)
        except Exception as exc:
            logger.debug("Usage end failed for %s: %s", guild_id, exc)

    async def _update_listeners_loop(self):
        """Periodically update peak_listeners on active usage rows."""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                for gid, usage_id in list(self._usage_ids.items()):
                    guild = self.get_guild(gid)
                    cfg = self._configs.get(gid)
                    if guild and cfg and cfg.channelid:
                        ch = guild.get_channel(cfg.channelid)
                        if ch:
                            count = self._humans(ch)
                            await self._db_exec(
                                "UPDATE ambient_sounds_usage "
                                "SET peak_listeners = GREATEST(peak_listeners, %s) "
                                "WHERE usage_id = %s",
                                (count, usage_id),
                            )
            except Exception as exc:
                logger.debug("Listener update error: %s", exc)
            await asyncio.sleep(30)
    # --- END AI-MODIFIED ---

    # ------------------------------------------------------------------
    #  Lifecycle events
    # ------------------------------------------------------------------

    async def on_ready(self):
        logger.info(
            "Bot #%d ready as %s — %d guilds",
            self.bot_number, self.user, len(self.guilds),
        )
        # --- AI-MODIFIED (2026-04-04) ---
        # Purpose: Track uptime for /status; removed _control_panel_loop
        #          (sticky re-post replaced by /panel slash command)
        self._ready_at = time.monotonic()
        # --- END AI-MODIFIED ---
        self.loop.create_task(self._poll_loop())
        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: Start background tasks for analytics and rental expiry
        self.loop.create_task(self._update_listeners_loop())
        self.loop.create_task(self._rental_expiry_loop())
        self.loop.create_task(self._lofi_reload_loop())
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-05-19) ---
        # Purpose: Refresh control panels every 60s so they reflect the live
        # voice-client state. Catches silent disconnects and stale Now Playing
        # data (panel was claiming "Now Playing: X" while the bot was actually
        # in force-disconnect cooldown).
        self.loop.create_task(self._panel_refresh_loop())
        # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: Auto-leave non-premium guilds on join; create config row for premium guilds
    async def on_guild_join(self, guild: discord.Guild):
        logger.info("Bot #%d joined %s (%s)", self.bot_number, guild.name, guild.id)
        try:
            rows = await self._db_fetch(
                "SELECT 1 FROM premium_guilds "
                "WHERE guildid = %s AND premium_until > NOW()",
                (guild.id,),
            )
            is_premium = bool(rows)
        except Exception as exc:
            logger.error("Premium check failed for %s: %s", guild.id, exc)
            return

        # --- AI-MODIFIED (2026-04-03) ---
        # Purpose: Temporarily disabled auto-leave for non-premium guilds to avoid
        # false positives (e.g. test DB missing premium rows for live servers)
        if not is_premium:
            logger.warning(
                "Bot #%d guild %s (%s) not premium — staying (auto-leave disabled)",
                self.bot_number, guild.name, guild.id,
            )
        # --- END AI-MODIFIED ---

        try:
            await self._db_exec(
                "INSERT INTO ambient_sounds_config "
                "(guildid, bot_number, status, enabled, updated_at) "
                "VALUES (%s, %s, 'idle', false, NOW()) "
                "ON CONFLICT (guildid, bot_number) DO UPDATE "
                "SET status = 'idle', updated_at = NOW()",
                (guild.id, self.bot_number),
            )
            logger.info(
                "Bot #%d created config row for premium guild %s (%s)",
                self.bot_number, guild.name, guild.id,
            )
        except Exception as exc:
            logger.error("Config row creation failed for guild %s: %s", guild.id, exc)
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-23) ---
    # Purpose: Handle sound voting button interactions from VC text chat widget
    # --- AI-MODIFIED (2026-04-03) ---
    # Purpose: Route control panel interactions alongside legacy vote/skip buttons
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get('custom_id', '')

        cp_prefix = f'cp{self.bot_number}:'
        if custom_id.startswith(cp_prefix):
            action = custom_id[len(cp_prefix):]
            if action == 'sound':
                values = interaction.data.get('values', [])
                if values:
                    await self._handle_sound_select(interaction, values[0])
            else:
                await self._handle_control_interaction(interaction, action)
            return

        if custom_id == f'lofi_skip:{self.bot_number}':
            await self._handle_skip(interaction)
            return
        prefix = f'sv{self.bot_number}:'
        if not custom_id.startswith(prefix):
            return
        sound_id = custom_id[len(prefix):]
        if sound_id not in SOUND_LABELS:
            return
        await self._handle_vote(interaction, sound_id)
    # --- END AI-MODIFIED ---

    async def _handle_vote(self, interaction: discord.Interaction, sound_id: str):
        gid = interaction.guild_id
        if not gid:
            return
        cfg = self._configs.get(gid)
        if not cfg or not cfg.enabled:
            await interaction.response.send_message("Voting is not active.", ephemeral=True)
            return

        if not getattr(cfg, 'voting_enabled', False):
            await interaction.response.send_message("Voting is not enabled.", ephemeral=True)
            return

        if gid not in self._votes:
            self._votes[gid] = {}
        self._votes[gid][interaction.user.id] = sound_id

        tally: dict[str, int] = {}
        for uid, sid in self._votes[gid].items():
            tally[sid] = tally.get(sid, 0) + 1

        current = cfg.sound_type
        current_votes = tally.get(current, 0)
        best_sound = max(tally, key=lambda s: tally[s])
        best_votes = tally[best_sound]

        cooldown_min = getattr(cfg, 'vote_cooldown_minutes', 30)
        last_switch = self._vote_last_switch.get(gid, 0)
        cooldown_ok = (time.monotonic() - last_switch) >= cooldown_min * 60

        switched = False
        if best_sound != current and best_votes > current_votes and cooldown_ok:
            cfg.sound_type = best_sound
            try:
                await self._db_exec(
                    "UPDATE ambient_sounds_config SET sound_type = %s, updated_at = NOW() "
                    "WHERE guildid = %s AND bot_number = %s",
                    (best_sound, gid, self.bot_number),
                )
            except Exception as exc:
                logger.error("Vote sound update failed: %s", exc)

            guild = interaction.guild
            if guild and guild.voice_client and guild.voice_client.is_connected():
                await self._voice_swap_source(gid, cfg)

            self._vote_last_switch[gid] = time.monotonic()
            self._votes[gid] = {}
            tally = {}
            switched = True

        await interaction.response.defer()

        msg_id = self._vote_message_ids.get(gid)
        if msg_id and interaction.channel:
            try:
                msg = await interaction.channel.fetch_message(msg_id)
                embed, view = self._build_vote_embed(gid, cfg, tally)
                await msg.edit(embed=embed, view=view)
            except Exception:
                pass

        if switched:
            label, emoji = SOUND_LABELS.get(best_sound, (best_sound, '\U0001f3b5'))
            try:
                await interaction.followup.send(
                    f"{emoji} Sound changed to **{label}** by vote!", ephemeral=False,
                )
            except Exception:
                pass

    def _build_vote_embed(self, gid: int, cfg: GuildConfig, tally: dict[str, int] | None = None):
        if tally is None:
            tally = {}
            for uid, sid in self._votes.get(gid, {}).items():
                tally[sid] = tally.get(sid, 0) + 1

        current_label, current_emoji = SOUND_LABELS.get(cfg.sound_type, ('Unknown', '\U0001f3b5'))
        embed = discord.Embed(
            title=f"{current_emoji} Now Playing: {current_label}",
            description="Vote for the next sound! The most-voted sound will play when it overtakes the current one.",
            color=0x5865F2,
        )

        lines = []
        for sid, (name, emoji) in SOUND_LABELS.items():
            count = tally.get(sid, 0)
            marker = " \u25c0 playing" if sid == cfg.sound_type else ""
            lines.append(f"{emoji} **{name}**: {count} vote{'s' if count != 1 else ''}{marker}")
        embed.add_field(name="Votes", value="\n".join(lines), inline=False)

        cooldown_min = getattr(cfg, 'vote_cooldown_minutes', 30)
        embed.set_footer(text=f"Cooldown: {cooldown_min}min between switches")

        view = discord.ui.View(timeout=None)
        for sid, (name, emoji) in SOUND_LABELS.items():
            btn = discord.ui.Button(
                label=name,
                emoji=emoji,
                custom_id=f'sv{self.bot_number}:{sid}',
                style=discord.ButtonStyle.primary if sid == cfg.sound_type else discord.ButtonStyle.secondary,
            )
            view.add_item(btn)
        return embed, view

    async def _post_vote_widget(self, gid: int, channel: discord.VoiceChannel, cfg: GuildConfig):
        """Post or update the voting widget in the VC text chat."""
        try:
            perms = channel.permissions_for(channel.guild.me)
            if not perms.send_messages:
                return

            embed, view = self._build_vote_embed(gid, cfg)

            old_msg_id = self._vote_message_ids.get(gid)
            if old_msg_id:
                try:
                    msg = await channel.fetch_message(old_msg_id)
                    await msg.edit(embed=embed, view=view)
                    return
                except Exception:
                    pass

            msg = await channel.send(embed=embed, view=view)
            self._vote_message_ids[gid] = msg.id
        except Exception as exc:
            logger.debug("Vote widget post failed for guild %s: %s", gid, exc)
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-03) ---
    # Purpose: Unified sticky control panel -- combines now-playing, voting, volume, and skip
    #          into a single persistent message that auto-refreshes to stay at bottom of chat

    VOLUME_STEPS = [25, 50, 75, 100]

    def _build_control_panel(self, gid: int, cfg: GuildConfig):
        """Build the unified control panel embed + view for a guild."""
        is_lofi = cfg.sound_type and cfg.sound_type.startswith('lofi')
        label, emoji = SOUND_LABELS.get(cfg.sound_type or '', (cfg.sound_type or 'None', '\U0001f3b5'))

        # --- AI-MODIFIED (2026-05-19) ---
        # Purpose: Render Now Playing from voice-client truth, not just the
        # _lofi_current dict. Without this, the panel could keep claiming
        # "Now Playing: X" while the bot was actually force-disconnected
        # (reported by shims: panel said "Cafe by Lukrembo", Skip button
        # correctly said "Nothing is playing").
        guild = self.get_guild(gid)
        vc = guild.voice_client if guild else None
        actually_playing = bool(vc and vc.is_connected() and vc.is_playing())
        # --- END AI-MODIFIED ---

        embed = discord.Embed(color=0x5865F2)
        embed.set_author(
            name=f'Sound Bot #{self.bot_number} \u2014 Control Panel',
            icon_url=self.user.display_avatar.url if self.user else None,
        )

        status_parts = []
        if is_lofi:
            current = self._lofi_current.get(gid)
            # --- AI-MODIFIED (2026-05-19) ---
            # Purpose: Only show Now Playing when the bot is actually playing.
            if current and actually_playing:
            # --- END AI-MODIFIED ---
                artist, title = current
                status_parts.append(f'\U0001f3b5 **Now Playing:** {title}')
                status_parts.append(f'\U0001f3a4 **Artist:** {artist}')
            else:
                status_parts.append(f'{emoji} **Sound:** {label}')
        else:
            status_parts.append(f'{emoji} **Sound:** {label}')

        vol_bar = ''
        vol_pct = cfg.volume or 50
        filled = round(vol_pct / 10)
        vol_bar = '\u2588' * filled + '\u2591' * (10 - filled)
        status_parts.append(f'\U0001f50a **Volume:** {vol_bar} {vol_pct}%')

        # --- AI-MODIFIED (2026-05-19) ---
        # Purpose: Surface error_msg on the panel when the bot isn't playing,
        # so users see why (e.g. "Force-disconnected \u2014 will rejoin after cooldown")
        # instead of having to check the dashboard.
        if not actually_playing and getattr(cfg, 'error_msg', None):
            status_parts.append(f'\u26a0\ufe0f {cfg.error_msg}')
        # --- END AI-MODIFIED ---

        embed.description = '\n'.join(status_parts)

        if getattr(cfg, 'voting_enabled', False):
            tally: dict[str, int] = {}
            for uid, sid in self._votes.get(gid, {}).items():
                tally[sid] = tally.get(sid, 0) + 1
            if tally:
                lines = []
                for sid, (name, em) in SOUND_LABELS.items():
                    count = tally.get(sid, 0)
                    if count > 0:
                        marker = ' \u25c0' if sid == cfg.sound_type else ''
                        lines.append(f'{em} {name}: **{count}**{marker}')
                if lines:
                    embed.add_field(name='Votes', value='\n'.join(lines), inline=False)

        embed.set_footer(text='Buttons stay active \u2022 Panel auto-refreshes')

        view = discord.ui.View(timeout=None)

        vol_down = discord.ui.Button(
            emoji='\U0001f509',
            custom_id=f'cp{self.bot_number}:vol_down',
            style=discord.ButtonStyle.secondary,
            disabled=vol_pct <= 25,
        )
        vol_up = discord.ui.Button(
            emoji='\U0001f50a',
            custom_id=f'cp{self.bot_number}:vol_up',
            style=discord.ButtonStyle.secondary,
            disabled=vol_pct >= 100,
        )
        view.add_item(vol_down)
        view.add_item(vol_up)

        if is_lofi:
            skip_btn = discord.ui.Button(
                label='Skip',
                emoji='\u23ed\ufe0f',
                custom_id=f'cp{self.bot_number}:skip',
                style=discord.ButtonStyle.primary,
            )
            view.add_item(skip_btn)

        # --- AI-MODIFIED (2026-04-04) ---
        # Purpose: Put sound select in same View to avoid a second message.
        #          Two messages caused orphaned "trail" selects every 10-min
        #          sticky refresh because only the first msg ID was tracked.
        sound_select = discord.ui.Select(
            placeholder=f'Change sound ({label})',
            custom_id=f'cp{self.bot_number}:sound',
            min_values=1,
            max_values=1,
            row=2,
            options=[
                discord.SelectOption(
                    label=name,
                    value=sid,
                    emoji=em,
                    default=(sid == cfg.sound_type),
                )
                for sid, (name, em) in SOUND_LABELS.items()
            ],
        )
        view.add_item(sound_select)

        return embed, [view]
        # --- END AI-MODIFIED ---

    async def _post_control_panel(self, gid: int, channel, cfg: GuildConfig, force_new: bool = False):
        """Post or update the sticky control panel in the VC text chat."""
        try:
            perms = channel.permissions_for(channel.guild.me)
            if not perms.send_messages:
                return

            # --- AI-MODIFIED (2026-05-19b) ---
            # Purpose: Debounce edits to the same panel message to avoid
            # Discord's per-message PATCH rate limit (~5 edits / 5 seconds).
            # With frequent force-disconnects + track changes + button clicks
            # + the periodic refresh loop, the same panel was being PATCHed
            # several times per second, triggering sustained 429 storms.
            # force_new=True (manual /panel) bypasses the debounce.
            if not force_new:
                last_refresh = self._control_last_refresh.get(gid, 0)
                if time.monotonic() - last_refresh < 8:
                    return
            # --- END AI-MODIFIED ---

            embed, views = self._build_control_panel(gid, cfg)
            old_id = self._control_msg_ids.get(gid)

            # --- AI-MODIFIED (2026-04-09) ---
            # Purpose: Only create new panels via /panel (force_new=True).
            # Auto-updates (song changes, button clicks) only edit existing panels.
            if old_id and not force_new:
                try:
                    msg = await channel.fetch_message(old_id)
                    await msg.edit(embed=embed, view=views[0])
                    self._control_last_refresh[gid] = time.monotonic()
                    return
                except discord.NotFound:
                    self._control_msg_ids.pop(gid, None)
                    self._control_channel_ids.pop(gid, None)
                    return
                except Exception:
                    return
            elif not force_new:
                return
            # --- END AI-MODIFIED ---

            if old_id:
                try:
                    old_msg = await channel.fetch_message(old_id)
                    await old_msg.delete()
                except Exception:
                    pass

            msgs = []
            msgs.append(await channel.send(embed=embed, view=views[0]))
            if len(views) > 1:
                msgs.append(await channel.send(view=views[1]))
            self._control_msg_ids[gid] = msgs[0].id
            self._control_channel_ids[gid] = channel.id
            self._control_last_refresh[gid] = time.monotonic()

            try:
                await self._db_exec(
                    "UPDATE ambient_sounds_config SET control_message_id = %s "
                    "WHERE guildid = %s AND bot_number = %s",
                    (str(msgs[0].id), gid, self.bot_number),
                )
            except Exception:
                pass

        except Exception as exc:
            logger.debug("Control panel post failed for guild %s: %s", gid, exc)

    # --- AI-REPLACED (2026-04-04) ---
    # Reason: Sticky re-post loop caused message trails every 10 minutes.
    #         Replaced by /panel slash command for on-demand re-posting.
    # --- Original code (commented out for rollback) ---
    # async def _ensure_sticky(self, gid: int):
    #     """Check if the control panel is still the last message; re-post if not."""
    #     channel_id = self._control_channel_ids.get(gid)
    #     msg_id = self._control_msg_ids.get(gid)
    #     if not channel_id or not msg_id:
    #         return
    #     cfg = self._configs.get(gid)
    #     if not cfg or not cfg.enabled:
    #         return
    #     guild = self.get_guild(gid)
    #     if not guild:
    #         return
    #     channel = guild.get_channel(channel_id)
    #     if not channel:
    #         return
    #     try:
    #         last_msgs = [m async for m in channel.history(limit=1)]
    #         if last_msgs and last_msgs[0].id != msg_id:
    #             await self._post_control_panel(gid, channel, cfg, force_new=True)
    #     except Exception:
    #         pass
    #
    # async def _control_panel_loop(self):
    #     """Background task: refresh sticky panels every 10 minutes so buttons never expire."""
    #     await self.wait_until_ready()
    #     while not self.is_closed():
    #         await asyncio.sleep(600)
    #         for gid in list(self._control_msg_ids):
    #             cfg = self._configs.get(gid)
    #             if not cfg or not cfg.enabled:
    #                 continue
    #             guild = self.get_guild(gid)
    #             if not guild:
    #                 continue
    #             channel_id = self._control_channel_ids.get(gid)
    #             if not channel_id:
    #                 continue
    #             channel = guild.get_channel(channel_id)
    #             if not channel:
    #                 continue
    #             try:
    #                 await self._ensure_sticky(gid)
    #             except Exception as exc:
    #                 logger.debug("Control panel refresh failed for %s: %s", gid, exc)
    # --- End original code ---
    # --- END AI-REPLACED ---

    async def _handle_control_interaction(self, interaction: discord.Interaction, action: str):
        """Handle all control panel button/select interactions."""
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            return
        cfg = self._configs.get(gid)
        if not cfg or not cfg.enabled:
            await interaction.response.send_message("Bot is not active.", ephemeral=True)
            return

        if action == 'vol_down':
            new_vol = max(25, (cfg.volume or 50) - 25)
            cfg.volume = new_vol
            try:
                await self._db_exec(
                    "UPDATE ambient_sounds_config SET volume = %s, updated_at = NOW() "
                    "WHERE guildid = %s AND bot_number = %s",
                    (new_vol, gid, self.bot_number),
                )
            except Exception as exc:
                logger.error("Volume update failed: %s", exc)
            vc = interaction.guild.voice_client
            if vc and vc.is_connected() and vc.is_playing():
                await self._voice_swap_source(gid, cfg)
            await interaction.response.defer()
            channel = interaction.channel
            if channel:
                await self._post_control_panel(gid, channel, cfg)

        elif action == 'vol_up':
            new_vol = min(100, (cfg.volume or 50) + 25)
            cfg.volume = new_vol
            try:
                await self._db_exec(
                    "UPDATE ambient_sounds_config SET volume = %s, updated_at = NOW() "
                    "WHERE guildid = %s AND bot_number = %s",
                    (new_vol, gid, self.bot_number),
                )
            except Exception as exc:
                logger.error("Volume update failed: %s", exc)
            vc = interaction.guild.voice_client
            if vc and vc.is_connected() and vc.is_playing():
                await self._voice_swap_source(gid, cfg)
            await interaction.response.defer()
            channel = interaction.channel
            if channel:
                await self._post_control_panel(gid, channel, cfg)

        elif action == 'skip':
            member = interaction.guild.get_member(interaction.user.id)
            if not member:
                await interaction.response.send_message("Could not verify permissions.", ephemeral=True)
                return
            if not (member.guild_permissions.manage_channels or member.guild_permissions.manage_guild):
                await interaction.response.send_message("Only moderators can skip songs.", ephemeral=True)
                return
            vc = interaction.guild.voice_client
            if not vc or not vc.is_connected() or not vc.is_playing():
                await interaction.response.send_message("Nothing is playing.", ephemeral=True)
                return
            self._stop_lofi(gid)
            vc.stop()
            await self._play_lofi(gid, cfg)
            current = self._lofi_current.get(gid)
            if current:
                await interaction.response.send_message(
                    f'\u23ed\ufe0f Skipped! Now: **{current[1]}** \u2014 {current[0]}',
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message('\u23ed\ufe0f Skipped!', ephemeral=True)
            channel = interaction.channel
            if channel:
                await self._post_control_panel(gid, channel, cfg)

        elif action.startswith('sound:'):
            pass

    async def _handle_sound_select(self, interaction: discord.Interaction, sound_id: str):
        """Handle sound picker select menu from control panel."""
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            return
        cfg = self._configs.get(gid)
        if not cfg or not cfg.enabled:
            await interaction.response.send_message("Bot is not active.", ephemeral=True)
            return

        if getattr(cfg, 'voting_enabled', False):
            if gid not in self._votes:
                self._votes[gid] = {}
            self._votes[gid][interaction.user.id] = sound_id

            tally: dict[str, int] = {}
            for uid, sid in self._votes[gid].items():
                tally[sid] = tally.get(sid, 0) + 1

            current = cfg.sound_type
            current_votes = tally.get(current, 0)
            best_sound = max(tally, key=lambda s: tally[s])
            best_votes = tally[best_sound]

            cooldown_min = getattr(cfg, 'vote_cooldown_minutes', 30)
            last_switch = self._vote_last_switch.get(gid, 0)
            cooldown_ok = (time.monotonic() - last_switch) >= cooldown_min * 60

            label, emoji = SOUND_LABELS.get(sound_id, (sound_id, '\U0001f3b5'))
            if best_sound != current and best_votes > current_votes and cooldown_ok:
                cfg.sound_type = best_sound
                try:
                    await self._db_exec(
                        "UPDATE ambient_sounds_config SET sound_type = %s, updated_at = NOW() "
                        "WHERE guildid = %s AND bot_number = %s",
                        (best_sound, gid, self.bot_number),
                    )
                except Exception as exc:
                    logger.error("Vote sound update failed: %s", exc)
                vc = interaction.guild.voice_client
                if vc and vc.is_connected():
                    await self._voice_swap_source(gid, cfg)
                self._vote_last_switch[gid] = time.monotonic()
                self._votes[gid] = {}
                bl, be = SOUND_LABELS.get(best_sound, (best_sound, '\U0001f3b5'))
                await interaction.response.send_message(
                    f'{be} Sound changed to **{bl}** by vote!', ephemeral=False,
                )
            else:
                await interaction.response.send_message(
                    f'Voted for {emoji} **{label}**!', ephemeral=True,
                )
        else:
            member = interaction.guild.get_member(interaction.user.id)
            if not member:
                await interaction.response.send_message("Could not verify permissions.", ephemeral=True)
                return
            if not (member.guild_permissions.manage_channels or member.guild_permissions.manage_guild):
                await interaction.response.send_message(
                    "Only moderators can change sounds. Ask an admin to enable voting for members!",
                    ephemeral=True,
                )
                return
            cfg.sound_type = sound_id
            try:
                await self._db_exec(
                    "UPDATE ambient_sounds_config SET sound_type = %s, updated_at = NOW() "
                    "WHERE guildid = %s AND bot_number = %s",
                    (sound_id, gid, self.bot_number),
                )
            except Exception as exc:
                logger.error("Sound change failed: %s", exc)
            vc = interaction.guild.voice_client
            if vc and vc.is_connected():
                await self._voice_swap_source(gid, cfg)
            label, emoji = SOUND_LABELS.get(sound_id, (sound_id, '\U0001f3b5'))
            await interaction.response.send_message(
                f'{emoji} Sound changed to **{label}**!', ephemeral=True,
            )

        channel = interaction.channel
        if channel:
            await self._post_control_panel(gid, channel, cfg)
    # --- END AI-MODIFIED ---

    async def on_guild_remove(self, guild: discord.Guild):
        logger.info("Bot #%d removed from %s (%s)", self.bot_number, guild.name, guild.id)
        self._configs.pop(guild.id, None)
        self._cancel(guild.id, self._disconnect_tasks)
        self._cancel(guild.id, self._connect_tasks)
        await self._update_status(guild.id, 'bot_not_in_guild')

    # ------------------------------------------------------------------
    #  Voice-state tracking
    # ------------------------------------------------------------------

    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: Bot stays in VC always; starts/stops PLAYING based on human presence
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            if member.id == self.user.id:
                await self._handle_self_voice_change(before, after)
            return

        guild_id = member.guild.id
        cfg = self._configs.get(guild_id)
        if not cfg or not cfg.enabled or not cfg.channelid or not cfg.sound_type:
            return

        vc = member.guild.voice_client
        joined = after.channel and after.channel.id == cfg.channelid
        left = before.channel and before.channel.id == cfg.channelid

        if joined and vc and vc.is_connected() and not vc.is_playing():
            await self._start_audio(guild_id, cfg, vc)
            await self._update_status(guild_id, 'active')
            logger.info("Bot #%d ▶ resumed in guild %s", self.bot_number, guild_id)

        if left and not joined:
            channel = before.channel
            if channel and self._humans(channel) == 0 and vc and vc.is_playing():
                self._stop_lofi(guild_id)
                vc.stop()
                await self._update_status(guild_id, 'idle')
                logger.info("Bot #%d ⏸ paused in guild %s (empty channel)", self.bot_number, guild_id)
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-23) ---
    # Purpose: Handle both force-disconnects (cooldown) and moderator moves (accept new channel)
    async def _handle_self_voice_change(
        self, before: discord.VoiceState, after: discord.VoiceState,
    ):
        if not before.channel:
            return
        gid = before.channel.guild.id
        cfg = self._configs.get(gid)
        if not cfg or not cfg.enabled:
            return

        if after.channel and after.channel.id != before.channel.id:
            new_ch = after.channel
            logger.info(
                "Bot #%d moved %s → #%s in guild %s",
                self.bot_number, before.channel.name, new_ch.name, gid,
            )
            cfg.channelid = new_ch.id
            try:
                await self._db_exec(
                    "UPDATE ambient_sounds_config "
                    "SET channelid = %s, updated_at = NOW() "
                    "WHERE guildid = %s AND bot_number = %s",
                    (new_ch.id, gid, self.bot_number),
                )
            except Exception as exc:
                logger.error("Channel update after move failed for %s: %s", gid, exc)

            guild = before.channel.guild
            vc = guild.voice_client
            if vc and vc.is_connected():
                if self._humans(new_ch) > 0:
                    if not vc.is_playing() and cfg.sound_type:
                        await self._start_audio(gid, cfg, vc)
                        await self._update_status(gid, 'active')
                else:
                    if vc.is_playing():
                        self._stop_lofi(gid)
                        vc.stop()
                    await self._update_status(gid, 'idle')
            return

        if not after.channel:
            if cfg.channelid == before.channel.id:
                # --- AI-REPLACED (2026-06-10) ---
                # Reason: the 2026-05-19c grace period (a single 5s sleep +
                #   is_connected() check) still misfired. discord.py keeps the
                #   VoiceClient alive while it retries the voice handshake
                #   (reconnect=True), and live logs showed reconnects to far
                #   media edges (japan/hkg/sin) taking 20-50s with "connection
                #   attempt 2" / "Timed out connecting to voice... Retrying".
                #   After 5s is_connected() was still False, so this handler
                #   declared "force-disconnected" MID-RECONNECT (3x in 3s for
                #   one event — every VOICE_STATE_UPDATE spawned its own grace
                #   sleep), applied the 60s cooldown, stopped the LoFi state,
                #   and its recovery then fought discord.py's in-flight
                #   handshake. Users saw the bot drop, go silent, or sit out
                #   cooldowns while actually connected.
                # What the new code does better:
                #   - single-flight: one grace check per guild at a time;
                #   - polls up to FORCE_DC_GRACE_TOTAL_S, exiting early when
                #     either recovered (is_connected()) or discord.py gave up
                #     (guild.voice_client is None — it tears the client down
                #     when it stops retrying, and on real kicks it does not
                #     auto-reconnect at all, so kicks are detected within one
                #     poll step and the anti-rejoin cooldown still applies);
                #   - on recovery, restarts audio if a concurrent handler had
                #     already stopped it, instead of leaving a silent bot.
                # --- Original code (commented out for rollback) ---
                # await asyncio.sleep(5)
                # guild = before.channel.guild
                # vc = guild.voice_client if guild else None
                # if vc and vc.is_connected():
                #     logger.debug(
                #         "Bot #%d transient voice blip recovered in guild %s — no action needed",
                #         self.bot_number, gid,
                #     )
                #     return
                # logger.warning(
                #     "Bot #%d force-disconnected in guild %s", self.bot_number, gid,
                # )
                # self._cooldowns[gid] = time.monotonic() + FORCE_DC_COOLDOWN_S
                # await self._update_status(
                #     gid, 'idle', 'Force-disconnected — will rejoin after cooldown',
                # )
                # self._stop_lofi(gid)
                # --- End original code ---
                if gid in self._grace_pending:
                    # A grace check for this guild is already in flight; let it decide.
                    return
                self._grace_pending.add(gid)
                try:
                    guild = before.channel.guild
                    recovered = False
                    gave_up = False
                    deadline = time.monotonic() + FORCE_DC_GRACE_TOTAL_S
                    while time.monotonic() < deadline:
                        await asyncio.sleep(FORCE_DC_GRACE_STEP_S)
                        vc = guild.voice_client if guild else None
                        if vc and vc.is_connected():
                            recovered = True
                            break
                        if vc is None:
                            gave_up = True
                            break

                    if recovered:
                        logger.info(
                            "Bot #%d transient voice blip recovered in guild %s — no action needed",
                            self.bot_number, gid,
                        )
                        # If a previous (pre-fix) teardown or the blip itself left us
                        # connected but silent, restart audio for present listeners.
                        cfg = self._configs.get(gid)
                        vc = guild.voice_client if guild else None
                        if (
                            cfg and cfg.enabled and cfg.sound_type
                            and vc and vc.is_connected() and not vc.is_playing()
                            and self._humans(vc.channel) > 0
                        ):
                            try:
                                await self._start_audio(gid, cfg, vc)
                                await self._update_status(gid, 'active')
                            except Exception as exc:
                                logger.warning(
                                    "Bot #%d failed to resume audio after blip in guild %s: %s",
                                    self.bot_number, gid, exc,
                                )
                        return

                    logger.warning(
                        "Bot #%d force-disconnected in guild %s (%s)",
                        self.bot_number, gid,
                        'voice client torn down' if gave_up else
                        f'not reconnected after {FORCE_DC_GRACE_TOTAL_S}s',
                    )
                    self._cooldowns[gid] = time.monotonic() + FORCE_DC_COOLDOWN_S
                    await self._update_status(
                        gid, 'idle', 'Force-disconnected — will rejoin after cooldown',
                    )
                    # Clear the stale Now Playing dict so the next panel render
                    # shows the cooldown state instead of the last track. The 60s
                    # _panel_refresh_loop picks this up (no immediate refresh here:
                    # that previously caused a 429 PATCH storm).
                    self._stop_lofi(gid)
                finally:
                    self._grace_pending.discard(gid)
                # --- END AI-REPLACED ---
    # --- END AI-MODIFIED ---

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _humans(channel: discord.VoiceChannel | None) -> int:
        if channel is None:
            return 0
        return sum(1 for m in channel.members if not m.bot)

    def _format_nick(self, cfg: GuildConfig) -> str:
        label, emoji = SOUND_LABELS.get(cfg.sound_type, (cfg.sound_type or 'Sound', '\U0001f3b5'))
        template = cfg.nickname_template or DEFAULT_NICK_TEMPLATE
        try:
            nick = template.format(emoji=emoji, sound=label, bot=self.bot_number)
        except (KeyError, IndexError, ValueError):
            nick = f'{emoji} {label}'
        return nick[:32]

    def _cancel(self, gid: int, store: dict[int, asyncio.Task]):
        task = store.pop(gid, None)
        if task and not task.done():
            task.cancel()

    # ------------------------------------------------------------------
    #  LoFi playlist & unified audio playback
    # ------------------------------------------------------------------

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: LoFi with mutagen metadata, loudnorm, fade, skip, crash recovery,
    #          dedup, sub-moods, blacklists, now-playing embed, presence rate-limiting

    # --- AI-REPLACED (2026-06-10) ---
    # Reason: Users reported the sound bots "constantly disconnecting". Two
    #   defects lived here:
    #   1. The 5-minute reload loop cleared _lofi_meta/_lofi_pools and then this
    #      method re-parsed EVERY file with mutagen, synchronously, on the shared
    #      asyncio event loop. With 10 bots in one process the loop stalled for
    #      a full-library parse roughly every 30 seconds, delaying gateway and
    #      voice websocket heartbeats (log signature: frequent "RESUMED" and
    #      voice 1006 reconnects).
    #   2. Clearing the dicts before rebuilding left a window where _play_lofi
    #      saw empty pools at a track change and gave up.
    # What the new code does better: builds into local dicts and atomically
    #   swaps them in (no empty-pool window), reuses cached metadata for files
    #   whose (size, mtime) are unchanged so periodic rescans cost ~one stat()
    #   per file instead of a mutagen parse, and the reload loop now runs the
    #   scan in a worker thread so the event loop never blocks. The noisy
    #   per-rescan INFO log only fires when the library actually changed.
    # --- Original code (commented out for rollback) ---
    # def _scan_lofi(self, lofi_dir: str):
    #     """Scan lofi directory tree for songs, read metadata, deduplicate."""
    #     if not os.path.isdir(lofi_dir):
    #         return
    #
    #     all_songs: list[str] = []
    #     mood_songs: dict[str, list[str]] = {}
    #     fingerprints: dict[tuple, str] = {}
    #
    #     for root, _dirs, files in os.walk(lofi_dir):
    #         for f in sorted(files):
    #             if not f.lower().endswith(('.mp3', '.ogg', '.wav', '.flac')):
    #                 continue
    #             path = os.path.join(root, f)
    #             artist, title, duration = self._read_meta(path)
    #
    #             try:
    #                 fsize = os.path.getsize(path)
    #             except OSError:
    #                 continue
    #             fp = (fsize, round(duration))
    #             if fp in fingerprints:
    #                 logger.debug(
    #                     "Skipping duplicate: %s (matches %s)",
    #                     f, os.path.basename(fingerprints[fp]),
    #                 )
    #                 continue
    #             fingerprints[fp] = path
    #
    #             self._lofi_meta[path] = (artist, title, duration)
    #             all_songs.append(path)
    #
    #             rel = os.path.relpath(root, lofi_dir)
    #             if rel != '.':
    #                 mood_key = f'lofi_{rel.replace(os.sep, "_").lower()}'
    #                 mood_songs.setdefault(mood_key, []).append(path)
    #
    #     self._lofi_pools['lofi'] = all_songs
    #     for mood, songs in mood_songs.items():
    #         self._lofi_pools[mood] = songs
    #         if mood not in SOUND_LABELS:
    #             pretty = mood.split('_', 1)[1].replace('_', ' ').title()
    #             SOUND_LABELS[mood] = (f'LoFi {pretty}', '\U0001f3b5')
    #
    #     logger.info(
    #         "Bot #%d scanned %d LoFi songs, moods: %s",
    #         self.bot_number, len(all_songs),
    #         list(mood_songs.keys()) or ['none'],
    #     )
    # --- End original code ---
    def _scan_lofi(self, lofi_dir: str):
        """Scan lofi directory tree for songs, read metadata, deduplicate.

        Safe to call from a worker thread: builds into local structures and
        atomically swaps them onto self at the end. Unchanged files (same
        size + mtime as the previous scan) reuse cached metadata and are not
        re-parsed with mutagen.
        """
        if not os.path.isdir(lofi_dir):
            return

        prev_meta = self._lofi_meta
        prev_stats = self._lofi_stats

        new_meta: dict[str, tuple[str, str, float]] = {}
        new_stats: dict[str, tuple[int, float]] = {}
        all_songs: list[str] = []
        mood_songs: dict[str, list[str]] = {}
        fingerprints: dict[tuple, str] = {}
        parsed = 0
        reused = 0

        for root, _dirs, files in os.walk(lofi_dir):
            for f in sorted(files):
                if not f.lower().endswith(('.mp3', '.ogg', '.wav', '.flac')):
                    continue
                path = os.path.join(root, f)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                stat_key = (st.st_size, st.st_mtime)

                cached = prev_meta.get(path)
                if cached is not None and prev_stats.get(path) == stat_key:
                    artist, title, duration = cached
                    reused += 1
                else:
                    artist, title, duration = self._read_meta(path)
                    parsed += 1

                fp = (st.st_size, round(duration))
                if fp in fingerprints:
                    logger.debug(
                        "Skipping duplicate: %s (matches %s)",
                        f, os.path.basename(fingerprints[fp]),
                    )
                    continue
                fingerprints[fp] = path

                new_meta[path] = (artist, title, duration)
                new_stats[path] = stat_key
                all_songs.append(path)

                rel = os.path.relpath(root, lofi_dir)
                if rel != '.':
                    mood_key = f'lofi_{rel.replace(os.sep, "_").lower()}'
                    mood_songs.setdefault(mood_key, []).append(path)

        new_pools: dict[str, list[str]] = {'lofi': all_songs}
        for mood, songs in mood_songs.items():
            new_pools[mood] = songs
            if mood not in SOUND_LABELS:
                pretty = mood.split('_', 1)[1].replace('_', ' ').title()
                SOUND_LABELS[mood] = (f'LoFi {pretty}', '\U0001f3b5')

        changed = set(new_meta) != set(prev_meta)

        # Atomic swap: readers always see either the old or the new library,
        # never a half-built or empty one.
        self._lofi_meta = new_meta
        self._lofi_stats = new_stats
        self._lofi_pools = new_pools

        log = logger.info if (changed or not reused) else logger.debug
        log(
            "Bot #%d scanned %d LoFi songs (%d parsed, %d cached), moods: %s",
            self.bot_number, len(all_songs), parsed, reused,
            list(mood_songs.keys()) or ['none'],
        )
    # --- END AI-REPLACED ---

    @staticmethod
    def _read_meta(path: str) -> tuple[str, str, float]:
        """Read (artist, title, duration) via mutagen; fallback to filename."""
        duration = 0.0
        fb_artist, fb_title = SoundBot._parse_filename(path)
        if mutagen is None:
            return fb_artist, fb_title, duration
        try:
            mf = mutagen.File(path, easy=True)
            if mf and mf.info:
                duration = mf.info.length or 0.0
            if mf:
                artist = (mf.get('artist') or [''])[0] or fb_artist
                title = (mf.get('title') or [''])[0] or fb_title
                return artist, title, duration
        except Exception:
            logger.debug("mutagen failed for %s, using filename", os.path.basename(path))
        return fb_artist, fb_title, duration

    @staticmethod
    def _parse_filename(path: str) -> tuple[str, str]:
        """Extract (artist, title) from 'Artist - Title (source).mp3'."""
        name = os.path.splitext(os.path.basename(path))[0]
        if ' - ' in name:
            artist, rest = name.split(' - ', 1)
            title = rest.rsplit('(', 1)[0].strip()
            return artist.strip(), title
        return 'Unknown Artist', name

    async def _play_lofi(self, gid: int, cfg: GuildConfig):
        """Select and play the next LoFi song with loudnorm, fade, crash recovery."""
        pool = self._lofi_pools.get(cfg.sound_type) or self._lofi_pools.get('lofi', [])
        if not pool:
            logger.warning("No LoFi songs in pool '%s'", cfg.sound_type)
            return

        guild = self.get_guild(gid)
        if not guild:
            return
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return

        playlist = self._lofi_playlists.get(gid)
        idx = self._lofi_indices.get(gid, 0)
        if not playlist or idx >= len(playlist):
            playlist = list(pool)
            random.shuffle(playlist)
            self._lofi_playlists[gid] = playlist
            idx = 0

        blacklist = self._lofi_blacklists.get(gid, set())
        while idx < len(playlist) and os.path.basename(playlist[idx]) in blacklist:
            idx += 1
        if idx >= len(playlist):
            filtered = [s for s in pool if os.path.basename(s) not in blacklist]
            playlist = filtered or list(pool)
            random.shuffle(playlist)
            self._lofi_playlists[gid] = playlist
            idx = 0

        song_path = playlist[idx]
        self._lofi_indices[gid] = idx + 1
        meta = self._lofi_meta.get(song_path)
        if meta:
            artist, title, duration = meta
        else:
            artist, title = self._parse_filename(song_path)
            duration = 0.0

        gen = self._lofi_gen.get(gid, 0) + 1
        self._lofi_gen[gid] = gen

        # --- AI-MODIFIED (2026-04-05) ---
        # Purpose: Removed loudnorm from real-time ffmpeg pipeline. LoFi files are now
        # pre-normalized on disk, so only volume and fade filters are needed at runtime.
        # --- Original code (commented out for rollback) ---
        # af_parts = ['loudnorm=I=-16:TP=-1.5:LRA=11', f'volume={vol}', 'afade=t=in:d=3']
        # --- End original code ---
        vol = cfg.volume / 100.0
        af_parts = [f'volume={vol}', 'afade=t=in:d=3']
        # --- END AI-MODIFIED ---
        if duration > 7:
            af_parts.append(f'afade=t=out:st={duration - 3:.1f}:d=3')
        af_chain = ','.join(af_parts)

        try:
            source = discord.FFmpegPCMAudio(
                song_path, options=f'-filter:a "{af_chain}"',
            )
        except Exception as exc:
            logger.error("FFmpeg source failed for %s: %s", os.path.basename(song_path), exc)
            errs = self._lofi_error_counts.get(gid, 0) + 1
            self._lofi_error_counts[gid] = errs
            if errs >= 3:
                await self._update_status(gid, 'error', 'Multiple LoFi playback failures')
                return
            self._lofi_indices[gid] = idx + 1
            await self._play_lofi(gid, cfg)
            return

        def after_play(error):
            if error:
                logger.error("LoFi playback error in guild %s: %s", gid, error)
                errs = self._lofi_error_counts.get(gid, 0) + 1
                self._lofi_error_counts[gid] = errs
                if errs >= 3:
                    return
            else:
                self._lofi_error_counts[gid] = 0
            if self._lofi_gen.get(gid) == gen:
                # --- AI-MODIFIED (2026-06-10) ---
                # Purpose: the future from run_coroutine_threadsafe was discarded,
                #   so if scheduling the next track failed the music stopped with
                #   no log at all (bot sat in the channel silent). Log it.
                future = asyncio.run_coroutine_threadsafe(
                    self._play_lofi(gid, cfg), self.loop,
                )

                def _log_next_track_failure(f):
                    try:
                        exc = f.exception()
                    except Exception:
                        return
                    if exc is not None:
                        logger.error(
                            "Next LoFi track failed to start in guild %s: %r", gid, exc,
                        )

                future.add_done_callback(_log_next_track_failure)
                # --- END AI-MODIFIED ---

        try:
            if vc.is_playing():
                vc.stop()
            vc.play(source, after=after_play)
        except Exception as exc:
            logger.error("vc.play failed for guild %s: %s", gid, exc)
            errs = self._lofi_error_counts.get(gid, 0) + 1
            self._lofi_error_counts[gid] = errs
            if errs < 3:
                self._lofi_indices[gid] = idx + 1
                await self._play_lofi(gid, cfg)
            return

        self._lofi_error_counts[gid] = 0
        self._lofi_current[gid] = (artist, title)
        await self._update_presence(f'{title} \u2014 {artist}', is_lofi=True)
        logger.info(
            "Bot #%d \u266b LoFi: %s \u2014 %s in guild %s",
            self.bot_number, title, artist, gid,
        )

        channel = guild.get_channel(cfg.channelid)
        if channel:
            self.loop.create_task(self._post_now_playing(gid, channel, artist, title))

        try:
            await self._db_exec(
                "UPDATE ambient_sounds_config "
                "SET current_song_title = %s, current_song_artist = %s "
                "WHERE guildid = %s AND bot_number = %s",
                (title[:200], artist[:200], gid, self.bot_number),
            )
        except Exception:
            pass
        try:
            await self._db_exec(
                "INSERT INTO lofi_play_history "
                "(guildid, bot_number, song_title, song_artist, song_filename) "
                "VALUES (%s, %s, %s, %s, %s)",
                (gid, self.bot_number, title[:200], artist[:200],
                 os.path.basename(song_path)[:300]),
            )
        except Exception:
            pass

    def _stop_lofi(self, gid: int):
        """Increment generation to prevent LoFi chaining; clear current song."""
        self._lofi_gen[gid] = self._lofi_gen.get(gid, 0) + 1
        self._lofi_current.pop(gid, None)
        self._lofi_error_counts.pop(gid, None)

    # --- AI-MODIFIED (2026-04-03) ---
    # Purpose: Post control panel when audio starts playing
    async def _start_audio(self, gid: int, cfg: GuildConfig, vc: discord.VoiceClient):
        """Unified playback start — routes to LoFi playlist or pre-encoded ambient."""
        if cfg.sound_type and cfg.sound_type.startswith('lofi'):
            await self._play_lofi(gid, cfg)
        else:
            self._stop_lofi(gid)
            source = self.audio_lib.get_source(cfg.sound_type, cfg.volume)
            vc.play(source)
            label, _ = SOUND_LABELS.get(cfg.sound_type, (cfg.sound_type or 'Sound', ''))
            await self._update_presence(label, is_lofi=False)

        guild = self.get_guild(gid)
        if guild and cfg.channelid:
            channel = guild.get_channel(cfg.channelid)
            if channel:
                await self._post_control_panel(gid, channel, cfg)
    # --- END AI-MODIFIED ---

    async def _update_presence(self, text: str | None = None, is_lofi: bool = False):
        """Set the bot's Discord presence with rate limiting and LoFi priority."""
        now = time.monotonic()
        if now - self._last_presence_update < 12:
            return
        if not is_lofi and self._lofi_current:
            return
        try:
            if text:
                await self.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.listening,
                        name=text,
                    )
                )
            else:
                await self.change_presence(activity=None)
            self._last_presence_update = now
        except Exception as exc:
            logger.debug("Presence update failed: %s", exc)

    # --- AI-REPLACED (2026-04-03) ---
    # Reason: Now Playing info is shown in the unified control panel instead of a separate embed
    # What the new code does better: Updates the control panel with current song info
    # --- Original code (commented out for rollback) ---
    # async def _post_now_playing(self, gid: int, channel, artist: str, title: str):
    #     """Post or update a Now Playing embed in the VC text chat."""
    #     try:
    #         perms = channel.permissions_for(channel.guild.me)
    #         if not perms.send_messages:
    #             return
    #         embed = discord.Embed(title='Now Playing', description=f'**{title}**\nby {artist}', color=0x1DB954)
    #         embed.set_footer(text='Moderators can skip with the button below')
    #         view = discord.ui.View(timeout=None)
    #         btn = discord.ui.Button(label='Skip', emoji='\u23ed\ufe0f', custom_id=f'lofi_skip:{self.bot_number}', style=discord.ButtonStyle.secondary)
    #         view.add_item(btn)
    #         old_id = self._np_message_ids.get(gid)
    #         if old_id:
    #             try:
    #                 msg = await channel.fetch_message(old_id)
    #                 await msg.edit(embed=embed, view=view)
    #                 return
    #             except Exception: pass
    #         msg = await channel.send(embed=embed, view=view)
    #         self._np_message_ids[gid] = msg.id
    #     except Exception as exc:
    #         logger.debug("Now Playing post failed for guild %s: %s", gid, exc)
    # --- End original code ---
    async def _post_now_playing(self, gid: int, channel, artist: str, title: str):
        """Update the control panel with the current song info."""
        cfg = self._configs.get(gid)
        if cfg:
            await self._post_control_panel(gid, channel, cfg)
    # --- END AI-REPLACED ---

    async def _handle_skip(self, interaction: discord.Interaction):
        """Handle the LoFi skip button — moderator only."""
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            return
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            await interaction.response.send_message(
                "Could not verify permissions.", ephemeral=True,
            )
            return
        if not (member.guild_permissions.manage_channels
                or member.guild_permissions.manage_guild):
            await interaction.response.send_message(
                "Only moderators can skip songs.", ephemeral=True,
            )
            return

        cfg = self._configs.get(gid)
        if not cfg or not cfg.enabled:
            await interaction.response.send_message("Bot is not active.", ephemeral=True)
            return

        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected() or not vc.is_playing():
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        self._stop_lofi(gid)
        vc.stop()
        await self._play_lofi(gid, cfg)

        current = self._lofi_current.get(gid)
        if current:
            await interaction.response.send_message(
                f'\u23ed\ufe0f Skipped! Now playing: **{current[1]}** \u2014 {current[0]}',
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                '\u23ed\ufe0f Skipped!', ephemeral=True,
            )

    async def _lofi_reload_loop(self):
        """Periodically rescan the lofi directory for new/removed songs."""
        await self.wait_until_ready()
        while not self.is_closed():
            await asyncio.sleep(300)
            if not self._lofi_dir:
                continue
            try:
                old_count = len(self._lofi_pools.get('lofi', []))
                # --- AI-REPLACED (2026-06-10) ---
                # Reason: clearing the dicts here opened an empty-pool window for
                #   any track change during the rescan, and running the scan
                #   inline blocked the shared event loop (heartbeat stalls ->
                #   gateway RESUMEs / voice 1006 drops; see _scan_lofi).
                # What the new code does better: _scan_lofi now swaps complete
                #   structures in atomically, and runs in a worker thread.
                # --- Original code (commented out for rollback) ---
                # self._lofi_meta.clear()
                # self._lofi_pools.clear()
                # self._scan_lofi(self._lofi_dir)
                # --- End original code ---
                await asyncio.to_thread(self._scan_lofi, self._lofi_dir)
                # --- END AI-REPLACED ---
                new_count = len(self._lofi_pools.get('lofi', []))
                if new_count != old_count:
                    logger.info("LoFi reload: %d \u2192 %d songs", old_count, new_count)
            except Exception as exc:
                logger.debug("LoFi reload error: %s", exc)

    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-05-19) ---
    # Purpose: Periodically refresh control panels so they reflect the live
    # voice-client state. Without this, a silent disconnect (no on_voice_state
    # event) or a force-disconnect during a cooldown can leave the panel
    # showing stale info until the next track change or button press.
    async def _panel_refresh_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            await asyncio.sleep(60)
            for gid in list(self._control_msg_ids.keys()):
                cfg = self._configs.get(gid)
                if not cfg or not cfg.enabled:
                    continue
                guild = self.get_guild(gid)
                if not guild:
                    continue
                channel_id = self._control_channel_ids.get(gid)
                if not channel_id:
                    continue
                channel = guild.get_channel(channel_id)
                if not channel:
                    continue
                try:
                    await self._post_control_panel(gid, channel, cfg)
                except Exception as exc:
                    logger.debug("Panel refresh failed for %s: %s", gid, exc)
    # --- END AI-MODIFIED ---

    # ------------------------------------------------------------------
    #  Deferred connect / disconnect
    # ------------------------------------------------------------------

    def _schedule_connect(self, gid: int, cfg: GuildConfig):
        self._cancel(gid, self._connect_tasks)

        async def _task():
            await asyncio.sleep(CONNECT_GRACE_S)
            if gid in self._cooldowns and time.monotonic() < self._cooldowns[gid]:
                return
            guild = self.get_guild(gid)
            if not guild:
                return
            await self._voice_connect(gid, cfg)

        self._connect_tasks[gid] = self.loop.create_task(_task())

    def _schedule_disconnect(self, gid: int):
        self._cancel(gid, self._disconnect_tasks)

        async def _task():
            await asyncio.sleep(DISCONNECT_GRACE_S)
            guild = self.get_guild(gid)
            cfg = self._configs.get(gid)
            if guild and cfg and cfg.channelid:
                ch = guild.get_channel(cfg.channelid)
                if ch and self._humans(ch) > 0:
                    return
            await self._voice_disconnect(gid)

        self._disconnect_tasks[gid] = self.loop.create_task(_task())

    # ------------------------------------------------------------------
    #  Voice connect / disconnect / swap
    # ------------------------------------------------------------------

    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: Connect to VC always; only play audio if humans are present
    # --- AI-MODIFIED (2026-04-13) ---
    # Purpose: Add WARNING-level logging to every failure path so connection
    # issues (especially for rentals) are visible in PM2 logs instead of
    # silently updating only the DB status.
    async def _voice_connect(self, gid: int, cfg: GuildConfig):
        guild = self.get_guild(gid)
        if not guild:
            logger.warning("Bot #%d cannot connect to guild %s — not in guild cache", self.bot_number, gid)
            await self._update_status(gid, 'error', 'Bot not in guild')
            return

        # --- AI-MODIFIED (2026-04-03) ---
        # Purpose: Fall back to fetch_channel API call when channel not in cache.
        # Private rooms restrict VIEW_CHANNEL, so the bot's cache won't include them.
        # fetch_channel + set_permissions grants visibility for future polls.
        # --- Original code (commented out for rollback) ---
        # channel = guild.get_channel(cfg.channelid)
        # if not channel:
        #     await self._update_status(gid, 'error', 'Channel not found or deleted')
        #     return
        # --- End original code ---
        channel = guild.get_channel(cfg.channelid)
        if not channel:
            try:
                channel = await self.fetch_channel(cfg.channelid)
                logger.info(
                    "Bot #%d fetched hidden channel %s via API in %s",
                    self.bot_number, cfg.channelid, guild.name,
                )
                try:
                    await channel.set_permissions(
                        guild.me,
                        connect=True, speak=True, view_channel=True,
                        reason="Sound bot: granting access to private room for rental",
                    )
                except discord.Forbidden:
                    logger.warning(
                        "Bot #%d cannot set permissions on channel %s — needs Manage Roles",
                        self.bot_number, cfg.channelid,
                    )
                except Exception as exc:
                    logger.warning("Bot #%d permission grant failed: %s", self.bot_number, exc)
            except discord.NotFound:
                logger.warning(
                    "Bot #%d channel %s not found in %s — deleted?",
                    self.bot_number, cfg.channelid, guild.name,
                )
                await self._update_status(gid, 'error', 'Channel not found or deleted')
                return
            except discord.Forbidden:
                logger.warning(
                    "Bot #%d cannot access channel %s in %s — missing View Channel permission",
                    self.bot_number, cfg.channelid, guild.name,
                )
                await self._update_status(gid, 'error', 'Cannot access channel — missing permissions')
                return
            except Exception as exc:
                logger.warning(
                    "Bot #%d channel fetch failed for %s in %s: %s",
                    self.bot_number, cfg.channelid, guild.name, exc,
                )
                await self._update_status(gid, 'error', f'Channel fetch failed: {str(exc)[:120]}')
                return
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: Auto-fix channel permissions when Connect/Speak is missing
        perms = channel.permissions_for(guild.me)
        if not perms.connect or not perms.speak:
            try:
                await channel.set_permissions(
                    guild.me,
                    connect=True, speak=True, view_channel=True,
                    reason="Sound bot auto-fix: needs Connect and Speak",
                )
                perms = channel.permissions_for(guild.me)
                if perms.connect and perms.speak:
                    logger.info(
                        "Bot #%d auto-fixed permissions in #%s (%s)",
                        self.bot_number, channel.name, guild.name,
                    )
                else:
                    logger.warning(
                        "Bot #%d still missing Connect/Speak in #%s (%s) after auto-fix attempt",
                        self.bot_number, channel.name, guild.name,
                    )
                    await self._update_status(
                        gid, 'error',
                        'Missing Connect or Speak permission — '
                        'please grant this bot Connect + Speak in this channel',
                    )
                    return
            except discord.Forbidden:
                logger.warning(
                    "Bot #%d cannot auto-fix permissions in #%s (%s) — needs Manage Roles",
                    self.bot_number, channel.name, guild.name,
                )
                await self._update_status(
                    gid, 'error',
                    'Missing Connect or Speak permission — '
                    'grant this bot Connect + Speak, or give it Manage Roles '
                    'so it can fix permissions automatically',
                )
                return
            except Exception as exc:
                logger.warning(
                    "Bot #%d permission fix failed in #%s (%s): %s",
                    self.bot_number, channel.name, guild.name, exc,
                )
                await self._update_status(gid, 'error', f'Permission fix failed: {str(exc)[:120]}')
                return
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-06-10) ---
        # Purpose: single-flight per guild. Overlapping _voice_connect runs
        #   (poll loop + reconnect task + grace recovery) raced each other and
        #   discord.py's own auto-reconnect — live logs showed two simultaneous
        #   voice handshakes followed by "Timed out connecting to voice" and
        #   empty "Connect failed" errors (TimeoutError has no message). A
        #   duplicate attempt now just skips; the 15s poll re-evaluates anyway.
        lock = self._connect_locks.setdefault(gid, asyncio.Lock())
        if lock.locked():
            logger.debug(
                "Bot #%d connect already in progress for guild %s — skipping duplicate",
                self.bot_number, gid,
            )
            return
        async with lock:
        # --- END AI-MODIFIED ---
            try:
                if guild.voice_client:
                    await guild.voice_client.disconnect(force=True)
                    # --- AI-MODIFIED (2026-06-10) ---
                    # Purpose: give discord.py a moment to fully tear down the old
                    #   VoiceClient before reconnecting; connecting on top of a
                    #   half-torn-down client raised "Already connected" /
                    #   handshake timeouts.
                    for _ in range(10):
                        if guild.voice_client is None:
                            break
                        await asyncio.sleep(0.2)
                    # --- END AI-MODIFIED ---

                vc = await channel.connect(timeout=30, reconnect=True)

                try:
                    await guild.me.edit(nick=self._format_nick(cfg))
                except discord.Forbidden:
                    pass
                except Exception as exc:
                    logger.debug("Nickname change failed in %s: %s", guild.name, exc)

                if self._humans(channel) > 0:
                    await self._start_audio(gid, cfg, vc)
                    await self._update_status(gid, 'active')
                    logger.info(
                        "Bot #%d ▶ %s in #%s (%s)",
                        self.bot_number, cfg.sound_type, channel.name, guild.name,
                    )
                else:
                    await self._update_status(gid, 'idle')
                    logger.info(
                        "Bot #%d ⏸ waiting in #%s (%s)",
                        self.bot_number, channel.name, guild.name,
                    )

                self._reconnect_attempts[gid] = 0

                # --- AI-MODIFIED (2026-03-23) ---
                # Purpose: Post voting widget in VC text chat if voting is enabled
                if getattr(cfg, 'voting_enabled', False):
                    self.loop.create_task(self._post_vote_widget(gid, channel, cfg))
                # --- END AI-MODIFIED ---

            except Exception as exc:
                # --- AI-MODIFIED (2026-06-10) ---
                # Purpose: include the exception type — TimeoutError stringifies to
                #   an empty message, which produced useless "Connect failed in X: "
                #   log lines and blank panel errors.
                logger.error(
                    "Connect failed in %s: %s: %s", guild.name, type(exc).__name__, exc,
                )
                await self._update_status(
                    gid, 'error', f'{type(exc).__name__}: {exc}'[:200],
                )
                # --- END AI-MODIFIED ---
                self._schedule_reconnect(gid)
    # --- END AI-MODIFIED ---

    def _schedule_reconnect(self, gid: int):
        delays = [5, 10, 20, 40, 60, 120, 300]
        attempt = self._reconnect_attempts.get(gid, 0)
        delay = delays[min(attempt, len(delays) - 1)]
        self._reconnect_attempts[gid] = attempt + 1

        async def _task():
            await asyncio.sleep(delay)
            cfg = self._configs.get(gid)
            if cfg and cfg.enabled and cfg.sound_type and cfg.channelid:
                guild = self.get_guild(gid)
                if guild:
                    await self._voice_connect(gid, cfg)

        self._cancel(gid, self._connect_tasks)
        self._connect_tasks[gid] = self.loop.create_task(_task())

    async def _voice_disconnect(self, gid: int):
        guild = self.get_guild(gid)
        if guild and guild.voice_client:
            try:
                self._stop_lofi(gid)
                guild.voice_client.stop()
                await guild.voice_client.disconnect(force=True)
            except Exception as exc:
                logger.debug("Disconnect error in %s: %s", gid, exc)

        if guild:
            try:
                await guild.me.edit(nick=None)
            except Exception:
                pass

        await self._update_status(gid, 'idle')
        logger.info("Bot #%d ⏹ guild %s", self.bot_number, gid)

    async def _voice_swap_source(self, gid: int, cfg: GuildConfig):
        guild = self.get_guild(gid)
        if not guild or not guild.voice_client or not guild.voice_client.is_connected():
            return

        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: End old usage session before swapping so a new one starts with the new sound
        if gid in self._usage_ids:
            await self._end_usage(gid)
        # --- END AI-MODIFIED ---

        try:
            self._stop_lofi(gid)
            guild.voice_client.stop()
            await self._start_audio(gid, cfg, guild.voice_client)

            try:
                await guild.me.edit(nick=self._format_nick(cfg))
            except Exception:
                pass

            await self._update_status(gid, 'active')
        except Exception as exc:
            logger.error("Swap source failed in %s: %s", guild.name, exc)

    # ------------------------------------------------------------------
    #  Schedule helpers
    # ------------------------------------------------------------------

    # --- AI-MODIFIED (2026-03-23) ---
    # Purpose: Load schedules for this bot and match against current guild-local time
    def _check_schedule_match(
        self, schedules: list[dict], tz_name: str,
    ) -> str | None:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo('UTC')
        now = datetime.datetime.now(tz)
        cur_time = now.time()
        cur_day = now.weekday()

        for s in schedules:
            days = s['days'] or [0, 1, 2, 3, 4, 5, 6]
            if cur_day not in days:
                continue
            st = s['start_time']
            et = s['end_time']
            if isinstance(st, datetime.datetime):
                st = st.time()
            if isinstance(et, datetime.datetime):
                et = et.time()
            if st <= et:
                if st <= cur_time < et:
                    return s['sound_type']
            else:
                if cur_time >= st or cur_time < et:
                    return s['sound_type']
        return None
    # --- END AI-MODIFIED ---

    # ------------------------------------------------------------------
    #  Rental helpers
    # ------------------------------------------------------------------

    # --- AI-MODIFIED (2026-03-23) ---
    # Purpose: Background loop to expire and clean up past-due rentals
    async def _rental_expiry_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                expired = await self._db_fetch(
                    "SELECT rental_id, guildid, channelid FROM ambient_sounds_rentals "
                    "WHERE bot_number = %s AND ended_at IS NULL AND expires_at <= NOW()",
                    (self.bot_number,),
                )
                for row in expired:
                    gid = int(row['guildid'])
                    rental_id = row['rental_id']
                    logger.info("Rental %d expired in guild %s", rental_id, gid)
                    await self._db_exec(
                        "UPDATE ambient_sounds_rentals SET ended_at = NOW() WHERE rental_id = %s",
                        (rental_id,),
                    )
                    rental_cfg = self._rental_configs.pop(gid, None)
                    if rental_cfg:
                        admin_cfg = None
                        try:
                            admin_rows = await self._db_fetch(
                                "SELECT enabled, channelid, sound_type FROM ambient_sounds_config "
                                "WHERE guildid = %s AND bot_number = %s",
                                (gid, self.bot_number),
                            )
                            if admin_rows:
                                r = admin_rows[0]
                                if r['enabled'] and r['channelid'] and r['sound_type']:
                                    admin_cfg = r
                        except Exception:
                            pass

                        if not admin_cfg:
                            await self._voice_disconnect(gid)

                    guild = self.get_guild(gid)
                    if guild:
                        ch = guild.get_channel(int(row['channelid']))
                        if ch:
                            try:
                                await ch.send(
                                    "\u23f0 **Rental expired** — the sound bot has been disconnected. "
                                    "Use `/room sound` to rent again!"
                                )
                            except Exception:
                                pass
            except Exception as exc:
                logger.debug("Rental expiry loop error: %s", exc)
            await asyncio.sleep(30)

    # --- AI-MODIFIED (2026-04-13) ---
    # Purpose: Upgrade rental logging from DEBUG to WARNING so rental failures
    # appear in PM2 logs. Users pay coins for rentals; silent failures are not acceptable.
    async def _poll_rentals(self):
        """Process active rentals — connect bots to rented room channels."""
        try:
            rental_rows = await self._db_fetch(
                "SELECT rental_id, guildid, channelid, sound_type, volume, expires_at "
                "FROM ambient_sounds_rentals "
                "WHERE bot_number = %s AND ended_at IS NULL AND expires_at > NOW()",
                (self.bot_number,),
            )
        except Exception as exc:
            logger.warning("Bot #%d rental query failed: %s", self.bot_number, exc)
            return

        active_gids: set[int] = set()
        for row in rental_rows:
            gid = int(row['guildid'])
            active_gids.add(gid)

            admin_cfg = self._configs.get(gid)
            if admin_cfg and admin_cfg.enabled and admin_cfg.channelid and admin_cfg.sound_type:
                continue

            guild = self.get_guild(gid)
            if not guild:
                logger.warning(
                    "Bot #%d rental #%s for guild %s — bot not in guild, cannot fulfil rental",
                    self.bot_number, row['rental_id'], gid,
                )
                continue

            rental_cfg = GuildConfig(
                guildid=gid, bot_number=self.bot_number,
                sound_type=row['sound_type'],
                channelid=int(row['channelid']),
                volume=row['volume'],
                enabled=True, status='active', error_msg=None,
                is_premium=True,
            )

            old = self._rental_configs.get(gid)
            self._rental_configs[gid] = rental_cfg
            self._configs[gid] = rental_cfg

            if not guild.voice_client or not guild.voice_client.is_connected():
                await self._voice_connect(gid, rental_cfg)
                await asyncio.sleep(STAGGER_CONNECT_S)
            elif old and (old.sound_type != rental_cfg.sound_type or old.volume != rental_cfg.volume):
                await self._voice_swap_source(gid, rental_cfg)

        for gid in list(self._rental_configs):
            if gid not in active_gids:
                del self._rental_configs[gid]
                admin_cfg = self._configs.get(gid)
                if not (admin_cfg and admin_cfg.enabled and admin_cfg.channelid):
                    guild = self.get_guild(gid)
                    if guild and guild.voice_client and guild.voice_client.is_connected():
                        await self._voice_disconnect(gid)
    # --- END AI-MODIFIED ---

    # ------------------------------------------------------------------
    #  Config polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self):
        await self.wait_until_ready()
        await asyncio.sleep(self.bot_number * 2)
        logger.info("Bot #%d config poll started", self.bot_number)

        while not self.is_closed():
            try:
                await self._poll_once()
            except Exception as exc:
                logger.error("Poll error: %s", exc)
            await asyncio.sleep(POLL_INTERVAL_S)

    async def _poll_once(self):
        # --- AI-MODIFIED (2026-04-04) ---
        # Purpose: Added control_message_id to SELECT for panel state restoration
        rows = await self._db_fetch(
            "SELECT a.guildid, a.bot_number, a.sound_type, a.channelid, "
            "       a.volume, a.enabled, a.status, a.error_msg, "
            "       a.nickname_template, a.voting_enabled, a.vote_cooldown_minutes, "
            "       a.control_message_id, "
            "       (pg.premium_until IS NOT NULL AND pg.premium_until > NOW()) AS is_premium "
            "FROM ambient_sounds_config a "
            "LEFT JOIN premium_guilds pg ON pg.guildid = a.guildid "
            "WHERE a.bot_number = %s",
            (self.bot_number,),
        )
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-05) ---
        # Purpose: Cache schedules, timezones, and blacklists with 60s TTL
        # to reduce DB queries. These change rarely (admin dashboard edits).
        # --- Original code (commented out for rollback) ---
        # sched_rows = await self._db_fetch(
        #     "SELECT guildid, sound_type, start_time, end_time, days "
        #     "FROM ambient_sounds_schedule WHERE bot_number = %s",
        #     (self.bot_number,),
        # )
        # ... (ran every poll cycle — every 5s)
        # --- End original code ---
        now_mono = time.monotonic()
        if now_mono - self._slow_cache_updated >= self._SLOW_CACHE_TTL_S:
            self._slow_cache_updated = now_mono
            try:
                sched_rows = await self._db_fetch(
                    "SELECT guildid, sound_type, start_time, end_time, days "
                    "FROM ambient_sounds_schedule WHERE bot_number = %s",
                    (self.bot_number,),
                )
            except Exception:
                sched_rows = []

            self._cached_schedules.clear()
            for sr in sched_rows:
                sg = int(sr['guildid'])
                self._cached_schedules.setdefault(sg, []).append(sr)

            self._cached_tz_map.clear()
            if self._cached_schedules:
                try:
                    tz_rows = await self._db_fetch(
                        "SELECT guildid, timezone FROM guild_config WHERE guildid = ANY(%s)",
                        (list(self._cached_schedules.keys()),),
                    )
                    self._cached_tz_map = {int(r['guildid']): r['timezone'] for r in tz_rows}
                except Exception:
                    pass

            try:
                bl_rows = await self._db_fetch(
                    "SELECT guildid, song_filename FROM lofi_blacklist"
                )
                self._lofi_blacklists.clear()
                for br in bl_rows:
                    bg = int(br['guildid'])
                    self._lofi_blacklists.setdefault(bg, set()).add(br['song_filename'])
            except Exception:
                pass

        schedules_by_guild = self._cached_schedules
        tz_map = self._cached_tz_map
        # --- END AI-MODIFIED ---

        seen: set[int] = set()
        connect_queue: list[tuple[int, GuildConfig]] = []

        for row in rows:
            gid = int(row['guildid'])
            seen.add(gid)

            cfg = GuildConfig(
                guildid=gid,
                bot_number=row['bot_number'],
                sound_type=row['sound_type'],
                channelid=int(row['channelid']) if row['channelid'] else None,
                volume=row['volume'],
                enabled=row['enabled'],
                status=row['status'],
                error_msg=row['error_msg'],
                is_premium=bool(row['is_premium']),
                nickname_template=row.get('nickname_template'),
                voting_enabled=bool(row.get('voting_enabled', False)),
                vote_cooldown_minutes=row.get('vote_cooldown_minutes', 30),
            )

            # --- AI-MODIFIED (2026-03-23) ---
            # Purpose: Override sound_type if a schedule slot matches current time
            if gid in schedules_by_guild:
                scheduled = self._check_schedule_match(
                    schedules_by_guild[gid], tz_map.get(gid, 'UTC'),
                )
                if scheduled:
                    cfg.sound_type = scheduled
            # --- END AI-MODIFIED ---

            # --- AI-MODIFIED (2026-04-04) ---
            # Purpose: Restore control panel message ID from DB after restart
            if gid not in self._control_msg_ids:
                cmid = row.get('control_message_id')
                if cmid:
                    try:
                        self._control_msg_ids[gid] = int(cmid)
                        if cfg.channelid:
                            self._control_channel_ids[gid] = cfg.channelid
                    except (ValueError, TypeError):
                        pass
            # --- END AI-MODIFIED ---

            guild = self.get_guild(gid)
            if not guild:
                if cfg.status != 'bot_not_in_guild':
                    await self._update_status(gid, 'bot_not_in_guild')
                self._configs[gid] = cfg
                continue

            # --- AI-REPLACED (2026-04-03) ---
            # Reason: Temporarily disabled auto-leave to avoid false positives
            # What the new code does better: Logs a warning but stays in the guild
            # --- Original code (commented out for rollback) ---
            # if not cfg.is_premium:
            #     if guild.voice_client and guild.voice_client.is_connected():
            #         await self._voice_disconnect(gid)
            #     logger.info(
            #         "Bot #%d leaving non-premium guild %s (%s)",
            #         self.bot_number, guild.name, gid,
            #     )
            #     try:
            #         await guild.leave()
            #     except Exception as exc:
            #         logger.error("Failed to leave guild %s: %s", gid, exc)
            #     self._configs[gid] = cfg
            #     continue
            # --- End original code ---
            if not cfg.is_premium:
                if gid not in self._rental_configs:
                    if guild.voice_client and guild.voice_client.is_connected():
                        await self._voice_disconnect(gid)
                    # --- AI-MODIFIED (2026-05-19) ---
                    # Purpose: Log this warning once per gid per process. The
                    # previous code logged it every poll cycle (every
                    # POLL_INTERVAL_S seconds), flooding the log for any
                    # guild that lost premium but kept its config row
                    # (e.g. lalisamanoban's server, 767742076275261490).
                    if gid not in self._logged_non_premium:
                        logger.warning(
                            "Bot #%d guild %s (%s) not premium — disconnected audio but staying (auto-leave disabled)",
                            self.bot_number, guild.name, gid,
                        )
                        self._logged_non_premium.add(gid)
                    # --- END AI-MODIFIED ---
                self._configs[gid] = cfg
                continue
            # --- AI-MODIFIED (2026-05-19) ---
            # Purpose: Reset the once-per-process log flag so a guild that
            # regains premium and later loses it again will warn once more.
            self._logged_non_premium.discard(gid)
            # --- END AI-MODIFIED ---
            # --- END AI-REPLACED ---

            # --- AI-MODIFIED (2026-04-03) ---
            # Purpose: Skip disconnect when an active rental manages this guild,
            # otherwise _poll_once disconnects and _poll_rentals reconnects every cycle
            if not cfg.enabled or not cfg.sound_type or not cfg.channelid:
                if gid not in self._rental_configs:
                    if guild.voice_client and guild.voice_client.is_connected():
                        await self._voice_disconnect(gid)
                self._configs[gid] = cfg
                continue
            # --- END AI-MODIFIED ---

            old = self._configs.get(gid)
            self._configs[gid] = cfg

            if old:
                if old.channelid != cfg.channelid:
                    if guild.voice_client and guild.voice_client.is_connected():
                        await self._voice_disconnect(gid)

                if (old.sound_type != cfg.sound_type or old.volume != cfg.volume):
                    if guild.voice_client and guild.voice_client.is_connected():
                        await self._voice_swap_source(gid, cfg)
                        continue

                # --- AI-MODIFIED (2026-03-23) ---
                # Purpose: Update nickname live when template changes
                if old.nickname_template != cfg.nickname_template:
                    if guild.voice_client and guild.voice_client.is_connected():
                        try:
                            await guild.me.edit(nick=self._format_nick(cfg))
                        except Exception:
                            pass
                # --- END AI-MODIFIED ---

            # --- AI-MODIFIED (2026-03-22) ---
            # Purpose: Always connect when configured, play only if humans present
            if not guild.voice_client or not guild.voice_client.is_connected():
                if gid not in self._cooldowns or time.monotonic() >= self._cooldowns[gid]:
                    connect_queue.append((gid, cfg))
            else:
                has_humans = False
                channel = guild.get_channel(cfg.channelid)
                if channel:
                    has_humans = self._humans(channel) > 0
                vc = guild.voice_client
                if has_humans and not vc.is_playing():
                    await self._start_audio(gid, cfg, vc)
                    await self._update_status(gid, 'active')
                elif not has_humans and vc.is_playing():
                    self._stop_lofi(gid)
                    vc.stop()
                    await self._update_status(gid, 'idle')
            # --- END AI-MODIFIED ---

        for gid in list(self._configs):
            if gid not in seen:
                guild = self.get_guild(gid)
                if guild and guild.voice_client and guild.voice_client.is_connected():
                    await self._voice_disconnect(gid)
                del self._configs[gid]

        for gid, cfg in connect_queue:
            await self._voice_connect(gid, cfg)
            await asyncio.sleep(STAGGER_CONNECT_S)

        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Create config rows for guilds the bot is in but have no DB entry
        for guild in self.guilds:
            if guild.id not in seen:
                try:
                    await self._db_exec(
                        "INSERT INTO ambient_sounds_config "
                        "(guildid, bot_number, status, enabled, updated_at) "
                        "VALUES (%s, %s, 'idle', false, NOW()) "
                        "ON CONFLICT (guildid, bot_number) DO NOTHING",
                        (guild.id, self.bot_number),
                    )
                except Exception as exc:
                    logger.debug("Config row auto-create failed for %s: %s", guild.id, exc)
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: Process active room rentals as additional connections
        await self._poll_rentals()
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-05) ---
        # Purpose: Throttle heartbeat writes to every ~90s instead of every poll cycle
        # --- Original code (commented out for rollback) ---
        # try:
        #     username = str(self.user) if self.user else None
        #     await self._db_exec(
        #         "INSERT INTO sounds_bot_heartbeat ..."
        #     )
        #     ... (ran every poll cycle)
        # --- End original code ---
        hb_now = time.monotonic()
        if hb_now - self._heartbeat_updated >= self._HEARTBEAT_INTERVAL_S:
            self._heartbeat_updated = hb_now
            try:
                username = str(self.user) if self.user else None
                await self._db_exec(
                    "INSERT INTO sounds_bot_heartbeat (bot_number, last_seen, bot_username, guild_count) "
                    "VALUES (%s, NOW(), %s, %s) "
                    "ON CONFLICT (bot_number) DO UPDATE "
                    "SET last_seen = NOW(), bot_username = EXCLUDED.bot_username, "
                    "    guild_count = EXCLUDED.guild_count",
                    (self.bot_number, username, len(self.guilds)),
                )
                if self._lofi_pools:
                    try:
                        await self._db_exec(
                            "UPDATE sounds_bot_heartbeat SET lofi_moods = %s "
                            "WHERE bot_number = %s",
                            (list(self._lofi_pools.keys()), self.bot_number),
                        )
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("Heartbeat write failed: %s", exc)
        # --- END AI-MODIFIED ---
        # --- END AI-MODIFIED ---
