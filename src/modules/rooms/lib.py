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


member_overwrite = discord.PermissionOverwrite(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    attach_files=True,
    embed_links=True,
    add_reactions=True,
    connect=True,
    speak=True,
    stream=True,
    use_application_commands=True,
    use_embedded_activities=True,
    external_emojis=True,
)
owner_overwrite = discord.PermissionOverwrite.from_pair(*member_overwrite.pair())
owner_overwrite.update(
    manage_channels=True,
    manage_webhooks=True,
    manage_messages=True,
    create_public_threads=True,
    create_private_threads=True,
    manage_threads=True,
    move_members=True,
)
bot_overwrite = discord.PermissionOverwrite.from_pair(*owner_overwrite.pair())
bot_overwrite.update(
    **dict(owner_overwrite),
    manage_permissions=True,
)
