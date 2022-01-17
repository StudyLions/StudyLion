from email.mime import image
import discord
import datetime
from meta.client import client
from bot.settings.setting_types import Integer
from meta import sharding

from modules.reminders.reminder import Reminder
from modules.reminders.data import reminders

from . import data as db
from data.conditions import GEQ

topgg_upvote_link = 'https://top.gg/bot/889078613817831495/vote'
remainder_content = "You can now Upvote me again in Top.gg. \nMy Upvote link is {}".format(topgg_upvote_link)

# Will return None if user has not voted in [-12.5hrs till now]
# else will return a Tuple containing timestamp of when exactly she voted
def get_last_voted_timestamp(userid: Integer):
    return db.topggvotes.select_one_where(
        userid=userid,
        select_columns="boostedTimestamp", 
        boostedTimestamp=GEQ(datetime.datetime.utcnow() - datetime.timedelta(hours=12.5)),
        _extra="ORDER BY boostedTimestamp DESC LIMIT 1"
    )

# Checks if a remainder is already running (immaterial of remind_at time)
# If no remainder exists creates a new remainder and schedules it
def create_remainder(userid):
    if not reminders.select_one_where(
        userid=userid,
        content=remainder_content,
        _extra="ORDER BY remind_at DESC LIMIT 1"
    ):
        last_vote_time = get_last_voted_timestamp(userid)

        # if no, Create reminder
        reminder = Reminder.create(
            userid=userid,
            content=remainder_content,
            message_link=None,
            interval=None,
            #remind_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=2)
            remind_at=last_vote_time[0] + datetime.timedelta(hours=12.5) if last_vote_time else datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
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
            embed=discord.Embed(
                title="Thankyou.",
                description='Thankyou for upvoting.',
                colour=discord.Colour.orange()
            ).set_image(
                url="https://cdn.discordapp.com/attachments/908283085999706153/930559064323268618/unknown.png"
            )

            await user.send(embed=embed)
        except discord.HTTPException:
            # Nothing we can really do here. Maybe tell the user about their reminder next time?
            pass
