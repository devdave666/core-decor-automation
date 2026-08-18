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
product", linked ones are tagged "LINKED". Click any card, fill in the
product name and URL, hit Save — it commits straight to `products.json` on
`main` via the GitHub API and is live within about a minute. Clear removes a
link. Log out wipes the saved token from that browser.

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
