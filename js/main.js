// ============================================================
// MSolutions3D — Script principal
// ============================================================

// -------- Statistiques de visites (Umami — sans cookie, RGPD) --------
// Pour ACTIVER : renseignez les deux valeurs ci-dessous (fournies par Umami,
// Cloud ou auto-hébergé). Laissées vides = aucun suivi (aucun impact).
// Pensez aussi à définir MSOLUTION_ANALYTICS_ORIGIN côté serveur (CSP).
const UMAMI_SRC = ""; // ex. "https://cloud.umami.is/script.js" ou "https://stats.msolutions3d.fr/script.js"
const UMAMI_WEBSITE_ID = ""; // ex. "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
if (UMAMI_SRC && UMAMI_WEBSITE_ID) {
  const s = document.createElement("script");
  s.defer = true;
  s.src = UMAMI_SRC;
  s.setAttribute("data-website-id", UMAMI_WEBSITE_ID);
  document.head.appendChild(s);
}

// Année courante dans le pied de page
document.getElementById("year").textContent = new Date().getFullYear();

// Menu mobile (burger)
const navToggle = document.getElementById("navToggle");
const mainNav = document.getElementById("mainNav");

navToggle.addEventListener("click", () => {
  const ouvert = mainNav.classList.toggle("open");
  navToggle.setAttribute("aria-expanded", ouvert ? "true" : "false");
});

// Fermer le menu mobile après un clic sur un lien
mainNav.querySelectorAll("a").forEach((lien) => {
  lien.addEventListener("click", () => {
    mainNav.classList.remove("open");
    navToggle.setAttribute("aria-expanded", "false");
  });
});

// Animations d'apparition au défilement
const observateur = new IntersectionObserver(
  (entrees) => {
    entrees.forEach((entree) => {
      if (entree.isIntersecting) {
        entree.target.classList.add("visible");
        observateur.unobserve(entree.target);
      }
    });
  },
  { threshold: 0.12 }
);

document.querySelectorAll(".reveal").forEach((el) => observateur.observe(el));
