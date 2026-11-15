r"""Laptop Remote: the phone controls this laptop -- live screen, mouse and
keyboard, Sarah, volume, buttons, PowerShell.

    .venv\Scripts\pythonw.exe -m remote             the server, no console window
    .venv\Scripts\python.exe -m remote --no-tunnel  only on this laptop (for trying out)
    .venv\Scripts\python.exe -m remote --install    start with Windows
    .venv\Scripts\python.exe -m remote --uninstall  do not start with Windows any more
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hmac
import json
import logging
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import aiohttp
import psutil
import yaml
from aiohttp import web

from . import desktop, keys, screen, sound, tunnel

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("remote")
NO_WINDOW = subprocess.CREATE_NO_WINDOW
UTF8 = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
STARTUP_LINK = r"""
$link = Join-Path ([Environment]::GetFolderPath('Startup')) 'Laptop Remote.lnk'
if ('{install}' -eq 'True') {{
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
    $s.TargetPath = '{program}'; $s.Arguments = '-m remote'; $s.WorkingDirectory = '{folder}'
    $s.Save(); "created $link"
}} elseif (Test-Path $link) {{ Remove-Item $link; "removed $link" }}
"""


def keys_of(cfg) -> dict:
    """The secret key and the push topic; made once, on the first start."""
    file = ROOT / cfg["secret_file"]
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps({"key": secrets.token_urlsafe(32),
                                    "topic": f"laptop-{secrets.token_hex(8)}"}))
    return json.loads(file.read_text())


def make_app(cfg, secret: dict, use_tunnel: bool) -> web.Application:
    hands = screen.Hands(keys.code, desktop.press, cfg["key_codes"], cfg["dry_run"])
    key = secret["key"].encode()

    @web.middleware
    async def need_key(request, handler):
        """Everything but the app's own files needs the secret key."""
        if request.path.startswith(("/api", "/ws")):
            given = request.headers.get("Authorization", "").removeprefix("Bearer ")
            given = given or request.query.get("key", "")
            if not hmac.compare_digest(given.encode(), key):
                return web.json_response({"error": "wrong key"}, status=401)
        return await handler(request)

    def run(command: list[str]) -> None:
        log.info("run: %s", command)
        if not cfg["dry_run"]:
            subprocess.Popen(command, creationflags=NO_WINDOW)

    # ------------------------------------------------------------------ api

    async def info(_):
        return web.json_response({
            "name": socket.gethostname(),
            "actions": [{"name": n, "confirm": a.get("confirm", False)}
                        for n, a in cfg["actions"].items()],
            "media": list(cfg["media"]), "keys": cfg["keys"],
            "shell": cfg["shell"]["enabled"]})

    async def status(_):
        battery = psutil.sensors_battery()
        return web.json_response({
            "battery": battery and round(battery.percent),
            "plugged": battery and battery.power_plugged,
            "cpu": psutil.cpu_percent(), "ram": psutil.virtual_memory().percent,
            "volume": await asyncio.to_thread(sound.volume),
            "muted": await asyncio.to_thread(sound.muted)})

    async def volume(request):
        body = await request.json()
        if cfg["dry_run"]:
            log.info("dry run: volume %s", body)
        elif "level" in body:
            await asyncio.to_thread(sound.set_volume, int(body["level"]))
        elif "mute" in body:
            await asyncio.to_thread(sound.set_muted, bool(body["mute"]))
        return await status(request)

    async def sarah(request):
        text = (await request.json())["text"]
        try:
            async with aiohttp.ClientSession() as http, http.post(
                    cfg["sarah"]["url"], json={"text": text}) as answer:
                reply = (await answer.json())["reply"]
        except aiohttp.ClientError:
            reply = "Sarah is not running."
        log.info('sarah: "%s" -> %s', text, reply)
        return web.json_response({"reply": reply})

    async def action(request):
        name = (await request.json())["name"]
        run(cfg["actions"][name]["cmd"])
        return web.json_response({"done": name})

    async def media(request):
        name = (await request.json())["name"]
        await asyncio.to_thread(hands.do, {"t": "keys", "keys": cfg["media"][name]})
        return web.json_response({"done": name})

    async def shell(request):
        if not cfg["shell"]["enabled"]:
            return web.json_response({"output": "The PowerShell box is switched off.", "code": -1})
        command = (await request.json())["cmd"]
        log.info("shell: %s", command)
        if cfg["dry_run"]:
            return web.json_response({"output": "(dry run)", "code": 0})
        # Encoded, so quotes and letters like "ü" reach PowerShell unchanged.
        encoded = base64.b64encode((UTF8 + command).encode("utf-16-le")).decode()
        process = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-EncodedCommand", encoded, creationflags=NO_WINDOW,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), cfg["shell"]["timeout_s"])
        except TimeoutError:
            process.kill()
            output = f"(stopped after {cfg['shell']['timeout_s']} s)".encode()
        text = output.decode("utf-8", "replace")[-cfg["shell"]["max_output"]:]
        return web.json_response({"output": text, "code": process.returncode})

    async def screenshot(_):
        return web.Response(body=await asyncio.to_thread(screen.png), content_type="image/png")

    # ------------------------------------------------------- live screen

    async def live(request):
        """The phone asks for a frame after showing the last one, so a slow
        connection simply gets fewer frames. It also sends mouse and keys here."""
        s = cfg["screen"]
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=1 << 20)
        await ws.prepare(request)
        wanted = asyncio.Event()

        async def send_frames():
            last, sent_at = None, 0.0
            while not ws.closed:
                await wanted.wait()
                await asyncio.sleep(max(0.0, sent_at + 1 / s["max_fps"] - time.monotonic()))
                image = await asyncio.to_thread(screen.grab, s["max_side"])
                pixels = image.tobytes()
                if pixels == last:                  # nothing changed: no data spent
                    await asyncio.sleep(s["idle_check_ms"] / 1000)
                    continue
                last, sent_at = pixels, time.monotonic()
                wanted.clear()
                await ws.send_bytes(await asyncio.to_thread(screen.jpeg, image, s["quality"]))

        sender = asyncio.create_task(send_frames())
        try:
            async for message in ws:
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                event = json.loads(message.data)
                if event["t"] == "frame":
                    wanted.set()
                else:
                    await asyncio.to_thread(hands.do, event)
        finally:
            sender.cancel()
        return ws

    # ---------------------------------------------------------- the app

    dist = ROOT / cfg["app"]

    async def index(_):
        return web.FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    app = web.Application(middlewares=[need_key])
    app.add_routes([web.get("/api/info", info), web.get("/api/status", status),
                    web.post("/api/volume", volume), web.post("/api/sarah", sarah),
                    web.post("/api/action", action), web.post("/api/media", media),
                    web.post("/api/shell", shell), web.get("/api/screenshot", screenshot),
                    web.get("/ws", live), web.get("/", index)])
    if dist.exists():
        app.router.add_static("/", dist)

    async def on_address(address: str) -> None:
        log.info("reachable from anywhere at %s", address)
        (ROOT / "data" / "address.txt").write_text(address)
        if cfg["push"]["enabled"]:
            link = f"{address}/#key={secret['key']}" if cfg["push"]["include_key"] else address
            await tunnel.push(cfg["push"], secret["topic"], address, link)

    async def start_tunnel(app):
        exe = ROOT / cfg["tunnel"]["exe"]
        if use_tunnel and cfg["tunnel"]["enabled"]:
            if exe.exists():
                app["tunnel"] = asyncio.create_task(
                    tunnel.keep_running(cfg, str(exe), cfg["server"]["port"], on_address))
            else:
                log.error("no tunnel: %s is missing (see README)", exe)

    app.on_startup.append(start_tunnel)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-tunnel", action="store_true", help="only reachable from this laptop")
    parser.add_argument("--install", action="store_true", help="start with Windows")
    parser.add_argument("--uninstall", action="store_true", help="do not start with Windows")
    args = parser.parse_args()
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

    if args.install or args.uninstall:
        script = STARTUP_LINK.format(install=args.install, folder=ROOT,
                                     program=Path(sys.executable).with_name("pythonw.exe"))
        print(subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             capture_output=True, text=True).stdout.strip())
        return

    log_file = ROOT / cfg["log"]
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(log_file, encoding="utf-8")]
    if sys.stdout:                       # there is none under pythonw
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.WARNING, handlers=handlers,
                        format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    log.setLevel(logging.INFO)

    secret = keys_of(cfg)
    host, port = cfg["server"]["host"], cfg["server"]["port"]
    log.info("phone app on this laptop: http://%s:%d/#key=%s", host, port, secret["key"])
    log.info("ntfy topic for the address: %s", secret["topic"])
    web.run_app(make_app(cfg, secret, not args.no_tunnel), host=host, port=port,
                print=None, access_log=None)


if __name__ == "__main__":
    main()
