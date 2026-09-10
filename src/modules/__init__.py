this_package = 'modules'

active = [
    # --- AI-MODIFIED (2026-09-10) ---
    # Purpose: Show the community fundraiser on user-requested responses.
    '.fundraiser',
    # --- END AI-MODIFIED ---
    '.sysadmin',
    '.config',
    '.user_config',
    '.skins',
    '.schedule',
    '.economy',
    '.ranks',
    '.reminders',
    '.shop',
    '.statistics',
    '.pomodoro',
    '.rooms',
    '.tasklist',
    '.rolemenus',
    '.member_admin',
    '.moderation',
    '.video_channels',
    # --- AI-MODIFIED (2026-03-31) ---
    # Purpose: Screen share enforcement module (mirrors video_channels for self_stream)
    '.screen_channels',
    # --- END AI-MODIFIED ---
    '.meta',
    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Disabled sponsor module per owner request
    # '.sponsors',
    # --- END AI-MODIFIED ---
    '.topgg',
    '.premium',
    '.test',
    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Added LionGotchi virtual pet module
    '.liongotchi',
    # --- END AI-MODIFIED ---
    # --- AI-MODIFIED (2026-03-20) ---
    # Purpose: Automated test harness (loads only if config enables it)
    '.test_harness',
    # --- END AI-MODIFIED ---
    # --- AI-MODIFIED (2026-03-21) ---
    # Purpose: Leaderboard auto-post module
    '.leaderboard_autopost',
    # --- END AI-MODIFIED ---
    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: Sticky messages premium feature (dashboard-only config)
    '.sticky_messages',
    # --- END AI-MODIFIED ---
    # --- AI-MODIFIED (2026-03-31) ---
    # Purpose: Shared kanban boards (collaborative task lists)
    '.shared_tasklist',
    # --- END AI-MODIFIED ---
    # --- AI-MODIFIED (2026-04-06) ---
    # Purpose: Anti AFK System premium feature (website-only config)
    '.anti_afk',
    # --- END AI-MODIFIED ---
    # --- AI-MODIFIED (2026-04-17) ---
    # Purpose: Name sync listeners (on_member_join/update, on_user_update)
    # so the dashboard members list keeps real names instead of placeholders.
    '.name_sync',
    # --- END AI-MODIFIED ---
    # --- AI-MODIFIED (2026-04-30) ---
    # Purpose: "Feature Your Server" website integration. Loads HTTP
    # listener (invite create + review notify) on shard 0; idle elsewhere.
    '.serverlisting',
    # --- END AI-MODIFIED ---
    # --- AI-MODIFIED (2026-05-15) ---
    # Purpose: Gift notification poller. Reads pending_notifications
    # rows written by the website's Stripe gift webhooks and delivers
    # Discord DMs to recipients / senders / guild admins. Shard 0 only.
    '.gift_notifications',
    # --- END AI-MODIFIED ---
]


async def setup(bot):
    for ext in active:
        await bot.load_extension(ext, package=this_package)
