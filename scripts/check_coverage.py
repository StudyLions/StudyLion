import os, re
locales_dir = 'locales'
locales = ['de','fr','es_ES','ja','ko','ru','zh_CN','pt_BR','tr','he_IL','bg','it','pl','vi','hi','cs','da','nl','sv_SE','th']
for locale in locales:
    total = 0; filled = 0
    ldir = os.path.join(locales_dir, locale, 'LC_MESSAGES')
    if not os.path.isdir(ldir): continue
    for f in os.listdir(ldir):
        if not f.endswith('.po'): continue
        with open(os.path.join(ldir, f), 'r', encoding='utf-8') as fh:
            content = fh.read()
        blocks = re.split(r'\n\n+', content)
        for block in blocks:
            if 'msgid ""' in block and 'msgstr ""' in block and 'Project-Id-Version' in block:
                continue
            msgid_match = re.search(r'msgid "(.+)"', block)
            msgstr_match = re.search(r'msgstr "(.+)"', block)
            if msgid_match:
                total += 1
                if msgstr_match:
                    filled += 1
    pct = (filled/total*100) if total else 0
    print(f'{locale}: {filled}/{total} ({pct:.0f}%)')
