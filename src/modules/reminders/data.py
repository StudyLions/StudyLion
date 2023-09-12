import discord

from data import RowModel, Registry
from data.columns import Integer, String, Timestamp, Bool

from babel import ctx_translator
from utils.lib import strfdur
from . import babel


_, _p, _np = babel._, babel._p, babel._np


class ReminderData(Registry, name='reminders'):
    class Reminder(RowModel):
        """
        Model representing a single reminder.
        Since reminders are likely to change across shards,
        does not use an explicit reference cache.

        Schema
        ------
        CREATE TABLE reminders(
            reminderid SERIAL PRIMARY KEY,
            userid BIGINT NOT NULL REFERENCES user_config(userid) ON DELETE CASCADE,
            remind_at TIMESTAMPTZ NOT NULL,
            content TEXT NOT NULL,
            message_link TEXT,
            interval INTEGER,
            created_at TIMESTAMP DEFAULT (now() at time zone 'utc'),
            title TEXT,
            footer TEXT
        );
        CREATE INDEX reminder_users ON reminders (userid);
        """
        _tablename_ = 'reminders'

        reminderid = Integer(primary=True)

        userid = Integer()  # User which created the reminder
        remind_at = Timestamp()  # Time when the reminder should be executed
        content = String()  # Content the user gave us to remind them
        message_link = String()  # Link to original confirmation message, for context
        interval = Integer()  # Repeat interval, if applicable
        created_at = Timestamp()  # Time when this reminder was originally created
        title = String()  # Title of the final reminder embed, only set in automated reminders
        footer = String()  # Footer of the final reminder embed, only set in automated reminders
        failed = Bool()  # Whether the reminder was already attempted and failed

        @property
        def timestamp(self) -> int:
            """
            Time when this reminder should be executed (next) as an integer timestamp.
            """
            return int(self.remind_at.timestamp())

        @property
        def set_response(self) -> discord.Embed:
            t = ctx_translator.get().t
            embed = discord.Embed(
                title=t(_p(
                    'reminder_set|title',
                    "Reminder Set!"
                )),
                description=t(_p(
                    'reminder_set|desc',
                    "At {timestamp} I will remind you about:\n"
                    "> {content}"
                )).format(
                    timestamp=discord.utils.format_dt(self.remind_at),
                    content=self.content,
                )[:2048],
                colour=discord.Colour.brand_green(),
            )
            if self.interval:
                embed.add_field(
                    name=t(_p(
                        'reminder_set|field:repeat|name',
                        "Repeats"
                    )),
                    value=t(_p(
                        'reminder_set|field:repeat|value',
                        "This reminder will repeat every `{interval}` (after the first reminder)."
                    )).format(interval=strfdur(self.interval, short=False)),
                    inline=False
                )
            return embed

        @property
        def embed(self) -> discord.Embed:
            t = ctx_translator.get().t

            embed = discord.Embed(
                title=self.title or t(_p('reminder|embed', "You asked me to remind you!")),
                colour=discord.Colour.orange(),
                description=self.content,
                timestamp=self.remind_at
            )

            if self.message_link:
                embed.add_field(
                    name=t(_p('reminder|embed', "Context?")),
                    value="[{click}]({link})".format(
                        click=t(_p('reminder|embed', "Click Here")),
                        link=self.message_link
                    )
                )

            if self.interval:
                embed.add_field(
                    name=t(_p('reminder|embed', "Next reminder")),
                    value=f"<t:{self.timestamp + self.interval}:R>"
                )

            if self.footer:
                embed.set_footer(text=self.footer)

            return embed

        @property
        def formatted(self):
            """
            Single-line string format for the reminder, intended for an embed.
            """
            t = ctx_translator.get().t
            content = self.content
            trunc_content = content[:50] + '...' * (len(content) > 50)

            if interval := self.interval:
                if not interval % (24 * 60 * 60):
                    # Exact day case
                    days = interval // (24 * 60 * 60)
                    repeat = t(_np(
                        'reminder|formatted|interval',
                        "Every day",
                        "Every `{days}` days",
                        days
                    )).format(days=days)
                elif not interval % (60 * 60):
                    # Exact hour case
                    hours = interval // (60 * 60)
                    repeat = t(_np(
                        'reminder|formatted|interval',
                        "Every hour",
                        "Every `{hours}` hours",
                        hours
                    )).format(hours=hours)
                else:
                    # Inexact interval, e.g 10m or 1h 10m.
                    # Use short duration format
                    repeat = t(_p(
                        'reminder|formatted|interval',
                        "Every `{duration}`"
                    )).format(duration=strfdur(interval))

                repeat = f"({repeat})"
            else:
                repeat = ""

            return "<t:{timestamp}:R>, [{content}]({jump_link}) {repeat}".format(
                jump_link=self.message_link,
                content=trunc_content,
                timestamp=self.timestamp,
                repeat=repeat
            )
