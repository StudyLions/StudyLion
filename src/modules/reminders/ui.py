from typing import Optional, TYPE_CHECKING
import asyncio
import datetime as dt

import discord
from discord.ui.select import select, Select, SelectOption
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.text_input import TextInput, TextStyle

from meta import LionBot
from meta.errors import UserInputError
from utils.lib import utc_now, MessageArgs, parse_duration
from utils.ui import MessageUI, AButton, AsComponents, ConfigEditor

from . import babel, logger

_, _p, _np = babel._, babel._p, babel._np

if TYPE_CHECKING:
    from .cog import Reminders


class ReminderList(MessageUI):
    def __init__(self, bot: LionBot, user: discord.User, **kwargs):
        super().__init__(callerid=user.id, **kwargs)

        self.bot = bot
        self.user = user
        self.userid = user.id

        self.cog: 'Reminders' = bot.get_cog('Reminders')
        if self.cog is None:
            raise ValueError("Cannot initialise ReminderList without loaded Reminder cog.")

        # UI state
        self._reminders = []

    # ----- UI API -----
    # ----- UI Components -----
    # Clear button
    @button(label="CLEAR_BUTTON_PLACEHOLDER", style=ButtonStyle.red)
    async def clear_button(self, press: discord.Interaction, pressed: Button):
        t = self.bot.translator.t

        reminders = self._reminders
        embed = discord.Embed(
            title=t(_p('ui:reminderlist|button:clear|confirm|title', "Are You Sure?")),
            description=t(_np(
                'ui:reminderlist|button:clear|confirm|desc',
                "Are you sure you want to delete your `{count}` reminder?",
                "Are you sure you want to clear your `{count}` reminders?",
                len(reminders)
            )).format(count=len(reminders)),
            colour=discord.Colour.dark_orange()
        )

        @AButton(label=t(_p('ui:reminderlist|button:clear|confirm|button:yes', "Yes, clear my reminders")))
        async def confirm(interaction, pressed):
            await interaction.response.defer()
            reminders = await self.cog.data.Reminder.table.delete_where(userid=self.userid)
            await self.cog.talk_cancel(*(r['reminderid'] for r in reminders)).send(
                self.cog.executor_name, wait_for_reply=False
            )
            await press.edit_original_response(
                embed=discord.Embed(
                    description=t(_p(
                        'ui:reminderlist|button:clear|success|desc',
                        "Your reminders have been cleared!"
                    )),
                    colour=discord.Colour.brand_green()
                ),
                view=None
            )
            await pressed.view.close()
            await self.cog.dispatch_update_for(self.userid)

        @AButton(label=t(_p('ui:reminderlist|button:clear|confirm|button:cancel', "Cancel")))
        async def deny(interaction, pressed):
            await interaction.response.defer()
            await press.delete_original_response()
            await pressed.view.close()

        components = AsComponents(confirm, deny)
        await press.response.send_message(embed=embed, view=components, ephemeral=True)

    async def clear_button_refresh(self):
        self.clear_button.label = self.bot.translator.t(_p(
            'ui:reminderlist|button:clear|label',
            "Clear Reminders"
        ))

    # New reminder button
    @button(label="NEW_BUTTON_PLACEHOLDER", style=ButtonStyle.green)
    async def new_button(self, press: discord.Interaction, pressed: Button):
        """
        Pop up a modal for the user to enter new reminder information.
        """
        t = self.bot.translator.t
        if press.guild:
            lmember = await self.bot.core.lions.fetch_member(press.guild.id, press.user.id)
            timezone = lmember.timezone
        else:
            luser = await self.bot.core.lions.fetch_user(press.user.id)
            timezone = luser.timezone
        default = dt.datetime.now(tz=timezone).replace(hour=0, minute=0, second=0, microsecond=0)

        time_field = TextInput(
            label=t(_p(
                'ui:reminderlist|button:new|modal|field:time|label',
                "When would you like to be reminded?"
            )),
            placeholder=default.strftime('%Y-%m-%d %H:%M'),
            required=True,
            max_length=100,
        )

        interval_field = TextInput(
            label=t(_p(
                'ui:reminderlist|button:new|modal|field:repeat|label',
                "How often should the reminder repeat?"
            )),
            placeholder=t(_p(
                'ui:reminderlist|button:new|modal|field:repeat|placeholder',
                "1 day 10 hours 5 minutes (Leave empty for no repeat.)"
            )),
            required=False,
            max_length=100,
        )

        content_field = TextInput(
            label=t(_p(
                'ui:reminderlist|button:new|modal|field:content|label',
                "What should I remind you?"
            )),
            required=True,
            style=TextStyle.long,
            max_length=2000,
        )

        modal = ConfigEditor(
            time_field, interval_field, content_field,
            title=t(_p(
                'ui:reminderlist|button:new|modal|title',
                "Set a Reminder"
            ))
        )

        @modal.submit_callback()
        async def create_reminder(interaction: discord.Interaction):
            remind_at = await self.cog.parse_time_static(time_field.value, timezone)
            if intervalstr := interval_field.value:
                interval = parse_duration(intervalstr)
                if interval is None:
                    raise UserInputError(
                        t(_p(
                            'ui:reminderlist|button:new|modal|parse|error:interval',
                            "Cannot parse '{value}' as a duration."
                        )).format(value=intervalstr)
                    )
            else:
                interval = None

            message = await self._original.original_response()

            reminder = await self.cog.create_reminder(
                userid=self.userid,
                remind_at=remind_at,
                content=content_field.value,
                message_link=message.jump_url,
                interval=interval,
            )
            embed = reminder.set_response
            await interaction.response.send_message(embed=embed, ephemeral=True)

        await press.response.send_modal(modal)

    async def new_button_refresh(self):
        self.new_button.label = self.bot.translator.t(_p(
            'ui:reminderlist|button:new|label',
            "New Reminder"
        ))
        self.new_button.disabled = (len(self._reminders) >= 25)

    # Cancel menu
    @select(cls=Select, placeholder="CANCEL_REMINDER_PLACEHOLDER", min_values=0, max_values=1)
    async def cancel_menu(self, selection: discord.Interaction, selected):
        """
        Select a number of reminders to delete.
        """
        await selection.response.defer()
        if selected.values:
            # Hopefully this is a list of reminderids
            values = selected.values

            # Delete from data
            await self.cog.data.Reminder.table.delete_where(reminderid=values)

            # Send cancellation
            await self.cog.talk_cancel(*values).send(self.cog.executor_name, wait_for_reply=False)

            self.cog._user_reminder_cache.pop(self.userid, None)
            await self.refresh()

    async def cancel_menu_refresh(self):
        t = self.bot.translator.t
        self.cancel_menu.placeholder = t(_p(
            'ui:reminderlist|select:remove|placeholder',
            "Select to cancel"
        ))
        self.cancel_menu.options = [
            SelectOption(
                label=f"[{i}] {reminder.content[:50] + '...' * (len(reminder.content) > 50)}",
                value=reminder.reminderid,
                emoji=self.bot.config.emojis.getemoji('clock')
            )
            for i, reminder in enumerate(self._reminders, start=1)
        ]
        self.cancel_menu.min_values = 0
        self.cancel_menu.max_values = len(self._reminders)

    # ----- UI Flow -----
    async def refresh_layout(self):
        to_refresh = (
            self.cancel_menu_refresh(),
            self.new_button_refresh(),
            self.clear_button_refresh(),
        )
        await asyncio.gather(*to_refresh)

        if self._reminders:
            self.set_layout(
                (self.new_button, self.clear_button,),
                (self.cancel_menu,),
            )
        else:
            self.set_layout(
                (self.new_button,),
            )

    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        reminders = self._reminders

        if reminders:
            lines = []
            num_len = len(str(len(reminders)))
            for i, reminder in enumerate(reminders):
                lines.append(
                    "`[{:<{}}]` | {}".format(
                        i+1,
                        num_len,
                        reminder.formatted
                    )
                )
            description = '\n'.join(lines)

            embed = discord.Embed(
                description=description,
                colour=discord.Colour.orange(),
                timestamp=utc_now()
            ).set_author(
                name=t(_p(
                    'ui:reminderlist|embed:list|author',
                    "Your reminders"
                )),
                icon_url=self.user.avatar or self.user.default_avatar
            ).set_footer(
                text=t(_p(
                    'ui:reminderlist|embed:list|footer',
                    "Click a reminder to jump back to the context!"
                ))
            )
        else:
            embed = discord.Embed(
                title=t(_p(
                    'ui:reminderlist|embed:no_reminders|title',
                    "You have no reminders set!"
                )).format(
                    remindme=self.bot.core.cmd_name_cache['remindme'].mention,
                ),
                colour=discord.Colour.dark_orange(),
            )
            embed.add_field(
                name=t(_p(
                    'ui:reminderlist|embed|tips:name',
                    "Reminder Tips"
                )),
                value=t(_p(
                    'ui:reminderlist|embed|tips:value',
                    "- Use {at_cmd} to set a reminder at a known time (e.g. `at 10 am`).\n"
                    "- Use {in_cmd} to set a reminder in a certain time (e.g. `in 2 hours`).\n"
                    "- Both commands support repeating reminders using the `every` parameter.\n"
                    "- Remember to tell me your timezone with {timezone_cmd} if you haven't already!"
                )).format(
                    at_cmd=self.bot.core.mention_cmd('remindme at'),
                    in_cmd=self.bot.core.mention_cmd('remindme in'),
                    timezone_cmd=self.bot.core.mention_cmd('my timezone'),
                )
            )

        return MessageArgs(embed=embed)

    async def reload(self):
        self._reminders = await self.cog.get_reminders_for(self.userid)
