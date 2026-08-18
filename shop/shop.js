// Fetches products.json and renders into #grid. A product with no productUrl
// is skipped entirely -- this page can go live with zero real links filled
// in and simply grows as they get added, rather than shipping broken cards.
// JSON (not a .js literal) specifically so admin.html can safely read-modify-
// write a single entry via the GitHub API without any risk of corrupting
// hand-written formatting or comments.

function appendTracking(url, id) {
  try {
    const u = new URL(url);
    u.searchParams.set("utm_source", "coredecor");
    u.searchParams.set("utm_medium", "shop_page");
    u.searchParams.set("utm_content", id);
    return u.toString();
  } catch {
    // productUrl wasn't a valid absolute URL -- surface it as-is rather than
    // silently dropping the link a human just typed in.
    return url;
  }
}

function renderCard(product) {
  const card = document.createElement("div");
  card.className = "card";

  const img = document.createElement("img");
  img.src = product.image;
  img.alt = `${product.style} ${product.room}`;
  img.loading = "lazy";
  card.appendChild(img);

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

  if (product.productName) {
    const productLine = document.createElement("p");
    productLine.className = "card-product";
    productLine.textContent = product.productName;
    body.appendChild(productLine);
  }

  const cta = document.createElement("a");
  cta.className = "card-cta";
  cta.href = appendTracking(product.productUrl, product.id);
  cta.target = "_blank";
  cta.rel = "noopener sponsored";
  cta.textContent = "Shop This Look";
  body.appendChild(cta);

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

  const shoppable = products.filter((p) => p.productUrl);

  if (shoppable.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent =
      "New shoppable looks are added regularly — check back soon, or follow @coredecor for the next drop.";
    grid.replaceWith(empty);
    return;
  }

  for (const product of shoppable) {
    grid.appendChild(renderCard(product));
  }
}

render();
