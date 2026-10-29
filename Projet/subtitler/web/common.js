// Fonctions partagées par les pages utilisateur et administration.

const OUTPUT_LABELS = {
  video_embedded: "Vidéo sous-titrée",
  video_track: "Vidéo + piste",
  subtitles: "Sous-titres",
  text: "Texte",
};

const STATUS_LABELS = {
  pending: "En attente",
  running: "En cours",
  done: "Terminé",
  failed: "Échec",
  cancelled: "Annulé",
};

function redirectToLogin() {
  const next = encodeURIComponent(location.pathname + location.search);
  location.replace(`login.html?next=${next}`);
}

async function api(path, options) {
  const response = await fetch(path, options);
  if (response.status === 401 && !path.startsWith("/api/auth/")) redirectToLogin();
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* corps non JSON */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

// Comme api(), pour une liste paginée : renvoie aussi le nombre total
// d'éléments (en-tête X-Total-Count).
async function apiPage(path) {
  const response = await fetch(path);
  if (response.status === 401) redirectToLogin();
  if (!response.ok) throw new Error(response.statusText);
  return { items: await response.json(), total: Number(response.headers.get("X-Total-Count")) };
}

// Vérifie la connexion et affiche l'utilisateur dans l'en-tête ; renvoie
// l'utilisateur, ou redirige vers la page de connexion.
async function requireUser() {
  let user;
  try {
    user = await api("/api/auth/me");
  } catch (error) {
    if (error.message === "Connexion requise") redirectToLogin();
    throw error;
  }
  document.getElementById("account-name").textContent = user.username;
  document.getElementById("account").hidden = false;
  document.getElementById("admin-link").hidden = !user.is_admin;
  document.getElementById("logout").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" });
    location.replace("login.html");
  });
  return user;
}

function formatSeconds(seconds) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min ${String(Math.round(seconds % 60)).padStart(2, "0")} s`;
}

function formatDate(iso) {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}
