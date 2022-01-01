import argparse

from constants import CONFIG_FILE

# ------------------------------
# Parsed commandline arguments
# ------------------------------
parser = argparse.ArgumentParser()
parser.add_argument('--conf',
                    dest='config',
                    default=CONFIG_FILE,
                    help="Path to configuration file.")
parser.add_argument('--shard',
                    dest='shard',
                    default=None,
                    type=int,
                    help="Shard number to run, if applicable.")

args = parser.parse_args()
