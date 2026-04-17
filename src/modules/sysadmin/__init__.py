from babel.translator import LocalBabel
babel = LocalBabel('sysadmin')


async def setup(bot):
    from .exec_cog import Exec
    from .blacklists import Blacklists
    from .guild_log import GuildLog
    from .presence import PresenceCtrl
    # --- AI-MODIFIED (2026-04-17) ---
    # Purpose: Register /leo backfill_names admin command for one-time
    # backfill of NULL display_name / username / avatar_hash rows.
    from .name_backfill import NameBackfill
    # --- END AI-MODIFIED ---

    from .dash import LeoSettings
    await bot.add_cog(LeoSettings(bot))

    await bot.add_cog(Blacklists(bot))
    await bot.add_cog(Exec(bot))
    await bot.add_cog(GuildLog(bot))
    await bot.add_cog(PresenceCtrl(bot))
    # --- AI-MODIFIED (2026-04-17) ---
    # Purpose: NameBackfill must load AFTER LeoSettings so it can
    # crossload its placeholder leo_group into the real one.
    await bot.add_cog(NameBackfill(bot))
    # --- END AI-MODIFIED ---
