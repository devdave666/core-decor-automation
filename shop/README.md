# Shop the Look

Static shoppable page for real affiliate products matched to Core Decor's
posted concepts. Served free via GitHub Pages (already enabled on this repo,
root of `main`) at:

https://devdave666.github.io/core-decor-automation/shop/

## Hotspots — one photo, several shoppable items

Each concept photo carries a `hotspots` array, not a single product. A
hotspot is one clickable dot placed at an `x`/`y` percentage on the photo
(e.g. the pendant light, the rug, the accent chair, the faucet), each with
its own `label`, `searchKeywords`, `productName`, `productUrl`, and
`marketplace`. On the public page (`shop.js`), a card only shows if at
least one of its hotspots has a real `productUrl` — and only linked
hotspots get a dot. Hover a dot (or tap it on mobile) to see the item name;
click it to go straight to that item's Amazon link. A plain-text list of
the same links sits below the photo as a non-hover fallback.

Positions are stored as percentages of the photo's own native size, and
both the public page and the admin editor render the image **without any
CSS crop** — that's deliberate: cropping would shift what's visible and
throw every dot off. Don't reintroduce `object-fit: cover` on `.card img`
or `.editor-image-wrap img` without re-deriving the crop math for every
existing hotspot.

The 57 existing concepts were seeded with an AI-drafted first pass at
non-lighting hotspots (rugs, chairs, faucets, mirrors, etc.) — positions
and search terms are a starting point, not verified against the real
photos pixel-by-pixel. Expect to reposition some dots and rewrite some
search terms while linking them for the first time.

## Adding a real product

### Option A — the admin page (no git needed)

https://devdave666.github.io/core-decor-automation/shop/admin.html

Not linked from the public page on purpose. First visit: create a GitHub
fine-grained personal access token scoped to **only this repository**, with
**Contents: Read and write** permission and nothing else (the page itself
walks through the exact steps and links straight to the token creation
form). Paste it in once — it's saved in that browser's local storage only,
never sent anywhere but `api.github.com`, and never touches this repo or any
file. From there, every concept shows as a card with a **linked/total**
badge (e.g. "2/4").

**Per card:**

1. Click a card — opens the full photo with every hotspot shown as a dot.
   Filled dots are linked; dashed dots are pending.
2. Click a dashed dot to edit it, or click empty space on the photo to add
   a brand new one. Drag any dot to reposition it — it saves the position
   the moment you let go, no extra click needed.
3. In the modal: pick **US (amazon.com)** or **CA (amazon.ca)** — both of
   Dev's Associates accounts are active now, so this matters (see
   "Amazon.ca vs Amazon.com" below). Click **"1. Search on Amazon"** —
   opens that marketplace's search for the item's search terms in a new
   tab.
4. On Amazon (logged into the matching Associates account): find the item,
   use **SiteStripe** (the toolbar Amazon shows at the top of the page) →
   **Text** → **Copy**. This step happens on Amazon's own page and can't be
   automated from here — it's the only way to generate a REAL
   affiliate-tagged link without API access.
5. Come back to this tab. Click **"2. Paste link from clipboard"** — it
   reads the clipboard automatically and fills the URL field (and flags if
   the pasted link is Amazon but the wrong marketplace for what's
   selected above, so a mismatched tag doesn't slip through unnoticed).
6. Click **Save**.

**Delete hotspot** removes a dot entirely (position and all) — use this for
a mistaken click or an AI-drafted item that isn't actually worth linking.
To just unlink an item while keeping its dot in place for later, clear the
URL field and Save instead. **Log out** wipes the saved token from that
browser.

Don't use this page on a shared/public computer, and revoke the token from
GitHub's settings if the device it's saved on is ever lost or compromised.

### Option B — edit the file directly

Open `products.json`, find the concept by `id` (matches the filename prefix
in `assets/application/`, e.g. `c01` = `c01_kit_modlux_app.png`), and fill
in one of its `hotspots` entries:

```json
{
  "id": "c01-h1",
  "x": 49,
  "y": 28,
  "label": "Pendant Light",
  "productName": "Brushed Brass 3-Head Pendant Light",
  "productUrl": "https://amzn.to/your-real-affiliate-link",
  "marketplace": "us",
  "searchKeywords": "3-light cluster bubble glass pendant light brass"
}
```

A hotspot with `"productUrl": null` never shows a dot — the page only
displays linked hotspots, so it's safe to fill these in gradually. No
rebuild step, no deploy step: GitHub Pages picks up the change automatically
once it's pushed to `main`, usually within a minute or two.

`shop.js` automatically appends `utm_source=coredecor&utm_medium=shop_page&
utm_content={conceptId}-{hotspotId}` to every link when a visitor clicks, so
click-through data per individual item (not just per photo) is trackable in
whichever affiliate dashboard or analytics tool reads UTM params — no
manual tagging needed per link.

## Design notes

- Matches the swatch-card brand register: dark editorial background, Fry's
  Baskerville for headings (same font already used for swatch labels, hosted
  from `concept_tools/fonts/` via raw.githubusercontent.com — no new asset).
- Product images are the SAME application photos already posted in reels/
  carousels, referenced directly from `assets/application/` via
  raw.githubusercontent.com — zero new render cost, and a viewer who
  recognizes a room from a video can find it here.
- `rel="sponsored"` on every hotspot link (dot and text-list version alike),
  and a disclosure line in the footer — required by Google/FTC guidance for
  affiliate links, not optional styling.
- Each hotspot carries a `searchKeywords` field — a short, concrete
  description of the real object identified by looking at that concept's
  photo (e.g. "3-light cluster bubble glass pendant light brass" for
  c01-h1), not guessed from the room/style name alone. Drives the admin
  modal's "Search on Amazon" button.

## Amazon.ca vs Amazon.com

Both of Dev's Associates accounts are active now (US and Canada), each with
its own tag. A tag copied from the wrong marketplace's SiteStripe won't
earn commission under the other account, so every hotspot records which
marketplace its link's tag belongs to (`"marketplace": "us"` or `"ca"`) and
the admin editor's US/CA toggle drives both the "Search on Amazon" button's
target domain and the paste-clipboard mismatch warning. Default is US.

**Smart, location-based redirect** (send a US visitor to amazon.com, a UK
visitor to amazon.co.uk, etc., automatically, while still crediting Dev) is
a real feature Amazon supports natively — it's called **OneLink**, set up
from Associates Central, and it's worth enabling now that two marketplace
tags exist. It requires an Associates tag in each marketplace OneLink
should route to; a third marketplace (e.g. UK) added later would need its
own tag before OneLink could route to it too. This hasn't been wired up
here yet — worth doing once there's real traffic to route, rather than
building a custom geo-IP redirect from scratch.

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
