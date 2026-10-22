"use strict";

// All records and filtering are handled by Django. JS only enhances the interface.
document.querySelectorAll("[data-auto-submit]").forEach((select) => {
  select.addEventListener("change", () => select.form.requestSubmit());
});

document.querySelectorAll("[data-dismiss-message]").forEach((button) => {
  button.addEventListener("click", () => button.closest(".toast").remove());
});

const sidebar = document.getElementById("sidebar");
const menuButton = document.querySelector("[data-open-menu]");
const overlay = document.querySelector("[data-close-menu]");
const setMenu = (isOpen) => {
  if (!sidebar || !menuButton || !overlay) return;
  sidebar.classList.toggle("is-open", isOpen);
  menuButton.setAttribute("aria-expanded", String(isOpen));
  overlay.hidden = !isOpen;
  document.body.style.overflow = isOpen ? "hidden" : "";
  if (isOpen) sidebar.querySelector("a").focus();
  else menuButton.focus();
};
menuButton?.addEventListener("click", () => setMenu(true));
overlay?.addEventListener("click", () => setMenu(false));
document.addEventListener("keydown", (event) => {
  if (!sidebar?.classList.contains("is-open")) return;
  if (event.key === "Escape") setMenu(false);
  if (event.key === "Tab") {
    const focusable = [...sidebar.querySelectorAll("a[href], button")];
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
});
window.matchMedia("(min-width: 901px)").addEventListener("change", (event) => {
  if (event.matches && sidebar?.classList.contains("is-open")) setMenu(false);
});

document.querySelectorAll("[data-toggle-password]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.getElementById(button.getAttribute("aria-controls"));
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "Masquer" : "Afficher";
    button.setAttribute("aria-label", show ? "Masquer le mot de passe" : "Afficher le mot de passe");
    button.setAttribute("aria-pressed", String(show));
  });
});

const bookingForm = document.querySelector("[data-booking-form]");
if (bookingForm) {
  const technician = bookingForm.querySelector("[name=technician]");
  const date = bookingForm.querySelector("[name=date]");
  const pc = bookingForm.querySelector("[name=pc]");
  const time = bookingForm.querySelector("[name=time]");
  const note = bookingForm.querySelector("[data-availability-note]");
  let controller;
  const updateAvailability = async () => {
    controller?.abort();
    if (!technician.value || !date.value) {
      time.disabled = false;
      note.textContent = "Choisissez un technicien et une date pour consulter les disponibilités.";
      return;
    }
    const activeController = new AbortController();
    controller = activeController;
    const selected = time.value;
    const params = new URLSearchParams({technician: technician.value, date: date.value, pc: pc.value, appointment: bookingForm.dataset.appointmentId});
    time.disabled = true;
    note.classList.remove("is-error");
    note.textContent = "Vérification des créneaux…";
    try {
      const response = await fetch(`${bookingForm.dataset.availabilityUrl}?${params}`, {signal: activeController.signal, headers: {Accept: "application/json"}});
      if (!response.ok) throw new Error("availability");
      const result = await response.json();
      time.replaceChildren(new Option("Choisir un créneau", ""));
      result.slots.forEach((slot) => {
        const option = new Option(slot.label + (slot.available ? "" : " · indisponible"), slot.value);
        option.disabled = !slot.available;
        option.selected = slot.available && slot.value === selected;
        time.append(option);
      });
      const count = result.slots.filter(slot => slot.available).length;
      note.textContent = count ? `${count} créneau${count > 1 ? "x" : ""} disponible${count > 1 ? "s" : ""}. ${result.note}` : "Aucun créneau disponible à cette date. Essayez une autre date ou un autre technicien.";
      note.classList.toggle("is-error", count === 0);
    } catch (error) {
      if (error.name === "AbortError") return;
      note.textContent = "La disponibilité sera vérifiée lors de la réservation. Vous pouvez aussi réessayer.";
      note.classList.add("is-error");
    } finally {
      if (controller === activeController && !activeController.signal.aborted) time.disabled = false;
    }
  };
  [technician, date, pc].forEach(field => field.addEventListener("change", updateAvailability));
  updateAvailability();
}

const interventionForm = document.querySelector("[data-intervention-form]");
if (interventionForm) {
  const list = interventionForm.querySelector("[data-parts-list]");
  const totalForms = interventionForm.querySelector("[name='parts-TOTAL_FORMS']");
  const limitNote = interventionForm.querySelector("[data-part-limit]");
  const calculate = () => {
    const labour = Number(interventionForm.querySelector("[data-labour-cost]").value) || 0;
    let total = labour;
    list.querySelectorAll("[data-part-row]:not([hidden])").forEach(row => {
      const quantity = Number(row.querySelector("[data-part-quantity]").value) || 0;
      const price = Number(row.querySelector("[data-part-price]").value) || 0;
      total += quantity * price;
    });
    interventionForm.querySelector("[data-cost-total]").textContent = total.toLocaleString("fr-TN", {minimumFractionDigits: 3, maximumFractionDigits: 3});
  };
  interventionForm.querySelector("[data-add-part]").addEventListener("click", () => {
    if (list.querySelectorAll("[data-part-row]:not([hidden])").length >= 20 || Number(totalForms.value) >= 40) {
      limitNote.textContent = "Vous pouvez renseigner jusqu’à 20 lignes de pièces. Enregistrez pour poursuivre après de nombreux changements.";
      return;
    }
    const index = Number(totalForms.value);
    const template = interventionForm.querySelector("[data-part-template]");
    const container = document.createElement("div");
    container.innerHTML = template.innerHTML.replaceAll("__prefix__", String(index));
    const row = container.firstElementChild;
    list.append(row);
    totalForms.value = String(index + 1);
    row.querySelector("[name$='-name']").focus();
    limitNote.textContent = "";
  });
  list.addEventListener("click", event => {
    const button = event.target.closest("[data-remove-part]");
    if (!button) return;
    const row = button.closest("[data-part-row]");
    row.querySelector("[name$='-DELETE']").checked = true;
    row.hidden = true;
    calculate();
  });
  interventionForm.addEventListener("input", calculate);
  calculate();
}

document.querySelectorAll("[data-submit-label]").forEach((button) => {
  button.dataset.originalHtml = button.innerHTML;
  button.dataset.initiallyDisabled = String(button.disabled);
});
document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", () => {
    const button = form.querySelector("[data-submit-label]");
    if (!button) return;
    button.disabled = true;
    button.textContent = button.dataset.submitLabel;
  });
});
window.addEventListener("pageshow", () => {
  // Restore submit buttons if the browser restores a page from its back cache.
  document.querySelectorAll("[data-submit-label]").forEach((button) => {
    button.disabled = button.dataset.initiallyDisabled === "true";
    button.innerHTML = button.dataset.originalHtml;
  });
});
