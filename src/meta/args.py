import argparse

from constants import CONFIG_FILE

# ------------------------------
# Parsed commandline arguments
# ------------------------------
parser = argparse.ArgumentParser()
parser.add_argument(
    '--conf',
    dest='config',
    default=CONFIG_FILE,
    help="Path to configuration file."
)
parser.add_argument(
    '--shard',
    dest='shard',
    default=None,
    type=int,
    help="Shard number to run, if applicable."
)
parser.add_argument(
    '--host',
    dest='host',
    default='127.0.0.1',
    help="IP address to run the app listener on."
)
parser.add_argument(
    '--port',
    dest='port',
    default='5001',
    help="Port to run the app listener on."
)

args = parser.parse_args()
