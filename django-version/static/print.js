const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = value => {if(!value)return '—';const parsed=new Date(String(value).includes('T')?value:String(value).replace(' ','T'));return Number.isFinite(parsed.getTime())?new Intl.DateTimeFormat('es-MX',{dateStyle:'short',timeStyle:'short'}).format(parsed):'Fecha no disponible'};
const money = value => new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(value || 0);
(async () => {
  const id = new URLSearchParams(location.search).get('id');
  try {
    const response = await fetch(`/api/orders/${id}`);
    if (!response.ok) throw new Error(response.status === 401 ? 'Inicia sesión antes de abrir el formato.' : 'No fue posible consultar el mantenimiento.');
    const o = await response.json();
    document.title = `${o.folio} - Formato de mantenimiento`;
    const sheet = document.querySelector('#sheet'); sheet.className = 'sheet';
    sheet.innerHTML = `<table class="doc-table">
      <tr><td class="logo">MESA</td><td class="doc-title" colspan="3">MANUFACTURAS ESPECIALIZADAS S.A.<br>PLANTA RAMOS</td></tr>
      <tr><td class="section" colspan="4">Datos generales de la máquina / equipo</td></tr>
      <tr><td class="label">Máquina / equipo:</td><td class="value" colspan="3">${esc(o.asset_name || 'Sin activo asociado')}</td></tr>
      <tr><td class="label">Marca:</td><td class="value">${esc(o.asset_brand || '—')}</td><td class="label">Modelo:</td><td class="value">${esc(o.asset_model || '—')}</td></tr>
      <tr><td class="label">Voltaje:</td><td class="value">${esc(o.asset_voltage || '—')}</td><td class="label">Código:</td><td class="value">${esc(o.asset_code || '—')}</td></tr>
      <tr><td class="section" colspan="4">Datos del mantenimiento</td></tr>
      <tr><td class="label">Folio:</td><td class="value">${esc(o.folio)}</td><td class="label">Estado:</td><td class="value">${esc(o.status)}</td></tr>
      <tr><td class="label">Código documental:</td><td class="value">${esc(o.closure_document_code||'Pendiente de configurar')}</td><td class="label">Revisión:</td><td class="value">${esc(o.closure_document_revision||'Pendiente')}</td></tr>
      <tr><td class="label">Ubicación:</td><td class="value" colspan="3">${esc(o.location||'—')}</td></tr>
      <tr><td class="label">Fecha y hora impresión:</td><td class="value" colspan="3">${date(new Date().toISOString())}</td></tr>
      <tr><td class="label">Fecha y hora inicio:</td><td class="value">${date(o.started_at || o.requested_at)}</td><td class="label">Fecha y hora cierre:</td><td class="value">${date(o.finished_at)}</td></tr>
      <tr><td class="label">Tipo:</td><td class="value">${esc(o.classification)}</td><td class="label">¿Realizado?</td><td class="value">${o.status === 'Completada' ? 'REALIZADO' : 'PENDIENTE'}</td></tr>
      <tr><td class="label">Responsable:</td><td class="value" colspan="3">${esc(o.technician_name || 'Sin asignar')}</td></tr>
      <tr><td class="label">Descripción:</td><td class="description" colspan="3">${esc(o.actions || o.reported_failure)}</td></tr>
      <tr><td class="label">Observaciones / falla:</td><td class="observations" colspan="3">${esc(o.reported_failure)}</td></tr>
      <tr><td class="label">Tiempo de reparación:</td><td class="value">${esc(o.labor_hours || 0)} horas</td><td class="label">Prioridad:</td><td class="value">${esc(o.priority)}</td></tr>
      <tr><td class="label">Costo insumos:</td><td class="value" colspan="3">${money(o.material_cost)}</td></tr>
      <tr><td class="label">Elaborado por:</td><td class="value" colspan="3">${esc(o.technician_name || 'Pendiente')}</td></tr>
      <tr><td class="label">Autorizado por:</td><td class="value signature" colspan="3">${esc(o.validator_name || 'Pendiente')}</td></tr>
      <tr><td class="label">Validado el:</td><td class="value" colspan="3">${date(o.validated_at)}</td></tr>
      <tr><td class="section" colspan="4">${o.status==='Completada'?'Cierre validado':'Borrador sin validación'}</td></tr>
      <tr><td class="section" colspan="4">Insumos / materiales</td></tr></table>
      <table class="doc-table materials"><thead><tr><th>Código</th><th>Descripción</th><th>Cantidad</th><th>Costo</th></tr></thead><tbody>${o.materials.length ? o.materials.map(m => `<tr><td>${esc(m.code || '—')}</td><td>${esc(m.description)}</td><td>${esc(m.quantity)}</td><td>${money(m.total)}</td></tr>`).join('') : '<tr><td colspan="4" style="text-align:center">Sin materiales registrados</td></tr>'}</tbody><tfoot><tr><th colspan="3" style="text-align:right">Total</th><th>${money(o.material_cost)}</th></tr></tfoot></table>
      <div class="footer-note">Documento generado por MESA Mantenimiento. Folio de trazabilidad: ${esc(o.folio)}</div>`;
  } catch (error) { document.querySelector('#sheet').innerHTML = `<div class="error">${esc(error.message)}</div>`; }
})();
