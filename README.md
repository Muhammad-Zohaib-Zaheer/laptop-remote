# Laptop Remote

Control a Windows laptop from your phone, from anywhere: its live screen, mouse
and keyboard, the volume, buttons (lock, sleep, restart…), a PowerShell box, and
the voice assistant Sarah if she is running on that laptop. The phone opens a
small web app (add it to the Home Screen and it looks like an app); the laptop
reaches the internet through a free Cloudflare tunnel, so no fixed IP, no router
settings and no VPN are needed.

## Set it up on a laptop

Download **`setup.bat`** from this repo and double-click it. It asks for
administrator rights, then does everything by itself:

1. Excludes **only its own folder** from Windows Defender (Defender stays on for
   the rest of the laptop) so the server file is not removed as a false positive.
2. Downloads this project into `%USERPROFILE%\laptop-remote`.
3. Installs Python if it is missing, then the four packages the server needs.
4. Downloads the tunnel (`cloudflared`).
5. Makes it start with Windows, and starts it now.
6. Prints the **ntfy topic** to subscribe to on the phone. When the laptop is
   online, ntfy sends the link; tap it to open the app.

### On the phone (free, no Apple account needed)

- Install **ntfy** from the App Store and subscribe to the topic `setup.bat` prints.
- Open the link it sends, then **Share → Add to Home Screen**.

## Remove it

Download and double-click **`uninstall.bat`**. It stops the server and tunnel,
removes the start-with-Windows shortcut and the Defender exclusion, and deletes
the folder — everything `setup.bat` did, undone.

## Good to know

- **Settings** all live in `config.yaml`: screen quality, the phone's buttons,
  whether the PowerShell box is on, and the tunnel.
- **A fixed address:** the free tunnel's address changes each start (that is why
  ntfy pushes it). With your own domain on Cloudflare you can set a permanent
  address — paste the tunnel token into `config.yaml`.
- **Keep it awake:** for an always-on server, set Windows power to never sleep
  when plugged in, and "closing the lid does nothing".
- **Antivirus:** a remote-control server looks, to antivirus, like the tools
  attackers use. On Windows Defender the folder exclusion handles it. On a laptop
  with managed antivirus (e.g. a company Bitdefender) an administrator must add
  the exclusion instead — the setup cannot.
- **Security:** every request needs a secret key, made fresh on each laptop and
  kept out of the repo. Share the link only with yourself.
