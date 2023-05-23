import discord
import re


def parse_members(memberstr: str) -> list[int]:
    """
    Parse a mixed list of ids and mentions into a list of memberids.
    """
    if memberstr:
        memberids = [int(x) for x in re.findall(r'[<@!\s]*([0-9]{15,20})[>\s,]*', memberstr)]
    else:
        memberids = []
    return memberids


owner_overwrite = discord.PermissionOverwrite(
    view_channel=True,
    manage_channels=True,
    manage_webhooks=True,
    attach_files=True,
    embed_links=True,
    add_reactions=True,
    manage_messages=True,
    create_public_threads=True,
    create_private_threads=True,
    manage_threads=True,
    connect=True,
    speak=True,
    stream=True,
    use_application_commands=True,
    use_embedded_activities=True,
    move_members=True,
    external_emojis=True
)
member_overwrite = discord.PermissionOverwrite(
    view_channel=True,
    send_messages=True,
    connect=True,
    speak=True,
    stream=True
)
