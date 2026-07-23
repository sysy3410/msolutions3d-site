// ============================================================
// MSolutions3D — interface d'administration
// ============================================================

(function () {
  "use strict";

  const TOKEN_KEY = "msolution_admin_token";
  let token = localStorage.getItem(TOKEN_KEY) || "";

  const $ = (id) => document.getElementById(id);
  const loginView = $("loginView");
  const appView = $("appView");
  const logoutBtn = $("logoutBtn");

  let projects = [];
  let clients = [];
  let orders = [];
  let invoices = [];
  let threads = [];
  let currentThreadId = null;
  let spools = [];
  let expenses = [];
  let settings = null;
  let devProjects = [];
  let currentProjectId = null;
  let currentTasks = [];
  let calcInited = false;
  let calcPriceHT = 0;

  function esc(v) {
    const d = document.createElement("div");
    d.textContent = v == null ? "" : String(v);
    return d.innerHTML;
  }
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 2600);
  }

  // ---- API --------------------------------------------------------------
  async function api(path, options = {}) {
    const opts = Object.assign({ headers: {} }, options);
    if (token) opts.headers["Authorization"] = "Bearer " + token;
    const res = await fetch(path, opts);
    if (res.status === 401) { logout(); throw new Error("Session expirée. Reconnectez-vous."); }
    if (!res.ok) {
      let detail = "Erreur " + res.status;
      try { const d = await res.json(); if (d && d.detail) detail = d.detail; } catch (e) {}
      throw new Error(detail);
    }
    if (res.status === 204) return null;
    return res.json();
  }

  // ---- Authentification -------------------------------------------------
  function showLogin() { loginView.hidden = false; appView.hidden = true; logoutBtn.hidden = true; }
  function showApp() {
    loginView.hidden = true; appView.hidden = false; logoutBtn.hidden = false;
    loadProjects(); loadClients(); loadOrders(); loadInvoices(); loadThreads();
    loadFilament(); loadExpenses(); loadAccounting(); loadSettings(); loadDevProjects();
  }
  function logout() { token = ""; localStorage.removeItem(TOKEN_KEY); showLogin(); }

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
      if (data.role !== "admin") throw new Error("Ce compte n'est pas administrateur.");
      token = data.token;
      localStorage.setItem(TOKEN_KEY, token);
      $("password").value = "";
      showApp();
    } catch (err) { $("loginError").textContent = err.message; }
  });
  logoutBtn.addEventListener("click", logout);

  // ---- Onglets ----------------------------------------------------------
  $("tabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    const name = btn.getAttribute("data-tab");
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === btn));
    document.querySelectorAll(".tab-panel").forEach((p) => {
      p.hidden = p.getAttribute("data-panel") !== name;
    });
    if (name === "devprojects") showDevList();
    if (name === "orders") showOrderList();
    if (name === "calc") initCalc();
  });

  // ---- Projets ----------------------------------------------------------
  async function loadProjects() {
    try { projects = await api("/api/projects"); } catch (e) { return; }
    const g = { impression3d: [], logiciel: [] };
    projects.forEach((p) => { if (g[p.type]) g[p.type].push(p); });
    renderProjectList("list-impression3d", g.impression3d, "count3d");
    renderProjectList("list-logiciel", g.logiciel, "countLog");
  }
  function projectRow(p) {
    const thumb = p.image
      ? `<img class="proj-thumb" src="${esc(p.image)}" alt="">`
      : `<div class="proj-thumb">${p.type === "logiciel" ? "&lt;/&gt;" : "🧩"}</div>`;
    const meta = p.type === "impression3d"
      ? (p.tags && p.tags.length ? p.tags.join(", ") : "—")
      : (p.subtitle || "—");
    return `<div class="proj-row">${thumb}<div class="proj-info"><h3>${esc(p.title)}</h3><p>${esc(meta)}</p></div>` +
      `<div class="proj-actions"><button class="btn-sm" data-act="edit" data-id="${p.id}">Modifier</button>` +
      `<button class="btn-sm btn-danger" data-act="delete" data-id="${p.id}">Supprimer</button></div></div>`;
  }
  function renderProjectList(id, items, countId) {
    $(countId).textContent = "(" + items.length + ")";
    $(id).innerHTML = items.length ? items.map(projectRow).join("") : `<p class="empty-note">Aucun projet.</p>`;
  }

  // ---- Clients ----------------------------------------------------------
  async function loadClients() {
    try { clients = await api("/api/admin/clients"); } catch (e) { return; }
    $("countClients").textContent = "(" + clients.length + ")";
    $("list-clients").innerHTML = clients.length ? clients.map(clientRow).join("") : `<p class="empty-note">Aucun client.</p>`;
    fillClientSelect($("orderClient"));
    fillClientSelect($("invoiceClient"));
  }
  function clientRow(c) {
    const status = c.active ? "" : " · désactivé";
    const meta = (c.company ? c.company + " · " : "") + c.email + status;
    return `<div class="proj-row"><div class="proj-thumb">👤</div>` +
      `<div class="proj-info"><h3>${esc(c.name || c.email)}</h3><p>${esc(meta)}</p></div>` +
      `<div class="proj-actions"><button class="btn-sm" data-cact="link" data-cid="${c.id}">Lien mot de passe</button>` +
      `<button class="btn-sm" data-cact="edit" data-cid="${c.id}">Modifier</button>` +
      `<button class="btn-sm btn-danger" data-cact="delete" data-cid="${c.id}">Supprimer</button></div></div>`;
  }
  function fillClientSelect(sel, selectedId) {
    if (!sel) return;
    sel.innerHTML = `<option value="">— choisir un client —</option>` +
      clients.map((c) => `<option value="${c.id}"${c.id === selectedId ? " selected" : ""}>` +
        `${esc(c.name || c.email)}${c.company ? " (" + esc(c.company) + ")" : ""}</option>`).join("");
  }

  // ---- Commandes --------------------------------------------------------
  async function loadOrders() {
    try { orders = await api("/api/admin/orders"); } catch (e) { return; }
    $("countOrders").textContent = "(" + orders.length + ")";
    $("list-orders").innerHTML = orders.length ? orders.map(orderRow).join("") : `<p class="empty-note">Aucune commande.</p>`;
  }
  function orderRow(o) {
    const meta = [o.client_name, o.category, o.amount].filter(Boolean).join(" · ");
    const badge = `<span class="status-badge st-${esc(o.status)}">${esc(o.status_label)}</span>`;
    const ref = o.reference ? esc(o.reference) + " — " : "";
    return `<div class="proj-row"><div class="proj-thumb">📦</div>` +
      `<div class="proj-info"><h3>${ref}${esc(o.title)} ${badge}</h3><p>${esc(meta)}</p></div>` +
      `<div class="proj-actions"><button class="btn-sm" data-oact="open" data-oid="${o.id}">Ouvrir</button>` +
      `<button class="btn-sm btn-danger" data-oact="delete" data-oid="${o.id}">Supprimer</button></div></div>`;
  }

  // ---- Factures ---------------------------------------------------------
  async function loadInvoices() {
    try { invoices = await api("/api/admin/invoices"); } catch (e) { return; }
    $("countInvoices").textContent = "(" + invoices.length + ")";
    $("list-invoices").innerHTML = invoices.length ? invoices.map(invoiceRow).join("") : `<p class="empty-note">Aucune facture.</p>`;
  }
  function invoiceRow(i) {
    const tag = (i.paid && i.paid_at) ? " · réglée le " + i.paid_at : (i.generated ? " · générée" : (i.has_file ? " · PDF importé" : ""));
    const meta = [i.client_name, i.amount, i.issued_date].filter(Boolean).join(" · ");
    const payBadge = `<span class="status-badge ${i.paid ? "st-paye" : "st-apayer"}">${esc(i.payment_label)}</span>`;
    const payBtn = `<button class="btn-sm" data-iact="pay" data-iid="${i.id}" data-paid="${i.paid ? 1 : 0}">${i.paid ? "Marquer à payer" : "Marquer payée"}</button>`;
    const dl = i.has_file ? `<button class="btn-sm" data-iact="download" data-iid="${i.id}">Voir le PDF</button>` : "";
    return `<div class="proj-row"><div class="proj-thumb">🧾</div>` +
      `<div class="proj-info"><h3>${esc(i.number || "Facture #" + i.id)} ${payBadge}</h3><p>${esc(meta)}${tag}</p></div>` +
      `<div class="proj-actions">${payBtn}${dl}<button class="btn-sm btn-danger" data-iact="delete" data-iid="${i.id}">Supprimer</button></div></div>`;
  }
  async function togglePayment(id, currentlyPaid) {
    const fd = new FormData();
    fd.append("paid", currentlyPaid ? "0" : "1");
    try {
      await api("/api/admin/invoices/" + id + "/payment", { method: "PUT", body: fd });
      toast(currentlyPaid ? "Facture remise à « à payer »." : "Facture marquée payée.");
      loadInvoices();
      if (currentOrderId) openOrder(currentOrderId);
    } catch (err) { toast(err.message); }
  }

  // ---- Délégation des clics --------------------------------------------
  appView.addEventListener("click", (e) => {
    const p = e.target.closest("button[data-act]");
    if (p) { const id = +p.dataset.id; p.dataset.act === "edit" ? openProjectForm(projects.find((x) => x.id === id)) : removeProject(id); return; }
    const c = e.target.closest("button[data-cact]");
    if (c) {
      const id = +c.dataset.cid; const a = c.dataset.cact;
      if (a === "edit") openClientForm(clients.find((x) => x.id === id));
      else if (a === "link") clientResetLink(id);
      else removeClient(id);
      return;
    }
    const o = e.target.closest("button[data-oact]");
    if (o) { const id = +o.dataset.oid; o.dataset.oact === "open" ? openOrder(id) : removeOrder(id); return; }
    const od = e.target.closest("button[data-docact]");
    if (od) {
      const id = +od.dataset.docid, a = od.dataset.docact;
      if (a === "send") sendDocument(id);
      else if (a === "pay") togglePayment(id, od.dataset.paid === "1");
      else downloadInvoice(id);
      return;
    }
    const i = e.target.closest("button[data-iact]");
    if (i) {
      const id = +i.dataset.iid, a = i.dataset.iact;
      if (a === "download") downloadInvoice(id);
      else if (a === "pay") togglePayment(id, i.dataset.paid === "1");
      else removeInvoice(id);
      return;
    }
    const t = e.target.closest("button[data-tact]");
    if (t) { openThread(+t.dataset.tid); return; }
    const s = e.target.closest("button[data-sact]");
    if (s) { const id = +s.dataset.sid; s.dataset.sact === "edit" ? openSpoolForm(spools.find((x) => x.id === id)) : removeSpool(id); return; }
    const x = e.target.closest("button[data-eact]");
    if (x) { const id = +x.dataset.eid; x.dataset.eact === "edit" ? openExpenseForm(expenses.find((y) => y.id === id)) : removeExpense(id); return; }
    const dp = e.target.closest("button[data-dpact]");
    if (dp) {
      const id = +dp.dataset.dpid, a = dp.dataset.dpact;
      if (a === "open") openDevProject(id);
      else removeDevProject(id);
      return;
    }
    const dt = e.target.closest("button[data-dtact]");
    if (dt) {
      const id = +dt.dataset.dtid;
      dt.dataset.dtact === "edit" ? openDevTaskForm(currentTasks.find((y) => y.id === id)) : removeDevTask(id);
    }
  });

  // ---- Modale projet ----------------------------------------------------
  const modal = $("modal");
  function applyTypeVisibility() {
    const type = $("type").value;
    document.querySelectorAll("[data-only]").forEach((el) => { el.hidden = el.getAttribute("data-only") !== type; });
  }
  $("type").addEventListener("change", applyTypeVisibility);
  function openProjectForm(project) {
    $("formError").textContent = ""; $("projectForm").reset();
    $("removeImage").checked = false; $("imagePreviewWrap").hidden = true;
    if (project) {
      $("modalTitle").textContent = "Modifier le projet";
      $("projectId").value = project.id; $("type").value = project.type;
      $("title").value = project.title || "";
      $("subtitle").value = project.subtitle || ""; $("description").value = project.description || "";
      $("tags").value = (project.tags || []).join(", "); $("features").value = (project.features || []).join("\n");
      $("position").value = project.position || 0;
      if (project.image) { $("imagePreview").src = project.image; $("imagePreviewWrap").hidden = false; }
    } else { $("modalTitle").textContent = "Ajouter un projet"; $("projectId").value = ""; $("position").value = 0; }
    applyTypeVisibility(); modal.hidden = false;
  }
  $("addBtn").addEventListener("click", () => openProjectForm(null));
  $("cancelBtn").addEventListener("click", () => (modal.hidden = true));
  modal.addEventListener("click", (e) => { if (e.target === modal) modal.hidden = true; });
  $("image").addEventListener("change", () => {
    const f = $("image").files[0]; if (!f) return;
    $("imagePreview").src = URL.createObjectURL(f); $("imagePreviewWrap").hidden = false; $("removeImage").checked = false;
  });
  $("projectForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("formError").textContent = "";
    const tags = $("tags").value.split(",").map((s) => s.trim()).filter(Boolean);
    const features = $("features").value.split("\n").map((s) => s.trim()).filter(Boolean);
    const fd = new FormData();
    fd.append("type", $("type").value); fd.append("title", $("title").value.trim());
    fd.append("subtitle", $("subtitle").value.trim());
    fd.append("description", $("description").value.trim());
    fd.append("tags", JSON.stringify(tags)); fd.append("features", JSON.stringify(features));
    fd.append("position", $("position").value || "0");
    if ($("removeImage").checked) fd.append("remove_image", "1");
    const file = $("image").files[0]; if (file) fd.append("image", file);
    const id = $("projectId").value;
    try {
      await api(id ? "/api/admin/projects/" + id : "/api/admin/projects", { method: id ? "PUT" : "POST", body: fd });
      modal.hidden = true; toast(id ? "Projet modifié." : "Projet ajouté."); loadProjects();
    } catch (err) { $("formError").textContent = err.message; }
  });
  async function removeProject(id) {
    const p = projects.find((x) => x.id === id);
    if (!p || !confirm(`Supprimer « ${p.title} » ?`)) return;
    try { await api("/api/admin/projects/" + id, { method: "DELETE" }); toast("Supprimé."); loadProjects(); } catch (err) { toast(err.message); }
  }

  // ---- Modale client ----------------------------------------------------
  const clientModal = $("clientModal");
  function openClientForm(client) {
    $("clientError").textContent = ""; $("clientForm").reset();
    if (client) {
      $("clientModalTitle").textContent = "Modifier le client";
      $("clientId").value = client.id; $("clientEmail").value = client.email; $("clientEmail").disabled = true;
      $("clientName").value = client.name || ""; $("clientCompany").value = client.company || "";
      $("clientPhone").value = client.phone || ""; $("clientActive").checked = client.active;
      $("clientInviteField").hidden = true; $("clientActiveField").hidden = false;
    } else {
      $("clientModalTitle").textContent = "Ajouter un client";
      $("clientId").value = ""; $("clientEmail").disabled = false; $("clientInvite").checked = true;
      $("clientInviteField").hidden = false; $("clientActiveField").hidden = true;
    }
    clientModal.hidden = false;
  }
  $("addClientBtn").addEventListener("click", () => openClientForm(null));
  $("clientCancelBtn").addEventListener("click", () => (clientModal.hidden = true));
  clientModal.addEventListener("click", (e) => { if (e.target === clientModal) clientModal.hidden = true; });
  $("clientForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("clientError").textContent = "";
    const id = $("clientId").value;
    const fd = new FormData();
    fd.append("name", $("clientName").value.trim()); fd.append("company", $("clientCompany").value.trim());
    fd.append("phone", $("clientPhone").value.trim());
    try {
      if (id) {
        fd.append("active", $("clientActive").checked ? "1" : "0");
        await api("/api/admin/clients/" + id, { method: "PUT", body: fd }); toast("Client mis à jour.");
      } else {
        fd.append("email", $("clientEmail").value.trim());
        fd.append("send_invite", $("clientInvite").checked ? "1" : "0");
        const created = await api("/api/admin/clients", { method: "POST", body: fd });
        if (created.generated_password) alert("Client créé.\n\nMot de passe provisoire (à transmettre) :\n" + created.generated_password);
        else if (created.invite_link) alert("Client créé. E-mail d'invitation envoyé.\n\nLien (au cas où) :\n" + created.invite_link);
        else toast("Client créé.");
      }
      clientModal.hidden = true; loadClients();
    } catch (err) { $("clientError").textContent = err.message; }
  });
  async function clientResetLink(id) {
    try { const r = await api("/api/admin/clients/" + id + "/reset-link", { method: "POST" });
      prompt("Lien de définition de mot de passe (valable 7 jours) :", r.link);
    } catch (err) { toast(err.message); }
  }
  async function removeClient(id) {
    const c = clients.find((x) => x.id === id);
    if (!c || !confirm(`Supprimer le compte de « ${c.name || c.email} » ?`)) return;
    try { await api("/api/admin/clients/" + id, { method: "DELETE" }); toast("Client supprimé."); loadClients(); } catch (err) { toast(err.message); }
  }

  // ---- Modale commande (avec lignes) -----------------------------------
  const orderModal = $("orderModal");
  let currentOrderId = null;
  let currentOrder = null;
  const euroCents = (c) => (((c || 0) / 100).toFixed(2)).replace(".", ",") + " €";

  function orderLineRow(desig, qty, unitEuro) {
    const div = document.createElement("div");
    div.className = "gen-line";
    div.style.cssText = "display:flex;gap:0.4rem;margin-bottom:0.4rem;align-items:center";
    div.innerHTML =
      `<input type="text" class="gl-desig" placeholder="Désignation" style="flex:1" value="${esc(desig || "")}">` +
      `<input type="text" class="gl-qty" placeholder="Qté" value="${esc(qty == null ? "1" : String(qty))}" style="width:3.5rem;text-align:center">` +
      `<input type="text" class="gl-pu" placeholder="PU HT €" style="width:6.5rem" value="${esc(unitEuro || "")}">` +
      `<button type="button" class="btn-sm gl-remove" title="Retirer">✕</button>`;
    return div;
  }
  function orderRecalc() {
    let total = 0;
    document.querySelectorAll("#orderLines .gen-line").forEach((row) => {
      const q = parseFloat((row.querySelector(".gl-qty").value || "1").replace(",", ".")) || 0;
      const pu = parseFloat((row.querySelector(".gl-pu").value || "0").replace(/[^\d.,-]/g, "").replace(",", ".")) || 0;
      total += q * pu;
    });
    $("orderTotalPreview").textContent = "Total HT : " + total.toFixed(2).replace(".", ",") + " €";
  }
  function collectOrderLines() {
    const lines = [];
    document.querySelectorAll("#orderLines .gen-line").forEach((row) => {
      const d = row.querySelector(".gl-desig").value.trim();
      if (d) lines.push({ designation: d, qty: row.querySelector(".gl-qty").value.trim() || "1", unit_price: row.querySelector(".gl-pu").value.trim() });
    });
    return lines;
  }

  function openOrderForm(order) {
    $("orderError").textContent = ""; $("orderForm").reset();
    fillClientSelect($("orderClient"), order ? order.client_id : undefined);
    $("orderLines").innerHTML = "";
    const vatOn = settings && settings.vat_applicable;
    $("orderVatField").hidden = !vatOn;
    if (order) {
      $("orderModalTitle").textContent = "Modifier la commande";
      $("orderId").value = order.id; $("orderClient").value = order.client_id; $("orderClient").disabled = true;
      $("orderTitle").value = order.title || ""; $("orderRef").value = order.reference || "";
      $("orderCategory").value = order.category || "autre"; $("orderStatus").value = order.status || "devis";
      $("orderDue").value = order.due_date || ""; $("orderDesc").value = order.description || "";
      if (vatOn) $("orderVat").value = order.vat_rate ? String(order.vat_rate).replace(".", ",") : (settings.default_vat_rate || "");
      (order.lines || []).forEach((l) => $("orderLines").appendChild(orderLineRow(l.designation, l.qty, l.unit_price_cents ? String(l.unit_price_cents / 100).replace(".", ",") : "")));
      if (!(order.lines || []).length) $("orderLines").appendChild(orderLineRow());
    } else {
      $("orderModalTitle").textContent = "Nouvelle commande";
      $("orderId").value = ""; $("orderClient").disabled = false;
      $("orderStatus").value = "devis"; $("orderCategory").value = "impression3d";
      if (vatOn) $("orderVat").value = settings.default_vat_rate || "";
      $("orderLines").appendChild(orderLineRow());
    }
    orderRecalc();
    orderModal.hidden = false;
  }
  $("addOrderBtn").addEventListener("click", () => {
    if (!clients.length) { toast("Ajoutez d'abord un client."); return; }
    openOrderForm(null);
  });
  $("orderAddLine").addEventListener("click", () => $("orderLines").appendChild(orderLineRow()));
  $("orderLines").addEventListener("click", (e) => { if (e.target.classList.contains("gl-remove")) { e.target.closest(".gen-line").remove(); orderRecalc(); } });
  $("orderLines").addEventListener("input", orderRecalc);
  $("orderCancelBtn").addEventListener("click", () => (orderModal.hidden = true));
  orderModal.addEventListener("click", (e) => { if (e.target === orderModal) orderModal.hidden = true; });
  $("orderForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("orderError").textContent = "";
    const id = $("orderId").value;
    const fd = new FormData();
    fd.append("title", $("orderTitle").value.trim()); fd.append("reference", $("orderRef").value.trim());
    fd.append("category", $("orderCategory").value); fd.append("status", $("orderStatus").value);
    fd.append("due_date", $("orderDue").value); fd.append("description", $("orderDesc").value.trim());
    fd.append("lines", JSON.stringify(collectOrderLines())); fd.append("vat_rate", $("orderVat").value.trim());
    try {
      if (id) {
        await api("/api/admin/orders/" + id, { method: "PUT", body: fd });
        orderModal.hidden = true; toast("Commande modifiée."); loadOrders();
        if (String(currentOrderId) === String(id)) openOrder(id);
      } else {
        fd.append("client_id", $("orderClient").value);
        if (!$("orderClient").value) throw new Error("Choisissez un client.");
        const created = await api("/api/admin/orders", { method: "POST", body: fd });
        orderModal.hidden = true; toast("Commande créée."); loadOrders(); openOrder(created.id);
      }
    } catch (err) { $("orderError").textContent = err.message; }
  });
  async function removeOrder(id) {
    const o = orders.find((x) => x.id === id);
    if (!o || !confirm(`Supprimer la commande « ${o.title} » ?`)) return;
    try { await api("/api/admin/orders/" + id, { method: "DELETE" }); toast("Commande supprimée."); loadOrders(); } catch (err) { toast(err.message); }
  }

  // ---- Vue détail de commande (cycle de vie) ---------------------------
  function showOrderList() { $("orderDetailView").hidden = true; $("orderListView").hidden = false; currentOrderId = null; }
  async function openOrder(id) {
    let d;
    try { d = await api("/api/admin/orders/" + id); } catch (e) { toast(e.message); return; }
    currentOrderId = id; currentOrder = d;
    $("orderListView").hidden = true; $("orderDetailView").hidden = false;
    $("orderDetailTitle").textContent = (d.reference ? d.reference + " — " : "") + d.title;
    const meta = [d.client_name ? "Client : " + d.client_name : "", d.status_label, "Total HT : " + d.amount,
      d.vat_rate ? "TVA " + String(d.vat_rate).replace(".", ",") + " %" : "", d.due_date ? "Échéance : " + d.due_date : ""].filter(Boolean).join("  ·  ");
    $("orderDetailMeta").textContent = meta + (d.description ? "  ·  " + d.description : "");
    $("orderStatusSelect").value = d.status;
    const lines = d.lines || [];
    $("orderLinesView").innerHTML = lines.length
      ? `<div class="acct-table-wrap"><table class="acct-table"><thead><tr><th>Désignation</th><th>Qté</th><th>PU HT</th><th>Total HT</th></tr></thead><tbody>` +
        lines.map((l) => `<tr><td>${esc(l.designation)}</td><td>${esc(String(l.qty))}</td><td>${euroCents(l.unit_price_cents)}</td><td>${euroCents(Math.round((l.qty || 1) * (l.unit_price_cents || 0)))}</td></tr>`).join("") +
        `</tbody><tfoot><tr><td>Total HT</td><td></td><td></td><td>${esc(d.amount)}</td></tr></tfoot></table></div>`
      : `<p class="empty-note">Aucune ligne. Cliquez sur « Modifier » pour en ajouter.</p>`;
    const docs = d.documents || [];
    $("orderDocs").innerHTML = docs.length ? docs.map(docRow).join("") : `<p class="empty-note">Aucun document. Générez un devis, puis la facture.</p>`;
  }
  function docRow(doc) {
    const kindBadge = `<span class="status-badge ${doc.kind === "devis" ? "st-devis" : "st-terminee"}">${esc(doc.kind_label)}</span>`;
    const payBadge = doc.kind === "facture" ? ` <span class="status-badge ${doc.paid ? "st-paye" : "st-apayer"}">${esc(doc.payment_label)}</span>` : "";
    const meta = [doc.amount, doc.issued_date, (doc.paid && doc.paid_at) ? "réglée le " + doc.paid_at : ""].filter(Boolean).join(" · ");
    const payBtn = doc.kind === "facture" ? `<button class="btn-sm" data-docact="pay" data-docid="${doc.id}" data-paid="${doc.paid ? 1 : 0}">${doc.paid ? "Marquer à payer" : "Marquer payée"}</button>` : "";
    return `<div class="proj-row"><div class="proj-thumb">${doc.kind === "devis" ? "📝" : "🧾"}</div>` +
      `<div class="proj-info"><h3>${esc(doc.number)} ${kindBadge}${payBadge}</h3><p>${esc(meta)}</p></div>` +
      `<div class="proj-actions">` +
      (doc.has_file ? `<button class="btn-sm" data-docact="view" data-docid="${doc.id}">Voir le PDF</button>` +
        `<button class="btn-sm" data-docact="send" data-docid="${doc.id}">Envoyer</button>` : "") +
      payBtn +
      `</div></div>`;
  }
  $("orderBackBtn").addEventListener("click", () => { showOrderList(); loadOrders(); });
  $("orderEditBtn").addEventListener("click", () => openOrderForm(currentOrder));
  $("orderStatusSelect").addEventListener("change", async () => {
    if (!currentOrder) return;
    const fd = new FormData();
    fd.append("title", currentOrder.title); fd.append("reference", currentOrder.reference || "");
    fd.append("category", currentOrder.category || "autre"); fd.append("status", $("orderStatusSelect").value);
    fd.append("due_date", currentOrder.due_date || ""); fd.append("description", currentOrder.description || "");
    fd.append("lines", JSON.stringify((currentOrder.lines || []).map((l) => ({ designation: l.designation, qty: l.qty, unit_price: String((l.unit_price_cents || 0) / 100).replace(".", ",") }))));
    fd.append("vat_rate", String(currentOrder.vat_rate || 0));
    try { await api("/api/admin/orders/" + currentOrderId, { method: "PUT", body: fd }); toast("Statut mis à jour."); openOrder(currentOrderId); loadOrders(); }
    catch (err) { toast(err.message); }
  });
  $("orderGenDevis").addEventListener("click", async () => {
    try { await api("/api/admin/orders/" + currentOrderId + "/devis", { method: "POST" }); toast("Devis généré."); openOrder(currentOrderId); loadInvoices(); }
    catch (err) { toast(err.message); }
  });
  $("orderGenFacture").addEventListener("click", async () => {
    try { await api("/api/admin/orders/" + currentOrderId + "/facture", { method: "POST" }); toast("Facture générée."); openOrder(currentOrderId); loadInvoices(); }
    catch (err) { toast(err.message); }
  });
  async function sendDocument(id) {
    if (!confirm("Envoyer ce document par e-mail au client ?")) return;
    try { await api("/api/admin/invoices/" + id + "/send", { method: "POST" }); toast("E-mail envoyé (journalisé en mode dev)."); }
    catch (err) { toast(err.message); }
  }

  // ---- Modale facture ---------------------------------------------------
  const invoiceModal = $("invoiceModal");
  function openInvoiceForm() {
    $("invoiceError").textContent = ""; $("invoiceForm").reset();
    fillClientSelect($("invoiceClient"));
    invoiceModal.hidden = false;
  }
  $("addInvoiceBtn").addEventListener("click", () => {
    if (!clients.length) { toast("Ajoutez d'abord un client."); return; }
    openInvoiceForm();
  });
  $("invoiceCancelBtn").addEventListener("click", () => (invoiceModal.hidden = true));
  invoiceModal.addEventListener("click", (e) => { if (e.target === invoiceModal) invoiceModal.hidden = true; });
  $("invoiceForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("invoiceError").textContent = "";
    if (!$("invoiceClient").value) { $("invoiceError").textContent = "Choisissez un client."; return; }
    const fd = new FormData();
    fd.append("client_id", $("invoiceClient").value);
    fd.append("number", $("invoiceNumber").value.trim()); fd.append("label", $("invoiceLabel").value.trim());
    fd.append("amount", $("invoiceAmount").value.trim()); fd.append("issued_date", $("invoiceDate").value);
    const file = $("invoiceFile").files[0]; if (file) fd.append("file", file);
    try {
      await api("/api/admin/invoices", { method: "POST", body: fd });
      invoiceModal.hidden = true; toast("Facture enregistrée."); loadInvoices();
    } catch (err) { $("invoiceError").textContent = err.message; }
  });
  async function removeInvoice(id) {
    const i = invoices.find((x) => x.id === id);
    if (!i || !confirm(`Supprimer la facture « ${i.number || "#" + i.id} » ?`)) return;
    try { await api("/api/admin/invoices/" + id, { method: "DELETE" }); toast("Facture supprimée."); loadInvoices(); } catch (err) { toast(err.message); }
  }

  // ---- Messagerie -------------------------------------------------------
  const msgModal = $("msgModal");

  async function loadThreads() {
    try { threads = await api("/api/admin/threads"); } catch (e) { return; }
    const totalUnread = threads.reduce((s, t) => s + t.unread, 0);
    $("countThreads").textContent = "(" + threads.length + ")";
    const badge = $("tabMsgBadge");
    if (totalUnread > 0) { badge.hidden = false; badge.textContent = totalUnread; } else badge.hidden = true;
    $("list-threads").innerHTML = threads.length
      ? threads.map(threadRow).join("")
      : `<p class="empty-note">Aucun client à contacter.</p>`;
  }
  function threadRow(t) {
    const unread = t.unread > 0 ? `<span class="tab-badge">${t.unread}</span>` : "";
    const preview = t.last_body ? (t.last_sender === "admin" ? "Vous : " : "") + t.last_body : "Pas encore de message";
    return `<div class="proj-row"><div class="proj-thumb">💬</div>` +
      `<div class="proj-info"><h3>${esc(t.client_name)} ${unread}</h3><p>${esc(preview)}</p></div>` +
      `<div class="proj-actions"><button class="btn-sm" data-tact="open" data-tid="${t.client_id}">Ouvrir</button></div></div>`;
  }
  function fmtTime(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  function renderThread(data) {
    $("msgThread").innerHTML = data.messages.length
      ? data.messages.map((m) => `<div class="msg-bubble msg-${m.sender}">${esc(m.body)}<span class="msg-time">${fmtTime(m.created_at)}</span></div>`).join("")
      : `<p class="msg-empty">Aucun message. Écrivez le premier.</p>`;
    $("msgThread").scrollTop = $("msgThread").scrollHeight;
  }
  async function openThread(cid) {
    currentThreadId = cid; $("msgError").textContent = ""; $("msgBody").value = "";
    try {
      const data = await api("/api/admin/messages/" + cid);
      $("msgModalTitle").textContent = "Conversation — " + data.client_name;
      renderThread(data); msgModal.hidden = false; loadThreads();
    } catch (err) { toast(err.message); }
  }
  $("msgCloseBtn").addEventListener("click", () => { msgModal.hidden = true; loadThreads(); });
  msgModal.addEventListener("click", (e) => { if (e.target === msgModal) { msgModal.hidden = true; loadThreads(); } });
  $("msgForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("msgError").textContent = "";
    const body = $("msgBody").value.trim();
    if (!body || !currentThreadId) return;
    const fd = new FormData(); fd.append("body", body);
    try {
      await api("/api/admin/messages/" + currentThreadId, { method: "POST", body: fd });
      $("msgBody").value = "";
      renderThread(await api("/api/admin/messages/" + currentThreadId));
    } catch (err) { $("msgError").textContent = err.message; }
  });

  // ---- Stock de filament -----------------------------------------------
  const spoolModal = $("spoolModal");
  async function loadFilament() {
    try { spools = await api("/api/admin/filament"); } catch (e) { return; }
    $("countStock").textContent = "(" + spools.length + ")";
    const lowCount = spools.filter((s) => s.low).length;
    const badge = $("tabStockBadge");
    if (lowCount > 0) { badge.hidden = false; badge.textContent = lowCount; } else badge.hidden = true;
    $("list-stock").innerHTML = spools.length ? spools.map(spoolRow).join("") : `<p class="empty-note">Aucune bobine en stock.</p>`;
  }
  function spoolRow(s) {
    const name = [s.material, s.color, s.brand].filter(Boolean).join(" · ") || "Bobine";
    const low = s.low ? " low" : "";
    const alert = s.low ? ` <span class="tab-badge">stock bas</span>` : "";
    return `<div class="proj-row"><div class="proj-thumb">🧵</div>` +
      `<div class="proj-info"><h3>${esc(name)}${alert}</h3>` +
      `<p>${s.weight_remaining_g} / ${s.weight_total_g} g · ${esc(s.cost)}</p>` +
      `<div class="stock-bar${low}"><span style="width:${s.percent}%"></span></div></div>` +
      `<div class="proj-actions"><button class="btn-sm" data-sact="edit" data-sid="${s.id}">Modifier</button>` +
      `<button class="btn-sm btn-danger" data-sact="delete" data-sid="${s.id}">Supprimer</button></div></div>`;
  }
  function openSpoolForm(s) {
    $("spoolError").textContent = ""; $("spoolForm").reset();
    if (s) {
      $("spoolModalTitle").textContent = "Modifier la bobine";
      $("spoolId").value = s.id; $("spoolMaterial").value = s.material || ""; $("spoolColor").value = s.color || "";
      $("spoolBrand").value = s.brand || ""; $("spoolTotal").value = s.weight_total_g; $("spoolRemaining").value = s.weight_remaining_g;
      $("spoolThreshold").value = s.low_threshold_g; $("spoolCost").value = s.cost_cents ? String(s.cost_cents / 100).replace(".", ",") : "";
      $("spoolSupplier").value = s.supplier || ""; $("spoolDate").value = s.purchase_date || ""; $("spoolNotes").value = s.notes || "";
    } else { $("spoolModalTitle").textContent = "Ajouter une bobine"; $("spoolId").value = ""; $("spoolTotal").value = 1000; $("spoolThreshold").value = 150; }
    spoolModal.hidden = false;
  }
  $("addSpoolBtn").addEventListener("click", () => openSpoolForm(null));
  $("spoolCancelBtn").addEventListener("click", () => (spoolModal.hidden = true));
  spoolModal.addEventListener("click", (e) => { if (e.target === spoolModal) spoolModal.hidden = true; });
  $("spoolForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("spoolError").textContent = "";
    const id = $("spoolId").value;
    const fd = new FormData();
    fd.append("material", $("spoolMaterial").value.trim()); fd.append("color", $("spoolColor").value.trim());
    fd.append("brand", $("spoolBrand").value.trim()); fd.append("weight_total_g", $("spoolTotal").value || "0");
    fd.append("weight_remaining_g", $("spoolRemaining").value || (id ? "0" : ""));
    fd.append("low_threshold_g", $("spoolThreshold").value || "0"); fd.append("cost", $("spoolCost").value.trim());
    fd.append("supplier", $("spoolSupplier").value.trim()); fd.append("purchase_date", $("spoolDate").value);
    fd.append("notes", $("spoolNotes").value.trim());
    try {
      await api(id ? "/api/admin/filament/" + id : "/api/admin/filament", { method: id ? "PUT" : "POST", body: fd });
      spoolModal.hidden = true; toast("Bobine enregistrée."); loadFilament(); loadAccounting();
    } catch (err) { $("spoolError").textContent = err.message; }
  });
  async function removeSpool(id) {
    const s = spools.find((x) => x.id === id);
    if (!s || !confirm("Supprimer cette bobine ?")) return;
    try { await api("/api/admin/filament/" + id, { method: "DELETE" }); toast("Bobine supprimée."); loadFilament(); loadAccounting(); } catch (err) { toast(err.message); }
  }

  // ---- Dépenses ---------------------------------------------------------
  const expenseModal = $("expenseModal");
  async function loadExpenses() {
    try { expenses = await api("/api/admin/expenses"); } catch (e) { return; }
    $("countExpenses").textContent = "(" + expenses.length + ")";
    $("list-expenses").innerHTML = expenses.length ? expenses.map(expenseRow).join("") : `<p class="empty-note">Aucune dépense enregistrée.</p>`;
  }
  function expenseRow(x) {
    const meta = [x.category_label, x.date].filter(Boolean).join(" · ");
    return `<div class="proj-row"><div class="proj-thumb">💶</div>` +
      `<div class="proj-info"><h3>${esc(x.label)} — ${esc(x.amount)}</h3><p>${esc(meta)}</p></div>` +
      `<div class="proj-actions"><button class="btn-sm" data-eact="edit" data-eid="${x.id}">Modifier</button>` +
      `<button class="btn-sm btn-danger" data-eact="delete" data-eid="${x.id}">Supprimer</button></div></div>`;
  }
  function openExpenseForm(x) {
    $("expenseError").textContent = ""; $("expenseForm").reset();
    if (x) {
      $("expenseModalTitle").textContent = "Modifier la dépense";
      $("expenseId").value = x.id; $("expenseLabel").value = x.label || ""; $("expenseCategory").value = x.category || "general";
      $("expenseAmount").value = x.amount_cents ? String(x.amount_cents / 100).replace(".", ",") : ""; $("expenseDate").value = x.date || ""; $("expenseNotes").value = x.notes || "";
    } else { $("expenseModalTitle").textContent = "Ajouter une dépense"; $("expenseId").value = ""; $("expenseCategory").value = "general"; }
    expenseModal.hidden = false;
  }
  $("addExpenseBtn").addEventListener("click", () => openExpenseForm(null));
  $("expenseCancelBtn").addEventListener("click", () => (expenseModal.hidden = true));
  expenseModal.addEventListener("click", (e) => { if (e.target === expenseModal) expenseModal.hidden = true; });
  $("expenseForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("expenseError").textContent = "";
    const id = $("expenseId").value;
    const fd = new FormData();
    fd.append("label", $("expenseLabel").value.trim()); fd.append("category", $("expenseCategory").value);
    fd.append("amount", $("expenseAmount").value.trim()); fd.append("date", $("expenseDate").value);
    fd.append("notes", $("expenseNotes").value.trim());
    try {
      await api(id ? "/api/admin/expenses/" + id : "/api/admin/expenses", { method: id ? "PUT" : "POST", body: fd });
      expenseModal.hidden = true; toast("Dépense enregistrée."); loadExpenses(); loadAccounting();
    } catch (err) { $("expenseError").textContent = err.message; }
  });
  async function removeExpense(id) {
    const x = expenses.find((y) => y.id === id);
    if (!x || !confirm(`Supprimer la dépense « ${x.label} » ?`)) return;
    try { await api("/api/admin/expenses/" + id, { method: "DELETE" }); toast("Dépense supprimée."); loadExpenses(); loadAccounting(); } catch (err) { toast(err.message); }
  }

  // ---- Contrôle de gestion ---------------------------------------------
  function currentPeriod() {
    const g = $("comptaGran").value;
    if (g === "year") return $("comptaYear").value || "";
    if (g === "month") return $("comptaMonth").value || "";
    if (g === "week") return $("comptaWeek").value || "";
    return "";
  }
  async function loadAccounting() {
    const period = currentPeriod();
    let data;
    try { data = await api("/api/admin/accounting" + (period ? "?period=" + encodeURIComponent(period) : "")); } catch (e) { return; }
    // remplir le sélecteur d'année (une fois)
    const sel = $("comptaYear");
    if (sel.dataset.filled !== "1") {
      const years = data.years.length ? data.years : [String(new Date().getFullYear())];
      sel.innerHTML = years.map((y) => `<option value="${y}">${y}</option>`).join("");
      sel.dataset.filled = "1";
    }
    renderAccounting(data);
  }
  function updateGranularity() {
    const g = $("comptaGran").value;
    $("comptaYear").hidden = g !== "year";
    $("comptaMonth").hidden = g !== "month";
    $("comptaWeek").hidden = g !== "week";
    loadAccounting();
  }
  function renderAccounting(d) {
    const netCls = d.net_cents >= 0 ? "pos" : "neg";
    const alert = d.low_stock.length
      ? `<div class="alert-box">⚠️ ${d.low_stock.length} bobine(s) en stock bas : ${d.low_stock.map((s) => esc([s.material, s.color].filter(Boolean).join(" ") || "bobine")).join(", ")}.</div>`
      : "";
    const rows = d.activities.map((a) =>
      `<tr><td>${esc(a.label)}</td><td>${esc(a.revenue)}</td><td>${esc(a.cost)}</td>` +
      `<td class="${a.margin_cents >= 0 ? "acct-pos" : "acct-neg"}">${esc(a.margin)}</td>` +
      `<td>${a.margin_pct == null ? "—" : a.margin_pct + " %"}</td></tr>`).join("");
    $("accountingBox").innerHTML =
      `<p class="hint" style="margin-bottom:0.8rem">Période analysée&nbsp;: <strong>${esc(d.period_label)}</strong></p>` +
      alert +
      `<div class="kpi-row">` +
      `<div class="kpi"><div class="kpi-label">Recettes</div><div class="kpi-value">${esc(d.total_revenue)}</div></div>` +
      `<div class="kpi"><div class="kpi-label">Coûts</div><div class="kpi-value">${esc(d.total_cost)}</div></div>` +
      `<div class="kpi ${netCls}"><div class="kpi-label">Résultat net ${d.net_pct == null ? "" : "(" + d.net_pct + " %)"}</div><div class="kpi-value">${esc(d.net)}</div></div>` +
      `</div>` +
      `<div class="acct-table-wrap"><table class="acct-table"><thead><tr>` +
      `<th>Activité</th><th>Recettes</th><th>Coûts</th><th>Marge</th><th>Taux</th></tr></thead>` +
      `<tbody>${rows}</tbody>` +
      `<tfoot><tr><td>Charges générales</td><td>—</td><td>${esc(d.general)}</td><td>—</td><td>—</td></tr>` +
      `<tr><td>Total</td><td>${esc(d.total_revenue)}</td><td>${esc(d.total_cost)}</td>` +
      `<td class="${d.net_cents >= 0 ? "acct-pos" : "acct-neg"}">${esc(d.net)}</td><td>${d.net_pct == null ? "—" : d.net_pct + " %"}</td></tr></tfoot>` +
      `</table></div>` +
      `<p class="hint" style="margin-top:0.8rem">Recettes = commandes acceptées (hors devis/annulées). Coût filament = achats de bobines, rattaché à l'impression 3D.</p>`;
  }
  $("comptaGran").addEventListener("change", updateGranularity);
  $("comptaYear").addEventListener("change", loadAccounting);
  $("comptaMonth").addEventListener("change", loadAccounting);
  $("comptaWeek").addEventListener("change", loadAccounting);

  async function downloadInvoice(id) {
    try {
      const res = await fetch("/api/admin/invoices/" + id + "/download", { headers: { Authorization: "Bearer " + token } });
      if (!res.ok) throw new Error("Téléchargement impossible.");
      const url = URL.createObjectURL(await res.blob());
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 15000);
    } catch (err) { toast(err.message); }
  }

  // ---- Paramètres société ----------------------------------------------
  async function loadSettings() {
    try { settings = await api("/api/admin/settings"); } catch (e) { return; }
    const s = settings, set = (id, v) => { const el = $(id); if (el) el.value = v == null ? "" : v; };
    set("setName", s.company_name); set("setLegal", s.legal_form); set("setAddress", s.address);
    set("setCP", s.postal_code); set("setCity", s.city); set("setSiret", s.siret);
    set("setApe", s.ape_code); set("setRcs", s.rcs); set("setCapital", s.capital);
    set("setEmail", s.email); set("setPhone", s.phone); set("setIban", s.iban); set("setBic", s.bic);
    $("setVatApplicable").checked = !!s.vat_applicable;
    set("setVatRate", s.default_vat_rate); set("setPayTerms", s.payment_terms);
    set("setPenalty", s.late_penalty); set("setPrefix", s.invoice_prefix); set("setNextNum", s.next_invoice_number);
  }
  $("settingsForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("settingsError").textContent = "";
    const fd = new FormData(), g = (id) => $(id).value.trim();
    fd.append("company_name", g("setName")); fd.append("legal_form", g("setLegal")); fd.append("address", g("setAddress"));
    fd.append("postal_code", g("setCP")); fd.append("city", g("setCity")); fd.append("siret", g("setSiret"));
    fd.append("ape_code", g("setApe")); fd.append("rcs", g("setRcs")); fd.append("capital", g("setCapital"));
    fd.append("email", g("setEmail")); fd.append("phone", g("setPhone")); fd.append("iban", g("setIban")); fd.append("bic", g("setBic"));
    fd.append("vat_applicable", $("setVatApplicable").checked ? "1" : "0");
    fd.append("default_vat_rate", g("setVatRate")); fd.append("payment_terms", g("setPayTerms"));
    fd.append("late_penalty", $("setPenalty").value.trim()); fd.append("invoice_prefix", g("setPrefix"));
    fd.append("next_invoice_number", $("setNextNum").value || "1");
    try { settings = await api("/api/admin/settings", { method: "PUT", body: fd }); toast("Paramètres enregistrés."); }
    catch (err) { $("settingsError").textContent = err.message; }
  });

  // ---- Génération de facture -------------------------------------------
  const invoiceGenModal = $("invoiceGenModal");
  function genLineRow() {
    const div = document.createElement("div");
    div.className = "gen-line";
    div.style.cssText = "display:flex;gap:0.4rem;margin-bottom:0.4rem;align-items:center";
    div.innerHTML =
      `<input type="text" class="gl-desig" placeholder="Désignation" style="flex:1">` +
      `<input type="text" class="gl-qty" placeholder="Qté" value="1" style="width:3.5rem;text-align:center">` +
      `<input type="text" class="gl-pu" placeholder="PU HT €" style="width:6.5rem">` +
      `<button type="button" class="btn-sm gl-remove" title="Retirer">✕</button>`;
    return div;
  }
  function genRecalc() {
    let total = 0;
    document.querySelectorAll("#genLines .gen-line").forEach((row) => {
      const qty = parseFloat((row.querySelector(".gl-qty").value || "1").replace(",", ".")) || 0;
      const pu = parseFloat((row.querySelector(".gl-pu").value || "0").replace(/[^\d.,-]/g, "").replace(",", ".")) || 0;
      total += qty * pu;
    });
    $("genTotalPreview").textContent = "Total HT estimé : " + total.toFixed(2).replace(".", ",") + " €";
  }
  function openGenInvoice() {
    $("invoiceGenError").textContent = ""; $("invoiceGenForm").reset();
    fillClientSelect($("genClient"));
    $("genLines").innerHTML = ""; $("genLines").appendChild(genLineRow());
    const vatOn = settings && settings.vat_applicable;
    $("genVatField").hidden = !vatOn;
    if (vatOn) $("genVat").value = settings.default_vat_rate;
    $("genIssued").value = new Date().toISOString().slice(0, 10);
    genRecalc();
    invoiceGenModal.hidden = false;
  }
  $("genInvoiceBtn").addEventListener("click", () => {
    if (!clients.length) { toast("Ajoutez d'abord un client."); return; }
    openGenInvoice();
  });
  $("genAddLine").addEventListener("click", () => $("genLines").appendChild(genLineRow()));
  $("genLines").addEventListener("click", (e) => { if (e.target.classList.contains("gl-remove")) { e.target.closest(".gen-line").remove(); genRecalc(); } });
  $("genLines").addEventListener("input", genRecalc);
  $("genCancelBtn").addEventListener("click", () => (invoiceGenModal.hidden = true));
  invoiceGenModal.addEventListener("click", (e) => { if (e.target === invoiceGenModal) invoiceGenModal.hidden = true; });
  $("invoiceGenForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("invoiceGenError").textContent = "";
    const lines = [];
    document.querySelectorAll("#genLines .gen-line").forEach((row) => {
      const desig = row.querySelector(".gl-desig").value.trim();
      if (desig) lines.push({ designation: desig, qty: row.querySelector(".gl-qty").value.trim() || "1", unit_price: row.querySelector(".gl-pu").value.trim() });
    });
    if (!$("genClient").value) { $("invoiceGenError").textContent = "Choisissez un client."; return; }
    if (!lines.length) { $("invoiceGenError").textContent = "Ajoutez au moins une ligne."; return; }
    const fd = new FormData();
    fd.append("client_id", $("genClient").value);
    fd.append("issued_date", $("genIssued").value); fd.append("due_date", $("genDue").value);
    fd.append("vat_rate", $("genVat").value.trim()); fd.append("label", $("genLabel").value.trim());
    fd.append("lines", JSON.stringify(lines));
    try {
      await api("/api/admin/invoices/generate", { method: "POST", body: fd });
      invoiceGenModal.hidden = true; toast("Facture générée."); loadInvoices();
    } catch (err) { $("invoiceGenError").textContent = err.message; }
  });

  // ---- Projets de développement (Gantt) --------------------------------
  const devProjectModal = $("devProjectModal");
  const devTaskModal = $("devTaskModal");
  const MONTHS_ABBR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

  function badgeClass(status) {
    return { en_cours: "", en_pause: "st-devis", termine: "st-terminee", annule: "st-annulee", a_faire: "st-devis" }[status] || "";
  }
  function parseD(s) {
    if (!s) return null;
    const p = String(s).split("-");
    if (p.length !== 3) return null;
    const d = new Date(+p[0], +p[1] - 1, +p[2]);
    return isNaN(d.getTime()) ? null : d;
  }
  function daysBetween(a, b) { return Math.round((b - a) / 86400000); }
  function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }

  function renderGantt(container, tasks) {
    const dated = tasks.filter((t) => parseD(t.start_date) && parseD(t.end_date));
    if (!dated.length) {
      container.innerHTML = `<div class="gantt-wrap"><div class="gantt-empty">Ajoutez des tâches avec une date de début et de fin pour afficher le diagramme de Gantt.</div></div>`;
      return;
    }
    let min = null, max = null;
    dated.forEach((t) => { const s = parseD(t.start_date), e = parseD(t.end_date); if (!min || s < min) min = s; if (!max || e > max) max = e; });
    min = addDays(min, -1); max = addDays(max, 1);
    const totalDays = daysBetween(min, max) + 1;
    const dayW = totalDays <= 45 ? 26 : totalDays <= 90 ? 15 : 9;
    const TL = totalDays * dayW;

    let headCells = "", gridCells = "";
    for (let i = 0; i < totalDays; i++) {
      const d = addDays(min, i), wd = d.getDay();
      const weekend = wd === 0 || wd === 6 ? " weekend" : "";
      const monthStart = d.getDate() === 1 ? " month-start" : "";
      let label = "";
      if (dayW >= 15) label = String(d.getDate());
      else if (wd === 1) label = d.getDate() + "/" + (d.getMonth() + 1);
      headCells += `<div class="gantt-day${weekend}${monthStart}" style="width:${dayW}px">${label}</div>`;
      gridCells += `<div class="gantt-cell${weekend}${monthStart}" style="width:${dayW}px"></div>`;
    }
    const today = new Date(); today.setHours(0, 0, 0, 0);
    let todayHtml = "";
    if (today >= min && today <= max) todayHtml = `<div class="gantt-today" style="left:${daysBetween(min, today) * dayW}px"></div>`;

    let rows = "";
    tasks.forEach((t) => {
      const s = parseD(t.start_date), e = parseD(t.end_date);
      let bar = "";
      if (s && e) {
        const x = daysBetween(min, s) * dayW;
        const w = Math.max(dayW, (daysBetween(s, e) + 1) * dayW);
        const done = t.status === "termine" ? " done" : "";
        bar = `<div class="gantt-bar${done}" style="left:${x}px;width:${w}px" title="${esc(t.name)} — ${t.progress}%"><div class="gantt-bar-fill" style="width:${t.progress}%"></div></div>`;
      }
      rows += `<div class="gantt-row"><div class="gantt-name" title="${esc(t.name)}"><span style="overflow:hidden;text-overflow:ellipsis">${esc(t.name)}</span><span style="color:var(--texte-doux);font-size:0.72rem">${t.progress}%</span></div>` +
        `<div class="gantt-track" style="width:${TL}px"><div class="gantt-grid">${gridCells}</div>${bar}${todayHtml}</div></div>`;
    });
    const caption = `${MONTHS_ABBR[min.getMonth()]} ${min.getFullYear()} → ${MONTHS_ABBR[max.getMonth()]} ${max.getFullYear()}  ·  ligne rouge = aujourd'hui`;
    container.innerHTML = `<p class="gantt-caption">${caption}</p><div class="gantt-wrap"><div class="gantt">` +
      `<div class="gantt-row gantt-header"><div class="gantt-name">Tâche</div><div class="gantt-track" style="width:${TL}px"><div class="gantt-days">${headCells}</div></div></div>` +
      rows + `</div></div>`;
  }

  function showDevList() { $("devDetailView").hidden = true; $("devListView").hidden = false; currentProjectId = null; }

  async function loadDevProjects() {
    try { devProjects = await api("/api/admin/dev-projects"); } catch (e) { return; }
    $("countDevProjects").textContent = "(" + devProjects.length + ")";
    $("list-devprojects").innerHTML = devProjects.length
      ? devProjects.map(devProjectRow).join("")
      : `<p class="empty-note">Aucun projet. Créez votre premier projet de développement.</p>`;
  }
  function devProjectRow(p) {
    const cl = p.client_name ? " · " + p.client_name : "";
    const prog = p.progress == null ? 0 : p.progress;
    const dates = [p.start_date, p.end_date].filter(Boolean).join(" → ");
    return `<div class="proj-row"><div class="proj-thumb">📊</div>` +
      `<div class="proj-info"><h3>${esc(p.name)} <span class="status-badge ${badgeClass(p.status)}">${esc(p.status_label)}</span></h3>` +
      `<p>${p.task_count || 0} tâche(s)${esc(cl)}${dates ? " · " + esc(dates) : ""}</p>` +
      `<div class="mini-bar"><span style="width:${prog}%"></span></div></div>` +
      `<div class="proj-actions"><button class="btn-sm" data-dpact="open" data-dpid="${p.id}">Ouvrir</button>` +
      `<button class="btn-sm btn-danger" data-dpact="delete" data-dpid="${p.id}">Supprimer</button></div></div>`;
  }

  async function openDevProject(id) {
    let data;
    try { data = await api("/api/admin/dev-projects/" + id); } catch (e) { toast(e.message); return; }
    currentProjectId = id; currentTasks = data.tasks || [];
    $("devListView").hidden = true; $("devDetailView").hidden = false;
    $("devDetailName").textContent = data.name;
    const meta = [data.status_label, data.client_name ? "Client : " + data.client_name : "",
      data.start_date && data.end_date ? data.start_date + " → " + data.end_date : "",
      data.progress != null ? "Avancement global : " + data.progress + " %" : "",
      data.description].filter(Boolean).join("  ·  ");
    $("devDetailMeta").textContent = meta;
    renderGantt($("ganttContainer"), currentTasks);
    renderTasks(currentTasks);
  }
  function renderTasks(tasks) {
    $("list-devtasks").innerHTML = tasks.length
      ? tasks.map(taskRow).join("")
      : `<p class="empty-note">Aucune tâche. Ajoutez des tâches (avec dates) pour construire le Gantt.</p>`;
  }
  function taskRow(t) {
    const dates = [t.start_date, t.end_date].filter(Boolean).join(" → ") || "sans dates";
    return `<div class="proj-row"><div class="proj-thumb">📌</div>` +
      `<div class="proj-info"><h3>${esc(t.name)} <span class="status-badge ${badgeClass(t.status)}">${esc(t.status_label)}</span></h3>` +
      `<p>${esc(dates)} · ${t.progress}%</p></div>` +
      `<div class="proj-actions"><button class="btn-sm" data-dtact="edit" data-dtid="${t.id}">Modifier</button>` +
      `<button class="btn-sm btn-danger" data-dtact="delete" data-dtid="${t.id}">Supprimer</button></div></div>`;
  }

  // Modale projet
  function openDevProjectForm(p) {
    $("devProjectError").textContent = ""; $("devProjectForm").reset();
    fillClientSelect($("dpClient"), p && p.client_id ? p.client_id : undefined);
    if (p) {
      $("devProjectTitle").textContent = "Modifier le projet";
      $("devProjectId").value = p.id; $("dpName").value = p.name || "";
      $("dpClient").value = p.client_id || ""; $("dpStatus").value = p.status || "en_cours";
      $("dpStart").value = p.start_date || ""; $("dpEnd").value = p.end_date || ""; $("dpDesc").value = p.description || "";
    } else { $("devProjectTitle").textContent = "Nouveau projet"; $("devProjectId").value = ""; $("dpStatus").value = "en_cours"; }
    devProjectModal.hidden = false;
  }
  $("addDevProjectBtn").addEventListener("click", () => openDevProjectForm(null));
  $("editDevProjectBtn").addEventListener("click", () => openDevProjectForm(devProjects.find((x) => x.id === currentProjectId)));
  $("devBackBtn").addEventListener("click", () => { showDevList(); loadDevProjects(); });
  $("dpCancelBtn").addEventListener("click", () => (devProjectModal.hidden = true));
  devProjectModal.addEventListener("click", (e) => { if (e.target === devProjectModal) devProjectModal.hidden = true; });
  $("devProjectForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("devProjectError").textContent = "";
    const id = $("devProjectId").value;
    const fd = new FormData();
    fd.append("name", $("dpName").value.trim()); fd.append("client_id", $("dpClient").value || "");
    fd.append("status", $("dpStatus").value); fd.append("start_date", $("dpStart").value);
    fd.append("end_date", $("dpEnd").value); fd.append("description", $("dpDesc").value.trim());
    try {
      await api(id ? "/api/admin/dev-projects/" + id : "/api/admin/dev-projects", { method: id ? "PUT" : "POST", body: fd });
      devProjectModal.hidden = true; toast(id ? "Projet modifié." : "Projet créé.");
      await loadDevProjects();
      if (id && currentProjectId) await openDevProject(currentProjectId);
    } catch (err) { $("devProjectError").textContent = err.message; }
  });

  // Modale tâche
  function openDevTaskForm(t) {
    $("devTaskError").textContent = ""; $("devTaskForm").reset();
    if (t) {
      $("devTaskTitle").textContent = "Modifier la tâche";
      $("dtId").value = t.id; $("dtName").value = t.name || "";
      $("dtStart").value = t.start_date || ""; $("dtEnd").value = t.end_date || "";
      $("dtStatus").value = t.status || "a_faire"; $("dtProgress").value = t.progress || 0;
    } else { $("devTaskTitle").textContent = "Ajouter une tâche"; $("dtId").value = ""; $("dtStatus").value = "a_faire"; $("dtProgress").value = 0; }
    devTaskModal.hidden = false;
  }
  $("addDevTaskBtn").addEventListener("click", () => { if (currentProjectId) openDevTaskForm(null); });
  $("dtCancelBtn").addEventListener("click", () => (devTaskModal.hidden = true));
  devTaskModal.addEventListener("click", (e) => { if (e.target === devTaskModal) devTaskModal.hidden = true; });
  $("dtStatus").addEventListener("change", () => { if ($("dtStatus").value === "termine") $("dtProgress").value = 100; });
  $("devTaskForm").addEventListener("submit", async (e) => {
    e.preventDefault(); $("devTaskError").textContent = "";
    const id = $("dtId").value;
    const fd = new FormData();
    fd.append("name", $("dtName").value.trim()); fd.append("start_date", $("dtStart").value);
    fd.append("end_date", $("dtEnd").value); fd.append("status", $("dtStatus").value);
    fd.append("progress", $("dtProgress").value || "0");
    try {
      await api(id ? "/api/admin/dev-tasks/" + id : "/api/admin/dev-projects/" + currentProjectId + "/tasks", { method: id ? "PUT" : "POST", body: fd });
      devTaskModal.hidden = true; toast(id ? "Tâche modifiée." : "Tâche ajoutée.");
      await openDevProject(currentProjectId); loadDevProjects();
    } catch (err) { $("devTaskError").textContent = err.message; }
  });

  async function removeDevProject(id) {
    const p = devProjects.find((x) => x.id === id);
    if (!p || !confirm(`Supprimer le projet « ${p.name} » et toutes ses tâches ?`)) return;
    try { await api("/api/admin/dev-projects/" + id, { method: "DELETE" }); toast("Projet supprimé."); showDevList(); loadDevProjects(); }
    catch (err) { toast(err.message); }
  }
  async function removeDevTask(id) {
    const t = currentTasks.find((x) => x.id === id);
    if (!t || !confirm(`Supprimer la tâche « ${t.name} » ?`)) return;
    try { await api("/api/admin/dev-tasks/" + id, { method: "DELETE" }); toast("Tâche supprimée."); await openDevProject(currentProjectId); loadDevProjects(); }
    catch (err) { toast(err.message); }
  }

  // ---- Calculateur de coût de production 3D ----------------------------
  const calcNum = (id) => parseFloat(($(id).value || "0").toString().replace(/[^\d.,-]/g, "").replace(",", ".")) || 0;
  const calcEur = (v) => (v || 0).toFixed(2).replace(".", ",") + " €";
  const calcFmt = (v) => (v == null ? "" : String(v).replace(".", ","));

  function fillCalcSpools() {
    const sel = $("calcSpool");
    if (!sel) return;
    const current = sel.value;
    let opts = `<option value="">— Saisie manuelle —</option>`;
    spools.forEach((s) => {
      const kg = s.weight_total_g ? (s.cost_cents / 100) / (s.weight_total_g / 1000) : 0;
      const label = [s.material, s.color].filter(Boolean).join(" ") || "Bobine";
      opts += `<option value="${s.id}" data-kg="${kg.toFixed(2)}">${esc(label)} — ${calcEur(kg)}/kg</option>`;
    });
    sel.innerHTML = opts;
    if (current) sel.value = current;
  }

  function calcCompute() {
    const kgPrice = calcNum("calcFilamentKg");
    const weight = calcNum("calcWeight");
    const printH = calcNum("calcPrintTime");
    const power = calcNum("calcPower");
    const elec = calcNum("calcElec");
    const machineH = calcNum("calcMachine");
    const laborH = calcNum("calcLaborTime");
    const laborRate = calcNum("calcLaborRate");
    const failPct = calcNum("calcFailure");
    const marginPct = calcNum("calcMargin");

    const material = (weight / 1000) * kgPrice;
    const energy = printH * (power / 1000) * elec;
    const machine = printH * machineH;
    const prod = material + energy + machine;
    const failure = prod * failPct / 100;
    const labor = laborH * laborRate;
    const cost = prod + failure + labor;
    const priceHT = cost * (1 + marginPct / 100);
    const marginEur = priceHT - cost;
    calcPriceHT = priceHT;

    const vatOn = settings && settings.vat_applicable;
    const vatRate = vatOn ? (settings.default_vat_rate || 20) : 0;
    const vat = priceHT * vatRate / 100;
    const priceTTC = priceHT + vat;

    $("calcResult").innerHTML =
      `<h3>Estimation</h3>` +
      `<table class="calc-table">` +
      `<tr><td>Matière${weight ? " (" + calcFmt(weight) + " g)" : ""}</td><td>${calcEur(material)}</td></tr>` +
      `<tr><td>Électricité</td><td>${calcEur(energy)}</td></tr>` +
      `<tr><td>Usure machine</td><td>${calcEur(machine)}</td></tr>` +
      `<tr><td>Provision échec (${calcFmt(failPct)} %)</td><td>${calcEur(failure)}</td></tr>` +
      `<tr><td>Main d'œuvre</td><td>${calcEur(labor)}</td></tr>` +
      `<tr class="calc-total"><td>Coût de revient</td><td>${calcEur(cost)}</td></tr>` +
      `<tr><td>Marge (${calcFmt(marginPct)} %)</td><td>${calcEur(marginEur)}</td></tr>` +
      `</table>` +
      `<div class="calc-price">` +
      `<div class="calc-ht"><span>Prix de vente HT</span><strong>${calcEur(priceHT)}</strong></div>` +
      (vatOn
        ? `<div><span>TVA (${calcFmt(vatRate)} %)</span><strong>${calcEur(vat)}</strong></div>` +
          `<div class="calc-ttc"><span>Prix TTC</span><strong>${calcEur(priceTTC)}</strong></div>`
        : ``) +
      `</div>` +
      `<button type="button" id="calcToOrder" class="btn btn-primary" style="width:100%;margin-top:1rem">Créer une commande avec ce prix</button>`;
  }

  function initCalc() {
    fillCalcSpools();
    if (!calcInited && settings) {
      $("calcPower").value = settings.calc_printer_power_w ?? 250;
      $("calcElec").value = calcFmt(settings.calc_elec_price ?? 0.25);
      $("calcMachine").value = calcFmt(settings.calc_machine_cost ?? 0.8);
      $("calcLaborRate").value = calcFmt(settings.calc_labor_cost ?? 35);
      $("calcFailure").value = calcFmt(settings.calc_failure_pct ?? 5);
      $("calcMargin").value = calcFmt(settings.calc_margin_pct ?? 50);
      calcInited = true;
    }
    calcCompute();
  }

  $("calcForm").addEventListener("input", calcCompute);
  $("calcSpool").addEventListener("change", () => {
    const opt = $("calcSpool").selectedOptions[0];
    const kg = opt && opt.getAttribute("data-kg");
    if (kg) $("calcFilamentKg").value = calcFmt(kg);
    calcCompute();
  });
  $("calcSaveDefaults").addEventListener("click", async () => {
    const fd = new FormData();
    fd.append("printer_power_w", String(Math.round(calcNum("calcPower"))));
    fd.append("elec_price", $("calcElec").value.trim());
    fd.append("machine_cost", $("calcMachine").value.trim());
    fd.append("labor_cost", $("calcLaborRate").value.trim());
    fd.append("failure_pct", $("calcFailure").value.trim());
    fd.append("margin_pct", $("calcMargin").value.trim());
    try { settings = await api("/api/admin/settings/calc", { method: "PUT", body: fd }); toast("Réglages enregistrés."); }
    catch (err) { toast(err.message); }
  });
  // Bouton « Créer une commande » (recréé à chaque calcul → délégation)
  $("calcResult").addEventListener("click", (e) => {
    if (!e.target.closest("#calcToOrder")) return;
    if (!clients.length) { toast("Ajoutez d'abord un client (onglet Clients)."); return; }
    document.querySelector('.tab[data-tab="orders"]').click();
    openOrderForm(null);
    $("orderCategory").value = "impression3d";
    $("orderTitle").value = "Impression 3D";
    const firstLine = document.querySelector("#orderLines .gen-line");
    if (firstLine) {
      firstLine.querySelector(".gl-desig").value = "Impression 3D";
      firstLine.querySelector(".gl-qty").value = "1";
      firstLine.querySelector(".gl-pu").value = calcPriceHT.toFixed(2).replace(".", ",");
      orderRecalc();
    }
  });

  // ---- Démarrage --------------------------------------------------------
  async function boot() {
    if (!token) { showLogin(); return; }
    try { const me = await api("/api/auth/me"); me.role === "admin" ? showApp() : logout(); }
    catch (err) { showLogin(); }
  }
  boot();
})();
