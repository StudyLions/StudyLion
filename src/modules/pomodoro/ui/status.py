from typing import Optional, TYPE_CHECKING
import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle

from meta import LionBot, conf
from utils.lib import utc_now
from utils.ui import LeoUI
from babel.translator import ctx_locale

from .. import babel
from ..lib import TimerRole
from .config import TimerOptionsUI
from .edit import TimerEditor

if TYPE_CHECKING:
    from ..timer import Timer

_p = babel._p


class TimerStatusUI(LeoUI):
    """
    UI representing a single Timer Status message.

    Not intended to persist across multiple stages/notifications.
    Does support updates.
    """
    def __init__(self, bot: LionBot, timer: 'Timer', channel: discord.abc.GuildChannel, show_present=True, **kwargs):
        # Set the locale context before it is copied in LeoUI
        # This is propagated via dispatch to component handlers
        ctx_locale.set(timer.locale.value)
        super().__init__(timeout=None, **kwargs)

        self.bot = bot
        self.timer = timer
        self.channel = channel
        self.show_present = show_present

    @property
    def locale(self):
        return self.timer.locale.value

    @button(label="PRESENT_PLACEHOLDER", emoji=conf.emojis.tick, style=ButtonStyle.green)
    async def present_button(self, press: discord.Interaction, pressed: Button):
        """
        Pressed to indicate the user is present.

        Does not send a visible response.
        """
        ctx_locale.set(self.locale)
        t = self.bot.translator.t
        member: discord.Member = press.user
        if member.voice and member.voice.channel and member.voice.channel.id == self.timer.data.channelid:
            self.timer.last_seen[member.id] = utc_now()
            response = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'ui:timer_status|button:present|ack',
                    "Thank you for marking your presence.\n"
                    "Good luck and stay productive!"
                ))
            )
            await press.response.send_message(embed=response, ephemeral=True)
            await self.timer.update_status_card()
        else:
            response = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'ui:timer_status|button:present|error:not_in_timer',
                    "You are not in this timer! "
                    "Join the timer channel by pressing {channel}."
                )).format(channel=self.timer.channel.mention if self.timer.channel else "**ERROR**")
            )
            await press.response.send_message(embed=response, ephemeral=True)

    async def refresh_present_button(self):
        t = self.bot.translator.t
        self.present_button.label = t(_p(
            'ui:timer_status|button:present|label',
            "Present"
        ), locale=self.locale)

    @button(label="EDIT_PLACEHOLDER", style=ButtonStyle.blurple)
    async def edit_button(self, press: discord.Interaction, pressed: Button):
        """
        Pressed to edit the timer. Response depends on role-level of user.
        """
        ctx_locale.set(self.locale)
        role = self.timer.get_member_role(press.user)
        if role >= TimerRole.OWNER:
            # Open ephemeral config UI
            await press.response.defer(thinking=True, ephemeral=True)
            ui = TimerOptionsUI(self.bot, self.timer, role, callerid=press.user.id)
            await ui.run(press)
        elif role is TimerRole.MANAGER:
            # Open config modal for work/break times
            modal = await TimerEditor.open_editor(self.bot, press, self.timer, press.user)
            await modal.wait()
        else:
            # No permissions
            t = self.bot.translator.t
            error_msg = t(_p(
                'ui:timer_status|button:edit|error:no_permissions',
                "Configuring this timer requires `MANAGE_CHANNEL` permissions on "
                "the timer channel, or the configured manager role!"
            ))
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=error_msg
            )
            await press.response.send_message(embed=embed, ephemeral=True)

    async def refresh_edit_button(self):
        t = self.bot.translator.t
        self.edit_button.label = t(_p(
            'ui:timer_status|button:edit|label',
            "Options"
        ), locale=self.locale)

    @button(label="START_PLACEHOLDER", style=ButtonStyle.green)
    async def start_button(self, press: discord.Interaction, pressed: Button):
        """
        Start a stopped timer.
        """
        ctx_locale.set(self.locale)
        t = self.bot.translator.t

        if self.timer.running:
            # Timer is already running. Race condition? (Should be impossible)
            # TODO: Log
            await press.response.send_message(
                embed=discord.Embed(
                    colour=discord.Colour.brand_red(),
                    description=t(_p(
                        'ui:timer_status|button:start|error:already_running',
                        "Cannot start a timer that is already running!"
                    ))
                ),
                ephemeral=True
            )
        else:
            role = self.timer.get_member_role(press.user)
            if role >= TimerRole.MANAGER or self.timer.auto_restart:
                # Start the timer
                await press.response.defer()
                await self.timer.start()
            else:
                embed = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'ui:timer_status|button:start|error:not_manager|title',
                        "Insufficient permissions!"
                    )),
                    description=t(_p(
                        'ui:timer_status|button:start|error:not_manager|desc',
                        "Starting this timer requires `MANAGE_CHANNEL` permissions on "
                        "the timer channel, or the configured `manager_role`!"
                    ))
                )
                await press.response.send_message(embed=embed, ephemeral=True)

    async def refresh_start_button(self):
        t = self.bot.translator.t
        self.start_button.label = t(_p(
            'ui:timer_status|button:start|label',
            "Start"
        ), locale=self.locale)

    @button(label="STOP PLACEHOLDER", style=ButtonStyle.red)
    async def stop_button(self, press: discord.Interaction, pressed: Button):
        """
        Stop a running timer.

        Note that unlike starting, stopping is allowed to be idempotent.
        """
        ctx_locale.set(self.locale)
        t = self.bot.translator.t
        role = self.timer.get_member_role(press.user)
        if role >= TimerRole.MANAGER:
            # Stop the timer
            await press.response.defer()
            await self.timer.stop()
        else:
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                title=t(_p(
                    'ui:timer_status|button:stop|error:not_manager|title',
                    "Insufficient permissions!"
                )),
                description=t(_p(
                    'ui:timer_status|button:stop|error:not_manager|desc',
                    "Stopping this timer requires `MANAGE_CHANNEL` permissions on "
                    "the timer channel, or the configured `manager_role`!"
                ))
            )
            await press.response.send_message(embed=embed, ephemeral=True)

    async def refresh_stop_button(self):
        t = self.bot.translator.t
        self.stop_button.label = t(_p(
            'ui:timer_status|button:stop|label',
            "Stop"
        ), locale=self.locale)

    async def refresh(self):
        """
        Refresh the internal UI components based on the current state of the Timer.
        """
        ctx_locale.set(self.locale)
        await asyncio.gather(
            self.refresh_present_button(),
            self.refresh_edit_button(),
            self.refresh_stop_button(),
            self.refresh_start_button(),
        )
        if self.timer.running:
            self.set_layout(
                (self.present_button, self.edit_button, self.stop_button)
            )
        else:
            self.set_layout(
                (self.present_button, self.edit_button, self.start_button)
            )
