import discord

from cmdClient import cmdClient

from meta import client, conf
from .lib import guide_link, animation_link


message = """
Thank you for inviting me to your community.
Get started by typing `{prefix}help` to see my commands, and `{prefix}config info` \
    to read about my configuration options!

To learn how to configure me and use all of my features, \
    make sure to [click here]({guide_link}) to read our full setup guide.

Remember, if you need any help configuring me, \
    want to suggest a feature, report a bug and stay updated, \
    make sure to join our main support and study server by [clicking here]({support_link}).

Best of luck with your studies!

""".format(
    guide_link=guide_link,
    support_link=conf.bot.get('support_link'),
    prefix=client.prefix
)


@client.add_after_event('guild_join', priority=0)
async def post_join_message(client: cmdClient, guild: discord.Guild):
    if (channel := guild.system_channel) and channel.permissions_for(guild.me).embed_links:
        embed = discord.Embed(
            description=message
        )
        embed.set_author(
            name="Hello! My name is Leo",
            icon_url="https://cdn.discordapp.com/emojis/933610591459872868.webp"
        )
        embed.set_image(url=animation_link)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            # Something went wrong sending the hi message
            # Not much we can do about this
            pass
