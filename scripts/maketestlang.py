import os
import string
import polib

templates = os.path.join('locales', 'templates')
test_target = os.path.join('locales', 'ceaser', 'LC_MESSAGES')


def translate_string(msgid: str) -> str:
    tokens = []
    lifted = False
    for c in msgid:
        if c in ('{', '}'):
            lifted = not lifted
        elif not lifted and c.isalpha():
            if c.isupper():
                letters = string.ascii_uppercase
            else:
                letters = string.ascii_lowercase
            index = letters.index(c)
            c = letters[(index + 1) % len(letters)]
        tokens.append(c)
    translated = ''.join(tokens)
    return translated


def translate_entry(entry: polib.POEntry):
    if entry.msgctxt and ('regex' in entry.msgctxt):
        # Ignore
        ...
    else:
        if entry.msgid_plural:
            entry.msgstr_plural = {
                '0': translate_string(entry.msgid),
                '1': translate_string(entry.msgid_plural)
            }
        elif entry.msgid:
            entry.msgstr = translate_string(entry.msgid)


def process_pot(domain, path):
    print(f"Processing pot for {domain}")
    entries = 0
    po = polib.pofile(path, encoding="UTF-8")
    po.metadata = {
        'Project-Id-Version': '1.0',
        'Report-Msgid-Bugs-To': 'you@example.com',
        'POT-Creation-Date': '2007-10-18 14:00+0100',
        'PO-Revision-Date': '2007-10-18 14:00+0100',
        'Last-Translator': 'you <you@example.com>',
        'Language-Team': 'English <yourteam@example.com>',
        'MIME-Version': '1.0',
        'Content-Type': 'text/plain; charset=utf-8',
        'Content-Transfer-Encoding': '8bit',
    }
    for entry in po.untranslated_entries():
        entries += 1
        translate_entry(entry)
    # Now save
    targetpo = os.path.join(test_target, f"{domain}.po")
    targetmo = os.path.join(test_target, f"{domain}.mo")
    po.save(targetpo)
    po.save_as_mofile(targetmo)
    print(f"Processed {entries} from POT {domain}.")
    return entries


def process_all():
    total = 0
    for file in os.scandir(templates):
        if file.name.endswith('pot'):
            print(f"Processing pot: {file.name[:-4]}")
            total += process_pot(file.name[:-4], file.path)
    print(f"Total strings: {total}")


if __name__ == '__main__':
    process_all()
