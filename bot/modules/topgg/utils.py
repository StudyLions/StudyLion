import discord
import datetime

from meta import sharding
from meta import conf
from meta.client import client
from utils.lib import utc_now
from settings.setting_types import Integer

from modules.reminders.reminder import Reminder
from modules.reminders.data import reminders

from . import data as db
from data.conditions import GEQ

topgg_upvote_link = 'https://top.gg/bot/889078613817831495/vote'
remainder_content = (
    "You can now vote again on top.gg!\n"
    "Click [here]({}) to vote, thank you for the support!"
).format(topgg_upvote_link)

lion_loveemote = conf.emojis.getemoji('lionlove')
lion_yayemote = conf.emojis.getemoji('lionyay')


def get_last_voted_timestamp(userid: Integer):
    """
    Will return None if user has not voted in [-12.5hrs till now]
    else will return a Tuple containing timestamp of when exactly she voted
    """
    return db.topggvotes.select_one_where(
        userid=userid,
        select_columns="boostedTimestamp",
        boostedTimestamp=GEQ(utc_now() - datetime.timedelta(hours=12.5)),
        _extra="ORDER BY boostedTimestamp DESC LIMIT 1"
    )


def create_remainder(userid):
    """
    Checks if a remainder is already running (immaterial of remind_at time)
    If no remainder exists creates a new remainder and schedules it
    """
    if not reminders.select_one_where(
        userid=userid,
        content=remainder_content,
        _extra="ORDER BY remind_at DESC LIMIT 1"
    ):
        last_vote_time = get_last_voted_timestamp(userid)

        # if no, Create reminder
        reminder = Reminder.create(
            userid=userid,
            # TODO using content as a selector is not a good method
            content=remainder_content,
            message_link=None,
            interval=None,
            title="Your boost is now available! {}".format(lion_yayemote),
            footer="Use `{}vote_reminder off` to stop receiving reminders.".format(client.prefix),
            remind_at=(
                last_vote_time[0] + datetime.timedelta(hours=12.5)
                if last_vote_time else
                utc_now() + datetime.timedelta(minutes=5)
            )
            # remind_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=2)
        )

        # Schedule reminder
        if sharding.shard_number == 0:
            reminder.schedule()


async def send_user_dm(userid):
    # Send the message, if possible
    if not (user := client.get_user(userid)):
        try:
            user = await client.fetch_user(userid)
        except discord.HTTPException:
            pass
    if user:
        try:
            embed = discord.Embed(
                title="Thank you for supporting our bot on Top.gg! {}".format(lion_yayemote),
                description=(
                    "By voting every 12 hours you will allow us to reach and help "
                    "even more students all over the world.\n"
                    "Thank you for supporting us, enjoy your LionCoins boost!"
                ),
                colour=discord.Colour.orange()
            ).set_image(
                url="https://cdn.discordapp.com/attachments/908283085999706153/932737228440993822/lion-yay.png"
            )

            await user.send(embed=embed)
        except discord.HTTPException:
            # Nothing we can really do here. Maybe tell the user about their reminder next time?
            pass
