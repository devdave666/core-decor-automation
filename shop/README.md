# Shop the Look

Static shoppable page for real affiliate products matched to Core Decor's
posted concepts. Served free via GitHub Pages (already enabled on this repo,
root of `main`) at:

https://devdave666.github.io/core-decor-automation/shop/

## Adding a real product

### Option A — the admin page (no git needed)

https://devdave666.github.io/core-decor-automation/shop/admin.html

Not linked from the public page on purpose. First visit: create a GitHub
fine-grained personal access token scoped to **only this repository**, with
**Contents: Read and write** permission and nothing else (the page itself
walks through the exact steps and links straight to the token creation
form). Paste it in once — it's saved in that browser's local storage only,
never sent anywhere but `api.github.com`, and never touches this repo or any
file. From there, every concept shows as a card: blank ones say "+ Add
product" plus a suggested search term, linked ones are tagged "LINKED".

**The fast path per card** (no Amazon product-search API access yet — see
"Amazon Creators API" below — so this is the real workflow until that
unlocks):

1. Click a card. The modal opens with a suggested search term already
   filled into the product name field (editable) and shown above the
   buttons.
2. Click **"1. Search on Amazon"** — opens Amazon.ca's search for that term
   in a new tab (Dev's Associates account is Canada-only until it qualifies
   for the US program too — see "Amazon.ca vs Amazon.com" below).
3. On Amazon (logged into Associates): find the item, use **SiteStripe**
   (the toolbar Amazon shows at the top of the page) → **Text** → **Copy**.
   This step happens on Amazon's own page and can't be automated from
   here — it's the only way to generate a REAL affiliate-tagged link
   without API access.
4. Come back to this tab. Click **"2. Paste link from clipboard"** — it
   reads the clipboard automatically and fills the URL field (and flags if
   it doesn't look like an Amazon link, so a wrong copy doesn't slip
   through unnoticed).
5. Click **Save**.

Five clicks total on our side, plus SiteStripe's own copy step on Amazon —
about as tight as this gets without programmatic product search. **Clear**
removes a link. **Log out** wipes the saved token from that browser.

Don't use this page on a shared/public computer, and revoke the token from
GitHub's settings if the device it's saved on is ever lost or compromised.

### Option B — edit the file directly

Open `products.json`, find the concept by `id` (matches the filename prefix
in `assets/application/`, e.g. `c01` = `c01_kit_modlux_app.png`), and fill
in:

```json
"productName": "Brushed Brass 3-Head Pendant Light",
"productUrl": "https://amzn.to/your-real-affiliate-link",
```

A card with `"productUrl": null` is never shown — the page only displays
concepts that actually have a real link, so it's safe to fill these in
gradually. No rebuild step, no deploy step: GitHub Pages picks up the change
automatically once it's pushed to `main`, usually within a minute or two.

`shop.js` automatically appends `utm_source=coredecor&utm_medium=shop_page&
utm_content={id}` to every link when a visitor clicks, so click-through data
per concept is trackable in whichever affiliate dashboard or analytics tool
reads UTM params — no manual tagging needed per link.

## Design notes

- Matches the swatch-card brand register: dark editorial background, Fry's
  Baskerville for headings (same font already used for swatch labels, hosted
  from `concept_tools/fonts/` via raw.githubusercontent.com — no new asset).
- Product images are the SAME application photos already posted in reels/
  carousels, referenced directly from `assets/application/` via
  raw.githubusercontent.com — zero new render cost, and a viewer who
  recognizes a room from a video can find it here.
- `rel="sponsored"` on every CTA link, and a disclosure line in the footer —
  required by Google/FTC guidance for affiliate links, not optional styling.
- Each product entry carries a `searchKeywords` field — a short, concrete
  description of the real object identified by actually looking at that
  concept's photo (e.g. "3-light cluster bubble glass pendant light brass"
  for c01), not guessed from the room/style name alone. Drives both the
  card hint and the admin modal's "Search on Amazon" button.

## Amazon.ca vs Amazon.com

Dev's Associates account is approved for **Amazon.ca only** — not yet
qualified for the US program. A tag copied from an amazon.com SiteStripe
won't earn commission under this account, so every link needs to be
generated from **amazon.ca**. The admin page's "Search on Amazon" button and
the paste-clipboard check both enforce this (the paste step flags any pasted
link that isn't `amazon.ca`).

**Smart, location-based redirect** (send a US visitor to amazon.com, a UK
visitor to amazon.co.uk, etc., while still crediting Dev) is a real feature
Amazon supports natively — it's called **OneLink**, set up from Associates
Central. It requires Dev to have (or add) an Associates tag in each
marketplace OneLink should route to; right now that's only `.ca`, so
OneLink isn't useful yet beyond what a plain `.ca` link already does. Once
the US program clears (see "Amazon Creators API" below — same 10-sales
threshold gates both), OneLink is the right next step rather than a custom
geo-IP redirect built here.

## Amazon Creators API — why this isn't fully automated (yet)

Amazon's Creators API (the PA-API 5.0 replacement) can search products and
generate affiliate links programmatically, but requires **10 qualifying
Associates sales in the past 30 days** — confirmed against this account's
real credentials, which return `AssociateNotEligible`. See `amazon_
creators.py`, `check_eligibility.py`, and llms.txt's "Amazon Creators API"
section. Once `check-amazon-eligibility.yml` reports success, the
SiteStripe step above can be replaced with a real automated search +
propose flow. Until then, this manual-but-tightened workflow is what
generates the sales that unlock that in the first place.
