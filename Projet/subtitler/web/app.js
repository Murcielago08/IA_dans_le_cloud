// Page utilisateur : envoi d'un fichier et suivi des traitements.

const POLL_MS = 2000;
const PAGE_SIZES = [5, 10, 50, 100];
const PAGE_SIZE_KEY = "subtitler.pageSize";

const form = document.getElementById("upload-form");
const fileInput = document.getElementById("file");
const drop = document.getElementById("drop");
const dropTitle = document.getElementById("drop-title");
const dropHint = document.getElementById("drop-hint");
const modelSelect = document.getElementById("model");
const submitButton = document.getElementById("submit");
const progress = document.getElementById("progress");
const message = document.getElementById("message");
const jobList = document.getElementById("jobs");
const emptyText = document.getElementById("empty");
const template = document.getElementById("job-template");
const clearAllButton = document.getElementById("clear-all");
const historyTools = document.getElementById("history-tools");
const pageSizeSelect = document.getElementById("page-size");
const pager = document.getElementById("pager");
const prevButton = document.getElementById("prev-page");
const nextButton = document.getElementById("next-page");
const pageInfo = document.getElementById("page-info");

const jobs = new Map(); // id -> dernier état connu (traitements de la page affichée)
const elements = new Map(); // id -> élément <li>
let page = 1;
let pageSize = 5;
let total = 0; // nombre de traitements dans tout l'historique
let maxUploadMb = 500;
let maxJobsPerUser = 5;

// --- Formulaire ---

function isAudio(file) {
  return file.name.toLowerCase().endsWith(".wav");
}

function onFileChosen() {
  const file = fileInput.files[0];
  hideMessage();
  if (!file) return;
  drop.classList.add("has-file");
  dropTitle.textContent = file.name;
  dropHint.textContent = `${(file.size / 2 ** 20).toFixed(1)} Mo · ${isAudio(file) ? "audio" : "vidéo"}`;

  const audio = isAudio(file);
  for (const radio of form.querySelectorAll("[data-video-only]")) {
    radio.disabled = audio;
    if (audio && radio.checked) form.querySelector('[value="subtitles"]').checked = true;
  }
}

function showMessage(text) {
  message.textContent = text;
  message.hidden = false;
}

function hideMessage() {
  message.hidden = true;
}

function upload(formData) {
  // XMLHttpRequest plutôt que fetch pour afficher la progression de l'envoi.
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/jobs");
    request.responseType = "json";
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        progress.firstElementChild.style.width = `${(100 * event.loaded) / event.total}%`;
      }
    };
    request.onload = () => {
      if (request.status === 401) redirectToLogin();
      if (request.status === 202) resolve(request.response);
      else reject(new Error(request.response?.detail || `Erreur ${request.status}`));
    };
    request.onerror = () => reject(new Error("Le serveur est injoignable"));
    request.send(formData);
  });
}

async function onSubmit(event) {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) {
    showMessage("Choisissez d'abord un fichier.");
    return;
  }
  if ([...jobs.values()].filter(isActive).length >= maxJobsPerUser) {
    showMessage(`Vous avez déjà ${maxJobsPerUser} traitements en cours : attendez qu'un traitement se termine.`);
    return;
  }
  if (file.size > maxUploadMb * 2 ** 20) {
    showMessage(`Le fichier dépasse la taille maximale de ${maxUploadMb} Mo.`);
    return;
  }
  hideMessage();
  submitButton.disabled = true;
  progress.hidden = false;
  progress.firstElementChild.style.width = "0";
  try {
    await upload(new FormData(form));
    // Le traitement le plus récent est en tête de la première page.
    await loadPage(1);
  } catch (error) {
    showMessage(error.message);
  } finally {
    submitButton.disabled = false;
    progress.hidden = true;
  }
}

// --- Liste des traitements ---

function isActive(job) {
  // Un état inconnu (null) sera redemandé au prochain passage.
  return !job || job.status === "pending" || job.status === "running";
}

// --- Pagination ---

function pageCount() {
  return Math.max(1, Math.ceil(total / pageSize));
}

// Taille de page mémorisée dans le navigateur (simple préférence d'affichage).
function loadPageSize() {
  try {
    const saved = Number(localStorage.getItem(PAGE_SIZE_KEY));
    if (PAGE_SIZES.includes(saved)) pageSize = saved;
  } catch { /* stockage indisponible : taille par défaut */ }
  pageSizeSelect.value = String(pageSize);
}

function onPageSizeChange() {
  pageSize = Number(pageSizeSelect.value);
  try {
    localStorage.setItem(PAGE_SIZE_KEY, String(pageSize));
  } catch { /* préférence non conservée */ }
  loadPage(1);
}

async function loadPage(number) {
  let result;
  try {
    result = await apiPage(`/api/jobs?limit=${pageSize}&offset=${(number - 1) * pageSize}`);
  } catch (error) {
    showMessage(`Impossible de charger l'historique : ${error.message}`);
    return;
  }
  page = number;
  total = result.total;
  // Page devenue vide (suppression du dernier élément) : on revient en arrière.
  if (result.items.length === 0 && page > 1) {
    await loadPage(Math.min(page - 1, pageCount()));
    return;
  }
  const ids = new Set(result.items.map((job) => job.id));
  // Les éléments déjà affichés sont conservés (un aperçu ouvert reste ouvert).
  [...jobs.keys()].filter((id) => !ids.has(id)).forEach(forget);
  jobs.clear();
  result.items.forEach((job) => jobs.set(job.id, job));
  render();
  schedulePoll();
}

function renderPager() {
  pager.hidden = total <= pageSize;
  pageInfo.textContent = `Page ${page} / ${pageCount()} · ${total} traitement${total > 1 ? "s" : ""}`;
  prevButton.disabled = page <= 1;
  nextButton.disabled = page >= pageCount();
}

function render() {
  const known = [...jobs.values()].filter(Boolean);
  emptyText.hidden = total > 0;
  historyTools.hidden = total === 0;
  renderPager();
  known.forEach((job, index) => {
    let element = elements.get(job.id);
    if (!element) {
      element = createJobElement(job);
      elements.set(job.id, element);
    }
    if (jobList.children[index] !== element) jobList.insertBefore(element, jobList.children[index] || null);
    updateJobElement(element, job);
  });
}

function createJobElement(job) {
  const element = template.content.firstElementChild.cloneNode(true);
  element.querySelector(".preview-btn").addEventListener("click", () => togglePreview(element, jobs.get(job.id)));
  element.querySelector(".delete-btn").addEventListener("click", () => deleteJob(job.id));
  element.querySelector(".cancel-btn").addEventListener("click", () => cancelJob(job.id));
  return element;
}

// --- Suppression (retire de l'historique ; le serveur conserve les fichiers) ---

function forget(id) {
  jobs.delete(id);
  elements.get(id)?.remove();
  elements.delete(id);
}

async function deleteJob(id) {
  if (!confirm(`Retirer « ${jobs.get(id).filename} » de votre historique ?`)) return;
  try {
    await api(`/api/jobs/${id}`, { method: "DELETE" });
    forget(id);
    // Recharge la page : le traitement suivant remonte de la page d'après.
    await loadPage(page);
  } catch (error) {
    showMessage(error.message);
  }
}

async function cancelJob(id) {
  if (!confirm(`Annuler le traitement de « ${jobs.get(id).filename} » ?`)) return;
  try {
    jobs.set(id, await api(`/api/jobs/${id}/cancel`, { method: "POST" }));
  } catch (error) {
    // Déjà terminé entre-temps : on affiche simplement son état réel.
    jobs.set(id, await api(`/api/jobs/${id}`).catch(() => jobs.get(id)));
    if (jobs.get(id).status !== "done") showMessage(error.message);
  }
  render();
}

async function deleteAll() {
  if (!confirm("Retirer tous vos traitements de votre historique ?")) return;
  try {
    await api("/api/jobs", { method: "DELETE" });
    [...jobs.keys()].forEach(forget);
    await loadPage(1);
  } catch (error) {
    showMessage(error.message);
  }
}

function updateJobElement(element, job) {
  element.querySelector(".job-name").textContent = job.filename;
  const meta = [OUTPUT_LABELS[job.output_kind], job.model, formatDate(job.created_at)];
  if (job.media_duration) meta.push(`durée ${formatSeconds(job.media_duration)}`);
  if (job.processing_time != null) meta.push(`traité en ${formatSeconds(job.processing_time)}`);
  element.querySelector(".job-meta").textContent = meta.join(" · ");

  const badge = element.querySelector(".badge");
  badge.className = `badge ${job.status}`;
  badge.textContent = STATUS_LABELS[job.status];

  element.querySelector(".cancel-btn").hidden = !isActive(job);
  const done = job.status === "done";
  element.querySelector(".preview-btn").hidden = !done;
  const download = element.querySelector(".download-btn");
  download.hidden = !done;
  download.href = `/api/jobs/${job.id}/result`;

  const error = element.querySelector(".job-error");
  error.hidden = job.status !== "failed";
  error.textContent = job.error || "";
}

async function togglePreview(element, job) {
  const container = element.querySelector(".preview");
  const button = element.querySelector(".preview-btn");
  if (!container.hidden) {
    container.hidden = true;
    container.replaceChildren(); // arrête la lecture vidéo
    button.textContent = "Aperçu";
    return;
  }
  container.replaceChildren(await buildPreview(job));
  container.hidden = false;
  button.textContent = "Masquer";
}

async function buildPreview(job) {
  const resultUrl = `/api/jobs/${job.id}/result?inline=true`;
  if (job.output_kind === "video_embedded" || job.output_kind === "video_track") {
    const video = document.createElement("video");
    video.controls = true;
    video.src = resultUrl;
    if (job.output_kind === "video_track") {
      // Les navigateurs n'affichent pas les pistes intégrées au MP4 :
      // on fournit la même piste au format WebVTT.
      const track = document.createElement("track");
      Object.assign(track, { kind: "subtitles", label: "Sous-titres", srclang: "en", default: true });
      track.src = `/api/jobs/${job.id}/subtitles.vtt`;
      video.append(track);
    }
    return video;
  }
  const pre = document.createElement("pre");
  if (job.output_kind === "subtitles") {
    try {
      const response = await fetch(resultUrl);
      pre.textContent = await response.text();
    } catch {
      pre.textContent = "Impossible de charger les sous-titres.";
    }
  } else {
    pre.textContent = job.text || "(aucun texte détecté)";
  }
  return pre;
}

// --- Suivi de l'avancement ---

let pollTimer = null;

function schedulePoll() {
  if (pollTimer === null) pollTimer = setTimeout(poll, POLL_MS);
}

async function poll() {
  pollTimer = null;
  await refresh([...jobs].filter(([, job]) => isActive(job)).map(([id]) => id));
  if ([...jobs.values()].some(isActive)) schedulePoll();
}

async function refresh(ids) {
  await Promise.all(ids.map(async (id) => {
    try {
      jobs.set(id, await api(`/api/jobs/${id}`));
    } catch (error) {
      if (error.message === "Traitement introuvable") forget(id);
    }
  }));
  render();
}

// --- Démarrage ---

async function init() {
  fileInput.addEventListener("change", onFileChosen);
  form.addEventListener("submit", onSubmit);
  clearAllButton.addEventListener("click", deleteAll);
  pageSizeSelect.addEventListener("change", onPageSizeChange);
  loadPageSize();
  prevButton.addEventListener("click", () => loadPage(page - 1));
  nextButton.addEventListener("click", () => loadPage(page + 1));
  for (const type of ["dragenter", "dragover"]) {
    drop.addEventListener(type, (event) => { event.preventDefault(); drop.classList.add("over"); });
  }
  for (const type of ["dragleave", "drop"]) {
    drop.addEventListener(type, () => drop.classList.remove("over"));
  }
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    fileInput.files = event.dataTransfer.files;
    onFileChosen();
  });

  try {
    await requireUser();
  } catch (error) {
    showMessage(`Le serveur ne répond pas : ${error.message}`);
    return;
  }

  try {
    const info = await api("/api/info");
    maxUploadMb = info.max_upload_mb;
    maxJobsPerUser = info.max_jobs_per_user;
    modelSelect.replaceChildren(...info.models.map((name) => new Option(name, name, false, name === info.default_model)));
  } catch (error) {
    showMessage(`Le serveur ne répond pas : ${error.message}`);
  }

  // Historique conservé côté serveur : le même sur tous les appareils de l'utilisateur.
  await loadPage(1);
}

init();
