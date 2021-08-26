from meta import client, conf, log

import data  # noqa

import core # noqa

import modules  # noqa

# Initialise all modules
client.initialise_modules()

# Log readyness and execute
log("Initial setup complete, logging in", context='SETUP')
client.run(conf.bot['TOKEN'])
