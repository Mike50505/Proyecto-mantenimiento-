(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
  const windowLabels = {dashboard:'Panel general', orders:'Órdenes de trabajo', assets:'Activos', preventives:'Preventivos', inventory:'Inventario', catalogs:'Catálogos', users:'Usuarios', imports:'Importación de Excel', audit:'Auditoría', downtime:'Paros y agenda'};
  const actionLabels = {'orders.create':'Crear solicitudes', 'orders.read':'Consultar órdenes', 'orders.edit':'Editar órdenes', 'orders.edit_dates':'Modificar fechas de órdenes', 'orders.assign':'Asignar técnicos', 'orders.transition':'Cambiar estado de órdenes', 'orders.validate':'Validar y cerrar órdenes', 'orders.time':'Registrar tiempos', 'assets.read':'Consultar activos', 'assets.edit':'Crear y editar activos', 'preventives.read':'Consultar preventivos', 'preventives.edit':'Crear y editar preventivos', 'inventory.read':'Consultar inventario', 'inventory.move':'Registrar salidas y devoluciones', 'inventory.adjust':'Ajustar existencias', 'catalogs.manage':'Administrar catálogos', 'users.manage':'Administrar usuarios e importaciones', 'audit.read':'Consultar auditoría'};
  const minimumActions = {dashboard:['orders.read'], orders:['orders.read'], downtime:['orders.read'], assets:['assets.read'], preventives:['preventives.read'], inventory:['inventory.read'], catalogs:['catalogs.manage'], users:['users.manage'], imports:['users.manage'], audit:['audit.read']};
  const roleKey = role => ({Operador:'Solicitante', Mantenimiento:'Técnico'}[role] || role || 'Solicitante');
  const same = (a, b) => JSON.stringify([...(a || [])].sort()) === JSON.stringify([...(b || [])].sort());

  function markup(schema, user = {}) {
    const defaults = schema.defaults[roleKey(user.role)] || {permissions:[], actions:[]};
    const customized = user.custom_permissions || (user.id && !['Administrador','Jefe de mantenimiento'].includes(user.role) &&
      (!same(user.permissions, defaults.permissions) || !same(user.actions, defaults.actions) || user.areas?.length));
    const selected = {permissions:user.permissions || defaults.permissions, actions:user.actions || defaults.actions, areas:user.areas || []};
    const group = (key, title, values, labels, help) => `<fieldset class="permission-section" data-permission-group="${key}"><legend>${title}</legend><p class="subtle">${help}</p>${key === 'areas' ? `<label class="permission-option"><input type="checkbox" data-all-areas ${selected.areas.length ? '' : 'checked'}>Todas las áreas</label>` : ''}<div class="permission-tools"><button type="button" class="btn btn-secondary" data-select-all="${key}">Seleccionar todas</button><button type="button" class="btn btn-secondary" data-clear="${key}">Quitar selección</button></div><div class="permission-grid">${values.map(value => `<label class="permission-option"><input type="checkbox" name="${key}" value="${escape(value)}" ${selected[key].includes(value) ? 'checked' : ''}><span>${escape(labels[value] || value)}</span></label>`).join('') || '<p class="subtle">No hay áreas registradas. Agrégalas en Catálogos.</p>'}</div></fieldset>`;
    return `<section class="field full permission-editor"><label class="permission-option permission-mode"><input type="checkbox" name="custom_permissions" value="1" ${customized ? 'checked' : ''}><span><b>Personalizar permisos de esta cuenta</b><small>Sin marcar, se usan los accesos del rol. Al personalizar, solo se permiten las opciones seleccionadas.</small></span></label><div data-permission-selections>${group('permissions', 'Ventanas visibles', schema.modules, windowLabels, 'Selecciona las ventanas que podrá abrir. Al marcar una ventana se activa su acción de consulta.')}${group('actions', 'Acciones permitidas', schema.actions, actionLabels, 'Selecciona qué puede hacer dentro de las ventanas autorizadas.')}${group('areas', 'Áreas autorizadas', [...new Set([...schema.areas, ...selected.areas])], {}, 'Todas las áreas permite el alcance general. Desmárcala para elegir áreas específicas.')}</div><p class="subtle" data-permission-summary role="status" aria-live="polite"></p></section>`;
  }

  function bind(wrap, schema) {
    const mode = wrap.querySelector('[name="custom_permissions"]');
    if (!mode) return () => ({});
    const role = wrap.querySelector('[name="role"]');
    const allAreas = wrap.querySelector('[data-all-areas]');
    const inputs = key => [...wrap.querySelectorAll(`input[name="${key}"]`)];
    const checked = key => inputs(key).filter(input => input.checked).map(input => input.value);
    function update() {
      wrap.querySelectorAll('[data-permission-group]').forEach(group => group.disabled = !mode.checked);
      inputs('areas').forEach(input => input.disabled = !mode.checked || allAreas.checked);
      const windows = checked('permissions').length, actions = checked('actions').length;
      wrap.querySelector('[data-permission-summary]').textContent = mode.checked
        ? `${windows} ventanas y ${actions} acciones seleccionadas.${windows === 0 ? ' Esta cuenta no tendrá ventanas disponibles.' : ''}`
        : 'Se usarán los permisos predeterminados del rol.';
    }
    function loadDefaults() {
      if (mode.checked) return;
      const defaults = schema.defaults[roleKey(role?.value)] || {permissions:[], actions:[]};
      for (const key of ['permissions', 'actions']) inputs(key).forEach(input => input.checked = defaults[key].includes(input.value));
      allAreas.checked = true;
      inputs('areas').forEach(input => input.checked = false);
      update();
    }
    wrap.addEventListener('change', event => {
      if (event.target === role) loadDefaults();
      if (event.target === mode && !mode.checked) loadDefaults();
      if (mode.checked && event.target.name === 'permissions' && event.target.checked) {
        const needed = minimumActions[event.target.value] || [];
        inputs('actions').forEach(input => {if (needed.includes(input.value)) input.checked = true;});
      }
      update();
    });
    wrap.addEventListener('click', event => {
      const button = event.target.closest('[data-select-all], [data-clear]');
      if (!button || !mode.checked) return;
      const key = button.dataset.selectAll || button.dataset.clear;
      const select = !!button.dataset.selectAll;
      if (key === 'areas') allAreas.checked = false;
      inputs(key).forEach(input => {input.checked = select;});
      if (key === 'permissions' && select) {
        const needed = schema.modules.flatMap(module => minimumActions[module] || []);
        inputs('actions').forEach(input => {if (needed.includes(input.value)) input.checked = true;});
      }
      update();
    });
    loadDefaults();
    update();
    return () => {
      if (mode.checked && !allAreas.checked && !checked('areas').length) throw new Error('Selecciona al menos un área o marca Todas las áreas.');
      return mode.checked ? {custom_permissions:true, permissions:checked('permissions'), actions:checked('actions'), areas:allAreas.checked ? [] : checked('areas')} : {custom_permissions:false};
    };
  }
  window.MesaPermissions = {markup, bind};
})();
