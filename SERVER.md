# Run SS Deal Finder 24/7 on a rented server

Your PC can be off. The server scans SS.lv all day, sends alerts to your phone (ntfy / Telegram / Discord), and you open the app from any phone or PC with your own private login.

## What you need
- A small Linux server (VPS): Ubuntu 22.04/24.04, 1 GB RAM is enough, roughly €4–6 per month at Hetzner, Contabo, DigitalOcean, etc. Give it your SSH key or root password when you create it. You get an **IP address**.
- On your Windows PC: the OpenSSH Client (Windows 10/11: Settings → Apps → Optional features). It is usually already there.

## Set up (once, about 5 minutes)
1. Double-click **Put the app on my server.bat** in the app folder.
2. Enter the server IP and login name (usually `root`). Answer **y** to copy your current data (deals, settings, tokens) to the server.
3. When asked, choose a password for the app (8+ characters) or press Enter to get a random one. **Write it down.**
4. It finishes by printing an address like `https://203-0-113-5.sslip.io`. Open it on your phone, log in, then install it: Android Chrome menu → **Install app**; iPhone Safari Share → **Add to Home Screen**.

The first start can take a minute while the HTTPS certificate is made.

## Update later
Unzip the new version and run **Put the app on my server.bat** again; answer **n** to the data question. Your data lives in `/opt/ssdeal/data` on the server and is never overwritten.

## Good to know
- **Address:** by default a free name from sslip.io that points at your server's IP. If you have your own domain, point an A record at the server and edit `/opt/ssdeal/.env` (`DOMAIN=...`), then `docker compose up -d` in `/opt/ssdeal`. A free DuckDNS name works too.
- **Accounts (several people):** the server has real accounts. The first account is the admin (name from `SSDEAL_ADMIN_USER`, default `admin`; password = `SSDEAL_PASSWORD` the first time, and anything already on the server moves into it). Log in at the address; the device stays logged in for 30 days. **Settings → Phone → Manage users** makes a one-time invite link; your friend opens it, picks a name and password, and gets an empty private copy of the app. Each person has their own database, settings, alerts and Discord bot; nobody can see or change anyone else's. Everyone changes their own password at `/account`. Limit: 6 accounts (`SSDEAL_MAX_USERS`). Each copy uses about 70 MB of memory when idle, so 3-4 people fit easily in 2 GB.
- **One scan for everyone:** the server is the only thing that talks to SS.lv. Each page is fetched once and the same copy goes to every account while it is fresh (lists: under 2 minutes, single ads: 3 hours; kept in `data/hub/pages.db`). Adding friends does not add traffic to SS.lv. Each account then rates those same listings with its own settings, so one ad can be a deal for you and nothing special for a friend. Manage users shows how many pages were shared.
- **Older listings:** besides the newest pages, the app slowly walks up to 40 pages deep into every feed in the background (6 pages every 5 minutes, taking turns, never delaying new-listing checks), so ads that have been up for weeks still appear in Listings and the price model has many more comparables. It repeats once a day. Old ads never trigger alerts. Settings: `scan.history_pages` (0 = off).
- **What is hidden:** services (repairs, rentals) and "wanted" ads (someone buying) are never listed. A listing that would be a loss to resell gets no "Interesting"/"Good deal" label (unless it is on your watchlist or My items).
- **Old vs new models:** the year, Apple model number (A1466...), Intel CPU generation, RAM, storage and HDD/SSD are read from the ad. Products sold for many years (MacBook Air/Pro Intel, XPS, X1 Carbon, Legion, Zephyrus, iPads...) are only compared with the same age, very old models and weak specs lower the score, and when the age is unknown a cheap price is not called a bargain. Existing listings are re-checked once after the update.
- **Forgot a password:** the admin can make a temporary one under Manage users. If the admin forgets: ask for help (do not delete the data folder).
- **Alerts:** Windows pop-ups don't exist on a server. Set up ntfy, Telegram or Discord in Settings → Notifications. Their links open your server address.
- **Android app:** point it at the server address; the server accepts the API token (tested on the server side, not with the app itself).
- **Backups:** the app already makes daily database backups in `/opt/ssdeal/data/backups`. Copy that folder somewhere now and then (your hosting provider's snapshot option is the easy way).
- **Logs:** `docker compose logs -f app` in `/opt/ssdeal`.
- **Security:** only the web server is exposed, over HTTPS; the app itself isn't reachable directly. Five wrong passwords from one address lock it out for a while.
- **Don't run the PC copy and the server copy at the same time** against SS.lv for long: you would double the requests. Use the PC app only to look, or switch scanning off there.

## Not verified yet
Not run against a real server or real Windows. SS.lv might treat a data-centre address differently from your home connection (slower, blocked or captchas). If the app shows scan errors or no new listings arrive on the server, send me the last lines of `docker compose logs app`.
