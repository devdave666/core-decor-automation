// Token-gated in-browser editor for shop/products.json. The token is a
// GitHub fine-grained PAT the user creates and pastes in themselves -- it
// lives ONLY in this browser's localStorage and is sent only to
// api.github.com, never anywhere else, never written to any file in this
// repo. This admin page is not linked from the public shop page.

const OWNER = "devdave666";
const REPO = "core-decor-automation";
const FILE_PATH = "shop/products.json";
const BRANCH = "main";
const TOKEN_KEY = "coredecor_shop_admin_token";

const tokenGate = document.getElementById("token-gate");
const toolbar = document.getElementById("toolbar");
const statusLine = document.getElementById("status-line");
const grid = document.getElementById("admin-grid");
const modalBackdrop = document.getElementById("modal-backdrop");
const modalTitle = document.getElementById("modal-title");
const modalName = document.getElementById("modal-name");
const modalUrl = document.getElementById("modal-url");
const modalError = document.getElementById("modal-error");

let currentSha = null;
let currentProducts = null;
let activeProductId = null;

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

function renderGrid() {
  grid.innerHTML = "";
  for (const product of currentProducts) {
    const card = document.createElement("div");
    card.className = `admin-card ${product.productUrl ? "is-linked" : "is-blank"}`;
    card.dataset.id = product.id;

    const img = document.createElement("img");
    img.src = product.image;
    img.alt = `${product.style} ${product.room}`;
    img.loading = "lazy";
    card.appendChild(img);

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

    const productLine = document.createElement("p");
    productLine.className = "admin-card-product";
    productLine.textContent = product.productName || "";
    body.appendChild(productLine);

    card.appendChild(body);
    card.addEventListener("click", () => openModal(product.id));
    grid.appendChild(card);
  }
}

function openModal(id) {
  activeProductId = id;
  const product = currentProducts.find((p) => p.id === id);
  modalTitle.textContent = `${product.id} — ${product.room}, ${product.style}`;
  modalName.value = product.productName || "";
  modalUrl.value = product.productUrl || "";
  modalError.hidden = true;
  modalBackdrop.hidden = false;
  modalName.focus();
}

function closeModal() {
  modalBackdrop.hidden = true;
  activeProductId = null;
}

async function handleSave() {
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
  const previous = { productName: product.productName, productUrl: product.productUrl };
  product.productName = name || null;
  product.productUrl = url || null;

  statusLine.textContent = `Saving ${activeProductId}...`;
  try {
    await saveProducts(token, currentProducts, `Shop admin: update ${activeProductId}`);
    statusLine.textContent = `Saved ${activeProductId} — live in about a minute.`;
    renderGrid();
    closeModal();
  } catch (err) {
    product.productName = previous.productName;
    product.productUrl = previous.productUrl;
    modalError.textContent = err.message;
    modalError.hidden = false;
    statusLine.textContent = "Save failed.";
  }
}

async function handleClear() {
  modalName.value = "";
  modalUrl.value = "";
  await handleSave();
}

function showTokenGate() {
  tokenGate.hidden = false;
  toolbar.hidden = true;
  grid.hidden = true;
}

async function showAdmin(token) {
  tokenGate.hidden = true;
  toolbar.hidden = false;
  statusLine.textContent = "Loading products...";
  try {
    const { products, sha } = await fetchProducts(token);
    currentProducts = products;
    currentSha = sha;
    grid.hidden = false;
    statusLine.textContent = `${products.length} concepts, ${products.filter((p) => p.productUrl).length} linked.`;
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
document.getElementById("modal-clear").addEventListener("click", handleClear);
modalBackdrop.addEventListener("click", (e) => {
  if (e.target === modalBackdrop) closeModal();
});

const existingToken = getToken();
if (existingToken) {
  showAdmin(existingToken);
} else {
  showTokenGate();
}
