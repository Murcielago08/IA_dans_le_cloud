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
};

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* corps non JSON */ }
    throw new Error(detail);
  }
  return response.json();
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
