this_package = 'modules'

active = [
    '.sysadmin',
    '.test',
    '.reminders'
]


async def setup(bot):
    for ext in active:
        await bot.load_extension(ext, package=this_package)
