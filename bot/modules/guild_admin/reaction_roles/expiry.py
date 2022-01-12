import logging
import traceback
import asyncio
import discord

from meta import client
from utils.lib import utc_now
from settings import GuildSettings

from .module import module
from .data import reaction_role_expiring

_expiring = {}
_wakeup_event = asyncio.Event()


# TODO: More efficient data structure for min optimisation, e.g. pre-sorted with bisection insert


# Public expiry interface
def schedule_expiry(guildid, userid, roleid, expiry, reactionid=None):
    """
    Schedule expiry of the given role for the given member at the given time.
    This will also cancel any existing expiry for this member, role pair.
    """
    reaction_role_expiring.delete_where(
        guildid=guildid,
        userid=userid,
        roleid=roleid,
    )
    reaction_role_expiring.insert(
        guildid=guildid,
        userid=userid,
        roleid=roleid,
        expiry=expiry,
        reactionid=reactionid
    )
    key = (guildid, userid, roleid)
    _expiring[key] = expiry.timestamp()
    _wakeup_event.set()


def cancel_expiry(*key):
    """
    Cancel expiry for the given member and role, if it exists.
    """
    guildid, userid, roleid = key
    reaction_role_expiring.delete_where(
        guildid=guildid,
        userid=userid,
        roleid=roleid,
    )
    if _expiring.pop(key, None) is not None:
        # Wakeup the expiry tracker for recalculation
        _wakeup_event.set()


def _next():
    """
    Calculate the next member, role pair to expire.
    """
    if _expiring:
        key, _ = min(_expiring.items(), key=lambda pair: pair[1])
        return key
    else:
        return None


async def _expire(key):
    """
    Execute reaction role expiry for the given member and role.
    This removes the role and logs the removal if applicable.
    If the user is no longer in the guild, it removes the role from the persistent roles instead.
    """
    guildid, userid, roleid = key
    guild = client.get_guild(guildid)
    if guild:
        role = guild.get_role(roleid)
        if role:
            member = guild.get_member(userid)
            if member:
                log = GuildSettings(guildid).event_log.log
                if role in member.roles:
                    # Remove role from member, and log if applicable
                    try:
                        await member.remove_roles(
                            role,
                            atomic=True,
                            reason="Expiring temporary reaction role."
                        )
                    except discord.HTTPException:
                        log(
                            "Failed to remove expired reaction role {} from {}.".format(
                                role.mention,
                                member.mention
                            ),
                            colour=discord.Colour.red(),
                            title="Could not remove expired Reaction Role!"
                        )
                    else:
                        log(
                            "Removing expired reaction role {} from {}.".format(
                                role.mention,
                                member.mention
                            ),
                            title="Reaction Role expired!"
                        )
            else:
                # Remove role from stored persistent roles, if existent
                client.data.past_member_roles.delete_where(
                    guildid=guildid,
                    userid=userid,
                    roleid=roleid
                )
    reaction_role_expiring.delete_where(
        guildid=guildid,
        userid=userid,
        roleid=roleid
    )


async def _expiry_tracker(client):
    """
    Track and launch role expiry.
    """
    while True:
        try:
            key = _next()
            diff = _expiring[key] - utc_now().timestamp() if key else None
            await asyncio.wait_for(_wakeup_event.wait(), timeout=diff)
        except asyncio.TimeoutError:
            # Timeout means next doesn't exist or is ready to expire
            if key and key in _expiring and _expiring[key] <= utc_now().timestamp() + 1:
                _expiring.pop(key)
                asyncio.create_task(_expire(key))
        except Exception:
            # This should be impossible, but catch and log anyway
            client.log(
                "Exception occurred while tracking reaction role expiry. Exception traceback follows.\n{}".format(
                    traceback.format_exc()
                ),
                context="REACTION_ROLE_EXPIRY",
                level=logging.ERROR
            )
        else:
            # Wakeup event means that we should recalculate next
            _wakeup_event.clear()


@module.launch_task
async def launch_expiry_tracker(client):
    """
    Launch the role expiry tracker.
    """
    asyncio.create_task(_expiry_tracker(client))
    client.log("Reaction role expiry tracker launched.", context="REACTION_ROLE_EXPIRY")


@module.init_task
def load_expiring_roles(client):
    """
    Initialise the expiring reaction role map, and attach it to the client.
    """
    rows = reaction_role_expiring.select_where()
    _expiring.clear()
    _expiring.update({(row['guildid'], row['userid'], row['roleid']): row['expiry'].timestamp() for row in rows})
    client.objects['expiring_reaction_roles'] = _expiring
    if _expiring:
        client.log(
            "Loaded {} expiring reaction roles.".format(len(_expiring)),
            context="REACTION_ROLE_EXPIRY"
        )
