import gettext, os
os.chdir(os.path.join(os.path.dirname(__file__), '..'))
locales = ["de", "fr", "ja", "es_ES", "ko", "bg", "pt_BR", "tr", "zh_CN", "hi"]
domains = ["economy", "shop", "ranks", "tasklist", "meta", "base", "topgg",
           "babel", "config", "moderation", "statistics", "reminders",
           "rolemenus", "rooms", "schedule", "Pomodoro", "voice-tracker",
           "settings_base", "lion-core", "sysadmin", "text-tracker", "video",
           "wards", "member_admin", "utils", "user_config", "exec", "test",
           "sponsors", "timer-gui", "goals-gui", "weekly-gui", "profile-gui",
           "monthly-gui", "leaderboard-gui", "stats-gui", "core_config"]
for loc in locales:
    loaded = failed = 0
    fail_doms = []
    for dom in domains:
        try:
            t = gettext.translation(dom, "locales/", languages=[loc])
            loaded += 1
        except OSError:
            failed += 1
            fail_doms.append(dom)
    status = "OK" if failed == 0 else f"MISSING: {', '.join(fail_doms)}"
    print(f"{loc}: {loaded}/{len(domains)} loaded  {status}")
