"""Keeps a Cloudflare tunnel running and tells the phone its address."""
from __future__ import annotations

import asyncio
import logging
import re

import aiohttp

log = logging.getLogger("remote")
QUICK_ADDRESS = re.compile(rb"https://[a-z0-9-]+\.trycloudflare\.com")


async def push(cfg, topic: str, address: str, link: str) -> None:
    """A notification on the phone (ntfy app); tapping it opens the remote."""
    try:
        async with aiohttp.ClientSession() as http:
            await http.post(f"{cfg['server']}/{topic}", data=f"Laptop is online: {address}",
                            headers={"Title": "Laptop Remote", "Click": link, "Tags": "computer"})
        log.info("address pushed to ntfy topic %s", topic)
    except aiohttp.ClientError as error:
        log.warning("could not push the address: %s", error)


async def keep_running(cfg, exe: str, port: int, on_address) -> None:
    """Start the tunnel, and start it again whenever it dies. Never returns."""
    t = cfg["tunnel"]
    if t["token"]:                       # your own tunnel: the address never changes
        command = [exe, "tunnel", "--no-autoupdate", "run", "--token", t["token"]]
    else:                                # quick tunnel: a new address each start
        command = [exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"]
    while True:
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        except OSError as error:
            log.error("tunnel not started (%s): %s", exe, error)
            return
        if t["hostname"]:
            await on_address(f"https://{t['hostname']}")
        async for line in process.stderr:   # cloudflared logs to stderr
            if found := QUICK_ADDRESS.search(line):
                await on_address(found.group().decode())
        log.warning("tunnel stopped (exit %s); starting it again", await process.wait())
        await asyncio.sleep(t["restart_after_s"])
