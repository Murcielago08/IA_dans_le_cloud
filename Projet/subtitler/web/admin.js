// Page d'administration : statistiques d'usage et derniers traitements.

const REFRESH_MS = 5000;
const PAGE_SIZES = [5, 10, 50, 100];
const PAGE_SIZE_KEY = "subtitler.adminPageSize";

const pageSizeSelect = document.getElementById("page-size");
let page = 1;
let pageSize = 5;
let total = 0;
let refreshTimer = null;

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function renderStats(stats) {
  document.getElementById("s-inferences").textContent = stats.inferences.total;
  document.getElementById("s-avg-time").textContent = formatSeconds(stats.avg_processing_time);
  document.getElementById("s-ratio").textContent =
    stats.avg_realtime_ratio == null ? "—" : `${Math.round(stats.avg_realtime_ratio * 100)} %`;
  document.getElementById("s-unfinished").textContent = stats.unfinished.total;
  document.getElementById("s-failed").textContent = stats.failed.total;
  document.getElementById("s-cancelled").textContent = stats.cancelled.total;
  document.getElementById("s-total").textContent = stats.total_jobs;

  const rows = Object.entries(OUTPUT_LABELS).map(([kind, label]) => {
    const tr = document.createElement("tr");
    tr.append(
      cell(label),
      cell(stats.inferences.by_kind[kind], "num"),
      cell(stats.unfinished.by_kind[kind], "num"),
      cell(stats.failed.by_kind[kind], "num"),
      cell(stats.cancelled.by_kind[kind], "num"),
    );
    return tr;
  });
  document.getElementById("by-kind").replaceChildren(...rows);
}

function renderJobs(jobs) {
  const rows = jobs.map((job) => {
    const tr = document.createElement("tr");
    const badge = document.createElement("span");
    badge.className = `badge ${job.status}`;
    badge.textContent = STATUS_LABELS[job.status];
    const status = document.createElement("td");
    status.append(badge);
    if (job.hidden_at) {
      const hidden = document.createElement("small");
      hidden.className = "hidden-note";
      hidden.textContent = "retiré par l'utilisateur";
      status.append(hidden);
    }

    const response = cell("", "text");
    const content = job.status === "failed" ? job.error : job.text;
    if (content) {
      // <details> : le texte complet s'affiche au clic.
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = content;
      details.append(summary);
      response.append(details);
    } else {
      response.textContent = "—";
    }

    tr.append(
      cell(formatDate(job.created_at)),
      cell(job.username ?? "—"),
      cell(job.filename),
      cell(OUTPUT_LABELS[job.output_kind]),
      status,
      cell(formatSeconds(job.media_duration), "num"),
      cell(formatSeconds(job.processing_time), "num"),
      cell(job.consent ? `Oui (${formatDate(job.consent_at)})` : "Non"),
      response,
    );
    return tr;
  });
  if (rows.length === 0) {
    const tr = document.createElement("tr");
    const td = cell("Aucun traitement pour l'instant.");
    td.colSpan = 9;
    tr.append(td);
    rows.push(tr);
  }
  document.getElementById("recent").replaceChildren(...rows);
}

// --- Pagination ---

function pageCount() {
  return Math.max(1, Math.ceil(total / pageSize));
}

function renderPager() {
  document.getElementById("pager").hidden = total <= pageSize;
  document.getElementById("page-info").textContent =
    `Page ${page} / ${pageCount()} · ${total} traitement${total > 1 ? "s" : ""}`;
  document.getElementById("prev-page").disabled = page <= 1;
  document.getElementById("next-page").disabled = page >= pageCount();
}

function goToPage(number) {
  page = number;
  refresh();
}

// Taille de page mémorisée dans le navigateur (simple préférence d'affichage).
function setupPageSize() {
  try {
    const saved = Number(localStorage.getItem(PAGE_SIZE_KEY));
    if (PAGE_SIZES.includes(saved)) pageSize = saved;
  } catch { /* stockage indisponible : taille par défaut */ }
  pageSizeSelect.value = String(pageSize);
  pageSizeSelect.addEventListener("change", () => {
    pageSize = Number(pageSizeSelect.value);
    try {
      localStorage.setItem(PAGE_SIZE_KEY, String(pageSize));
    } catch { /* préférence non conservée */ }
    goToPage(1);
  });
  document.getElementById("prev-page").addEventListener("click", () => goToPage(page - 1));
  document.getElementById("next-page").addEventListener("click", () => goToPage(page + 1));
}

async function refresh() {
  clearTimeout(refreshTimer); // un changement de page relance l'actualisation tout de suite
  const message = document.getElementById("message");
  try {
    const [stats, jobs] = await Promise.all([
      api("/api/stats"),
      apiPage(`/api/jobs?all=true&limit=${pageSize}&offset=${(page - 1) * pageSize}`),
    ]);
    total = jobs.total;
    if (jobs.items.length === 0 && page > 1) {
      // La page n'existe plus (moins de traitements qu'avant) : dernière page.
      page = pageCount();
      refresh();
      return;
    }
    renderStats(stats);
    renderJobs(jobs.items);
    renderPager();
    message.hidden = true;
    document.getElementById("updated").textContent =
      `dernière mise à jour ${new Date().toLocaleTimeString("fr-FR")}`;
  } catch (error) {
    message.textContent = `Le serveur ne répond pas : ${error.message}`;
    message.hidden = false;
  }
  // Une seule actualisation programmée, même si deux refresh() se sont croisés.
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refresh, REFRESH_MS);
}

requireUser()
  .then((user) => {
    if (user.is_admin) {
      setupPageSize();
      refresh();
    } else {
      const message = document.getElementById("message");
      message.textContent = "Cette page est réservée à l'administrateur.";
      message.hidden = false;
    }
  })
  .catch(() => {});
