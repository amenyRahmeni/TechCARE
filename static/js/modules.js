"use strict";
(() => {
  const input = document.querySelector("[data-photo-input]");
  const preview = document.querySelector("[data-photo-preview]");
  let previous;
  input?.addEventListener("change", () => {
    if (previous) URL.revokeObjectURL(previous);
    const file = input.files[0];
    preview.hidden = !file;
    input.setCustomValidity(file && file.size > 5 * 1024 * 1024 ? "La photo doit faire au maximum 5 Mo." : "");
    if (!file) return;
    previous = URL.createObjectURL(file);
    preview.querySelector("[data-photo-image]").src = previous;
    preview.querySelector("[data-photo-name]").textContent = file.name;
  });
})();

(() => {
  const form = document.querySelector("[data-repair-form]");
  if (!form) return;
  const problem = form.querySelector("[name=problem]");
  const technician = form.querySelector("[name=technician]");
  const note = form.querySelector("[data-repair-technicians-note]");
  const submit = form.querySelector("[data-submit-label]");
  let controller;
  const update = async () => {
    controller?.abort();
    if (!problem.value) {
      technician.replaceChildren(new Option("Choisissez d’abord le type de panne", ""));
      technician.disabled = false;
      submit.disabled = false;
      note.textContent = "Choisissez le type de panne pour afficher les techniciens qualifiés.";
      return;
    }
    const selected = technician.value;
    const active = new AbortController();
    controller = active;
    technician.disabled = true;
    submit.disabled = true;
    note.textContent = "Recherche des techniciens qualifiés…";
    try {
      const response = await fetch(`${form.dataset.techniciansUrl}?${new URLSearchParams({problem: problem.value})}`, {signal: active.signal, headers: {Accept: "application/json"}});
      if (!response.ok) throw new Error("technicians");
      const result = await response.json();
      technician.replaceChildren(new Option("Choisir un technicien", ""));
      result.technicians.forEach(item => {
        const option = new Option(`${item.name} · ${item.specialty}`, item.id);
        option.selected = String(item.id) === selected;
        technician.append(option);
      });
      note.textContent = result.technicians.length ? `${result.technicians.length} technicien(s) qualifié(s) disponible(s).` : "Aucun technicien qualifié n’est disponible pour ce type de panne pour le moment.";
      note.classList.toggle("is-error", !result.technicians.length);
    } catch (error) {
      if (error.name === "AbortError") return;
      note.textContent = "La qualification du technicien sera vérifiée à l’envoi de la demande. Vous pouvez réessayer.";
    } finally {
      if (controller === active) {
        technician.disabled = false;
        submit.disabled = false;
      }
    }
  };
  problem.addEventListener("change", update);
  update();
})();
