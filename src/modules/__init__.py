this_package = 'modules'

active = [
    '.sysadmin',
    '.config',
    '.user_config',
    '.economy',
    '.ranks',
    '.reminders',
    '.shop',
    '.tasklist',
    '.statistics',
    '.pomodoro',
    '.rooms',
    '.meta',
    '.test',
]


async def setup(bot):
    for ext in active:
        await bot.load_extension(ext, package=this_package)
