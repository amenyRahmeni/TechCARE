"use strict";

(() => {
  const root = document.querySelector("[data-campaign-compose]");
  if (!root) return;
  const form = root.querySelector("form");
  const audience = form.elements.audience;
  const choices = root.querySelector("[data-campaign-recipients]");
  const counts = JSON.parse(document.querySelector("#notification-audience-counts").textContent);
  const title = form.elements.title;
  const message = form.elements.message;
  const level = form.elements.level;
  const submit = root.querySelector("[data-campaign-submit]");

  function update() {
    const selected = audience.value === "selected";
    choices.hidden = !selected;
    const count = selected ? choices.querySelectorAll('input[type="checkbox"]:checked').length : (counts[audience.value] || 0);
    root.querySelector("[data-audience-count]").textContent = `${count} destinataire${count === 1 ? "" : "s"}`;
    root.querySelector("[data-audience-label]").textContent = count ? audience.selectedOptions[0].textContent : "Choisissez au moins un compte actif avant l’envoi.";
    root.querySelector("[data-preview-title]").textContent = title.value.trim() || "Le titre de votre notification";
    root.querySelector("[data-preview-message]").textContent = message.value.trim() || "Votre message apparaîtra ici pendant la rédaction.";
    root.querySelector("[data-preview-level]").textContent = level.selectedOptions[0].textContent;
    root.querySelector("[data-preview-icon]").className = "notification-type-icon level-" + level.value;
    root.querySelector("[data-message-count]").textContent = `${message.value.length} / 700 caractères`;
    submit.disabled = count === 0;
  }

  root.querySelector("[data-recipient-search]").addEventListener("input", event => {
    const query = event.target.value.toLocaleLowerCase("fr").trim();
    let found = 0;
    choices.querySelectorAll("[data-recipient-choice]").forEach(choice => {
      choice.hidden = !choice.textContent.toLocaleLowerCase("fr").includes(query);
      if (!choice.hidden) found++;
    });
    root.querySelector("[data-recipient-empty]").hidden = found > 0;
  });
  form.addEventListener("input", update);
  form.addEventListener("change", update);
  window.addEventListener("pageshow", update);
  update();
})();
