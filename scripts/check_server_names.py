import polib, os, re
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

for locale in ["de", "vi", "fr", "es_ES", "tr", "pl"]:
    for domain in ["config", "babel", "Pomodoro", "rolemenus", "statistics",
                    "user_config", "shop", "meta", "voice-tracker", "moderation",
                    "schedule", "rooms", "tasklist", "member_admin", "economy",
                    "lion-core", "sysadmin", "exec", "reminders", "video",
                    "settings_base", "text-tracker"]:
        path = f"locales/{locale}/LC_MESSAGES/{domain}.po"
        if not os.path.exists(path):
            continue
        po = polib.pofile(path)
        for e in po:
            if not e.msgctxt or not e.msgstr:
                continue
            ctx = e.msgctxt
            is_name = False
            if '|' not in ctx:
                if ctx.startswith(('cmd:', 'group:', 'command')):
                    is_name = True
            else:
                last = ctx.split('|')[-1]
                if last.startswith('param:') and 'desc' not in last:
                    is_name = True
            if not is_name:
                continue
            if re.match(r'^[a-z0-9_-]+$', e.msgid):
                s = e.msgstr
                if s != s.lower() or ' ' in s or not re.match(r'^[\w-]+$', s, re.UNICODE):
                    print(f"  {locale}/{domain}: [{ctx}] '{e.msgid}' => '{s}'")
