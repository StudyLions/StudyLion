import polib, re, os
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

def is_name_entry(ctx):
    if not ctx:
        return False
    if '|' not in ctx:
        return ctx.startswith(('cmd:', 'group:', 'command'))
    last = ctx.split('|')[-1]
    return last.startswith('param:') and not last.endswith('desc')

def is_valid(name):
    if not name or len(name) > 32:
        return False
    if name != name.lower():
        return False
    return bool(re.match(r'^[\w-]{1,32}$', name))

problems = []
for loc_dir in sorted(os.listdir('locales')):
    lc = os.path.join('locales', loc_dir, 'LC_MESSAGES')
    if not os.path.isdir(lc):
        continue
    for f in sorted(os.listdir(lc)):
        if not f.endswith('.po'):
            continue
        try:
            po = polib.pofile(os.path.join(lc, f))
        except:
            continue
        for e in po:
            if not e.msgctxt or not e.msgstr:
                continue
            if is_name_entry(e.msgctxt) and not is_valid(e.msgstr):
                problems.append((loc_dir, f, e.msgctxt, e.msgid, e.msgstr))

print(f"Found {len(problems)} invalid command/param names:")
for loc, f, ctx, mid, mstr in problems[:30]:
    print(f"  {loc}/{f}: [{ctx}] '{mid}' => '{mstr}'")
if len(problems) > 30:
    print(f"  ... and {len(problems)-30} more")
