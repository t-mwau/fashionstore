let products = [];
const productGrid = document.getElementById("productGrid");
const cartCount = document.getElementById("cartCount");
const cartItems = document.getElementById("cartItems");
const cartTotal = document.getElementById("cartTotal");
const checkoutButton = document.getElementById("checkoutBtn");
const searchInput = document.getElementById("searchInput");
const liveMessage = document.getElementById("storeMessage");
const productResults = document.getElementById("productResults");
const categoryButtons = [...document.querySelectorAll(".category-btn")];
const checkoutModal = new bootstrap.Modal(document.getElementById("checkoutModal"));

let activeCategory = "All";
let cart = [];

function loadCart() {
  try {
    const saved = JSON.parse(localStorage.getItem("urbanwear-cart") || "[]");
    if (!Array.isArray(saved)) return [];
    return saved.filter(item =>
      Number.isInteger(item.id) &&
      Number.isInteger(item.quantity) &&
      item.quantity > 0 &&
      products.some(product => product.id === item.id)
    );
  } catch (error) {
    console.error("Unable to read the saved cart.", error);
    return [];
  }
}

function money(amount) {
  return `KSh ${amount.toLocaleString("en-KE")}`;
}

function saveCart() {
  try {
    localStorage.setItem("urbanwear-cart", JSON.stringify(cart));
  } catch (error) {
    console.error("Unable to save the cart in this browser.", error);
    showMessage("Your cart is available for this visit but could not be saved in this browser.", "warning");
  }
}

function showMessage(message, type = "info") {
  liveMessage.textContent = message;
  liveMessage.className = `alert alert-${type} py-2`;
  liveMessage.hidden = false;
}

function renderProducts() {
  const search = searchInput.value.trim().toLocaleLowerCase();
  const filtered = products.filter(product => {
    const categoryMatches = activeCategory === "All" || product.category === activeCategory;
    const searchMatches = `${product.name} ${product.category}`.toLocaleLowerCase().includes(search);
    return categoryMatches && searchMatches;
  });

  if (filtered.length === 0) {
    productResults.textContent = "No products found.";
    productGrid.innerHTML = '<p class="col-12 text-center py-5">No products match your search. Try another name or category.</p>';
    return;
  }

  productResults.textContent = `Showing ${filtered.length} ${filtered.length === 1 ? "product" : "products"}.`;
  productGrid.innerHTML = filtered.map(product => `
    <article class="col-6 col-lg-3">
      <div class="card product-card shadow-sm h-100">
        <img src="images/${product.image}" class="product-image"
             id="product-image-${product.id}"
             alt="${product.name}" loading="lazy" width="440" height="440">
        <div class="card-body px-2 px-md-3 d-flex flex-column">
          <p class="product-category mb-1">${product.category}</p>
          <h3 class="product-name">${product.name}</h3>
          ${product.gallery?.length ? `
            <div class="product-gallery" role="group" aria-label="${product.name} photos">
              <button type="button" class="product-image-choice active"
                      data-product-id="${product.id}" data-image="${product.image}"
                      aria-label="Show photo 1 of ${product.name}" aria-pressed="true">
                <img src="images/${product.image}" alt="" loading="lazy">
              </button>
              ${product.gallery.map((image, index) => `
                <button type="button" class="product-image-choice"
                        data-product-id="${product.id}" data-image="${image}"
                        aria-label="Show photo ${index + 2} of ${product.name}" aria-pressed="false">
                  <img src="images/${image}" alt="" loading="lazy">
                </button>
              `).join("")}
            </div>
          ` : ""}
          <p class="product-price mt-auto mb-3">${money(product.price)}</p>
          <button class="btn btn-dark w-100 add-to-cart" type="button"
                  data-product-id="${product.id}" aria-label="Add ${product.name} to cart">
            Add to Cart
          </button>
        </div>
      </div>
    </article>
  `).join("");
}

function renderCart() {
  const count = cart.reduce((sum, item) => sum + item.quantity, 0);
  const total = cart.reduce((sum, item) => {
    const product = products.find(candidate => candidate.id === item.id);
    return sum + product.price * item.quantity;
  }, 0);

  cartCount.textContent = count;
  cartTotal.textContent = money(total);
  checkoutButton.disabled = cart.length === 0;

  if (cart.length === 0) {
    cartItems.innerHTML = '<p class="text-center text-secondary py-4">Your cart is empty. Add an item to get started.</p>';
    saveCart();
    return;
  }

  cartItems.innerHTML = cart.map(item => {
    const product = products.find(candidate => candidate.id === item.id);
    return `
      <div class="d-flex justify-content-between align-items-center gap-3 border-bottom py-3">
        <div class="d-flex align-items-center gap-3">
          <img class="cart-product-image" src="images/${product.image}" alt="">
          <div>
            <h3 class="cart-product-name mb-1">${product.name}</h3>
            <small>${money(product.price)} each</small>
            <div class="mt-2 d-flex align-items-center gap-2">
              <button class="btn btn-sm btn-outline-secondary quantity-change"
                      data-product-id="${product.id}" data-change="-1"
                      aria-label="Remove one ${product.name}">−</button>
              <span aria-label="Quantity">${item.quantity}</span>
              <button class="btn btn-sm btn-outline-secondary quantity-change"
                      data-product-id="${product.id}" data-change="1"
                      aria-label="Add one ${product.name}">+</button>
            </div>
          </div>
        </div>
        <strong>${money(product.price * item.quantity)}</strong>
      </div>
    `;
  }).join("");

  saveCart();
}

function addToCart(id) {
  const item = cart.find(candidate => candidate.id === id);
  if (item) item.quantity += 1;
  else cart.push({ id, quantity: 1 });
  renderCart();
  const product = products.find(candidate => candidate.id === id);
  showMessage(`${product.name} added to your cart.`, "success");
}

function changeQuantity(id, change) {
  const item = cart.find(candidate => candidate.id === id);
  if (!item) return;
  item.quantity += change;
  if (item.quantity <= 0) cart = cart.filter(candidate => candidate.id !== id);
  renderCart();
}

document.querySelectorAll(".category-btn").forEach(button => {
  button.addEventListener("click", () => {
    activeCategory = button.dataset.category;
    categoryButtons.forEach(categoryButton => {
      const selected = categoryButton === button;
      categoryButton.classList.toggle("active", selected);
      categoryButton.setAttribute("aria-pressed", String(selected));
    });
    renderProducts();
  });
});

searchInput.addEventListener("input", renderProducts);

productGrid.addEventListener("click", event => {
  const imageChoice = event.target.closest(".product-image-choice");
  if (imageChoice) {
    const { productId, image } = imageChoice.dataset;
    const product = products.find(candidate => candidate.id === Number(productId));
    const imageElement = document.getElementById(`product-image-${productId}`);
    imageElement.src = `images/${image}`;
    imageElement.alt = product.name;
    imageChoice.closest(".product-gallery").querySelectorAll(".product-image-choice").forEach(button => {
      const selected = button === imageChoice;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    return;
  }
  const button = event.target.closest(".add-to-cart");
  if (button) addToCart(Number(button.dataset.productId));
});

cartItems.addEventListener("click", event => {
  const button = event.target.closest(".quantity-change");
  if (button) changeQuantity(Number(button.dataset.productId), Number(button.dataset.change));
});

document.getElementById("newsletterForm").addEventListener("submit", event => {
  event.preventDefault();
  showMessage("Thanks for subscribing. Newsletter delivery will be enabled when email service is connected.", "success");
  event.target.reset();
});

checkoutButton.addEventListener("click", () => {
  document.getElementById("checkoutAmount").textContent = cartTotal.textContent;
  document.getElementById("checkoutMessage").hidden = true;
  checkoutModal.show();
});

document.getElementById("mpesaForm").addEventListener("submit", async event => {
  event.preventDefault();
  const submitButton = document.getElementById("mpesaSubmit");
  const message = document.getElementById("checkoutMessage");
  submitButton.disabled = true;
  submitButton.textContent = "Contacting M-Pesa sandbox…";
  message.hidden = false;
  message.className = "alert alert-info";
  message.textContent = "Requesting a sandbox payment prompt. Do not enter a real PIN in a test environment.";

  try {
    const response = await fetch("/api/mpesa/stkpush", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        phone: document.getElementById("mpesaPhone").value,
        items: cart.map(item => ({ id: item.id, quantity: item.quantity }))
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The M-Pesa sandbox request failed.");

    message.className = "alert alert-success";
    message.textContent = result.message;
    await pollPaymentStatus(result.checkoutRequestID, message);
  } catch (error) {
    message.className = "alert alert-warning";
    message.textContent = error.message;
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Send M-Pesa sandbox prompt";
  }
});

async function pollPaymentStatus(checkoutRequestID, message) {
  const maxAttempts = 24;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 5000));
    try {
      const response = await fetch(`/api/mpesa/status?checkoutRequestID=${encodeURIComponent(checkoutRequestID)}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not check sandbox payment status.");
      if (result.status === "paid") {
        message.className = "alert alert-success";
        message.textContent = "Sandbox payment confirmed. This is a test transaction, not a real charge.";
        cart = [];
        renderCart();
        return;
      }
      if (result.status === "failed") {
        message.className = "alert alert-danger";
        message.textContent = result.message || "The sandbox payment was not completed.";
        return;
      }
      message.textContent = result.message;
    } catch (error) {
      message.className = "alert alert-warning";
      message.textContent = error.message;
      return;
    }
  }
  message.className = "alert alert-warning";
  message.textContent = "No sandbox callback has arrived yet. Check the payment status with the store before retrying.";
}

document.getElementById("year").textContent = new Date().getFullYear();
fetch("products.json")
  .then(response => {
    if (!response.ok) throw new Error(`Could not load the product list (HTTP ${response.status}).`);
    return response.json();
  })
  .then(catalog => {
    if (!Array.isArray(catalog) || catalog.length === 0) {
      throw new Error("The product list is empty or invalid.");
    }
    products = catalog;
    const listedImages = catalog.flatMap(product => [product.image, ...(product.gallery || [])]);
    const actualImages = Array.from({ length: 41 }, (_, index) => `image${index}.png`)
      .filter(image => image !== "image25.png");
    const unusedImages = actualImages.filter(image => !listedImages.includes(image));
    if (unusedImages.length) {
      throw new Error(`These image files are not assigned to the catalog: ${unusedImages.join(", ")}.`);
    }
    cart = loadCart();
    renderProducts();
    renderCart();
  })
  .catch(error => {
    console.error("Unable to initialize UrbanWear.", error);
    productGrid.innerHTML = '<p class="col-12 text-center py-5">Products could not be loaded. Refresh the page or contact the store.</p>';
    showMessage(error.message, "danger");
  });
