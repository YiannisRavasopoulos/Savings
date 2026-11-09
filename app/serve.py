"""Run both web apps in one process: the user app on 8080 and the admin app on 8091.

Docker publishes 8080 to the LAN and 8091 only to this PC's 127.0.0.1 (see docker-compose.yml).
"""
from __future__ import annotations

import asyncio
import contextlib
import signal

import uvicorn

from .admin import create_admin_app
from .main import create_app


class _Server(uvicorn.Server):
    """uvicorn.Server without its own signal handling; we stop both servers together."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield

    def install_signal_handlers(self) -> None:   # older uvicorn versions
        pass


async def main() -> None:
    servers = [
        _Server(uvicorn.Config(create_app(), host="0.0.0.0", port=8080, log_level="info")),
        _Server(uvicorn.Config(create_admin_app(), host="0.0.0.0", port=8091, log_level="info")),
    ]

    def stop(*_):
        for s in servers:
            s.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop)
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
