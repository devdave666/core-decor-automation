# Shop the Look

Static shoppable page for real affiliate products matched to Core Decor's
posted concepts. Served free via GitHub Pages (already enabled on this repo,
root of `main`) at:

https://devdave666.github.io/core-decor-automation/shop/

## Adding a real product

Open `products.js`, find the concept by `id` (matches the filename prefix in
`assets/application/`, e.g. `c01` = `c01_kit_modlux_app.png`), and fill in:

```js
productName: "Brushed Brass 3-Head Pendant Light",
productUrl: "https://amzn.to/your-real-affiliate-link",
```

A card with `productUrl: null` is never shown — the page only displays
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
