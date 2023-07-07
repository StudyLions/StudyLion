# !/bin/python3

from datetime import datetime
import sys
import os
import tracemalloc
import asyncio
import logging
import yappi
import aiomonitor


sys.path.insert(0, os.path.join(os.getcwd()))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))

tracemalloc.start()


def loop_exception_handler(loop, context):
    print(context)
    task: asyncio.Task = context.get('task', None)
    if task is not None:
        addendum = f"<Task name='{task.get_name()}' stack='{task.get_stack()}'>"
        message = context.get('message', '')
        context['message'] = ' '.join((message, addendum))
    loop.default_exception_handler(context)


def main():
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(loop_exception_handler)
    loop.set_debug(enabled=True)

    yappi.set_clock_type("WALL")
    with yappi.run():
        with aiomonitor.start_monitor(loop):
            from bot import _main
            try:
                _main()
            finally:
                yappi.get_func_stats().save('logs/callgrind.out.' + datetime.utcnow().isoformat(), 'CALLGRIND')


if __name__ == '__main__':
    main()
