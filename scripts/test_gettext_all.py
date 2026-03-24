import gettext, os
os.chdir(os.path.join(os.path.dirname(__file__), '..'))
locales = ["bg","cs","da","de","el","es_ES","fi","fr","hi","hr","hu","id","it",
           "ja","ko","lt","nl","no","pl","pt_BR","ro","ru","sv_SE","th","tr",
           "uk","vi","zh_CN","zh_TW","he_IL","ceaser"]
domains = ["economy","shop","ranks","meta","base","topgg","babel","config",
           "moderation","statistics","reminders","rolemenus","rooms","schedule",
           "Pomodoro","voice-tracker","settings_base","lion-core","sysadmin",
           "text-tracker","video","wards","member_admin","utils","user_config",
           "exec","test","sponsors","timer-gui","goals-gui","weekly-gui",
           "profile-gui","monthly-gui","leaderboard-gui","stats-gui",
           "core_config","tasklist"]
total_ok = total_fail = 0
failed_locales = []
for loc in locales:
    ok = fail = 0
    for dom in domains:
        try:
            gettext.translation(dom, "locales/", languages=[loc])
            ok += 1
        except OSError:
            fail += 1
    total_ok += ok
    total_fail += fail
    if fail > 0:
        failed_locales.append(f"{loc}: {ok}/{len(domains)} ({fail} failed)")
    else:
        print(f"{loc}: {ok}/{len(domains)} OK")
if failed_locales:
    print("--- FAILURES ---")
    for f in failed_locales:
        print(f)
print(f"TOTAL: {total_ok} loaded, {total_fail} failed out of {len(locales)*len(domains)}")
