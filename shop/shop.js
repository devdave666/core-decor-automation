// Fetches products.json and renders into #grid. A concept with no LINKED
// hotspot (a hotspot with a real productUrl) is skipped entirely -- this
// page can go live with zero real links filled in and simply grows as they
// get added, rather than shipping broken cards. JSON (not a .js literal)
// specifically so admin.html can safely read-modify-write a single entry
// via the GitHub API without any risk of corrupting hand-written formatting
// or comments.
//
// Each concept photo can carry several hotspots (light fixture, rug, chair,
// etc.), each independently linked to its own Amazon affiliate URL. Cards
// render the raw image at its native aspect ratio (no CSS crop) specifically
// so a hotspot's x/y percentage -- recorded in the admin editor against that
// same native, uncropped image -- lands in exactly the same spot here.
// Cropping (object-fit: cover) would shift the visible frame and throw off
// every dot's position.

function appendTracking(url, contentId) {
  try {
    const u = new URL(url);
    u.searchParams.set("utm_source", "coredecor");
    u.searchParams.set("utm_medium", "shop_page");
    u.searchParams.set("utm_content", contentId);
    return u.toString();
  } catch {
    // productUrl wasn't a valid absolute URL -- surface it as-is rather than
    // silently dropping the link a human just typed in.
    return url;
  }
}

function renderCard(product, linkedHotspots) {
  const card = document.createElement("div");
  card.className = "card";

  const imageWrap = document.createElement("div");
  imageWrap.className = "card-image";

  const img = document.createElement("img");
  img.src = product.image;
  img.alt = `${product.style} ${product.room}`;
  img.loading = "lazy";
  imageWrap.appendChild(img);

  for (const hotspot of linkedHotspots) {
    const dot = document.createElement("a");
    dot.className = "hotspot-dot";
    dot.style.left = `${hotspot.x}%`;
    dot.style.top = `${hotspot.y}%`;
    dot.href = appendTracking(hotspot.productUrl, `${product.id}-${hotspot.id}`);
    dot.target = "_blank";
    dot.rel = "noopener sponsored";
    dot.setAttribute("aria-label", hotspot.productName || hotspot.label);

    const label = document.createElement("span");
    label.className = "hotspot-label";
    label.textContent = hotspot.productName || hotspot.label;
    dot.appendChild(label);

    imageWrap.appendChild(dot);
  }

  card.appendChild(imageWrap);

  const body = document.createElement("div");
  body.className = "card-body";

  const tag = document.createElement("p");
  tag.className = "card-tag";
  tag.textContent = product.room;
  body.appendChild(tag);

  const title = document.createElement("h3");
  title.className = "card-title";
  title.textContent = product.style;
  body.appendChild(title);

  const shopList = document.createElement("ul");
  shopList.className = "card-shop-list";
  for (const hotspot of linkedHotspots) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = appendTracking(hotspot.productUrl, `${product.id}-${hotspot.id}`);
    a.target = "_blank";
    a.rel = "noopener sponsored";
    a.textContent = hotspot.productName || hotspot.label;
    li.appendChild(a);
    shopList.appendChild(li);
  }
  body.appendChild(shopList);

  card.appendChild(body);
  return card;
}

async function render() {
  const grid = document.getElementById("grid");
  let products;
  try {
    const res = await fetch("products.json", { cache: "no-store" });
    products = await res.json();
  } catch (err) {
    console.error("Failed to load products.json", err);
    return;
  }

  const shoppable = products
    .map((p) => ({ product: p, linkedHotspots: (p.hotspots || []).filter((h) => h.productUrl) }))
    .filter((p) => p.linkedHotspots.length > 0);

  if (shoppable.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent =
      "New shoppable looks are added regularly — check back soon, or follow @coredecor for the next drop.";
    grid.replaceWith(empty);
    return;
  }

  for (const { product, linkedHotspots } of shoppable) {
    grid.appendChild(renderCard(product, linkedHotspots));
  }
}

render();
