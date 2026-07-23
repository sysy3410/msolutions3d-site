// ============================================================
// MSolutions3D — chargement dynamique du portfolio
// Récupère les projets via l'API et remplit les grilles des pages
// « Impression 3D » (réalisations) et « Logiciels » (projets).
// ============================================================

(function () {
  "use strict";

  function esc(value) {
    const d = document.createElement("div");
    d.textContent = value == null ? "" : String(value);
    return d.innerHTML;
  }

  function tagSpans(tags) {
    return (tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join(" ");
  }

  function featureItems(features) {
    return (features || []).map((f) => `<li>${esc(f)}</li>`).join("");
  }

  // Carte « réalisation » (impression 3D)
  function cardImpression(p) {
    const img = p.image
      ? `<img src="${esc(p.image)}" alt="${esc(p.title)}" class="realisation-img" loading="lazy">`
      : "";
    const tags =
      p.tags && p.tags.length ? `<p class="audience-tags">${tagSpans(p.tags)}</p>` : "";
    const cls = p.image ? " clickable-card" : "";
    const data = p.image ? ` data-full="${esc(p.image)}" data-caption="${esc(p.title)}"` : "";
    return (
      `<article class="card realisation${cls}"${data}>` +
      `${img}<h3>${esc(p.title)}</h3>` +
      `<p>${esc(p.description)}</p>${tags}</article>`
    );
  }

  // Carte « projet logiciel »
  function cardLogiciel(p) {
    const head = p.image
      ? `<img src="${esc(p.image)}" alt="${esc(p.title)}" class="product-logo">`
      : `<div class="product-logo product-logo-custom" aria-hidden="true">✦</div>`;
    const sub = p.subtitle ? `<p class="card-tag">${esc(p.subtitle)}</p>` : "";
    const desc = p.description ? `<p>${esc(p.description)}</p>` : "";
    const feats =
      p.features && p.features.length
        ? `<ul class="feature-list">${featureItems(p.features)}</ul>`
        : "";
    const cls = p.image ? " clickable-card" : "";
    const data = p.image ? ` data-full="${esc(p.image)}" data-caption="${esc(p.title)}"` : "";
    return (
      `<article class="card card-product injected${cls}"${data}>` +
      `<div class="card-product-head">${head}<div><h3>${esc(p.title)}</h3>${sub}</div></div>` +
      `${desc}${feats}</article>`
    );
  }

  async function load() {
    const containers = document.querySelectorAll("[data-portfolio]");
    if (!containers.length) return;

    let data;
    try {
      const res = await fetch("/api/projects", { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error("HTTP " + res.status);
      data = await res.json();
    } catch (err) {
      // API indisponible (site ouvert sans le serveur) : on laisse le
      // contenu statique en place (ex. la carte « offre sur mesure »).
      console.warn("Portfolio : API indisponible,", err.message);
      return;
    }

    containers.forEach((container) => {
      const type = container.getAttribute("data-portfolio");
      const items = data.filter((p) => p.type === type);

      if (type === "impression3d") {
        const limit = parseInt(container.getAttribute("data-limit") || "0", 10);
        const shown = limit > 0 ? items.slice(0, limit) : items;
        container.innerHTML = shown.map(cardImpression).join("");
        const empty = container.parentElement.querySelector(".portfolio-empty");
        if (empty) empty.hidden = items.length > 0;
        // Bouton « voir toutes les réalisations » : visible dès qu'il y a des réalisations.
        const more = container.parentElement.querySelector(".realisations-more");
        if (more) more.hidden = items.length === 0;
      } else if (type === "logiciel") {
        // Nettoie d'éventuelles cartes déjà injectées, garde l'offre statique.
        container.querySelectorAll(".injected").forEach((n) => n.remove());
        const offer = container.querySelector(".offer-card");
        const html = items.map(cardLogiciel).join("");
        if (offer) offer.insertAdjacentHTML("beforebegin", html);
        else container.innerHTML = html;
      }
    });
  }

  // ---- Visionneuse d'image (lightbox) ----------------------------------
  let lightboxEl = null;

  function ensureLightbox() {
    if (lightboxEl) return lightboxEl;
    lightboxEl = document.createElement("div");
    lightboxEl.className = "lightbox";
    lightboxEl.innerHTML =
      '<button class="lightbox-close" type="button" aria-label="Fermer">×</button>' +
      '<img class="lightbox-img" alt="">' +
      '<p class="lightbox-caption"></p>';
    document.body.appendChild(lightboxEl);
    const close = () => lightboxEl.classList.remove("open");
    lightboxEl.addEventListener("click", (e) => {
      if (e.target === lightboxEl || e.target.classList.contains("lightbox-close")) close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && lightboxEl.classList.contains("open")) close();
    });
    return lightboxEl;
  }

  function openLightbox(src, caption) {
    if (!src) return;
    const lb = ensureLightbox();
    lb.querySelector(".lightbox-img").src = src;
    lb.querySelector(".lightbox-caption").textContent = caption || "";
    lb.classList.add("open");
  }

  // Clic sur une carte possédant une image → agrandissement
  document.addEventListener("click", (e) => {
    const card = e.target.closest(".clickable-card");
    if (!card || e.target.closest("a, button")) return;
    openLightbox(card.getAttribute("data-full"), card.getAttribute("data-caption"));
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
