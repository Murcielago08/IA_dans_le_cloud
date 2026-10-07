// Page d'administration : statistiques d'usage et derniers traitements.

const REFRESH_MS = 5000;

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
  document.getElementById("s-total").textContent = stats.total_jobs;

  const rows = Object.entries(OUTPUT_LABELS).map(([kind, label]) => {
    const tr = document.createElement("tr");
    tr.append(
      cell(label),
      cell(stats.inferences.by_kind[kind], "num"),
      cell(stats.unfinished.by_kind[kind], "num"),
      cell(stats.failed.by_kind[kind], "num"),
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
      cell(job.filename),
      cell(OUTPUT_LABELS[job.output_kind]),
      status,
      cell(formatSeconds(job.media_duration), "num"),
      cell(formatSeconds(job.processing_time), "num"),
      response,
    );
    return tr;
  });
  if (rows.length === 0) {
    const tr = document.createElement("tr");
    const td = cell("Aucun traitement pour l'instant.");
    td.colSpan = 7;
    tr.append(td);
    rows.push(tr);
  }
  document.getElementById("recent").replaceChildren(...rows);
}

async function refresh() {
  const message = document.getElementById("message");
  try {
    const [stats, jobs] = await Promise.all([api("/api/stats"), api("/api/jobs?limit=50")]);
    renderStats(stats);
    renderJobs(jobs);
    message.hidden = true;
    document.getElementById("updated").textContent =
      `dernière mise à jour ${new Date().toLocaleTimeString("fr-FR")}`;
  } catch (error) {
    message.textContent = `Le serveur ne répond pas : ${error.message}`;
    message.hidden = false;
  }
  setTimeout(refresh, REFRESH_MS);
}

refresh();
