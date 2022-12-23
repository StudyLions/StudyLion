import importlib
from .. import drawing
from . import goals, leaderboard, stats, tasklist

from cmdClient import cmd, checks


@cmd("reloadgui",
     desc="Reload all GUI drawing modules.")
@checks.is_owner()
async def cmd_reload_gui(ctx):
    importlib.reload(drawing.goals)
    importlib.reload(drawing.leaderboard)
    importlib.reload(drawing.profile)
    importlib.reload(drawing.stats)
    importlib.reload(drawing.tasklist)
    importlib.reload(drawing.weekly)
    importlib.reload(drawing.monthly)

    importlib.reload(goals)
    importlib.reload(leaderboard)
    importlib.reload(stats)
    importlib.reload(tasklist)
    await ctx.reply("GUI plugin reloaded.")
