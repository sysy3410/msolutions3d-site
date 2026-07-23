// ============================================================
// MSolutions3D — espace client
// ============================================================

(function () {
  "use strict";

  const TOKEN_KEY = "msolution_client_token";
  let token = localStorage.getItem(TOKEN_KEY) || "";

  const $ = (id) => document.getElementById(id);
  const loginView = $("loginView");
  const appView = $("appView");
  const logoutBtn = $("logoutBtn");

  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 2600);
  }

  async function api(path, options = {}) {
    const opts = Object.assign({ headers: {} }, options);
    if (token) opts.headers["Authorization"] = "Bearer " + token;
    const res = await fetch(path, opts);
    if (res.status === 401) { logout(); throw new Error("Session expirée."); }
    if (!res.ok) {
      let detail = "Erreur " + res.status;
      try { const d = await res.json(); if (d && d.detail) detail = d.detail; } catch (e) {}
      throw new Error(detail);
    }
    return res.json();
  }

  function esc(v) { const d = document.createElement("div"); d.textContent = v == null ? "" : String(v); return d.innerHTML; }

  function showLogin() { loginView.hidden = false; appView.hidden = true; logoutBtn.hidden = true; }
  function showApp(user) {
    loginView.hidden = true; appView.hidden = false; logoutBtn.hidden = false;
    $("clientName").textContent = user.name || user.email;
    loadOrders(); loadInvoices(); loadMessages();
  }
  function logout() { token = ""; localStorage.removeItem(TOKEN_KEY); showLogin(); }

  // ---- Commandes ----
  async function loadOrders() {
    let list;
    try { list = await api("/api/client/orders"); } catch (e) { return; }
    $("cOrders").textContent = "(" + list.length + ")";
    $("clientOrders").innerHTML = list.length
      ? list.map(orderCard).join("")
      : `<p class="empty-note">Aucune commande pour l'instant.</p>`;
  }

  function orderCard(o) {
    let timeline;
    if (o.status === "annulee") {
      timeline = `<p><span class="status-badge st-annulee">Commande annulée</span></p>`;
    } else {
      const steps = o.steps.map((s, idx) => {
        const cls = o.step >= 0 ? (idx < o.step ? "done" : idx === o.step ? "done current" : "") : "";
        return `<div class="timeline-step ${cls}">${esc(s.label)}</div>`;
      }).join("");
      timeline = `<div class="timeline">${steps}</div>`;
    }
    const ref = o.reference ? esc(o.reference) + " — " : "";
    const meta = [o.amount ? "Montant HT : " + o.amount : "", o.due_date ? "Échéance : " + o.due_date : ""].filter(Boolean).join(" · ");
    const docs = (o.documents || []).filter((d) => d.has_file);
    const docsHtml = docs.length
      ? `<p class="order-meta" style="margin-top:0.7rem">Documents : ` +
        docs.map((d) => `<button class="btn-sm" data-download="${d.id}">${esc(d.kind_label)} ${esc(d.number)}</button>`).join(" ") + `</p>`
      : "";
    const acceptHtml = o.can_accept
      ? `<button class="btn btn-primary" data-accept="${o.id}" style="margin-top:0.8rem">✓ Accepter le devis</button>`
      : "";
    return `<article class="card order-card" style="margin-bottom:1rem">` +
      `<h3>${ref}${esc(o.title)}</h3>` +
      (o.description ? `<p class="order-meta">${esc(o.description)}</p>` : "") +
      (meta ? `<p class="order-meta">${esc(meta)}</p>` : "") +
      timeline + docsHtml + acceptHtml + `</article>`;
  }

  // Accepter un devis
  document.getElementById("appView").addEventListener("click", async (e) => {
    const acc = e.target.closest("button[data-accept]");
    if (!acc) return;
    if (!confirm("Accepter ce devis ? Votre commande passera en production.")) return;
    try {
      await api("/api/client/orders/" + acc.getAttribute("data-accept") + "/accept", { method: "POST" });
      toast("Devis accepté — merci !");
      loadOrders();
    } catch (err) { toast(err.message); }
  });

  // ---- Factures ----
  async function loadInvoices() {
    let list;
    try { list = await api("/api/client/invoices"); } catch (e) { return; }
    $("cInvoices").textContent = "(" + list.length + ")";
    $("clientInvoices").innerHTML = list.length
      ? list.map(invoiceRow).join("")
      : `<p class="empty-note">Aucune facture pour l'instant.</p>`;
  }

  function invoiceRow(i) {
    const meta = [i.label, i.amount, i.issued_date, (i.paid && i.paid_at) ? "réglée le " + i.paid_at : ""].filter(Boolean).join(" · ");
    const payBadge = `<span class="status-badge ${i.paid ? "st-paye" : "st-apayer"}">${esc(i.payment_label)}</span>`;
    const btn = i.has_file
      ? `<button class="btn-sm" data-download="${i.id}">Télécharger le PDF</button>`
      : `<span class="hint">PDF indisponible</span>`;
    return `<div class="proj-row"><div class="proj-thumb">🧾</div>` +
      `<div class="proj-info"><h3>${esc(i.number || "Facture #" + i.id)} ${payBadge}</h3><p>${esc(meta)}</p></div>` +
      `<div class="proj-actions">${btn}</div></div>`;
  }

  // Téléchargement sécurisé (avec le jeton dans l'en-tête, pas dans l'URL)
  document.getElementById("appView").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-download]");
    if (!btn) return;
    const id = btn.getAttribute("data-download");
    try {
      const res = await fetch("/api/client/invoices/" + id + "/download", { headers: { Authorization: "Bearer " + token } });
      if (!res.ok) throw new Error("Téléchargement impossible.");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "facture-" + id + ".pdf";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 3000);
    } catch (err) { toast(err.message); }
  });

  $("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("loginError").textContent = "";
    const fd = new FormData();
    fd.append("email", $("email").value.trim());
    fd.append("password", $("password").value);
    try {
      const res = await fetch("/api/auth/login", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Connexion refusée.");
      token = data.token;
      localStorage.setItem(TOKEN_KEY, token);
      $("password").value = "";
      const me = await api("/api/auth/me");
      showApp(me);
    } catch (err) {
      $("loginError").textContent = err.message;
    }
  });

  logoutBtn.addEventListener("click", logout);

  // Mot de passe oublié
  $("forgotLink").addEventListener("click", (e) => {
    e.preventDefault();
    $("forgotBox").hidden = !$("forgotBox").hidden;
    $("forgotEmail").value = $("email").value;
  });

  $("forgotBtn").addEventListener("click", async () => {
    const email = $("forgotEmail").value.trim();
    if (!email) { $("forgotMsg").textContent = "Indiquez votre e-mail."; return; }
    const fd = new FormData();
    fd.append("email", email);
    try {
      await fetch("/api/auth/password-reset/request", { method: "POST", body: fd });
      $("forgotMsg").textContent = "Si un compte existe, un e-mail vient d'être envoyé.";
    } catch (e) {
      $("forgotMsg").textContent = "Si un compte existe, un e-mail vient d'être envoyé.";
    }
  });

  // ---- Messagerie ----
  function fmtTime(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  async function loadMessages() {
    let msgs;
    try { msgs = await api("/api/client/messages"); } catch (e) { return; }
    const thread = $("clientThread");
    thread.innerHTML = msgs.length
      ? msgs.map((m) => `<div class="msg-bubble msg-${m.sender}">${esc(m.body)}<span class="msg-time">${fmtTime(m.created_at)}</span></div>`).join("")
      : `<p class="msg-empty">Aucun message. Écrivez-nous, nous répondrons rapidement.</p>`;
    thread.scrollTop = thread.scrollHeight;
  }
  document.getElementById("clientMsgForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("clientMsgError").textContent = "";
    const body = $("clientMsgBody").value.trim();
    if (!body) return;
    const fd = new FormData(); fd.append("body", body);
    try {
      await api("/api/client/messages", { method: "POST", body: fd });
      $("clientMsgBody").value = "";
      loadMessages();
    } catch (err) { $("clientMsgError").textContent = err.message; }
  });

  // ---- Changer mon mot de passe ----
  document.getElementById("changePwForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("pwError").textContent = ""; $("pwSuccess").hidden = true;
    const cur = $("curPw").value, np = $("newPw").value, np2 = $("newPw2").value;
    if (np !== np2) { $("pwError").textContent = "Les deux nouveaux mots de passe ne correspondent pas."; return; }
    const fd = new FormData(); fd.append("current_password", cur); fd.append("new_password", np);
    try {
      await api("/api/auth/change-password", { method: "POST", body: fd });
      $("changePwForm").reset();
      $("pwSuccess").hidden = false;
      toast("Mot de passe modifié.");
    } catch (err) { $("pwError").textContent = err.message; }
  });

  // Démarrage
  async function boot() {
    if (!token) { showLogin(); return; }
    try {
      const me = await api("/api/auth/me");
      showApp(me);
    } catch (err) { showLogin(); }
  }

  boot();
})();
