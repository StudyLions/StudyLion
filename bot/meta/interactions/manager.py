import asyncio
import logging
from datetime import datetime, timedelta


class InteractionManager:
    def __init__(self, timeout=600, extend=None):
        self.futures = []
        self.self_futures = []

        self.cleanup_function = self._cleanup
        self.timeout_function = self._timeout
        self.close_function = self._close

        self.timeout = timeout
        self.extend = extend or timeout
        self.expires_at = None

        self.cleaned_up = asyncio.Event()

    async def _timeout_loop(self):
        diff = (self.expires_at - datetime.now()).total_seconds()
        while True:
            try:
                await asyncio.sleep(diff)
            except asyncio.CancelledError:
                break
            diff = (self.expires_at - datetime.now()).total_seconds()
            if diff <= 0:
                asyncio.create_task(self.run_timeout())
                break

    def extend_timeout(self):
        new_expiry = max(datetime.now() + timedelta(seconds=self.extend), self.expires_at)
        self.expires_at = new_expiry

    async def wait(self):
        """
        Wait until the manager is "done".
        That is, until all the futures are done, or `closed` is set.
        """
        closed_task = asyncio.create_task(self.cleaned_up.wait())
        futures_task = asyncio.create_task(asyncio.wait(self.futures))
        await asyncio.wait((closed_task, futures_task), return_when=asyncio.FIRST_COMPLETED)

    async def __aenter__(self):
        if self.timeout is not None:
            self.expires_at = datetime.now() + timedelta(seconds=self.timeout)
            self.self_futures.append(
                asyncio.create_task(self._timeout_loop())
            )
        return self

    async def __aexit__(self, *args):
        if not self.cleaned_up.is_set():
            await self.cleanup(exiting=True)

    async def _cleanup(self, manager, timeout=False, closing=False, exiting=False, **kwargs):
        for future in self.futures:
            future.cancel()
        for future in self.self_futures:
            future.cancel()
        self.cleaned_up.set()

    def on_cleanup(self, func):
        self.cleanup_function = func
        return func

    async def cleanup(self, **kwargs):
        try:
            await self.cleanup_function(self, **kwargs)
        except Exception:
            logging.debug("An error occurred while cleaning up the InteractionManager", exc_info=True)

    async def _timeout(self, manager, **kwargs):
        await self.cleanup(timeout=True, **kwargs)

    def on_timeout(self, func):
        self.timeout_function = func
        return func

    async def run_timeout(self):
        try:
            await self.timeout_function(self)
        except Exception:
            logging.debug("An error occurred while timing out the InteractionManager", exc_info=True)

    async def close(self, **kwargs):
        """
        Request closure of the manager.
        """
        try:
            await self.close_function(self, **kwargs)
        except Exception:
            logging.debug("An error occurred while closing the InteractionManager", exc_info=True)

    def on_close(self, func):
        self.close_function = func
        return func

    async def _close(self, manager, **kwargs):
        await self.cleanup(closing=True, **kwargs)

    def add_future(self, future):
        self.futures.append(future)
        return future
