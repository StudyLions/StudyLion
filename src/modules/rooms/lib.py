import discord
import re

# --- AI-MODIFIED (2026-03-22) ---
# Purpose: Dashboard URL constants for link buttons in Discord room messages
from meta import WEBSITE_URL
ROOM_DASHBOARD_URL = f"{WEBSITE_URL}/dashboard/rooms"
ROOM_ADMIN_URL_TEMPLATE = WEBSITE_URL + "/dashboard/servers/{guild_id}/rooms"
# --- END AI-MODIFIED ---


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
    manage_webhooks=True,
    manage_channels=True,
    manage_messages=True,
    move_members=True,
)
bot_overwrite = discord.PermissionOverwrite.from_pair(*owner_overwrite.pair())

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Overwrite for the admin-configured room moderator role (view, connect, send msgs)
mod_role_overwrite = discord.PermissionOverwrite(
    view_channel=True,
    connect=True,
    send_messages=True,
    read_message_history=True,
)
# --- END AI-MODIFIED ---
