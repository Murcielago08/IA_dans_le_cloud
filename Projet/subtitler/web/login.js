// Page de connexion et de création de compte.

const loginForm = document.getElementById("login-form");
const password = document.getElementById("password");
const submitButton = document.getElementById("submit");
const message = document.getElementById("message");
let signup = false;

function nextPage() {
  // Uniquement un chemin local : pas de redirection vers un autre site.
  const next = new URLSearchParams(location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "index.html";
}

function setMode(isSignup) {
  signup = isSignup;
  document.getElementById("title").textContent = signup ? "Créer un compte" : "Connexion";
  document.getElementById("lead").textContent = signup
    ? "Choisissez un identifiant et un mot de passe d'au moins 8 caractères."
    : "Connectez-vous pour transcrire vos fichiers et retrouver vos traitements.";
  submitButton.textContent = signup ? "Créer le compte" : "Se connecter";
  password.autocomplete = signup ? "new-password" : "current-password";
  document.getElementById("switch-text").textContent = signup ? "Déjà un compte ?" : "Pas encore de compte ?";
  document.getElementById("switch-btn").textContent = signup ? "Se connecter" : "Créer un compte";
  message.hidden = true;
}

async function onSubmit(event) {
  event.preventDefault();
  submitButton.disabled = true;
  message.hidden = true;
  try {
    await api(signup ? "/api/auth/register" : "/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: loginForm.username.value, password: password.value }),
    });
    location.replace(nextPage());
  } catch (error) {
    message.textContent = error.message;
    message.hidden = false;
  } finally {
    submitButton.disabled = false;
  }
}

async function init() {
  loginForm.addEventListener("submit", onSubmit);
  document.getElementById("switch-btn").addEventListener("click", () => setMode(!signup));
  try {
    await api("/api/auth/me");
    location.replace(nextPage()); // déjà connecté
    return;
  } catch { /* pas de session : on reste sur la page */ }
  try {
    const info = await api("/api/info");
    document.getElementById("switch").hidden = !info.signup_enabled;
  } catch (error) {
    message.textContent = `Le serveur ne répond pas : ${error.message}`;
    message.hidden = false;
  }
}

init();
