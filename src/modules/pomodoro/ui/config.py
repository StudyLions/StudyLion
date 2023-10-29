from typing import Optional, TYPE_CHECKING
import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, Select, RoleSelect, ChannelSelect

from meta import LionBot, conf
from utils.lib import utc_now, MessageArgs, error_embed
from utils.ui import MessageUI
from babel.translator import ctx_locale

from .. import babel
from ..lib import TimerRole
from ..options import TimerOptions

from .edit import TimerEditor

if TYPE_CHECKING:
    from ..timer import Timer


_p = babel._p


class TimerOptionsUI(MessageUI):
    """
    View options for and reconfigure a single timer.
    """

    def __init__(self, bot: LionBot, timer: 'Timer', role: TimerRole, **kwargs):
        self.locale = timer.locale.value
        ctx_locale.set(self.locale)
        super().__init__(**kwargs)

        self.bot = bot
        self.timer = timer
        self.role = role

    async def interaction_check(self, interaction: discord.Interaction):
        if self.timer.destroyed:
            t = self.bot.translator.t
            error = t(_p(
                'ui:timer_options|error:timer_destroyed',
                "This timer no longer exists! Closing option menu."
            ))
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=error
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await self.quit()
            return False
        else:
            return await super().interaction_check(interaction)

    @button(label="EDIT_PLACEHOLDER", style=ButtonStyle.blurple)
    async def edit_button(self, press: discord.Interaction, pressed: Button):
        """
        Open the edit modal to modify focus/break/threshold/name/format_string
        """
        modal = await TimerEditor.open_editor(self.bot, press, self.timer, press.user, callback=self.refresh)
        await modal.wait()

    async def refresh_edit_button(self):
        self.edit_button.label = self.bot.translator.t(_p(
            'ui:timer_options|button:edit|label',
            "Edit"
        ))

    @button(label="VOICE_ALERT_PLACEHOLDER", style=ButtonStyle.green)
    async def voice_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        value = not self.timer.voice_alerts
        setting = self.timer.config.get('voice_alerts')
        setting.value = value
        await setting.write()
        await self.refresh(thinking=press)

    async def refresh_voice_button(self):
        button = self.voice_button
        button.label = self.bot.translator.t(_p(
            'ui:timer_options|button:voice_alerts|label',
            "Voice Alerts"
        ))
        if self.timer.voice_alerts:
            button.style = ButtonStyle.green
        else:
            button.style = ButtonStyle.grey

    @button(label="DELETE_PLACEHOLDER", style=ButtonStyle.red)
    async def delete_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True)
        channelid = self.timer.data.channelid
        # Destroy through cog to maintain cache
        cog = self.bot.get_cog('TimerCog')
        await cog.destroy_timer(self.timer, reason="Manually destroyed through OptionUI")
        await self.quit()

        t = self.bot.translator.t
        embed = discord.Embed(
            colour=discord.Colour.brand_red(),
            title=t(_p(
                'ui:timer_options|button:delete|success|title',
                "Timer Deleted"
            )),
            description=t(_p(
                'ui:timer_options|button:delete|success|description',
                "The timer in {channel} has been removed."
            )).format(channel=f"<#{channelid}>")
        )
        await press.edit_original_response(embed=embed)

    async def refresh_delete_button(self):
        self.delete_button.label = self.bot.translator.t(_p(
            'ui:timer_options|button:delete|label',
            "Delete"
        ))

    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def close_button(self, press: discord.Interaction, pressed: Button):
        print("HERE")
        await press.response.defer()
        await self.quit()

    async def refresh_close_button(self):
        pass

    @select(cls=ChannelSelect, placeholder="VOICE_CHANNEL_PLACEHOLDER", channel_types=[discord.ChannelType.voice])
    async def voice_menu(self, selection: discord.Interaction, selected):
        ...

    async def refresh_voice_menu(self):
        self.voice_menu.placeholder = self.bot.translator.t(_p(
            'ui:timer_options|menu:voice_channel|placeholder',
            "Set Voice Channel"
        ))

    @select(cls=ChannelSelect,
            placeholder="NOTIFICATION_PLACEHOLDER",
            channel_types=[discord.ChannelType.text, discord.ChannelType.voice],
            min_values=0, max_values=1)
    async def notification_menu(self, selection: discord.Interaction, selected):
        await selection.response.defer(thinking=True, ephemeral=True)
        value = selected.values[0] if selected.values else None
        setting = self.timer.config.get('notification_channel')

        await setting._check_value(self.timer.data.channelid, value)
        setting.value = value
        await setting.write()
        await self.timer.send_status()
        await self.refresh(thinking=selection)

    async def refresh_notification_menu(self):
        self.notification_menu.placeholder = self.bot.translator.t(_p(
            'ui:timer_options|menu:notification_channel|placeholder',
            "Set Notification Channel"
        ))

    @select(cls=RoleSelect, placeholder="ROLE_PLACEHOLDER", min_values=0, max_values=1)
    async def manage_role_menu(self, selection: discord.Interaction, selected):
        await selection.response.defer(thinking=True, ephemeral=True)
        value = selected.values[0] if selected.values else None
        setting = self.timer.config.get('manager_role')
        setting.value = value
        await setting.write()
        await self.refresh(thinking=selection)

    async def refresh_manage_role_menu(self):
        self.manage_role_menu.placeholder = self.bot.translator.t(_p(
            'ui:timer_options|menu:manager_role|placeholder',
            "Set Manager Role"
        ))

    # ----- UI FLow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t

        title = t(_p(
            'ui:timer_options|embed|title',
            "Timer Control Panel for {channel}"
        )).format(channel=f"<#{self.timer.data.channelid}>")

        table = await TimerOptions().make_setting_table(self.timer.data.channelid, timer=self.timer)

        footer = t(_p(
            'ui:timer_options|embed|footer',
            "Hover over the option names to view descriptions."
        ))

        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=title,
            description=table
        )
        embed.set_footer(text=footer)

        # Add pattern field
        embed.add_field(
            name=t(_p('ui:timer_options|embed|field:pattern|name', "Pattern")),
            value=t(_p(
                'ui:timer_options|embed|field:pattern|value',
                "**`{focus_len} minutes`** focus\n**`{break_len} minutes`** break"
            )).format(
                focus_len=self.timer.data.focus_length // 60,
                break_len=self.timer.data.break_length // 60
            )
        )

        # Add channel name field
        embed.add_field(
            name=t(_p(
                'ui:timer_options|embed|field:channel_name|name',
                "Channel Name Preview"
            )),
            value=t(_p(
                'ui:timer_options|embed|field:channel_name|value',
                "**`{name}`**\n(The actual channel name may not match due to ratelimits.)"
            )).format(name=self.timer.channel_name)
        )

        # Add issue field (if there are any permission issues).
        issues = await self._get_issues()
        if issues:
            embed.add_field(
                name=t(_p(
                    'ui:timer_options|embed|field:issues|name',
                    "Issues"
                )),
                value='\n'.join(f"{conf.emojis.warning} {issue}" for issue in issues),
                inline=False
            )
        return MessageArgs(embed=embed)

    async def _get_issues(self):
        """
        Report any issues with the timer setup, particularly with permissions.
        """
        t = self.bot.translator.t

        issues = []
        if self.timer.channel is None:
            issues.append(
                t(_p(
                    'ui:timer_options|issue:no_voice_channel',
                    "The configured voice channel does not exist! Please update it below."
                ))
            )
        else:
            channel = self.timer.channel
            # Check join and speak permissions
            my_voice_permissions = channel.permissions_for(channel.guild.me)
            if self.timer.voice_alerts and not (my_voice_permissions.connect and my_voice_permissions.speak):
                issues.append(
                    t(_p(
                        'ui:timer_options|issue:cannot_speak',
                        "Voice alerts are on, but I don't have speaking permissions in {channel}"
                    )).format(channel=channel.mention)
                )
            if not my_voice_permissions.manage_channels:
                issues.append(
                    t(_p(
                        'ui:timer_options|issue:cannot_change_name',
                        "I cannot update the name of {channel}! (Needs `MANAGE_CHANNELS` permission)"
                    )).format(channel=channel.mention)
                )

        notif_channelid = self.timer.data.notification_channelid
        if notif_channelid:
            channel = self.bot.get_channel(notif_channelid)
            if channel is None:
                issues.append(
                    t(_p(
                        'ui:timer_options|issue:notif_channel_dne',
                        "Configured notification channel does not exist!"
                    ))
                )
            else:
                perms = channel.permissions_for(channel.guild.me)
                if not (perms.embed_links and perms.attach_files):
                    issues.append(
                        t(_p(
                            'ui:timer_options|issue:notif_channel_write',
                            "I cannot attach files (`ATTACH_FILES`) or send embeds (`EMBED_LINKS`) in {channel}"
                        )).format(channel=channel.mention)
                    )

                if not (perms.manage_webhooks):
                    issues.append(
                        t(_p(
                            'ui:timer_options|issues:cannot_make_webhooks',
                            "I cannot create the notification webhook (`MANAGE_WEBHOOKS`) in {channel}"
                        )).format(channel=channel.mention)
                    )
        return issues

    async def refresh_layout(self):
        if self.timer.owned:
            # Owned timers cannot change their voice channel, text channel, or manager role.
            await asyncio.gather(
                self.refresh_edit_button(),
                self.refresh_close_button(),
                self.refresh_voice_button(),
                self.refresh_delete_button(),
            )
            self.set_layout(
                (self.edit_button, self.voice_button, self.delete_button, self.close_button)
            )
        else:
            await asyncio.gather(
                self.refresh_edit_button(),
                self.refresh_close_button(),
                self.refresh_voice_button(),
                self.refresh_delete_button(),
                # self.refresh_voice_menu(),
                self.refresh_manage_role_menu(),
                self.refresh_notification_menu()
            )
            self.set_layout(
                # (self.voice_menu,),
                (self.notification_menu,),
                (self.manage_role_menu,),
                (self.edit_button, self.voice_button, self.delete_button, self.close_button)
            )

    async def reload(self):
        """
        Nothing to reload.
        """
        pass
