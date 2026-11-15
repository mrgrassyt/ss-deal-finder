# mrgrass.me

The portfolio site: projects, tech lab, photography, shop, marketplace listings, devlog, about, plus a private dashboard
to manage all of it. Python (Starlette) + SQLite, server-rendered pages, no build step.

## Managing the site

Open `https://mrgrass.me/admin` and sign in.

- **First password**: the one in `/opt/ssdeal/.env` (`SITE_ADMIN_PASSWORD`, or `SSDEAL_PASSWORD` if that is not set).
  Change it under **Password** straight away; after that the `.env` value is ignored.
- **Projects, Devlog, Tech Lab, Equipment, Photography, My Listings, Shop, Now, Roadmap, Playground**: add, edit, hide or delete.
  "Hide" takes something off the site without deleting it. Devlog articles start as drafts until you press Publish.
- **Photography → Upload photos** takes many files at once and fills in camera, lens and settings from each file.
  Location data is always removed from uploaded pictures.
- **Listings and Shop**: change Available / Reserved / Sold / Archived right in the list. Sold items move behind "Show sold items";
  archived ones disappear from the site.
- **Messages**: everything sent through the contact form or "Ask about this".
- **Settings**: home page text, accent colour, links, About page, which pages and statistics are hidden.

## What needs configuring (optional)

| Feature | Status | To turn on |
| --- | --- | --- |
| Email copy of new messages | Off. Messages always arrive in the dashboard. | Add `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SITE_MAIL_TO` to `.env`, then `docker compose up -d` |
| Automatic Vinted / eBay sync | Not built. Listings are added by hand. | Would need each marketplace's API access |
| Payments | Not built on purpose. Items link to the marketplace or open the inquiry form. | |

## Where things live

- `app/schema.py` — every content type and its fields. The dashboard forms and the validation both come from this file,
  so a new field is one line here plus one line in the template that should show it.
- `app/main.py` — pages, search, contact form, dashboard API. `app/auth.py` — sign-in. `app/media.py` — uploads.
- `app/seed.py` — the content the site starts with (only used on the very first start).
- `templates/` — one file per page. `static/css/site.css` — design tokens at the top. `static/js/grass.js` — the grass.
- Data: `/opt/ssdeal/sitedata` on the server (`site.db` and `media/`). Back up that folder to back up the site.

## Running it locally

```
pip install -r requirements.txt
SITE_ADMIN_PASSWORD=something-long uvicorn app.main:app --port 8770
python -m pytest tests          # needs: pip install pytest httpx
```
