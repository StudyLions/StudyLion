this_package = 'modules'

active = [
    '.sysadmin',
    '.config',
    '.economy',
    '.reminders',
    '.shop',
    '.tasklist',
    '.statistics',
    '.test',
]


async def setup(bot):
    for ext in active:
        await bot.load_extension(ext, package=this_package)
