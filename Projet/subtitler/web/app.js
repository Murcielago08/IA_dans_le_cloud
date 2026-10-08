// Page utilisateur : envoi d'un fichier et suivi des traitements.

const STORAGE_KEY = "subtitler.jobs";
const POLL_MS = 2000;

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

const jobs = new Map(); // id -> dernier état connu
const elements = new Map(); // id -> élément <li>
let maxUploadMb = 500;

// --- Historique local des traitements de cet utilisateur ---

function loadJobIds() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}

function saveJobIds() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...jobs.keys()]));
  } catch { /* stockage indisponible : l'historique ne sera pas conservé */ }
}

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
  if (file.size > maxUploadMb * 2 ** 20) {
    showMessage(`Le fichier dépasse la taille maximale de ${maxUploadMb} Mo.`);
    return;
  }
  hideMessage();
  submitButton.disabled = true;
  progress.hidden = false;
  progress.firstElementChild.style.width = "0";
  try {
    const job = await upload(new FormData(form));
    jobs.set(job.id, job);
    // Le traitement le plus récent en premier.
    const ordered = new Map([[job.id, job], ...jobs]);
    jobs.clear();
    ordered.forEach((value, key) => jobs.set(key, value));
    saveJobIds();
    render();
    schedulePoll();
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

function render() {
  const known = [...jobs.values()].filter(Boolean);
  emptyText.hidden = known.length > 0;
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
  return element;
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
      if (error.message === "Traitement introuvable") {
        jobs.delete(id);
        elements.get(id)?.remove();
        elements.delete(id);
      }
    }
  }));
  saveJobIds();
  render();
}

// --- Démarrage ---

async function init() {
  fileInput.addEventListener("change", onFileChosen);
  form.addEventListener("submit", onSubmit);
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
    const info = await api("/api/info");
    maxUploadMb = info.max_upload_mb;
    modelSelect.replaceChildren(...info.models.map((name) => new Option(name, name, false, name === info.default_model)));
  } catch (error) {
    showMessage(`Le serveur ne répond pas : ${error.message}`);
  }

  const ids = loadJobIds();
  ids.forEach((id) => jobs.set(id, null));
  await refresh(ids);
  schedulePoll();
}

init();
