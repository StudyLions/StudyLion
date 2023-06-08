# !/bin/python3

import sys
import os
import tracemalloc
import asyncio
import logging


sys.path.insert(0, os.path.join(os.getcwd()))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))

tracemalloc.start()
event_loop = asyncio.get_event_loop()


def loop_exception_handler(loop, context):
    print(context)
    task: asyncio.Task = context.get('task', None)
    if task is not None:
        addendum = f"<Task name='{task.name}' stack='{task.get_stack()}'>"
        message = context.get('message', '')
        context['message'] = ' '.join((message, addendum))
    loop.default_exception_handler(context)


event_loop.set_exception_handler(loop_exception_handler)
event_loop.set_debug(enabled=True)


if __name__ == '__main__':
    from bot import _main
    _main()
