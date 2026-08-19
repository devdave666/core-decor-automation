// Token-gated in-browser editor for shop/products.json. The token is a
// GitHub fine-grained PAT the user creates and pastes in themselves -- it
// lives ONLY in this browser's localStorage and is sent only to
// api.github.com, never anywhere else, never written to any file in this
// repo. This admin page is not linked from the public shop page.
//
// Each concept photo can carry multiple hotspots (light fixture, rug,
// chair, ...), each its own Amazon affiliate link. Clicking a grid card
// opens the full photo in the editor view: click an existing dot to edit
// it, click empty space to add a new one, drag a dot to reposition. The
// editor displays the image at native aspect ratio (no CSS crop) -- same as
// shop.js -- so a hotspot's x/y percentage means the same spot in both
// places.

const OWNER = "devdave666";
const REPO = "core-decor-automation";
const FILE_PATH = "shop/products.json";
const BRANCH = "main";
const TOKEN_KEY = "coredecor_shop_admin_token";

const MARKET_HOSTS = { us: "www.amazon.com", ca: "www.amazon.ca" };

const tokenGate = document.getElementById("token-gate");
const toolbar = document.getElementById("toolbar");
const statusLine = document.getElementById("status-line");
const grid = document.getElementById("admin-grid");

const editor = document.getElementById("editor");
const editorBack = document.getElementById("editor-back");
const editorTitle = document.getElementById("editor-title");
const editorImageWrap = document.getElementById("editor-image-wrap");
const editorImage = document.getElementById("editor-image");
const editorGridOverlay = document.getElementById("editor-grid-overlay");
const gridSizeInput = document.getElementById("grid-size");
const gridSizeLabel = document.getElementById("grid-size-label");

const GRID_SIZE_KEY = "coredecor_shop_admin_grid_size";

const modalBackdrop = document.getElementById("modal-backdrop");
const modalTitle = document.getElementById("modal-title");
const modalLabel = document.getElementById("modal-label");
const modalSearchTerms = document.getElementById("modal-search-terms");
const modalName = document.getElementById("modal-name");
const modalUrl = document.getElementById("modal-url");
const modalError = document.getElementById("modal-error");
const modalNotice = document.getElementById("modal-notice");
const marketUsBtn = document.getElementById("modal-market-us");
const marketCaBtn = document.getElementById("modal-market-ca");
const searchAmazonBtn = document.getElementById("modal-search-amazon");
const pasteClipboardBtn = document.getElementById("modal-paste-clipboard");
const deleteBtn = document.getElementById("modal-delete");

let currentProducts = null;
let activeProductId = null;
let activeHotspotId = null; // null while the modal is creating a brand-new hotspot
let pendingNewHotspot = null; // { x, y } while creating, until Save
let selectedMarket = "us";
let visibilityListener = null;

function utf8ToBase64(str) {
  return btoa(unescape(encodeURIComponent(str)));
}

function base64ToUtf8(str) {
  return decodeURIComponent(escape(atob(str)));
}

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function ghHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
  };
}

async function fetchProducts(token) {
  const res = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/contents/${FILE_PATH}?ref=${BRANCH}`,
    { headers: ghHeaders(token), cache: "no-store" }
  );
  if (!res.ok) {
    throw new Error(`GitHub API ${res.status}: ${res.status === 401 ? "invalid or expired token" : res.status === 403 ? "token lacks Contents read/write on this repo" : "request failed"}`);
  }
  const body = await res.json();
  const products = JSON.parse(base64ToUtf8(body.content));
  return { products, sha: body.sha };
}

async function saveProducts(token, products, message) {
  // Always re-fetch immediately before writing so we PUT against the latest
  // sha -- avoids clobbering a change made from another tab/device since
  // this page loaded.
  const { sha: freshSha } = await fetchProducts(token);
  const res = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/contents/${FILE_PATH}`,
    {
      method: "PUT",
      headers: { ...ghHeaders(token), "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        content: utf8ToBase64(JSON.stringify(products, null, 2) + "\n"),
        sha: freshSha,
        branch: BRANCH,
      }),
    }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(`GitHub API ${res.status}: ${body.message || "save failed"}`);
  }
  return res.json();
}

function nextHotspotId(product) {
  const n = (product.hotspots || []).length + 1;
  return `${product.id}-h${n}`;
}

function renderGrid() {
  grid.innerHTML = "";
  for (const product of currentProducts) {
    const hotspots = product.hotspots || [];
    const linked = hotspots.filter((h) => h.productUrl).length;

    const card = document.createElement("div");
    card.className = "admin-card";
    card.dataset.id = product.id;

    const img = document.createElement("img");
    img.src = product.image;
    img.alt = `${product.style} ${product.room}`;
    img.loading = "lazy";
    card.appendChild(img);

    const badge = document.createElement("span");
    badge.className = `admin-card-badge ${linked === hotspots.length && hotspots.length > 0 ? "is-complete" : linked === 0 ? "is-pending" : ""}`;
    badge.textContent = `${linked}/${hotspots.length}`;
    card.appendChild(badge);

    const body = document.createElement("div");
    body.className = "admin-card-body";

    const tag = document.createElement("p");
    tag.className = "admin-card-tag";
    tag.textContent = `${product.id} — ${product.room}`;
    body.appendChild(tag);

    const title = document.createElement("h4");
    title.className = "admin-card-title";
    title.textContent = product.style;
    body.appendChild(title);

    card.appendChild(body);
    card.addEventListener("click", () => openEditor(product.id));
    grid.appendChild(card);
  }
}

function openEditor(productId) {
  activeProductId = productId;
  const product = currentProducts.find((p) => p.id === productId);
  editorTitle.textContent = `${product.id} — ${product.room}, ${product.style}`;
  editorImage.src = product.image;
  editorImage.alt = `${product.style} ${product.room}`;
  grid.hidden = true;
  editor.hidden = false;
  renderMarkers();
}

function closeEditor() {
  editor.hidden = true;
  grid.hidden = false;
  activeProductId = null;
}

function renderMarkers() {
  editorImageWrap.querySelectorAll(".editor-marker").forEach((el) => el.remove());
  const product = currentProducts.find((p) => p.id === activeProductId);
  (product.hotspots || []).forEach((hotspot, i) => {
    const marker = document.createElement("div");
    marker.className = `editor-marker ${hotspot.productUrl ? "" : "is-pending"}`;
    marker.style.left = `${hotspot.x}%`;
    marker.style.top = `${hotspot.y}%`;
    marker.dataset.index = i + 1;
    marker.dataset.hotspotId = hotspot.id;
    attachMarkerDrag(marker, hotspot);
    editorImageWrap.appendChild(marker);
  });
}

function attachMarkerDrag(marker, hotspot) {
  let startX, startY, dragging;

  marker.addEventListener("pointerdown", (e) => {
    e.stopPropagation();
    // Capture can throw if the pointer isn't recognized as active (e.g. a
    // synthetic/replayed event) -- position tracking below doesn't depend
    // on capture actually succeeding, so a failed capture is harmless.
    try { marker.setPointerCapture(e.pointerId); } catch {}
    startX = e.clientX;
    startY = e.clientY;
    dragging = false;
  });

  marker.addEventListener("pointermove", (e) => {
    if (startX === undefined) return;
    if (!dragging && Math.hypot(e.clientX - startX, e.clientY - startY) < 5) return;
    dragging = true;
    const rect = editorImage.getBoundingClientRect();
    const x = snap(((e.clientX - rect.left) / rect.width) * 100);
    const y = snap(((e.clientY - rect.top) / rect.height) * 100);
    marker.style.left = `${x}%`;
    marker.style.top = `${y}%`;
  });

  marker.addEventListener("pointerup", async (e) => {
    try { marker.releasePointerCapture(e.pointerId); } catch {}
    if (dragging) {
      const rect = editorImage.getBoundingClientRect();
      hotspot.x = snap(((e.clientX - rect.left) / rect.width) * 100);
      hotspot.y = snap(((e.clientY - rect.top) / rect.height) * 100);
      statusLine.textContent = `Saving position for ${hotspot.id}...`;
      try {
        await saveProducts(getToken(), currentProducts, `Shop admin: reposition ${hotspot.id}`);
        statusLine.textContent = `Repositioned ${hotspot.id}.`;
      } catch (err) {
        statusLine.textContent = `Failed to save position: ${err.message}`;
      }
    } else {
      openModal(activeProductId, hotspot.id);
    }
    startX = undefined;
  });
}

function clamp(n) {
  return Math.max(0, Math.min(100, n));
}

// The grid is a visual + snapping aid, not stored data -- every x/y still
// saves as a plain percentage. "Tighter" grid = more cells = finer snap
// resolution, which is what actually fixes hotspots landing near an item
// instead of on it.
let gridSize = Number(localStorage.getItem(GRID_SIZE_KEY)) || 40;

function snap(n) {
  const cell = 100 / gridSize;
  return clamp(Math.round(n / cell) * cell);
}

function updateGridOverlay() {
  const cellPct = 100 / gridSize;
  editorGridOverlay.style.setProperty("--cell", `${cellPct}%`);
  gridSizeLabel.textContent = `${gridSize}×${gridSize}`;
  gridSizeInput.value = gridSize;
}

gridSizeInput.addEventListener("input", () => {
  gridSize = Number(gridSizeInput.value);
  localStorage.setItem(GRID_SIZE_KEY, String(gridSize));
  updateGridOverlay();
});

updateGridOverlay();

editorImageWrap.addEventListener("click", (e) => {
  if (e.target !== editorImage) return;
  const rect = editorImage.getBoundingClientRect();
  const x = snap(((e.clientX - rect.left) / rect.width) * 100);
  const y = snap(((e.clientY - rect.top) / rect.height) * 100);
  pendingNewHotspot = { x, y };
  openModal(activeProductId, null);
});

editorBack.addEventListener("click", closeEditor);

function setMarket(market) {
  selectedMarket = market;
  marketUsBtn.classList.toggle("is-active", market === "us");
  marketCaBtn.classList.toggle("is-active", market === "ca");
}

marketUsBtn.addEventListener("click", () => setMarket("us"));
marketCaBtn.addEventListener("click", () => setMarket("ca"));
modalSearchTerms.addEventListener("input", () => {
  searchAmazonBtn.disabled = !modalSearchTerms.value.trim();
});

function openModal(productId, hotspotId) {
  activeProductId = productId;
  activeHotspotId = hotspotId;
  const product = currentProducts.find((p) => p.id === productId);
  const hotspot = hotspotId ? product.hotspots.find((h) => h.id === hotspotId) : null;

  modalTitle.textContent = hotspot ? `${product.id} — Edit ${hotspot.label || hotspot.id}` : `${product.id} — New hotspot`;
  modalLabel.value = hotspot?.label || "";
  modalSearchTerms.value = hotspot?.searchKeywords || "";
  modalName.value = hotspot?.productName || (hotspot?.searchKeywords ? titleCase(hotspot.searchKeywords) : "");
  modalUrl.value = hotspot?.productUrl || "";
  setMarket(hotspot?.marketplace || "us");
  deleteBtn.hidden = !hotspot;
  modalError.hidden = true;
  modalNotice.hidden = true;
  pasteClipboardBtn.classList.remove("pulse");
  searchAmazonBtn.disabled = !modalSearchTerms.value.trim();

  modalBackdrop.hidden = false;
  modalLabel.focus();
}

function titleCase(s) {
  return s.replace(/\w\S*/g, (w) => w[0].toUpperCase() + w.slice(1));
}

function closeModal() {
  modalBackdrop.hidden = true;
  activeHotspotId = null;
  pendingNewHotspot = null;
  if (visibilityListener) {
    document.removeEventListener("visibilitychange", visibilityListener);
    visibilityListener = null;
  }
}

function handleSearchAmazon() {
  const terms = modalSearchTerms.value.trim();
  if (!terms) return;
  window.open(`https://${MARKET_HOSTS[selectedMarket]}/s?k=${encodeURIComponent(terms)}`, "_blank", "noopener");

  // When the user comes back to this tab (after grabbing a SiteStripe link
  // on Amazon), pulse the paste button so the next step is obvious --
  // removes the need to remember what to do next.
  if (visibilityListener) document.removeEventListener("visibilitychange", visibilityListener);
  visibilityListener = () => {
    if (document.visibilityState === "visible") {
      pasteClipboardBtn.classList.add("pulse");
      document.removeEventListener("visibilitychange", visibilityListener);
      visibilityListener = null;
    }
  };
  document.addEventListener("visibilitychange", visibilityListener);
}

async function handlePasteClipboard() {
  pasteClipboardBtn.classList.remove("pulse");
  modalError.hidden = true;
  try {
    const text = (await navigator.clipboard.readText()).trim();
    if (!text) {
      modalNotice.textContent = "Clipboard is empty — copy the SiteStripe link first, then try again.";
      modalNotice.hidden = false;
      return;
    }
    modalUrl.value = text;
    const looksLikeAmazon = /amazon\.[a-z.]+|amzn\.to/i.test(text);
    const hasAmazonDomain = /amazon\.[a-z.]+/i.test(text);
    const expectedHost = MARKET_HOSTS[selectedMarket].replace(/^www\./, ""); // "amazon.com" or "amazon.ca"
    const matchesExpected = new RegExp(expectedHost.replace(".", "\\."), "i").test(text);
    const wrongMarketplace = hasAmazonDomain && !matchesExpected;
    modalNotice.textContent = !looksLikeAmazon
      ? "Pasted — doesn't look like an Amazon link, double check before saving."
      : wrongMarketplace
      ? `Pasted — this doesn't look like an ${expectedHost} link. You selected ${selectedMarket.toUpperCase()} above; re-copy from the matching Amazon site or switch the marketplace toggle.`
      : "Pasted.";
    modalNotice.hidden = false;
  } catch {
    modalNotice.textContent = "Couldn't read the clipboard automatically — paste manually into the URL field (Ctrl+V).";
    modalNotice.hidden = false;
    modalUrl.focus();
  }
}

async function handleSave() {
  const label = modalLabel.value.trim();
  const searchTerms = modalSearchTerms.value.trim();
  const name = modalName.value.trim();
  const url = modalUrl.value.trim();

  if (url) {
    try {
      new URL(url);
    } catch {
      modalError.textContent = "That doesn't look like a valid URL (needs https://...).";
      modalError.hidden = false;
      return;
    }
  }

  const token = getToken();
  const product = currentProducts.find((p) => p.id === activeProductId);
  product.hotspots = product.hotspots || [];

  let hotspot = activeHotspotId ? product.hotspots.find((h) => h.id === activeHotspotId) : null;
  const isNew = !hotspot;
  const previous = hotspot ? { ...hotspot } : null;

  if (isNew) {
    hotspot = {
      id: nextHotspotId(product),
      x: pendingNewHotspot.x,
      y: pendingNewHotspot.y,
      label: "",
      productName: null,
      productUrl: null,
      marketplace: "us",
      searchKeywords: "",
    };
    product.hotspots.push(hotspot);
  }

  hotspot.label = label || null;
  hotspot.searchKeywords = searchTerms || null;
  hotspot.productName = name || null;
  hotspot.productUrl = url || null;
  hotspot.marketplace = selectedMarket;

  statusLine.textContent = `Saving ${hotspot.id}...`;
  try {
    await saveProducts(token, currentProducts, `Shop admin: update ${hotspot.id}`);
    statusLine.textContent = `Saved ${hotspot.id} — live in about a minute.`;
    activeHotspotId = hotspot.id;
    pendingNewHotspot = null;
    renderGrid();
    renderMarkers();
    closeModal();
  } catch (err) {
    if (isNew) {
      product.hotspots = product.hotspots.filter((h) => h.id !== hotspot.id);
    } else {
      Object.assign(hotspot, previous);
    }
    modalError.textContent = err.message;
    modalError.hidden = false;
    statusLine.textContent = "Save failed.";
  }
}

async function handleDelete() {
  if (!activeHotspotId) return;
  const token = getToken();
  const product = currentProducts.find((p) => p.id === activeProductId);
  const index = product.hotspots.findIndex((h) => h.id === activeHotspotId);
  if (index === -1) return;
  const [removed] = product.hotspots.splice(index, 1);

  statusLine.textContent = `Deleting ${removed.id}...`;
  try {
    await saveProducts(token, currentProducts, `Shop admin: delete ${removed.id}`);
    statusLine.textContent = `Deleted ${removed.id}.`;
    renderGrid();
    renderMarkers();
    closeModal();
  } catch (err) {
    product.hotspots.splice(index, 0, removed);
    modalError.textContent = err.message;
    modalError.hidden = false;
    statusLine.textContent = "Delete failed.";
  }
}

function showTokenGate() {
  tokenGate.hidden = false;
  toolbar.hidden = true;
  grid.hidden = true;
  editor.hidden = true;
}

async function showAdmin(token) {
  tokenGate.hidden = true;
  toolbar.hidden = false;
  statusLine.textContent = "Loading products...";
  try {
    const { products } = await fetchProducts(token);
    currentProducts = products;
    grid.hidden = false;
    const totalHotspots = products.reduce((sum, p) => sum + (p.hotspots || []).length, 0);
    const linkedHotspots = products.reduce((sum, p) => sum + (p.hotspots || []).filter((h) => h.productUrl).length, 0);
    statusLine.textContent = `${products.length} concepts, ${linkedHotspots}/${totalHotspots} hotspots linked.`;
    renderGrid();
  } catch (err) {
    statusLine.textContent = err.message;
    // Bad token -- drop back to the gate so it can be corrected.
    localStorage.removeItem(TOKEN_KEY);
    showTokenGate();
  }
}

document.getElementById("token-save").addEventListener("click", () => {
  const value = document.getElementById("token-input").value.trim();
  if (!value) return;
  localStorage.setItem(TOKEN_KEY, value);
  showAdmin(value);
});

document.getElementById("logout-btn").addEventListener("click", () => {
  localStorage.removeItem(TOKEN_KEY);
  currentProducts = null;
  showTokenGate();
});

document.getElementById("modal-cancel").addEventListener("click", closeModal);
document.getElementById("modal-save").addEventListener("click", handleSave);
deleteBtn.addEventListener("click", handleDelete);
searchAmazonBtn.addEventListener("click", handleSearchAmazon);
pasteClipboardBtn.addEventListener("click", handlePasteClipboard);
modalBackdrop.addEventListener("click", (e) => {
  if (e.target === modalBackdrop) closeModal();
});

const existingToken = getToken();
if (existingToken) {
  showAdmin(existingToken);
} else {
  showTokenGate();
}
