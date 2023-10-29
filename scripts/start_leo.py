# !/bin/python3

import sys
import os

sys.path.insert(0, os.path.join(os.getcwd()))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))


if __name__ == '__main__':
    from bot import _main
    _main()
