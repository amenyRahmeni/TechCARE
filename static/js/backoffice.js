(() => {
  const form = document.querySelector('[data-account-form]');
  if (!form) return;
  const role = form.querySelector('[name="role"]');
  function updateRoleFields() {
    const technician = role.value === 'technician';
    form.querySelectorAll('[data-technician-field]').forEach(element => {
      element.hidden = !technician;
      element.querySelectorAll('input').forEach(input => {
        input.disabled = !technician;
        if (input.name === 'specialty') input.required = technician;
      });
    });
  }
  role.addEventListener('change', updateRoleFields);
  updateRoleFields();
})();
