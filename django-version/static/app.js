const $ = (s, root=document) => root.querySelector(s);
const makeRequestKey=()=>{if(typeof crypto!=='undefined'&&typeof crypto.randomUUID==='function'&&crypto.randomUUID!==makeRequestKey)return crypto.randomUUID();if(typeof crypto!=='undefined'&&typeof crypto.getRandomValues==='function'){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return [...bytes].map(value=>value.toString(16).padStart(2,'0')).join('')+'-'+Date.now()}return `${Date.now()}-${Math.random().toString(36).slice(2)}`};
if(typeof crypto!=='undefined'&&typeof crypto.randomUUID!=='function'){try{crypto.randomUUID=makeRequestKey}catch{} }
const state = { view:'dashboard', catalogs:null, user:null, pollTimer:null, lastOrderTotal:null, orderSignature:null, dashboardFrom:'', dashboardTo:'', auditFilters:{from:'',to:'',entity_type:'',action:'',q:''}, auditPage:1 };
const titles = {
  dashboard:['Panel general','Resumen operativo de Planta Ramos'],
  orders:['Órdenes de trabajo','Registro, atención y seguimiento'],
  assets:['Activos','Maquinaria, infraestructura y unidades'],
  catalogs:['Catálogos','Valores disponibles para captura y asignación'],
  inventory:['Inventario','Existencias, mínimos y movimientos'],
  preventives:['Mantenimiento preventivo','Programa de actividades próximas'],
  downtime:['Paros y agenda','Indisponibilidad y carga de técnicos'],
  users:['Administración de usuarios','Accesos, contraseñas y permisos'],
  imports:['Vista previa de Excel','Revisión de hojas y códigos antes de migrar'],
  audit:['Auditoría','Historial de cambios del sistema']
};
const fmtDate = value => {
  if(value===null||value===undefined||value==='')return '—';
  try{
    const raw=String(value).trim();
    const normalized=/^\d{4}-\d{2}-\d{2} \d/.test(raw)?raw.replace(' ','T'):raw.includes('T')?raw:raw+'T12:00';
    const parsed=value instanceof Date?value:new Date(normalized);
    if(!Number.isFinite(parsed.getTime()))return 'Fecha no disponible';
    return new Intl.DateTimeFormat('es-MX',{dateStyle:'medium'}).format(parsed);
  }catch{
    return 'Fecha no disponible';
  }
};
const money = value => new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(value||0);
const esc = value => String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const badgeClass = status => ({'Completada':'completed','En proceso':'process','Disponible':'available','Operativa':'available','En mantenimiento':'maintenance','Detenido':'stopped','Parada':'stopped','Operación restringida':'overdue','Fuera de servicio':'overdue','Sin información':'overdue','Próximo':'upcoming','Vencido':'overdue'}[status]||'');
const badge = status => `<span class="badge ${badgeClass(status)}">${esc(status)}</span>`;
const csrfToken=()=>document.cookie.split('; ').find(part=>part.startsWith('csrftoken='))?.split('=').slice(1).join('=')||'';
async function api(url,options={}){let res;try{const method=(options.method||'GET').toUpperCase();const headers={...options.headers};if(!(options.body instanceof FormData))headers['Content-Type']='application/json';if(!['GET','HEAD','OPTIONS','TRACE'].includes(method))headers['X-CSRFToken']=decodeURIComponent(csrfToken());res=await fetch(url,{...options,headers});}catch{throw new Error('No se pudo contactar al servidor. Tu captura sigue aquí; revisa la conexión y reintenta.');}const data=await res.json();if(!res.ok){if(res.status===401&&url!=='/api/auth/login')showLogin();throw new Error(data.error||'No se pudo completar la operación');}return data;}
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600)}

async function renderDashboard(){
  const period=new URLSearchParams();if(state.dashboardFrom)period.set('from',state.dashboardFrom);if(state.dashboardTo)period.set('to',state.dashboardTo);
  const suffix=period.size?'?'+period.toString():'';
  const d=await api('/api/dashboard'+suffix);
  const alerts=(await api('/api/alerts')).alerts;
  const max=Math.max(1,...d.byStatus.map(x=>x.value));
  $('#content').innerHTML=`
    <section class="card" style="margin-bottom:18px"><form id="dashboard-period" class="toolbar"><label>OT desde <input type="date" id="dashboard-from" value="${esc(state.dashboardFrom)}"></label><label>hasta <input type="date" id="dashboard-to" value="${esc(state.dashboardTo)}"></label><button class="btn btn-secondary" type="submit">Aplicar período</button><button class="btn btn-secondary" id="dashboard-reset" type="button">Quitar período</button><a class="btn btn-secondary" href="/api/dashboard/export.xlsx${suffix}">Exportar OT del corte</a></form><small class="subtle">El período usa la fecha de solicitud de las OT. Activos, inventario, preventivos y alertas muestran condiciones actuales.</small></section>
    <section class="metrics">
      ${metric('Órdenes registradas',d.orders.total,'≡','Histórico de órdenes')}
      ${metric('Reportes nuevos',d.orders.new_orders||0,'●',`${d.orders.unassigned||0} sin asignar`)}
      ${metric('Horas hombre',Number(d.orders.labor_hours).toFixed(1),'◴','Acumuladas en órdenes')}
      ${metric('Gasto en materiales',money(d.orders.material_cost),'$','Salidas menos devoluciones registradas')}
    </section>
    <section class="grid-2">
      <div class="card"><h3>Estado de órdenes</h3><div class="bars">${d.byStatus.map(x=>`<div class="bar-row"><span>${esc(x.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${x.value/max*100}%"></div></div><b>${x.value}</b></div>`).join('')}</div></div>
      <div class="card"><h3>Atención operativa</h3><small class="subtle">Corte: ${esc(fmtDate(d.updated_at))}</small><div class="metrics" style="grid-template-columns:1fr 1fr;margin:0">
        <div><div class="metric-value">${d.assets.maintenance||0}</div><span class="subtle">Activos en mantenimiento</span></div>
        <div><div class="metric-value">${d.preventives.attention||0}</div><span class="subtle">Preventivos por atender</span><button class="order-action" onclick="navigate('preventives')">Ver programa</button></div>
        <div><div class="metric-value" style="color:var(--red)">${d.assets.stopped||0}</div><span class="subtle">Máquinas paradas</span></div>
        <div><div class="metric-value">${d.orders.critical||0}</div><span class="subtle">OT prioridad Paro de máquina</span></div>
        <div><div class="metric-value">${d.assets.total||0}</div><span class="subtle">Activos registrados</span></div>
        <div><div class="metric-value">${d.inventory.low_stock||0}</div><span class="subtle">Insumos en/bajo mínimo</span><button class="order-action" onclick="navigate('inventory')">Ver inventario</button></div>
      </div>${d.assets.stopped_details?.length?`<div class="timeline">${d.assets.stopped_details.map(asset=>`<div class="timeline-item"><b>${esc(asset.code)} · ${esc(asset.name)}</b><small>Parada: ${esc(asset.cause||'Causa pendiente')}</small><button class="order-action asset-detail" data-id="${asset.id}">Ver activo</button></div>`).join('')}</div>`:''}</div>
    </section>
    <section class="card table-card" style="margin-top:20px"><div class="table-head"><div><h3>Alertas operativas <span class="badge">${alerts.length}</span></h3><span class="subtle">Condiciones vigentes de activos, OT, preventivos e inventario.</span></div><a class="btn btn-secondary" href="/api/alerts/export.xlsx">Exportar XLSX</a></div>${alerts.length?`<div class="table-wrap"><table><thead><tr><th>Severidad</th><th>Alerta</th><th>Detalle</th><th>Estado</th><th>Atención</th></tr></thead><tbody>${alerts.map(a=>`<tr><td class="${a.severity==='Crítica'?'priority-critical':''}">${esc(a.severity)}</td><td><b>${esc(a.title)}</b>${a.area?`<div class="subtle">${esc(a.area)}</div>`:''}</td><td>${esc(a.detail)}</td><td>${badge(a.status)}</td><td>${a.status==='Atendida'?`<small>${esc(a.handled_by||'')} · ${fmtDate(a.handled_at)}</small><div class="subtle">${esc(a.handling_note)}</div>`:''}<button class="order-action alert-handle" data-id="${a.id}">${a.status==='Atendida'?'Actualizar nota':'Registrar atención'}</button></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">No hay alertas operativas activas.</div>'}</section>
    <section class="grid-2" style="margin-top:20px">
      <div class="card table-card"><div class="table-head"><h3>Prioridad de atención</h3><span class="live-note">Actualización automática</span></div>${d.urgent.length?`<div class="table-wrap"><table><thead><tr><th>Folio</th><th>Activo</th><th>Prioridad</th><th></th></tr></thead><tbody>${d.urgent.map(o=>`<tr><td class="folio">${esc(o.folio)}</td><td>${esc(o.asset||'Sin activo')}</td><td class="${o.priority==='Paro de máquina'?'priority-critical':''}">${esc(o.priority)}</td><td><button class="order-action order-detail" data-id="${o.id}">Atender</button></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">No hay órdenes pendientes.</div>'}</div>
      <div class="card"><h3>Trabajo por clasificación</h3><div class="bars">${d.byClassification.map(x=>`<div class="bar-row"><span>${esc(x.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${x.value/Math.max(1,...d.byClassification.map(y=>y.value))*100}%"></div></div><b>${x.value}</b></div>`).join('')}</div></div>
    </section>
    <section class="card table-card" style="margin-top:20px"><div class="table-head"><h3>Actividad reciente</h3><button class="btn btn-secondary" onclick="navigate('orders')">Ver todas</button></div>${ordersTable(d.recent)}</section>`;
  $('#dashboard-period').onsubmit=event=>{event.preventDefault();state.dashboardFrom=$('#dashboard-from').value;state.dashboardTo=$('#dashboard-to').value;renderDashboard()};
  $('#dashboard-reset').onclick=()=>{state.dashboardFrom='';state.dashboardTo='';renderDashboard()};
  document.querySelectorAll('.alert-handle').forEach(button=>button.onclick=async()=>{const alert=alerts.find(x=>x.id===Number(button.dataset.id));const note=prompt(`Registra la atención para: ${alert.title}`,alert.handling_note||'');if(note===null)return;button.disabled=true;try{await api('/api/alerts',{method:'POST',body:JSON.stringify({id:alert.id,note})});toast('Atención de alerta registrada');await renderDashboard()}catch(error){toast(error.message)}finally{button.disabled=false}});
}
function metric(label,value,icon,note){return `<article class="metric"><div class="metric-top"><span>${label}</span><span class="metric-icon">${icon}</span></div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></article>`}
function ordersTable(rows){return rows.length?`<div class="table-wrap"><table><thead><tr><th>Folio</th><th>Activo</th><th>Fecha</th><th>Prioridad</th><th>Estado</th><th></th></tr></thead><tbody>${rows.map(o=>`<tr><td class="folio">${esc(o.folio)}</td><td>${esc(o.asset||o.asset_name||'Sin activo')}</td><td>${fmtDate(o.requested_at)}</td><td class="${o.priority==='Paro de máquina'?'priority-critical':''}">${esc(o.priority)}</td><td>${badge(o.status)}</td><td><button class="order-action order-detail" data-id="${o.id}">${state.user?.role==='Solicitante'?'Consultar':o.status==='Pendiente de validación'&&['Administrador','Jefatura','Jefe de mantenimiento'].includes(state.user?.role)?'Revisar y validar':'Ver / atender'}</button></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty">${state.user?.role==='Solicitante'?'Todavía no has levantado ningún reporte.':'Todavía no hay órdenes registradas.'}</div>`}

async function renderOrders(){
  if(state.user.role==='Solicitante'){
    const rows=await api('/api/orders');
    $('#content').innerHTML=`<div class="section-head"><div><h2>Mis reportes</h2><p>Seguimiento de las ${rows.length} solicitudes que has realizado</p></div><button class="btn btn-primary" id="new-order">+ Levantar reporte</button></div><section class="card" style="margin-bottom:18px"><div class="asset-title"><span class="metric-icon">＋</span><div><h3 style="margin:0 0 5px">¿Encontraste una falla?</h3><span class="subtle">Mantenimiento recibirá el reporte y aquí podrás consultar su avance.</span></div></div></section><section class="card table-card"><div class="table-head"><h3>Historial de mis solicitudes</h3><span class="live-note">Estados actualizados automáticamente</span></div>${ordersTable(rows)}</section>`;
    $('#new-order').onclick=openOrder; return;
  }
  const rows=await api('/api/orders');let status='Todas';let query='';
  $('#content').innerHTML=`<div class="section-head"><div><h2>Bandeja de órdenes</h2><p>${rows.filter(x=>x.status==='Abierta').length} reportes nuevos · ${rows.filter(x=>x.status==='En proceso').length} en proceso · ${rows.filter(x=>x.status==='Pendiente de validación').length} por validar</p></div><div class="toolbar"><input class="search" id="order-search" placeholder="Buscar folio, activo o falla"><a class="btn btn-secondary" id="order-export" href="/api/orders/export.csv">Exportar CSV</a><a class="btn btn-secondary" id="order-export-xlsx" href="/api/orders/export.xlsx">Exportar XLSX</a><button class="btn btn-primary" id="new-order">+ Nueva orden</button></div></div><div class="filter-row">${['Todas','Abierta','Programada','En proceso','Pausada','Espera de material','Pendiente de validación','Completada','Cancelada'].map((x,i)=>`<button class="filter-chip ${i===0?'active':''}" data-status="${x}">${x}</button>`).join('')}</div><section class="card table-card" id="order-table"></section>`;
  const paint=()=>{const filters=new URLSearchParams();if(status!=='Todas')filters.set('status',status);if(query)filters.set('q',query);const suffix=filters.size?'?'+filters.toString():'';$('#order-export').href='/api/orders/export.csv'+suffix;$('#order-export-xlsx').href='/api/orders/export.xlsx'+suffix;$('#order-table').innerHTML=ordersTable(rows.filter(o=>(status==='Todas'||o.status===status)&&`${o.folio} ${o.asset_name} ${o.asset_code||''} ${o.reported_failure} ${o.requester_name}`.toLowerCase().includes(query)))};paint();
  $('#new-order').onclick=()=>openOrder();$('#order-search').oninput=e=>{query=e.target.value.toLowerCase();paint()};document.querySelectorAll('.filter-chip').forEach(button=>button.onclick=()=>{status=button.dataset.status;document.querySelectorAll('.filter-chip').forEach(x=>x.classList.toggle('active',x===button));paint()});
}
  async function renderAssets(){const rows=await api('/api/assets');$('#content').innerHTML=`<div class="section-head"><div><h2>Base de datos de máquinas y equipos</h2><p>Ficha técnica, identidad y estado operativo por activo</p></div><div class="toolbar"><input class="search" id="asset-search" placeholder="Buscar máquina, código, alias o área"><a class="btn btn-secondary" id="asset-export" href="/api/assets/export.xlsx">Exportar XLSX</a><button class="btn btn-primary" id="new-asset">+ Nuevo activo</button></div></div><section class="card table-card" id="asset-table"></section>`;const paint=q=>{$('#asset-table').innerHTML=`<div class="table-wrap"><table><thead><tr><th>Activo / códigos</th><th>Tipo</th><th>Marca</th><th>Área</th><th>Estado operativo</th><th>Criticidad</th><th></th></tr></thead><tbody>${rows.filter(a=>`${a.name} ${a.code} ${a.original_code||''} ${a.alias_codes||''} ${a.area} ${a.brand}`.toLowerCase().includes(q)).map(a=>`<tr><td><div class="asset-title"><span class="asset-symbol">◇</span><div><b>${esc(a.name)}</b><div class="subtle">${esc(a.code)}${a.original_code?` · Origen: ${esc(a.original_code)}`:''}</div></div></div></td><td>${esc(a.asset_type||a.category)}</td><td>${esc(a.brand||'—')}</td><td>${esc(a.area)}</td><td>${badge(a.operational_status||a.status)}${a.operational_status_cause?`<div class="subtle">${esc(a.operational_status_cause)}</div>`:''}</td><td>${a.critical?'Crítico':'Normal'}</td><td><button class="order-action asset-detail" data-id="${a.id}">Ver expediente</button></td></tr>`).join('')}</tbody></table></div>`};paint('');$('#asset-search').oninput=e=>{const q=e.target.value.toLowerCase();paint(q);$('#asset-export').href='/api/assets/export.xlsx'+(q?'?q='+encodeURIComponent(q):'')};$('#new-asset').onclick=openAsset;}
async function renderPreventives(){const rows=await api('/api/preventives');$('#content').innerHTML=`<div class="section-head"><div><h2>Programa preventivo</h2><p>Plantillas versionadas y generación controlada de OT</p></div><div class="toolbar"><a class="btn btn-secondary" href="/api/preventives/export.xlsx">Exportar XLSX</a><button class="btn btn-primary" id="new-preventive">+ Programar</button></div></div><section class="card table-card"><div class="table-wrap"><table><thead><tr><th>Próxima fecha</th><th>Activo</th><th>Actividad / plantilla</th><th>Frecuencia</th><th>Responsable</th><th>Estado</th><th>Versión</th><th>Orden</th></tr></thead><tbody>${rows.map(p=>`<tr><td><b>${fmtDate(p.next_date)}</b></td><td>${esc(p.asset_name)}<div class="subtle">${esc(p.asset_code)}</div></td><td><b>${esc(p.title)}</b><div class="subtle">${esc(p.template_code||'Sin código')} · ${esc(p.applies_when||'Configuración pendiente')}</div></td><td>${esc(p.frequency)}</td><td>${esc(p.responsible_name||'Sin asignar')}</td><td>${badge(p.status)}</td><td><button class="order-action preventive-history" data-id="${p.id}" aria-label="Ver historial de ${esc(p.title)}">Historial · v${p.version||1}</button><button class="order-action preventive-tasks" data-id="${p.id}">Tareas y fechas</button></td><td>${p.work_order_id?`<button class="order-action order-detail" data-id="${p.work_order_id}">Ver orden</button>`:`<button class="order-action edit-preventive" data-id="${p.id}">Editar</button> <button class="order-action generate-order" data-id="${p.id}">Generar OT</button>`}</td></tr>`).join('')}</tbody></table></div></section>`;$('#new-preventive').onclick=()=>openPreventive();document.querySelectorAll('.preventive-tasks').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await openPreventiveTasks(Number(button.dataset.id))}catch(error){toast(error.message)}finally{button.disabled=false}});document.querySelectorAll('.preventive-history').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await openPreventiveHistory(Number(button.dataset.id))}catch(error){toast(error.message)}finally{button.disabled=false}});document.querySelectorAll('.edit-preventive').forEach(button=>button.onclick=()=>openPreventive(rows.find(row=>row.id===Number(button.dataset.id))));document.querySelectorAll('.generate-order').forEach(button=>button.onclick=async()=>{button.disabled=true;try{const result=await api(`/api/preventives/${button.dataset.id}/order`,{method:'POST'});toast(`Orden ${result.folio||''} generada`);render()}catch(error){toast(error.message)}finally{button.disabled=false}});}

async function openTaskChecklist(planId,task){
  const plan=(await api('/api/preventives')).find(row=>row.id===planId);const canEdit=!plan.work_order_id&&(['Administrador','Jefe de mantenimiento'].includes(state.user.role)||state.user.actions?.includes('preventives.edit'));let items=await api(`/api/preventives/${planId}/tasks/${task.id}/checklist`);
  const wrap=readModal('Checklist · '+esc(task.title),`<p class="subtle">Define los puntos que deberán validarse en cada ocurrencia.</p><section data-checklist-list></section>${canEdit?`<form data-checklist-form class="form-grid"><div class="field full"><label>Ítem</label><input name="prompt" required maxlength="500" placeholder="Ej. Revisar nivel de aceite"></div><div class="field"><label>Posición</label><input name="position" type="number" min="1" value="${items.length+1}" required></div><label class="check-row"><input name="required" type="checkbox" checked> Obligatorio</label><div class="field full"><button class="btn btn-primary" type="submit">Agregar ítem</button></div><p data-checklist-error role="alert" hidden></p></form>`:'<p class="subtle">Consulta de checklist; no tienes permiso para editar.</p>'}`);
  const list=$('[data-checklist-list]',wrap);const paint=()=>{list.innerHTML=items.length?'<ol>'+items.map(item=>`<li>${esc(item.prompt)} ${item.required?'· obligatorio':'· opcional'}</li>`).join('')+'</ol>':'<p>No hay ítems configurados.</p>'};paint();const form=$('[data-checklist-form]',wrap);if(form)form.onsubmit=async event=>{event.preventDefault();const error=$('[data-checklist-error]',form);try{const data=Object.fromEntries(new FormData(form));const saved=await api(`/api/preventives/${planId}/tasks/${task.id}/checklist`,{method:'POST',body:JSON.stringify({...data,position:Number(data.position),required:data.required==='on'})});items.push(saved);paint();form.reset();form.position.value=items.length+1;toast('Ítem agregado')}catch(failure){error.textContent=failure.message;error.hidden=false}};
}
async function openOccurrenceChecklist(planId,occurrenceId){
  const data=await api(`/api/preventives/${planId}/occurrences/${occurrenceId}/checklist`);const wrap=readModal('Checklist de ocurrencia',`<p class="subtle">Responde todos los ítems obligatorios antes de cerrar la revisión.</p><form data-occurrence-checklist class="form-grid">${data.items.length?data.items.map(item=>`<div class="field full"><label>${esc(item.prompt)}${item.required?' *':''}</label><select name="item-${item.id}" ${item.required?'required':''}><option value="">Seleccionar…</option><option>Sí</option><option>No</option><option>N/A</option></select><input name="note-${item.id}" placeholder="Nota opcional" value="${esc(item.notes||'')}"></div>`).join(''):'<p>No hay ítems configurados para esta tarea.</p>'}<div class="field full"><button class="btn btn-primary" type="submit">Guardar respuestas</button></div><p data-occurrence-checklist-error role="alert" hidden></p></form>`);const form=$('[data-occurrence-checklist]',wrap);form.onsubmit=async event=>{event.preventDefault();const values=new FormData(form),answers=data.items.map(item=>({item_id:item.id,answer:values.get('item-'+item.id),notes:values.get('note-'+item.id)})).filter(answer=>answer.answer);try{await api(`/api/preventives/${planId}/occurrences/${occurrenceId}/checklist`,{method:'POST',body:JSON.stringify({answers})});toast('Checklist guardado');wrap.remove()}catch(error){const target=$('[data-occurrence-checklist-error]',form);target.textContent=error.message;target.hidden=false}};
}
async function openPreventiveTasks(id){
  const plans=await api('/api/preventives');
  let plan=plans.find(p=>p.id===id);
  if(!plan)throw Error('Preventivo no disponible');
  let tasks=await api('/api/preventives/'+id+'/tasks');
  const canEdit=!plan.work_order_id&&(['Administrador','Jefe de mantenimiento'].includes(state.user.role)||state.user.actions?.includes('preventives.edit'));
  const canGenerate=canEdit&&(['Administrador','Jefe de mantenimiento'].includes(state.user.role)||state.user.actions?.includes('orders.create'));
  const today=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);
  const until=new Date(today+'T12:00:00Z');until.setUTCDate(until.getUTCDate()+90);
  const wrap=readModal('Tareas y fechas · '+esc(plan.title),`
    <p>Fechas por tarea: genera una OT para el vencimiento que quieras programar. Las fechas previstas no indican trabajo ejecutado.</p>
    <section data-task-list></section>
    ${canEdit?`<details class="detail-box"><summary>Agregar tarea</summary>
    <form data-task-form class="form-grid">
      <div class="field full"><label for="task-title">Descripción</label><input id="task-title" name="title" required></div>
      <div class="field"><label for="task-interval">Cada</label><input id="task-interval" name="interval_value" type="number" min="1" max="1200" step="1" value="1" required></div>
      <div class="field"><label for="task-unit">Unidad</label><select id="task-unit" name="interval_unit"><option value="months">Meses</option><option value="days">Días</option></select></div>
      <div class="field full"><label for="task-anchor">Primer vencimiento</label><input id="task-anchor" name="anchor_date" type="date" min="1900-01-01" required value="${esc(plan.next_date)}"><span class="subtle">Los meses conservan este día, ajustándolo al último disponible cuando sea necesario.</span></div>
      <div class="field full"><button class="btn btn-primary" type="submit">Guardar tarea</button></div>
      <p data-task-error role="alert" tabindex="-1" hidden></p>
    </form></details>`:`<p class="subtle">${plan.work_order_id?'Plan con OT generada: tareas en consulta histórica.':'Consulta de tareas; no tienes permiso para agregar.'}</p>`}
    <h3>Fechas previstas</h3>
    <form data-calendar-form class="form-grid">
      <div class="field"><label for="calendar-from">Desde</label><input id="calendar-from" name="from" type="date" min="1900-01-01" value="${today}" required></div>
      <div class="field"><label for="calendar-to">Hasta</label><input id="calendar-to" name="to" type="date" min="1900-01-01" value="${until.toISOString().slice(0,10)}" required></div>
      <div class="field full"><span class="subtle">Horizonte máximo: 366 días.</span><button class="btn btn-secondary" type="submit">Consultar fechas</button></div>
    </form>
    <p data-occurrence-error role="alert" tabindex="-1" hidden></p><div data-compliance-result aria-live="polite"></div><div data-calendar-result aria-live="polite"></div>`);
  const list=$('[data-task-list]',wrap),result=$('[data-calendar-result]',wrap),complianceResult=$('[data-compliance-result]',wrap);
  const paint=()=>{list.innerHTML=tasks.length?'<h3>Tareas configuradas</h3><ul>'+tasks.map(t=>'<li style="overflow-wrap:anywhere">'+esc(t.title)+' · cada '+esc(t.interval_value)+' '+(t.interval_unit==='months'?'meses':'días')+' · primer vencimiento '+esc(fmtDate(t.anchor_date))+'</li>').join('')+'</ul>':'<p>Configuración pendiente: este plan no tiene tareas con intervalo definido.</p>'};
  const addChecklistButtons=()=>list.querySelectorAll('li').forEach((li,index)=>{if(li.querySelector('[data-task-checklist]'))return;const button=document.createElement('button');button.type='button';button.className='order-action';button.dataset.taskChecklist=tasks[index].id;button.textContent='Checklist';button.onclick=()=>openTaskChecklist(id,tasks[index]);li.append(' ',button)});
  const calendar=$('[data-calendar-form]',wrap);
  const upcomingButton=document.createElement('button');upcomingButton.type='button';upcomingButton.className='btn btn-secondary';upcomingButton.textContent='Ver próximos vencimientos';calendar.before(upcomingButton);upcomingButton.onclick=async()=>{upcomingButton.disabled=true;try{const from=today,to=until.toISOString().slice(0,10),data=await api(`/api/preventives/${id}/upcoming?from=${from}&to=${to}`);result.innerHTML=data.occurrences.length?'<h3>Próximos vencimientos</h3><ul>'+data.occurrences.map(item=>'<li>'+esc(fmtDate(item.base_date))+' · '+esc(tasks.find(task=>task.id===item.task_id)?.title||'Tarea #'+item.task_id)+' · '+(item.persisted?'OT ya generada':'Sin OT')+'</li>').join('')+'</ul>':'<p>No hay vencimientos en los próximos 30 días.</p>'}catch(error){result.textContent=error.message}finally{upcomingButton.disabled=false}};
  async function loadCalendar(){
    const button=$('button',calendar);button.disabled=true;result.textContent='Consultando fechas…';
    try{
      const query=new URLSearchParams(new FormData(calendar));
      const todayForCompliance=new Date().toISOString().slice(0,10);
      const [data,saved,compliance]=await Promise.all([api('/api/preventives/'+id+'/calendar?'+query),api('/api/preventives/'+id+'/occurrences'),api('/api/preventives/'+id+'/compliance?'+query+'&as_of='+todayForCompliance)]);
      const byKey=new Map(saved.map(o=>[o.task_id+':'+o.occurrence_index,o]));
      queueMicrotask(()=>{if(!compliance.eligible)return;const detail=document.createElement('details');detail.innerHTML='<summary>Ver detalle por tarea</summary><div class="table-wrap"><table><thead><tr><th>Tarea</th><th>Fecha base</th><th>Estado</th><th>Ejecución</th></tr></thead><tbody>'+compliance.occurrences.map(row=>'<tr><td>'+esc(tasks.find(task=>task.id===row.task_id)?.title||'Tarea #'+row.task_id)+'</td><td>'+esc(fmtDate(row.base_date))+'</td><td>'+esc(row.status)+'<div class="subtle">'+esc(row.reason)+'</div></td><td>'+esc(row.executed_date?fmtDate(row.executed_date):'Pendiente')+'</td></tr>').join('')+'</tbody></table></div>';complianceResult.append(detail)});
      const groups=[...data.occurrences.reduce((map,item)=>{const key=item.base_date,items=map.get(key)||[];if(!byKey.has(item.task_id+':'+item.occurrence_index))items.push(item);map.set(key,items);return map},new Map()).entries()].filter(([,items])=>items.length>1);
      complianceResult.innerHTML=compliance.eligible?'<div class="detail-box"><b>Cumplimiento del período</b><div>'+Object.entries(compliance.counts).map(([key,value])=>'<span style="margin-right:12px">'+esc(key)+': '+esc(value)+'</span>').join('')+'</div><small>'+(compliance.compliance_percent===null?'No calculable':esc(compliance.compliance_percent)+'% en fecha base')+'</small></div>':'<p class="subtle">Cumplimiento pendiente: no hay tareas programadas en este período.</p>';
      result.innerHTML=data.configuration_pending?'<p>Configuración pendiente: agrega tareas para calcular fechas.</p>':data.occurrences.length?'<ul>'+data.occurrences.map(o=>{
        const existing=byKey.get(o.task_id+':'+o.occurrence_index);
        const execution=existing?.execution?.state&&existing.execution.state!=='Sin ejecución registrada'?'<span> · Ejecución: '+esc(existing.execution.state)+'</span>':'';
        const action=existing?'<span> · '+esc(existing.order_status)+'</span>'+execution+' <button type="button" class="order-action" data-occurrence-order="'+existing.work_order_id+'">Abrir '+esc(existing.folio)+'</button>':canGenerate?'<button type="button" class="btn btn-secondary" data-generate-task="'+o.task_id+'" data-occurrence-index="'+o.occurrence_index+'">Generar OT</button>':'<span> · Sin OT'+(plan.work_order_id?'; plan con OT anterior: requiere conciliación':'')+'</span>';
        return '<li style="overflow-wrap:anywhere;margin-bottom:12px">'+esc(fmtDate(o.base_date))+' · '+esc(tasks.find(t=>t.id===o.task_id)?.title||'Tarea #'+o.task_id)+' '+action+'</li>';
      }).join('')+'</ul>':'<p>No hay fechas previstas en el período seleccionado.</p>';
      result.querySelectorAll('[data-occurrence-order]').forEach(button=>button.onclick=async()=>{
        button.disabled=true;
        try{await openOrderDetail(Number(button.dataset.occurrenceOrder));wrap.remove();}
        catch(error){toast(error.message);button.disabled=false}
      });
      result.querySelectorAll('li').forEach((li,index)=>{const occurrence=data.occurrences[index],existing=occurrence&&byKey.get(occurrence.task_id+':'+occurrence.occurrence_index);if(existing&&!li.querySelector('[data-occurrence-checklist]')){const button=document.createElement('button');button.type='button';button.className='order-action';button.dataset.occurrenceChecklist=existing.id;button.textContent='Checklist';button.onclick=()=>openOccurrenceChecklist(id,existing.id);li.append(' ',button)}});
      result.querySelectorAll('li').forEach((li,index)=>{const occurrence=data.occurrences[index],existing=occurrence&&byKey.get(occurrence.task_id+':'+occurrence.occurrence_index);if(existing){const button=document.createElement('button');button.type='button';button.className='order-action';button.textContent='Reprogramar';button.onclick=async()=>{const scheduled=window.prompt('Nueva fecha (YYYY-MM-DD)',existing.scheduled_at||occurrence.base_date);const reason=window.prompt('Motivo de reprogramación');if(!scheduled||!reason)return;try{const order=await api('/api/orders/'+existing.work_order_id);await api(`/api/preventives/${id}/occurrences/${existing.id}/reschedule`,{method:'POST',body:JSON.stringify({scheduled_at:scheduled,reason,version:order.version})});toast('Ocurrencia reprogramada');await loadCalendar()}catch(error){toast(error.message)}};li.append(' ',button)}});
      result.querySelectorAll('[data-generate-task]').forEach(button=>button.onclick=async()=>{
        if(button.disabled)return;
        button.disabled=true;button.textContent='Generando…';
        const error=$('[data-occurrence-error]',wrap);error.hidden=true;
        try{
          const generated=await api('/api/preventives/'+id+'/occurrences',{method:'POST',body:JSON.stringify({task_id:Number(button.dataset.generateTask),occurrence_index:Number(button.dataset.occurrenceIndex),version:plan.version})});
          await loadCalendar();toast(generated.replayed?'La ocurrencia ya tenía una OT':'OT '+generated.folio+' generada');render();
        }catch(failure){error.textContent=failure.message;error.hidden=false;error.focus();button.disabled=false;button.textContent='Generar OT'}
      });
    }catch(error){result.textContent=error.message}finally{button.disabled=false}
  }
  calendar.onsubmit=event=>{event.preventDefault();loadCalendar()};
  const form=$('[data-task-form]',wrap);
  if(form)form.onsubmit=async event=>{
    event.preventDefault();const button=$('button',form),error=$('[data-task-error]',form);if(button.disabled)return;
    button.disabled=true;error.hidden=true;
    try{
      const data=Object.fromEntries(new FormData(form));
      const saved=await api('/api/preventives/'+id+'/tasks',{method:'POST',body:JSON.stringify({...data,interval_value:Number(data.interval_value),version:plan.version})});
      plan.version=saved.version;
      tasks.push({id:saved.id,...data,interval_value:Number(data.interval_value)});
      form.reset();paint();addChecklistButtons();await loadCalendar();toast('Tarea guardada');render();
    }catch(failure){error.textContent=failure.message;error.hidden=false;error.focus()}finally{button.disabled=false}
  };
  paint();addChecklistButtons();await loadCalendar();
}

async function renderCatalogs(){
  const entries=await api('/api/catalog-entries');
  const labels={priority:'Prioridad',classification:'Clasificación',specialty:'Especialidad',area:'Área',line:'Línea',shift:'Turno'};
  $('#content').innerHTML=`<div class="section-head"><div><h2>Catálogos de captura</h2><p>Desactiva valores sin borrar registros históricos.</p></div><button class="btn btn-primary" id="new-catalog-entry">+ Nuevo valor</button></div><section class="card table-card"><div class="table-wrap"><table><thead><tr><th>Catálogo</th><th>Valor</th><th>Estado</th><th>Acción</th></tr></thead><tbody>${entries.map(entry=>`<tr><td>${esc(labels[entry.kind]||entry.kind)}</td><td>${esc(entry.value)}</td><td>${entry.active?'Activo':'Inactivo'}</td><td><button class="order-action toggle-catalog" data-id="${entry.id}" data-active="${entry.active}" aria-label="${entry.active?'Desactivar':'Activar'} ${esc(entry.value)}">${entry.active?'Desactivar':'Activar'}</button></td></tr>`).join('')}</tbody></table></div></section>`;
  $('#new-catalog-entry').onclick=()=>modal('Nuevo valor de catálogo',`<div class="field"><label>Catálogo</label><select name="kind" required>${Object.entries(labels).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></div><div class="field"><label>Valor</label><input name="value" maxlength="120" required></div><div class="field"><label>Orden</label><input name="sort_order" type="number" min="0" value="0" required></div>`,async data=>{await api('/api/catalog-entries',{method:'POST',body:JSON.stringify(data)});state.catalogs=null});
  document.querySelectorAll('.toggle-catalog').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await api(`/api/catalog-entries/${button.dataset.id}`,{method:'PATCH',body:JSON.stringify({active:button.dataset.active!=='true'})});state.catalogs=null;await renderCatalogs()}catch(error){toast(error.message);button.disabled=false}});
}

async function renderInventory(){
  const rows=await api('/api/inventory');
  const low=rows.filter(x=>x.low_stock).length;
  const categories=[...new Set(rows.map(row=>row.category).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'es'));
  $('#content').innerHTML=`<div class="section-head"><div><h2>Inventario de refacciones</h2><p>${rows.length} insumos · ${low} en mínimo o por debajo</p></div><div class="toolbar" style="flex-wrap:wrap"><a class="btn btn-secondary" href="/api/inventory/template.csv" title="Descargar plantilla CSV/Excel para llenar">Plantilla CSV</a><a class="btn btn-secondary inventory-export" data-format="csv" href="/api/inventory/export.csv">Exportar CSV</a><a class="btn btn-secondary inventory-export" data-format="xlsx" href="/api/inventory/export.xlsx">Exportar XLSX</a><button class="btn btn-secondary" id="import-inventory-btn" title="Subir archivo CSV con vista previa">Importar CSV</button><input type="file" id="inventory-file-input" accept=".csv,.txt" style="display:none"><button class="btn btn-primary" id="new-inventory">+ Nuevo insumo</button><button class="btn btn-secondary" id="new-inventory-grid">Captura por celdas</button></div></div><section class="card" style="margin-bottom:16px"><div class="toolbar" style="flex-wrap:wrap"><label>Buscar<input class="search" id="inventory-search" placeholder="Código, descripción o ubicación"></label><label>Categoría<select id="inventory-category"><option value="">Todas</option>${categories.map(category=>`<option value="${esc(category)}">${esc(category)}</option>`).join('')}</select></label><label>Existencia<select id="inventory-stock"><option value="">Todas</option><option value="low">Reabastecer</option><option value="available">Sobre mínimo</option></select></label><button class="btn btn-secondary" id="inventory-clear">Limpiar filtros</button><span class="live-note" id="inventory-count"></span></div></section><section class="card table-card"><div class="table-head"><h3>Existencias actuales</h3><span class="live-note">Stock actualizado al registrar movimientos</span></div><div class="table-wrap"><table><thead><tr><th>Código</th><th>Insumo</th><th>Categoría</th><th>Existencia</th><th>Mín / Máx</th><th>Costo unitario</th><th>Estado</th><th></th></tr></thead><tbody id="inventory-rows"></tbody></table></div></section>`;
  const paint=()=>{
    const params=new URLSearchParams();
    const q=$('#inventory-search').value.trim(),category=$('#inventory-category').value,stock=$('#inventory-stock').value;
    if(q)params.set('q',q);if(category)params.set('category',category);if(stock)params.set('stock',stock);
    const suffix=params.size?'?'+params.toString():'';
    $('.inventory-export[data-format="csv"]').href='/api/inventory/export.csv'+suffix;
    $('.inventory-export[data-format="xlsx"]').href='/api/inventory/export.xlsx'+suffix;
    const filtered=rows.filter(item=>(!q||`${item.code} ${item.name} ${item.category} ${item.location}`.toLocaleLowerCase('es').includes(q.toLocaleLowerCase('es')))&&(!category||item.category===category)&&(!stock||(stock==='low'?item.low_stock:!item.low_stock)));
    $('#inventory-count').textContent=`Mostrando ${filtered.length} de ${rows.length}`;
    $('#inventory-rows').innerHTML=filtered.map(i=>`<tr><td class="folio">${esc(i.code)}</td><td><b>${esc(i.name)}</b><div class="subtle">${esc(i.location||'Sin ubicación')}</div></td><td>${esc(i.category)}</td><td><b>${Number(i.stock).toFixed(2)}</b> ${esc(i.unit)}</td><td>${Number(i.min_stock).toFixed(2)} / ${Number(i.max_stock).toFixed(2)}</td><td>${money(i.unit_cost)}</td><td>${i.low_stock?'<span class="badge overdue">Reabastecer</span>':'<span class="badge available">Suficiente'}</span></td><td><button class="order-action inventory-movement" data-id="${i.id}">Movimiento</button><button class="order-action inventory-return" data-id="${i.id}">Devolución</button><button class="order-action inventory-history" data-id="${i.id}">Historial</button></td></tr>`).join('')||'<tr><td colspan="8" class="empty">No hay insumos para estos filtros.</td></tr>';
    document.querySelectorAll('.inventory-movement').forEach(button=>button.onclick=()=>openInventoryMovement(rows.find(x=>x.id===Number(button.dataset.id))));
    document.querySelectorAll('.inventory-return').forEach(button=>button.onclick=()=>openInventoryMovement(rows.find(x=>x.id===Number(button.dataset.id)),null,true));
    document.querySelectorAll('.inventory-history').forEach(button=>button.onclick=()=>openInventoryHistory(rows.find(x=>x.id===Number(button.dataset.id))));
  };
  $('#inventory-search').oninput=paint;$('#inventory-category').onchange=paint;$('#inventory-stock').onchange=paint;
  $('#inventory-clear').onclick=()=>{$('#inventory-search').value='';$('#inventory-category').value='';$('#inventory-stock').value='';paint()};paint();
  
  $('#new-inventory').onclick=openInventory;
  $('#new-inventory-grid').onclick=openInventoryGrid;

  const fileInput = $('#inventory-file-input');
  const importBtn = $('#import-inventory-btn');
  if (importBtn && fileInput) {
    importBtn.onclick = () => fileInput.click();
    fileInput.onchange = e => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async event => {
        try {
          const text = event.target.result;
          const preview = await api('/api/inventory/preview-import', {
            method: 'POST',
            body: JSON.stringify({ csvText: text })
          });
          openInventoryPreview(preview);
        } catch(err) {
          toast(err.message || 'Error al procesar el archivo');
        } finally {
          fileInput.value = '';
        }
      };
      reader.readAsText(file, 'UTF-8');
    };
  }
}

async function openInventoryHistory(item){
  try{
    const movements=await api(`/api/inventory/${item.id}/movements`);
    const fmt=value=>value?new Date(value).toLocaleString('es-MX'):'—';
    const wrap=readModal(`Movimientos · ${esc(item.code)}`,`<p><b>${esc(item.name)}</b> · existencia actual ${Number(item.stock).toFixed(4)} ${esc(item.unit)}</p>${movements.length?`<div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Movimiento</th><th>Cantidad</th><th>Costo unitario</th><th>OT</th><th>Registró</th><th>Notas</th></tr></thead><tbody>${movements.map(row=>`<tr><td>${esc(fmt(row.created_at))}</td><td>${esc(row.type)}${row.return_of?` · salida #${row.return_of}`:''}</td><td>${Number(row.quantity).toFixed(4)} ${esc(item.unit)}</td><td>${money(row.unit_cost)}</td><td>${esc(row.folio||'—')}</td><td>${esc(row.user_name||'Sistema')}</td><td>${esc(row.notes||'')}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">Este insumo todavía no tiene movimientos.</div>'}`);
    return wrap;
  }catch(error){toast(error.message)}
}

function openInventoryPreview(preview) {
  // Current stock map passed from server for 'update' rows
  const existingStock = {};
  preview.rows.forEach(r => { if (r.status === 'update') existingStock[r.code] = r.currentStock ?? null; });

  const hasDuplicates = preview.updateCount > 0;

  const stockModeSection = hasDuplicates ? `
    <div class="field full" style="background:var(--surface-2,#f8f9fa);border:1px solid var(--line-color);border-radius:var(--radius-md);padding:14px 16px;margin-bottom:4px">
      <label style="font-weight:600;margin-bottom:10px;display:block"> ${preview.updateCount} insumo(s) ya existen — ¿Qué hacer con el stock?</label>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:normal;padding:10px 16px;border-radius:var(--radius-md);border:2px solid var(--accent);background:var(--accent-soft,rgba(59,130,246,.08))">
          <input type="radio" name="stockMode" value="replace" checked style="accent-color:var(--accent)">
          <span><strong> Reemplazar</strong><br><small style="color:var(--text-2)">El stock del archivo sustituye al actual</small></span>
        </label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:normal;padding:10px 16px;border-radius:var(--radius-md);border:2px solid var(--line-color)">
          <input type="radio" name="stockMode" value="add" style="accent-color:var(--accent)">
          <span><strong> Sumar</strong><br><small style="color:var(--text-2)">El stock del archivo se agrega al actual</small></span>
        </label>
      </div>
    </div>
  ` : '';

  const statusBadge = (status, error) => {
    if (status === 'new') return '<span class="badge available"> Nuevo</span>';
    if (status === 'update') return '<span class="badge process" id="update-badge-lbl"> Reemplazar</span>';
    return `<span class="badge overdue" title="${esc(error||'Error')}"> ${esc(error||'Error')}</span>`;
  };

  const content = `
    <div class="detail-summary" style="margin-bottom:16px">
      <div class="detail-box"><span>Nuevos a registrar</span><strong style="color:var(--green)">${preview.newCount}</strong></div>
      <div class="detail-box"><span>A actualizar</span><strong style="color:var(--yellow)">${preview.updateCount}</strong></div>
      <div class="detail-box"><span>Filas con error</span><strong style="color:var(--red)">${preview.errorCount}</strong></div>
    </div>
    ${stockModeSection}
    <div class="field full">
      <label>Vista previa de los insumos detectados (${preview.validCount} válidos de ${preview.total} filas totales)</label>
      <div class="table-wrap" style="max-height:280px;overflow-y:auto;border:1px solid var(--line-color);border-radius:var(--radius-md);margin-top:6px">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Código</th>
              <th>Descripción</th>
              <th>Categoría</th>
              <th>Stock en archivo</th>
              ${hasDuplicates ? '<th>Stock actual</th><th>Stock resultante</th>' : ''}
              <th>Costo ($)</th>
              <th>Acción</th>
            </tr>
          </thead>
          <tbody id="preview-tbody">
            ${preview.rows.map(r => `
              <tr style="${r.status==='error'?'background:var(--red-soft)':''}" data-code="${esc(r.code||'')}" data-status="${r.status}" data-stock="${r.stock}" data-current="${r.currentStock ?? ''}">
                <td>${r.rowNum}</td>
                <td class="folio">${esc(r.code||'—')}</td>
                <td><b>${esc(r.name||'—')}</b><div class="subtle">${esc(r.location||'Sin ubicación')}</div></td>
                <td>${esc(r.category)}</td>
                <td><b>${r.stock}</b> ${esc(r.unit)}</td>
                ${hasDuplicates ? `<td class="cell-current">${r.status==='update' ? (r.currentStock ?? '—') : '—'}</td><td class="cell-result" style="font-weight:600">${r.status==='update' ? r.stock : (r.status==='new'?r.stock:'—')}</td>` : ''}
                <td>${money(r.unit_cost)}</td>
                <td class="cell-badge">${statusBadge(r.status, r.error)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;

  const wrap = readModal('Vista Previa de Carga Masiva - Inventario', content);

  // Live-update table when mode changes
  if (hasDuplicates) {
    const radios = wrap.querySelectorAll('input[name="stockMode"]');
    const updateTable = () => {
      const mode = wrap.querySelector('input[name="stockMode"]:checked')?.value || 'replace';
      // Update radio label styles
      wrap.querySelectorAll('label:has(input[name="stockMode"])').forEach(lbl => {
        const radio = lbl.querySelector('input');
        lbl.style.border = radio.checked ? '2px solid var(--accent)' : '2px solid var(--line-color)';
        lbl.style.background = radio.checked ? 'var(--accent-soft,rgba(59,130,246,.08))' : '';
      });
      // Update table rows
      wrap.querySelectorAll('#preview-tbody tr[data-status="update"]').forEach(row => {
        const fileStock = Number(row.dataset.stock) || 0;
        const currentStock = row.dataset.current !== '' ? Number(row.dataset.current) : null;
        const resultCell = row.querySelector('.cell-result');
        const badgeCell = row.querySelector('.cell-badge');
        if (resultCell) {
          const result = mode === 'add' && currentStock !== null ? (currentStock + fileStock) : fileStock;
          resultCell.textContent = result.toFixed(2);
        }
        if (badgeCell) {
          badgeCell.innerHTML = mode === 'add'
            ? '<span class="badge process"> Sumar</span>'
            : '<span class="badge process"> Reemplazar</span>';
        }
      });
    };
    radios.forEach(r => r.addEventListener('change', updateTable));
    updateTable();
  }

  if (preview.validCount > 0) {
    const actions = wrap.querySelector('.form-actions');
    const confirmBtn = document.createElement('button');
    confirmBtn.className = 'btn btn-primary';
    confirmBtn.textContent = `Confirmar y Cargar (${preview.validCount} insumos)`;
    confirmBtn.onclick = async () => {
      const stockMode = wrap.querySelector('input[name="stockMode"]:checked')?.value || 'replace';
      confirmBtn.disabled = true;
      try {
        const res = await api('/api/inventory/import', {
          method: 'POST',
          body: JSON.stringify({
            rows: preview.rows.filter(r => r.status !== 'error'),
            stockMode
          })
        });
        wrap.remove();
        const modeLabel = stockMode === 'add' ? 'sumando al stock existente' : 'reemplazando el stock existente';
        toast(`¡Se importaron ${res.importedCount} insumos correctamente (${modeLabel})!`);
        renderInventory();
      } catch(err) {
        toast(err.message || 'Error al importar datos');
      } finally {
        confirmBtn.disabled = false;
      }
    };
    actions.appendChild(confirmBtn);
  }
}
function openInventoryGrid(){
  const columns=[['code','Código',true],['name','Descripción',true],['category','Categoría',false],['unit','Unidad',false],['stock','Existencia',false],['min_stock','Mínimo',false],['max_stock','Máximo',false],['unit_cost','Costo unitario',false],['location','Ubicación',false]];
  let rows=Array.from({length:8},()=>Object.fromEntries(columns.map(([key])=>[key,''])));
  const wrap=readModal('Captura de inventario por celdas',`<p class="subtle">Pega directamente desde Excel empezando por la columna Código. Orden: Código, Descripción, Categoría, Unidad, Existencia, Mínimo, Máximo, Costo unitario, Ubicación. Se admiten tabuladores y renglones.</p><div class="sheet-toolbar"><button type="button" class="btn btn-secondary" data-sheet-add>Agregar filas</button><button type="button" class="btn btn-secondary" data-sheet-clear>Limpiar</button><span data-sheet-status>0 filas listas</span></div><div class="sheet-wrap"><table class="entry-sheet"><thead><tr>${columns.map(([,label])=>`<th>${label}</th>`).join('')}<th></th></tr></thead><tbody data-sheet-body></tbody></table></div><div class="form-error" data-sheet-error role="alert" hidden></div><div class="form-actions"><button type="button" class="btn btn-secondary close-read">Cancelar</button><button type="button" class="btn btn-primary" data-sheet-save>Validar y guardar filas</button></div>`);
  const body=wrap.querySelector('[data-sheet-body]'),status=wrap.querySelector('[data-sheet-status]'),error=wrap.querySelector('[data-sheet-error]');
  const cell=(value,key)=>`<input data-col="${key}" value="${esc(value)}" ${['stock','min_stock','max_stock','unit_cost'].includes(key)?'inputmode="decimal"':''} aria-label="${key}">`;
  const paint=()=>{body.innerHTML=rows.map((row,index)=>`<tr data-sheet-row="${index}">${columns.map(([key])=>`<td>${cell(row[key],key)}</td>`).join('')}<td><button type="button" class="sheet-remove" data-remove-row="${index}" aria-label="Eliminar fila">?</button></td></tr>`).join('');status.textContent=`${rows.filter(row=>Object.values(row).some(value=>String(value).trim())).length} filas con datos`};
  const read=()=>{rows=[...body.querySelectorAll('tr')].map(tr=>Object.fromEntries([...tr.querySelectorAll('[data-col]')].map(input=>[input.dataset.col,input.value])))};
  body.addEventListener('input',()=>{read();status.textContent=`${rows.filter(row=>Object.values(row).some(value=>String(value).trim())).length} filas con datos`});
  body.addEventListener('paste',event=>{const input=event.target.closest('[data-col]');if(!input)return;const text=event.clipboardData?.getData('text/plain')||'';if(!text.includes('\t')&&!text.includes('\n'))return;event.preventDefault();read();const tr=input.closest('tr'),startRow=Number(tr.dataset.sheetRow),startCol=columns.findIndex(([key])=>key===input.dataset.col),matrix=text.replace(/\r/g,'').replace(/\n$/,'').split('\n').map(line=>line.split('\t'));while(rows.length<startRow+matrix.length)rows.push(Object.fromEntries(columns.map(([key])=>[key,''])));matrix.forEach((values,rowIndex)=>values.forEach((value,colIndex)=>{const column=columns[startCol+colIndex];if(column)rows[startRow+rowIndex][column[0]]=value}));paint();const next=body.querySelector(`tr[data-sheet-row="${startRow}"] [data-col="${columns[Math.min(startCol+matrix[0].length,columns.length-1)][0]}"]`);next?.focus()});
  body.addEventListener('click',event=>{const button=event.target.closest('[data-remove-row]');if(!button)return;read();rows.splice(Number(button.dataset.removeRow),1);if(rows.length<1)rows.push(Object.fromEntries(columns.map(([key])=>[key,''])));paint()});
  wrap.querySelector('[data-sheet-add]').onclick=()=>{read();rows.push(...Array.from({length:8},()=>Object.fromEntries(columns.map(([key])=>[key,'']))));paint()};
  wrap.querySelector('[data-sheet-clear]').onclick=()=>{rows=Array.from({length:8},()=>Object.fromEntries(columns.map(([key])=>[key,''])));error.hidden=true;paint()};
  wrap.querySelector('[data-sheet-save]').onclick=async buttonEvent=>{const button=buttonEvent.currentTarget;read();const filled=rows.filter(row=>Object.values(row).some(value=>String(value).trim()));if(!filled.length){error.textContent='Pega o captura al menos una fila.';error.hidden=false;return}button.disabled=true;error.hidden=true;try{const result=await api('/api/inventory/bulk-create',{method:'POST',body:JSON.stringify({rows:filled})});toast(`${result.created} insumos guardados`);wrap.remove();renderInventory()}catch(failure){error.textContent=failure.message;error.hidden=false;button.disabled=false}};
  paint();
}

function inventoryFields(i={}){return `<div class="field"><label>Código</label><input name="code" required value="${esc(i.code||'')}" placeholder="MAT-001"></div><div class="field"><label>Descripción</label><input name="name" required value="${esc(i.name||'')}"></div><div class="field"><label>Categoría</label><input name="category" required value="${esc(i.category||'Refacción')}"></div><div class="field"><label>Unidad</label><select name="unit"><option ${i.unit==='pieza'?'selected':''}>pieza</option><option ${i.unit==='litro'?'selected':''}>litro</option><option ${i.unit==='metro'?'selected':''}>metro</option><option ${i.unit==='kilogramo'?'selected':''}>kilogramo</option><option ${i.unit==='juego'?'selected':''}>juego</option></select></div><div class="field"><label>Existencia inicial</label><input name="stock" type="number" min="0" step="0.01" value="${i.stock||0}"></div><div class="field"><label>Stock mínimo</label><input name="min_stock" type="number" min="0" step="0.01" value="${i.min_stock||0}"></div><div class="field"><label>Stock máximo</label><input name="max_stock" type="number" min="0" step="0.01" value="${i.max_stock||0}"></div><div class="field"><label>Costo unitario</label><input name="unit_cost" type="number" min="0" step="0.01" value="${i.unit_cost||0}"></div><div class="field full"><label>Ubicación</label><input name="location" value="${esc(i.location||'')}" placeholder="Anaquel A-01"></div>`}
function openInventory(){modal('Nuevo insumo',inventoryFields(),d=>api('/api/inventory',{method:'POST',body:JSON.stringify(d)}).then(()=>state.catalogs=null));}
async function openInventoryMovement(item,orderId=null,returnOnly=false){
  const rows=await api('/api/inventory');item=rows.find(x=>x.id===item.id);
  const requestKey=makeRequestKey();
  const movements=returnOnly?await api(`/api/inventory/${item.id}/movements`):[];
  const outgoing=movements.filter(m=>m.type==='Salida');
  const wrap=modal(returnOnly?'Registrar devolución':orderId?'Confirmar salida':'Registrar movimiento',`
    <div class="detail-box full"><strong>${esc(item.code)} · ${esc(item.name)}</strong><small>Disponible: ${item.stock} ${esc(item.unit)}</small></div>
    <div class="field"><label>Tipo</label><select name="type">${(returnOnly?['Devolución']:orderId?['Salida']:['Entrada','Salida','Ajuste']).map(x=>`<option>${x}</option>`).join('')}</select></div>
    <div class="field"><label>Cantidad <span class="subtle">(en Ajuste: saldo final)</span></label><input name="quantity" type="number" min="0" step="0.0001" required></div>
    ${returnOnly?`<div class="field full"><label>Salida de origen</label><select name="return_of" required><option value="">Seleccionar salida…</option>${outgoing.map(m=>`<option value="${m.id}">Salida #${m.id} · ${m.quantity} ${esc(item.unit)} · ${fmtDate(m.created_at.replace(' ','T'))}</option>`).join('')}</select></div>`:''}
    <div class="field cost-field"><label>Costo unitario de entrada</label><input name="unit_cost" type="number" min="0" step="0.0001" value="${item.unit_cost}"><span class="subtle">Las salidas y devoluciones conservan el costo calculado por el servidor.</span></div>
    <div class="field full"><label>Referencia / motivo</label><input name="notes"><span class="subtle">Obligatorio para ajustes de existencia.</span></div>`,
    d=>api(`/api/inventory/${item.id}/movement`,{method:'POST',body:JSON.stringify({...d,version:item.version,request_key:requestKey,work_order_id:orderId})}).then(()=>state.catalogs=null));
  const type=$('[name=type]',wrap);const update=()=>{$('.cost-field',wrap).hidden=type.value!=='Entrada';$('[name=notes]',wrap).required=type.value==='Ajuste';};type.onchange=update;update();
}
async function openOrderMaterial(orderId){
  const rows=await api('/api/inventory');if(!rows.length){toast('Primero registra un insumo en Inventario');return;}
  const wrap=modal('Seleccionar material',`<div class="field full"><label>Insumo de almacén</label><select name="item_id" required><option value="">Seleccionar…</option>${rows.map(i=>`<option value="${i.id}">${esc(i.code)} · ${esc(i.name)} · ${i.stock} ${esc(i.unit)}</option>`).join('')}</select></div>`,async d=>{setTimeout(()=>openInventoryMovement(rows.find(x=>x.id===Number(d.item_id)),orderId),0);});
  wrap.querySelector('button:not([type])').textContent='Continuar';
}
const moduleLabels={dashboard:'Panel general',orders:'Órdenes',assets:'Activos',inventory:'Inventario',preventives:'Preventivos',users:'Usuarios',audit:'Auditoría'};
const actionLabels={'orders.create':'Crear solicitudes','orders.read':'Consultar OT','orders.edit':'Editar OT','orders.assign':'Asignar técnicos','orders.transition':'Cambiar estados','orders.validate':'Validar cierres','orders.time':'Registrar tiempos','assets.read':'Consultar activos','assets.edit':'Editar activos','preventives.read':'Consultar preventivos','preventives.edit':'Editar preventivos','inventory.read':'Consultar inventario','inventory.move':'Registrar movimientos','inventory.adjust':'Ajustar inventario','users.manage':'Administrar usuarios','audit.read':'Consultar auditoría'};
async function renderUsers(){
  const rows=await api('/api/users');
  $('#content').innerHTML=`<div class="section-head"><div><h2>Usuarios del sistema</h2><p>Los accesos se asignan automáticamente según el rol</p></div><button class="btn btn-primary" id="new-user">+ Crear usuario</button></div><section class="card table-card"><div class="table-wrap"><table><thead><tr><th>Nombre</th><th>Nómina</th><th>Usuario</th><th>Rol</th><th>Acceso</th><th>Estado</th><th></th></tr></thead><tbody>${rows.map(u=>`<tr><td><b>${esc(u.name)} ${esc(u.last_name||'')}</b></td><td>${esc(u.employee_number)}</td><td class="folio">${esc(u.username||'—')}</td><td><b>${esc(u.role_name)}</b></td><td><div class="permission-list">${u.permissions.map(p=>`<span class="permission-pill">${esc(moduleLabels[p]||p)}</span>`).join('')}</div></td><td>${u.active?badge('Disponible'):'<span class="badge">Inactivo</span>'}</td><td><button class="btn btn-secondary edit-user" data-id="${u.id}">Administrar</button></td></tr>`).join('')}</tbody></table></div></section>`;
  $('#new-user').onclick=openUser;
  document.querySelectorAll('.edit-user').forEach(button=>button.onclick=()=>openUserAdmin(rows.find(u=>u.id===Number(button.dataset.id))));
}

async function catalogs(){return state.catalogs||(state.catalogs=await api('/api/catalogs'))}
function modal(title,fields,onSubmit,onSaved=null){
  const wrap=document.createElement('div');wrap.className='modal-backdrop';
  wrap.innerHTML=`<div class="modal"><div class="modal-head"><h2>${title}</h2><button class="close" type="button">×</button></div><form class="form"><div class="form-grid">${fields}</div><div class="form-error" role="alert" tabindex="-1" hidden></div><div class="form-actions"><button type="button" class="btn btn-secondary cancel">Cancelar</button><button class="btn btn-primary">Guardar</button></div></form></div>`;
  if(/Nueva orden|Levantar reporte/.test(title)){const field=document.createElement('div');field.className='field full';field.innerHTML='<label>Checklist autónomo (si aplica)</label><textarea name="autonomous_checklist" maxlength="2000" placeholder="Describe la revisión autónoma, limpieza, inspección o anomalía encontrada"></textarea>';wrap.querySelector('.form-grid').append(field);const classification=wrap.querySelector('[name="classification"]');const toggle=()=>field.hidden=classification&&classification.value!=='Mantenimiento Autónomo';if(classification){classification.addEventListener('change',toggle);toggle()}}
  document.body.append(wrap);const close=MesaUI.dialog(wrap);
  $('.close',wrap).onclick=close;$('.cancel',wrap).onclick=close;
  $('form',wrap).onsubmit=async e=>{
    e.preventDefault();const form=e.target,submit=form.querySelector('button:not([type="button"])'),error=$('.form-error',wrap);
    if(submit.disabled)return;error.hidden=true;submit.disabled=true;submit.textContent='Guardando…';
    const formData=new FormData(form),data=Object.fromEntries(formData);
    if(form.querySelector('[name="permissions"]'))data.permissions=formData.getAll('permissions');
    if(form.querySelector('[name="work_order_ids"]'))data.work_order_ids=formData.getAll('work_order_ids');
    if(form.querySelector('[name="participant_ids"]'))data.participant_ids=formData.getAll('participant_ids');
    const materialRows=[...form.querySelectorAll('.material-row')];
    if(materialRows.length)data.materials=materialRows.map(row=>({code:$('[data-material="code"]',row).value,description:$('[data-material="description"]',row).value,quantity:$('[data-material="quantity"]',row).value,unit_cost:$('[data-material="unit_cost"]',row).value}));
    try{await onSubmit(data);close();toast('Registro guardado correctamente');if(onSaved)await onSaved();else render();}
    catch(err){error.textContent=err.message;error.hidden=false;error.focus();}
    finally{submit.disabled=false;submit.textContent='Guardar';}
  };return wrap;
}
function readModal(title,content){
  const wrap=document.createElement('div');wrap.className='modal-backdrop';wrap.innerHTML=`<div class="modal"><div class="modal-head"><h2>${title}</h2><button class="close">×</button></div><div class="form">${content}<div class="form-actions"><button class="btn btn-secondary close-read">Cerrar</button></div></div></div>`;
  document.body.append(wrap);const close=MesaUI.dialog(wrap);$('.close',wrap).onclick=close;$('.close-read',wrap).onclick=close;return wrap;
}
const options=(rows,value='id',label='name')=>rows.map(x=>`<option value="${esc(x[value])}">${esc(x[label])}</option>`).join('');
function openUser(){modal('Crear usuario',`<div class="field"><label>Nombre</label><input name="name" required></div><div class="field"><label>Apellido</label><input name="last_name" required></div><div class="field"><label>Número de nómina</label><input name="employee_number" required></div><div class="field"><label>Nombre de usuario</label><input name="username" placeholder="Si se deja vacío, se usará la nómina"></div><div class="field"><label for="user-role">Rol</label><select id="user-role" name="role" aria-describedby="user-role-help"><option value="Operador">Operador</option><option value="Mantenimiento">Personal de mantenimiento</option><option value="Jefe de mantenimiento">Jefe de mantenimiento</option></select><span class="subtle" id="user-role-help">Jefe de mantenimiento tiene acceso completo, igual que el administrador.</span></div><div class="field"><label>Contraseña temporal</label><input name="password" type="password" minlength="8" required></div><div class="field full"><span class="subtle">Operador: solamente levanta reportes. Personal de mantenimiento: administra la operación, excepto usuarios.</span></div>`,d=>api('/api/users',{method:'POST',body:JSON.stringify(d)}).then(()=>state.catalogs=null));}
function openUserAdmin(user){
  const isAdmin=user.role==='Administrador';
  const initialRole=user.role==='Solicitante'?'Operador':user.role==='Técnico'?'Mantenimiento':user.role;
  const wrap=modal(`Administrar a ${esc(user.name)} ${esc(user.last_name||'')}`,`<div class="field"><label>Número de nómina</label><input value="${esc(user.employee_number)}" disabled></div><div class="field"><label>Usuario</label><input value="${esc(user.username||'')}" disabled></div>${isAdmin?'':`<div class="field"><label for="user-role">Rol</label><select id="user-role" name="role" aria-describedby="user-role-help"><option value="Operador" ${user.role==='Solicitante'?'selected':''}>Operador</option><option value="Mantenimiento" ${user.role==='Técnico'?'selected':''}>Personal de mantenimiento</option><option value="Jefe de mantenimiento" ${user.role==='Jefe de mantenimiento'?'selected':''}>Jefe de mantenimiento</option>${user.role==='Jefatura'?'<option value="Jefatura" selected>Jefatura</option>':''}</select><span class="subtle" id="user-role-help">Jefe de mantenimiento tiene acceso completo, igual que el administrador.</span></div>`}<div class="field ${isAdmin?'full':''}"><label>Nueva contraseña</label><input name="password" type="password" minlength="8" placeholder="Dejar vacío para conservar la actual"><span class="subtle">Al cambiarla se cerrarán sus sesiones activas.</span></div>${isAdmin?'<div class="field full"><span class="subtle">El administrador principal siempre tiene acceso completo.</span></div>':`<div class="field full"><label>Permisos por acción</label><input name="actions_text" value="${esc((user.actions||[]).join(', '))}" placeholder="Ejemplo: orders.read, orders.time"><span class="subtle">Separar acciones con comas. Vacío restaura los permisos predeterminados del rol.</span></div><div class="field full"><label>Áreas autorizadas</label><input name="areas_text" value="${esc((user.areas||[]).join(', '))}" placeholder="Ejemplo: Prensas, Embarques"><span class="subtle">Vacío permite todas las áreas.</span></div><div class="field full"><label class="check-option"><input type="checkbox" name="active" value="1" ${user.active?'checked':''}>Usuario activo</label></div>`}`,
    d=>api(`/api/users/${user.id}`,{method:'PATCH',body:JSON.stringify({password:d.password||undefined,role:isAdmin?undefined:d.role,active:isAdmin?true:d.active==='1',actions:isAdmin||d.role==='Jefe de mantenimiento'?undefined:d.role!==initialRole?[]:d.actions_text.split(',').map(x=>x.trim()).filter(Boolean),areas:isAdmin||d.role==='Jefe de mantenimiento'?undefined:d.role!==initialRole?[]:d.areas_text.split(',').map(x=>x.trim()).filter(Boolean)})}));
  if(!isAdmin){
    const role=wrap.querySelector('[name="role"]');
    const updatePermissions=()=>{
      const fullAccess=role.value==='Jefe de mantenimiento';
      ['actions_text','areas_text'].forEach(name=>{const field=wrap.querySelector(`[name="${name}"]`);field.disabled=fullAccess;field.closest('.field').hidden=fullAccess});
    };
    role.addEventListener('change',updatePermissions);updatePermissions();
  }
}
async function openOrder(assetId=null){const requestKey=makeRequestKey();const c=await catalogs();const now=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);const operator=state.user.role==='Solicitante';const wrap=modal(operator?'Levantar reporte':'Nueva orden de trabajo',`
  <div class="field"><label>Fecha de solicitud</label><input name="requested_at" type="datetime-local" value="${now}" required></div>
  ${operator?`<div class="field"><label>Solicitante</label><input value="${esc(state.user.name)} ${esc(state.user.last_name)} · Nómina ${esc(state.user.employee_number)}" disabled><input type="hidden" name="requester_id" value="${state.user.id}"></div>`:`<div class="field"><label>Solicitante</label><select name="requester_id" required><option value="">Seleccionar…</option>${options(c.users)}</select></div>`}
  <div class="field"><label>Prioridad</label><select name="priority" required><option value="">Seleccionar…</option>${c.priorities.map(x=>`<option>${esc(x)}</option>`).join('')}</select></div>
  <div class="field full" data-downtime-confirm><label>¿La máquina está realmente parada?</label><select name="machine_stopped" required><option value="">Confirmar…</option><option value="yes">Sí, registrar paro</option><option value="no">No, solo prioridad crítica</option></select><span class="subtle">Una OT crítica no cambia por sí sola el estado del activo.</span></div>
  <div class="field full" data-downtime-cause><label>Causa del paro</label><input name="downtime_cause" maxlength="500" placeholder="Describe por qué el equipo está detenido"></div>
  <div class="field"><label>Clasificación</label><select name="classification" required><option value="">Seleccionar…</option>${c.classifications.map(x=>`<option>${esc(x)}</option>`).join('')}</select></div>
  <div class="field"><label>Activo</label><select name="asset_id"><option value="">Sin activo asociado</option>${c.assets.map(x=>`<option value="${x.id}" ${x.id===assetId?'selected':''}>${esc(x.name)}</option>`).join('')}</select></div>
  <div class="field"><label>Ubicación de atención</label><input name="location" placeholder="Área, línea o instalación"></div>
  ${operator?'':`<div class="field"><label>Especialidad</label><select name="specialty"><option value="">Por definir</option>${c.specialties.map(x=>`<option>${esc(x)}</option>`).join('')}</select></div>`}
  <div class="field full"><label>Falla o necesidad reportada</label><textarea name="reported_failure" required placeholder="Describe claramente el requerimiento"></textarea></div>
  ${operator?'':`<div class="field"><label>Técnico asignado</label><select name="technician_id"><option value="">Sin asignar</option>${options(c.users.filter(x=>['Técnico','Jefatura','Jefe de mantenimiento'].includes(x.role)))}</select></div>`}`,d=>api('/api/orders',{method:'POST',headers:{'Idempotency-Key':requestKey},body:JSON.stringify(d)}).then(result=>{if(operator)setTimeout(()=>toast(`Reporte ${result.folio} enviado a Mantenimiento`),100)}));
  const priority=$('[name="priority"]',wrap),confirmation=$('[data-downtime-confirm]',wrap),answer=$('[name="machine_stopped"]',wrap),causeField=$('[data-downtime-cause]',wrap),cause=$('[name="downtime_cause"]',wrap);
  const toggle=()=>{const critical=priority.value==='Paro de máquina';confirmation.hidden=!critical;answer.disabled=!critical;const stopped=critical&&answer.value==='yes';causeField.hidden=!stopped;cause.disabled=!stopped;cause.required=stopped};
  priority.addEventListener('change',toggle);answer.addEventListener('change',toggle);toggle();}
function openOrderForAsset(asset){openOrder(asset.id)}
function openTimeEntry(orderId){const now=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);modal('Registrar sesión de trabajo',`<div class="field"><label>Inicio</label><input name="started_at" type="datetime-local" value="${now}" required></div><div class="field"><label>Fin</label><input name="finished_at" type="datetime-local" required></div><div class="field full"><label>Observación</label><input name="pause_reason" placeholder="Pausa, espera o captura manual"></div>`,d=>api(`/api/orders/${orderId}/time-entries`,{method:'POST',body:JSON.stringify(d)}));}
function preventiveExecutionPanel(o){
  const e=o.preventive_execution;
  if(!e)return '';
  const stateLabel=e.state==='Sin ejecución registrada'?'Pendiente de ejecución':e.state;
  const events=e.events||[];
  return '<section class="field full preventive-execution" aria-labelledby="preventive-execution-title"><h3 id="preventive-execution-title">Ejecución preventiva</h3><div class="detail-summary"><div class="detail-box"><span>Estado</span><strong>'+esc(stateLabel)+'</strong></div><div class="detail-box"><span>Fecha base</span><strong>'+esc(fmtDate(e.base_date))+'</strong></div><div class="detail-box"><span>Ejecutada</span><strong>'+esc(e.executed_at?fmtDate(e.executed_at):'Pendiente')+'</strong></div><div class="detail-box"><span>Validada</span><strong>'+esc(e.validated_at?fmtDate(e.validated_at):'Pendiente')+'</strong></div></div><div class="timeline">'+(events.length?events.map(event=>'<div class="timeline-item"><b>'+esc(({terminated:'Terminada',validated:'Validada',returned:'Devuelta a trabajo',cancelled:'Cancelada',reopened:'Reabierta'}[event.event]||event.event))+'</b><small>'+esc(event.recorded_at)+' · Usuario #'+esc(event.user_id)+'</small>'+(event.notes?'<small>'+esc(event.notes)+'</small>':'')+(event.reason?'<small>Motivo: '+esc(event.reason)+'</small>':'')+'</div>').join(''):'<div class="subtle">La ejecución todavía no tiene eventos.</div>')+'</div></section>';
}
async function openOrderDetail(id){
  const [o,c,inventory]=await Promise.all([api(`/api/orders/${id}`),catalogs(),state.user.role==='Solicitante'?Promise.resolve([]):api('/api/inventory').catch(()=>[])]);
  if(state.user.role==='Solicitante'){
    readModal(`${o.folio} · Estado del reporte`,`<div class="detail-summary"><div class="detail-box"><span>Estado actual</span><strong>${badge(o.status)}</strong></div><div class="detail-box"><span>Prioridad</span><strong>${esc(o.priority)}</strong></div><div class="detail-box"><span>Fecha de solicitud</span><strong>${fmtDate(o.requested_at)}</strong></div></div><div class="field"><label>Activo o área</label><div class="detail-box"><strong>${esc(o.asset_name||'Sin activo asociado')}</strong><small>${esc(o.asset_code||'')}</small></div></div><div class="field" style="margin-top:14px"><label>Falla reportada</label><div class="detail-box">${esc(o.reported_failure)}</div></div><div class="field" style="margin-top:14px"><label>Atención de mantenimiento</label><div class="detail-box"><strong>${esc(o.technician_name||'Pendiente de asignación')}</strong><small>${o.actions?esc(o.actions):'Mantenimiento todavía no ha registrado acciones.'}</small></div></div>${o.finished_at?`<div class="field" style="margin-top:14px"><label>Terminación</label><div class="detail-box">${fmtDate(o.finished_at)} · ${o.labor_hours||0} horas hombre</div></div>`:''}`);return;
  }
  const dt=value=>{if(!value)return '';const parsed=new Date(value);return Number.isNaN(parsed.getTime())?String(value).slice(0,16):new Date(parsed.getTime()-parsed.getTimezoneOffset()*60000).toISOString().slice(0,16)};
  const selected=(value,current)=>value==current?'selected':'';
  const transitions={Abierta:['Programada','En proceso','Cancelada'],Programada:['En proceso','Abierta','Cancelada'],'En proceso':['Pausada','Espera de material','Pendiente de validación','Cancelada'],Pausada:['En proceso','Cancelada'],'Espera de material':['En proceso','Cancelada'],'Pendiente de validación':['En proceso']};
  const availableTransitions=(transitions[o.status]||[]).filter(status=>status!=='Cancelada'||['Administrador','Jefatura','Jefe de mantenimiento'].includes(state.user.role));
  const active=!['Completada','Cancelada','Pendiente de validación'].includes(o.status);
  const canTrackTime=o.status==='En proceso';
  const assignedPeople=[...new Map([o.technician_id,...o.participants.map(person=>person.id)].filter(Boolean).map(personId=>[personId,c.users.find(person=>person.id===personId)])).values()].filter(Boolean);
  const timeUserSelect=state.user.role==='Técnico'?'<p class="subtle">Tiempo de tu propia sesión</p>':`<label>Técnico<select class="time-user-id">${assignedPeople.map(person=>`<option value="${person.id}">${esc(person.name)}</option>`).join('')}</select></label>`;
  const openOwnEntry=o.time_entries.find(entry=>entry.user_id===state.user.id&&!entry.finished_at);
  const now=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);
  let currentVersion=o.version;
  const saveOrderChanges=async raw=>{
    const data={...raw};delete data.status;delete data.date_change_reason;
    for(const key of ['requested_at','scheduled_at','started_at','finished_at'])if(data[key]===dt(o[key]))delete data[key];
    const technicianPicker=wrap.querySelector('.technician-picker');
    if(technicianPicker){
      const ids=[...technicianPicker.querySelectorAll('.technician-option[aria-pressed="true"]')].map(button=>Number(button.dataset.technicianId));
      const primary=ids.includes(o.technician_id)?o.technician_id:(ids[0]||null);
      data.technician_id=primary;data.participant_ids=ids.filter(id=>id!==primary);
    }
    const saved=await api(`/api/orders/${id}`,{method:'PATCH',body:JSON.stringify({...data,version:currentVersion})});
    currentVersion=saved.version;
    return saved;
  };
  const wrap=modal(`${o.folio} · Atención de orden`,`
    <div class="field full order-overview"><div class="detail-summary"><div class="detail-box"><span>Solicitante</span><strong>${esc(o.requester_name)}</strong><small>Nómina ${esc(o.requester_number)}</small></div><div class="detail-box"><span>Solicitud</span><strong>${fmtDate(o.requested_at)}</strong><small>${esc(o.priority)}</small></div><div class="detail-box"><span>Activo</span><strong>${esc(o.asset_name||'Sin activo')}</strong><small>${esc(o.asset_code||'')}</small></div></div></div>
    <section class="field full order-attention" aria-labelledby="order-attention-title">
      <div class="section-title"><div><span class="section-kicker">Operación</span><h3 id="order-attention-title">Atención de la orden</h3></div><div>${badge(o.status)}</div></div>
      <div class="order-attention-grid">
        <div class="operation-card"><div class="operation-card-head"><span class="operation-step">1</span><div><h4>Cambiar estado</h4><p>Registra el avance actual de la atención.</p></div></div>${availableTransitions.length?`<label>Nuevo estado<select class="order-state-select">${availableTransitions.map(status=>`<option value="${esc(status)}">${esc(status)}</option>`).join('')}</select></label><button type="button" class="btn btn-primary apply-order-state" data-id="${o.id}" data-version="${o.version}">Actualizar estado</button>`:`<p class="operation-empty">No hay cambios disponibles desde este estado.</p>`}</div>
        <div class="operation-card"><div class="operation-card-head"><span class="operation-step">2</span><div><h4>Sesiones de trabajo</h4><p>Inicia o cierra intervalos; la pausa no suma tiempo.</p></div></div>${timeUserSelect}<div class="toolbar"><button type="button" class="btn btn-secondary time-action" data-action="start" ${canTrackTime&&assignedPeople.length?'':'disabled'}>Iniciar</button><button type="button" class="btn btn-secondary time-action" data-action="pause" ${canTrackTime&&assignedPeople.length?'':'disabled'}>Pausar</button><button type="button" class="btn btn-secondary time-action" data-action="finish" ${canTrackTime&&assignedPeople.length?'':'disabled'}>Terminar sesión</button></div><label>Motivo de pausa<input class="time-pause-reason" placeholder="Ej. espera de material"></label><small>${openOwnEntry?'Tu sesión está activa desde '+esc(fmtDate(openOwnEntry.started_at)):'Sin sesión activa propia'}</small><details><summary>Captura manual de tiempo</summary><label>Inicio<input class="inline-time-start" type="datetime-local" value="${now}"></label><label>Fin<input class="inline-time-finish" type="datetime-local"></label><label>Observación<input class="inline-time-note" placeholder="Motivo o referencia"></label><button type="button" class="btn btn-secondary save-inline-time" data-id="${o.id}" ${canTrackTime&&assignedPeople.length?'':'disabled'}>Agregar intervalo</button></details><div class="timeline">${o.time_entries.length?o.time_entries.map(entry=>`<div class="timeline-item"><b>${esc(entry.user_name)} · ${entry.finished_at?'Intervalo cerrado':'En curso'}</b><small>${esc(fmtDate(entry.started_at))} ${entry.finished_at?'→ '+esc(fmtDate(entry.finished_at)):''}</small>${entry.pause_reason?`<small>${esc(entry.pause_reason)}</small>`:''}</div>`).join(''):'<span class="subtle">Todavía no hay tiempo registrado.</span>'}</div></div>
        <div class="operation-card"><div class="operation-card-head"><span class="operation-step">3</span><div><h4>Agregar material</h4><p>Confirma la salida desde almacén.</p></div></div>${inventory.length?`<label>Material<select class="inline-material-item"><option value="">Seleccionar material…</option>${inventory.map(item=>`<option value="${item.id}">${esc(item.code)} · ${esc(item.name)} · ${item.stock} ${esc(item.unit)}</option>`).join('')}</select></label><label>Cantidad<input class="inline-material-quantity" type="number" min="0.0001" step="0.0001" placeholder="0"></label><label>Referencia<input class="inline-material-note" placeholder="Uso o ubicación"></label><button type="button" class="btn btn-secondary save-inline-material" data-id="${o.id}" ${active?'':'disabled'}>Agregar material</button>`:'<p class="operation-empty">No hay materiales disponibles en inventario.</p>'}</div>
      </div>
      <p class="operation-help">Guarda primero cualquier cambio pendiente en los datos de la orden antes de registrar estado, tiempo o material.</p>
    </section>
    <div class="field"><label>Ubicación de atención</label><input name="location" value="${esc(o.location||'')}" placeholder="Área, línea o instalación"></div>
    <div class="field"><label>Fecha de solicitud</label><input name="requested_at" type="datetime-local" value="${dt(o.requested_at)}"><span class="subtle">Modificar requiere permiso y motivo.</span></div>
    <div class="field"><label>Fecha programada</label><input name="scheduled_at" type="datetime-local" value="${dt(o.scheduled_at)}"><span class="subtle">Opcional; se conserva el historial del cambio.</span></div>
    <div class="field"><label>Prioridad</label><select name="priority">${(c.priorities.includes(o.priority)?c.priorities:[o.priority,...c.priorities]).map(x=>`<option ${selected(x,o.priority)}>${esc(x)}</option>`).join('')}</select></div>
     <div class="field"><label>Técnico asignado</label><select name="technician_id"><option value="">Sin asignar</option>${c.users.filter(x=>['Técnico','Jefatura','Jefe de mantenimiento'].includes(x.role)).map(x=>`<option value="${x.id}" ${selected(x.id,o.technician_id)}>${esc(x.name)}</option>`).join('')}</select></div>
     ${['Administrador','Jefatura','Jefe de mantenimiento'].includes(state.user.role)?`<div class="field"><label>Colaboradores</label><select name="participant_ids" multiple size="4">${c.users.filter(x=>(['Técnico','Jefatura','Jefe de mantenimiento'].includes(x.role))&&x.id!==o.technician_id).map(x=>`<option value="${x.id}" ${o.participants.some(person=>person.id===x.id)?'selected':''}>${esc(x.name)}</option>`).join('')}</select><span class="subtle">Ctrl o Cmd para elegir varios.</span></div>`:`<div class="field"><label>Colaboradores</label><div class="detail-box">${o.participants.map(person=>esc(person.name)).join(', ')||'Sin colaboradores'}</div></div>`}
    <div class="field"><label>Especialidad</label><select name="specialty"><option value="">Por definir</option>${(o.specialty&&!c.specialties.includes(o.specialty)?[o.specialty,...c.specialties]:c.specialties).map(x=>`<option ${selected(x,o.specialty)}>${esc(x)}</option>`).join('')}</select></div>
    <div class="field full"><label>Falla reportada</label><textarea name="reported_failure">${esc(o.reported_failure)}</textarea></div>
    <div class="field full"><label>Acciones realizadas / despiece</label><textarea name="actions" placeholder="Diagnóstico, reparación y pruebas realizadas">${esc(o.actions||'')}</textarea></div>
    <div class="field"><label>Fecha y hora de inicio</label><input type="datetime-local" value="${dt(o.started_at)}" disabled></div>
    <div class="field"><label>Fecha y hora de término</label><input type="datetime-local" value="${dt(o.finished_at)}" disabled></div>
    <div class="field"><label>Horas hombre</label><input type="number" value="${o.labor_hours||0}" disabled></div>
    <div class="field full"><label>Materiales utilizados</label><div class="materials-history">${o.materials.length?o.materials.map(m=>`<div class="detail-box"><strong>${esc(m.code||'')} · ${esc(m.description)}</strong><small>Salida: ${m.quantity} · Devuelto: ${m.returned_quantity||0} · Costo neto: ${money(m.total)}</small></div>`).join(''):'<p class="subtle">Sin consumos registrados.</p>'}</div><span class="subtle">Cada salida conserva su costo de origen. Las devoluciones se registran en Inventario.</span></div>
    <div class="field full"><div class="toolbar"><a class="btn btn-secondary" href="/print.html?id=${o.id}" target="_blank">Vista de impresión del formato</a>${state.user.actions?.includes('orders.edit')&&(state.user.role!=='Técnico'||o.technician_id===state.user.id)?`<button type="button" class="btn btn-primary generate-order-pdf">Crear PDF versionado</button>`:''}<button type="button" class="btn btn-secondary order-pdf-history">Historial de PDF</button></div></div>
    <div class="field full"><details class="detail-box order-history"><summary>Historial de la orden (${o.events.length})</summary><div class="timeline">${o.events.length?o.events.map(e=>`<div class="timeline-item"><b>${esc(e.event)}</b><small>${esc(e.user_name||'Sistema')} · ${fmtDate(e.created_at.replace(' ','T'))}</small>${e.details?`<small>${esc(e.details)}</small>`:''}</div>`).join(''):'<div class="subtle">El historial comenzará con la próxima actualización.</div>'}</div></details></div>`,
    d=>saveOrderChanges(d),async()=>{await render();await openOrderDetail(id)});
  const overview=wrap.querySelector('.order-overview');
  const requestPanel=document.createElement('section');
  requestPanel.className='field full request-origin';
  requestPanel.setAttribute('aria-labelledby','request-origin-title');
  const canEditRequest=active&&['Administrador','Jefatura','Jefe de mantenimiento'].includes(state.user.role)&&state.user.actions?.includes('orders.edit');
  requestPanel.innerHTML=`<div class="request-origin-head"><div><span class="section-kicker">Reporte recibido</span><h3 id="request-origin-title">Información proporcionada al levantar la OT</h3><p>Datos de la solicitud. Se muestran bloqueados para evitar cambios accidentales.</p></div>${canEditRequest?'<button type="button" class="btn btn-secondary edit-request-origin">Habilitar edición</button>':''}</div><div class="request-origin-grid"><div class="field"><label>Solicitante</label><div class="detail-box"><strong>${esc(o.requester_name)}</strong><small>Nómina ${esc(o.requester_number)}</small></div></div><div class="field"><label>Activo</label><div class="detail-box"><strong>${esc(o.asset_name||'Sin activo asociado')}</strong><small>${esc(o.asset_code||'')}</small></div></div><div class="field"><label>Clasificación</label><div class="detail-box"><strong>${esc(o.classification||'Sin clasificación')}</strong></div></div></div>`;
  overview.replaceWith(requestPanel);
  const requestGrid=requestPanel.querySelector('.request-origin-grid');
  for(const name of ['requested_at','priority','location','reported_failure']){
    const field=wrap.querySelector(`[name="${name}"]`)?.closest('.field');
    if(field){requestGrid.append(field);field.querySelectorAll('input,select,textarea').forEach(input=>input.disabled=true)}
  }
  const requestFailure=requestGrid.querySelector('[name="reported_failure"]')?.closest('.field');
  requestFailure?.classList.add('full');
  $('.edit-request-origin',requestPanel)?.addEventListener('click',event=>{
    for(const input of requestGrid.querySelectorAll('[name="priority"],[name="location"],[name="reported_failure"]'))input.disabled=false;
    if(state.user.actions?.includes('orders.edit_dates'))requestGrid.querySelector('[name="requested_at"]').disabled=false;
    event.currentTarget.textContent='Edición habilitada';event.currentTarget.disabled=true;
    requestPanel.classList.add('is-editing');
  });
  wrap.querySelector('.order-attention-grid .operation-card:nth-child(2)')?.remove();
  const materialCard=wrap.querySelector('.order-attention-grid .operation-card:nth-child(2)');
  if(materialCard)materialCard.querySelector('.operation-step').textContent='2';
  const operationHelp=$('.operation-help',wrap);
  if(operationHelp)operationHelp.textContent='Al terminar el trabajo, los cambios pendientes se guardan antes de enviar la OT a validación.';
  const requestedDateHelp=wrap.querySelector('[name="requested_at"]')?.closest('.field')?.querySelector('.subtle');
  if(requestedDateHelp)requestedDateHelp.textContent='La fecha puede cambiarla personal autorizado. El motivo es opcional.';
  const technicianField=wrap.querySelector('[name="technician_id"]')?.closest('.field');
  const collaboratorField=wrap.querySelector('[name="participant_ids"]')?.closest('.field')||[...wrap.querySelectorAll('.form-grid > .field')].find(field=>field.querySelector('label')?.textContent==='Colaboradores');
  const selectedTechnicians=new Set([o.technician_id,...o.participants.map(person=>person.id)].filter(Boolean));
  if(technicianField){
    const field=document.createElement('div');field.className='field full';
    if(['Administrador','Jefatura','Jefe de mantenimiento'].includes(state.user.role)){
      field.innerHTML=`<label id="technician-picker-label-${id}">Técnicos asignados</label><div class="technician-picker"><button type="button" class="technician-picker-trigger" aria-expanded="false" aria-controls="technician-options-${id}" aria-labelledby="technician-picker-label-${id} technician-picker-summary-${id}"><span id="technician-picker-summary-${id}"></span><span aria-hidden="true">▾</span></button><div class="technician-picker-menu" id="technician-options-${id}" hidden>${c.users.filter(person=>['Técnico','Jefatura'].includes(person.role)).map(person=>`<button type="button" class="technician-option" data-technician-id="${person.id}" aria-pressed="${selectedTechnicians.has(person.id)}"><span>${esc(person.name)}</span><span class="technician-option-mark" aria-hidden="true">✓</span></button>`).join('')||'<p class="subtle">No hay técnicos disponibles.</p>'}</div></div><small class="subtle">Abre la lista y selecciona uno o varios técnicos.</small>`;
    }else field.innerHTML=`<label>Técnicos asignados</label><div class="detail-box">${[o.technician_name,...o.participants.map(person=>person.name)].filter(Boolean).map(esc).join(', ')||'Sin asignar'}</div>`;
    technicianField.replaceWith(field);
    const picker=field.querySelector('.technician-picker');
    if(picker){
      const trigger=picker.querySelector('.technician-picker-trigger'),menu=picker.querySelector('.technician-picker-menu'),summary=picker.querySelector('[id^="technician-picker-summary-"]');
      const selected=()=>[...picker.querySelectorAll('.technician-option[aria-pressed="true"]')];
      const updateSummary=()=>{const names=selected().map(button=>button.querySelector('span').textContent);summary.textContent=names.length?names.join(', '):'Sin técnicos asignados';trigger.title=summary.textContent};
      const close=()=>{menu.hidden=true;trigger.setAttribute('aria-expanded','false')};
      trigger.onclick=()=>{menu.hidden=!menu.hidden;trigger.setAttribute('aria-expanded',String(!menu.hidden))};
      picker.querySelectorAll('.technician-option').forEach(button=>button.onclick=()=>{button.setAttribute('aria-pressed',String(button.getAttribute('aria-pressed')!=='true'));updateSummary();picker.dispatchEvent(new Event('change',{bubbles:true}))});
      wrap.addEventListener('click',event=>{if(!picker.contains(event.target))close()});
      picker.addEventListener('keydown',event=>{if(event.key==='Escape'){close();trigger.focus()}});
      if(!active)picker.querySelectorAll('button').forEach(button=>button.disabled=true);
      updateSummary();
    }
  }
  collaboratorField?.remove();
  const workStart=wrap.querySelectorAll('input[type="datetime-local"][disabled]')[0];
  const workFinish=wrap.querySelectorAll('input[type="datetime-local"][disabled]')[1];
  if(workStart){workStart.disabled=false;workStart.name='started_at';workStart.id=`order-work-start-${id}`;const field=workStart.closest('.field');const label=field?.querySelector('label');if(label){label.textContent='Inicio del trabajo';label.htmlFor=workStart.id}}
  if(workFinish){workFinish.disabled=false;workFinish.name='finished_at';workFinish.id=`order-work-finish-${id}`;const field=workFinish.closest('.field');const label=field?.querySelector('label');if(label){label.textContent='Fin del trabajo';label.htmlFor=workFinish.id}}
  const laborInput=wrap.querySelector('input[type="number"][disabled]');
  const laborExplanation=document.createElement('small');laborExplanation.className='subtle';
  laborInput?.closest('.field')?.append(laborExplanation);
  const previewLabor=()=>{
    const picker=wrap.querySelector('.technician-picker');
    const technicians=picker?picker.querySelectorAll('.technician-option[aria-pressed="true"]').length:selectedTechnicians.size;
    const start=workStart?.value?new Date(workStart.value):null,finish=workFinish?.value?new Date(workFinish.value):null;
    const hours=start&&finish&&finish>start?(finish-start)/3600000:0;
    if(laborInput)laborInput.value=(hours*technicians).toFixed(2);
    laborExplanation.textContent=start&&finish&&finish<=start?'El término debe ser posterior al inicio.':`${hours.toFixed(2)} horas × ${technicians} técnico(s) = ${(hours*technicians).toFixed(2)} horas hombre`;
  };
  for(const input of [workStart,workFinish,wrap.querySelector('.technician-picker')])input?.addEventListener('change',previewLabor);
  previewLabor();
  const transitionSelect=$('.order-state-select',wrap),transitionButton=$('.apply-order-state',wrap);
  const transitionButtonLabel=status=>status==='Pendiente de validaci\u00f3n'?'Terminar trabajo · enviar a validaci\u00f3n':status==='Cancelada'?'Cancelar OT':status?`Cambiar a ${status}`:'Selecciona un siguiente paso';
  if(transitionSelect&&transitionButton){
    if(o.status==='En proceso'){
      const finishOption=[...transitionSelect.options].find(option=>option.value==='Pendiente de validaci\u00f3n');
      if(finishOption)transitionSelect.value=finishOption.value;
    }
    transitionButton.textContent=transitionButtonLabel(transitionSelect.value);
    const flowCard=transitionSelect.closest('.operation-card');
    if(o.status==='En proceso'&&flowCard){const note=document.createElement('p');note.className='subtle';note.textContent='Indica inicio, fin, técnicos, acciones y notas de cierre. Este botón guarda los cambios y envía la OT a revisión.';flowCard.append(note)}
    transitionSelect.addEventListener('change',()=>{transitionButton.textContent=transitionButtonLabel(transitionSelect.value)},{capture:true});
  }
  const sessionCard=null;
  const sessionHelp=sessionCard?.querySelector('.operation-card-head p');
  if(sessionHelp)sessionHelp.textContent='Registra el tiempo efectivo por técnico y calcula las horas hombre. Terminar una sesión no cierra la OT; las pausas no suman.';
  const manualTimeHelp=wrap.querySelector('.order-attention-grid details');
  if(manualTimeHelp){const note=document.createElement('p');note.className='subtle';note.textContent='Agrega un intervalo ya trabajado. Jefatura puede corregirlo desde el historial.';manualTimeHelp.insertBefore(note,manualTimeHelp.querySelector('label'))}
  const lifecycleInputs=wrap.querySelectorAll('input[type="datetime-local"][disabled]');
  const lifecycleNotes=['La OT registra este momento al pasar a En proceso.','Se registra al enviar el trabajo a validación. Para ajustar horas trabajadas, corrige las sesiones.'];
  lifecycleInputs.forEach((input,index)=>{const field=input.closest('.field');const label=field?.querySelector('label');if(label)label.textContent=index===0?'Inicio de la OT':'Término de la OT';if(field&&lifecycleNotes[index]){const note=document.createElement('small');note.className='subtle';note.textContent=lifecycleNotes[index];field.append(note)}});
  const documentGuidance={closure_document_code:['Código documental (opcional)','Clave del formato oficial de mantenimiento usado en planta. Déjalo vacío si no manejan una.'],closure_document_revision:['Revisión documental (opcional)','Revisión impresa en ese formato; no es la versión del PDF generado.'],closure_notes:['Notas de cierre','Resume el diagnóstico, reparación, pruebas y resultado para el expediente.']};
  for(const [name,[labelText,helpText]] of Object.entries(documentGuidance)){const field=wrap.querySelector(`[name="${name}"]`)?.closest('.field');if(!field)continue;const label=field.querySelector('label');if(label)label.textContent=labelText;const note=document.createElement('small');note.className='subtle';note.textContent=helpText;field.append(note)}
  queueMicrotask(()=>{for(const [name,[labelText,helpText]] of Object.entries(documentGuidance)){const field=wrap.querySelector(`[name="${name}"]`)?.closest('.field');if(!field)continue;const label=field.querySelector('label');if(label)label.textContent=labelText;let note=field.querySelector('.document-field-help');if(!note){note=document.createElement('small');note.className='subtle document-field-help';field.append(note)}note.textContent=helpText}});
  queueMicrotask(()=>{for(const name of ['closure_document_code','closure_document_revision','date_change_reason'])wrap.querySelector(`[name="${name}"]`)?.closest('.field')?.remove()});
  const generatePdfButton=$('.generate-order-pdf',wrap);
  if(generatePdfButton)generatePdfButton.onclick=async()=>{generatePdfButton.disabled=true;const pdfTab=window.open('about:blank','_blank');try{const document=await api(`/api/orders/${id}/documents`,{method:'POST',body:'{}'});if(pdfTab)pdfTab.location.replace(document.url);else window.location.assign(document.url);toast(document.created?`Versión ${document.version} guardada`:'Sin cambios; se abrió la última versión guardada')}catch(error){pdfTab?.close();toast(error.message)}finally{generatePdfButton.disabled=false}};
  $('.order-pdf-history',wrap).onclick=async()=>{try{const documents=await api(`/api/orders/${id}/documents`);const content=documents.length?`<div class="timeline">${documents.map(document=>`<div class="timeline-item"><b>Versión ${document.version} · ${esc(document.document_number)}</b><small>${esc(fmtDate(document.created_at))} · ${esc(document.created_by_name)} · OT v${document.source_order_version}</small><small>Código ${esc(document.document_code||'Pendiente')} · revisión ${esc(document.document_revision||'Pendiente')}</small><a class="order-action" href="/api/orders/${id}/documents/${document.id}" target="_blank" rel="noopener">Abrir PDF</a></div>`).join('')}</div>`:'<p class="subtle">Todavía no hay versiones de PDF archivadas.</p>';readModal(`PDF versionado · ${esc(o.folio)}`,content)}catch(error){toast(error.message)}};  wrap.querySelector('.form-actions').insertAdjacentHTML('beforebegin',`<div class="field full"><label>Notas documentales del cierre</label><textarea name="closure_notes" placeholder="Resumen del trabajo, pruebas y resultado">${esc(o.closure_notes||'')}</textarea></div><div class="field"><label>Código documental</label><input name="closure_document_code" value="${esc(o.closure_document_code||'')}" placeholder="Pendiente de configurar"></div><div class="field"><label>Revisión documental</label><input name="closure_document_revision" value="${esc(o.closure_document_revision||'')}" placeholder="Rev. 00"></div><div class="field full"><label>Motivo de cambio de fecha</label><input name="date_change_reason" placeholder="Solo si modificas solicitud o programación"></div>`);
  const updateSessionControls=()=>{const targetId=state.user.role==='Técnico'?state.user.id:Number($('.time-user-id',wrap)?.value),eligible=canTrackTime&&assignedPeople.some(person=>person.id===targetId),running=o.time_entries.find(entry=>entry.user_id===targetId&&!entry.finished_at);wrap.querySelectorAll('.time-action').forEach(button=>button.disabled=!eligible||(button.dataset.action==='start'?Boolean(running):!running));const status=wrap.querySelector('.operation-card:nth-child(2) > small');if(status)status.textContent=running?`Sesión activa desde ${fmtDate(running.started_at)}`:'Sin sesión activa para este técnico';const manual=$('.save-inline-time',wrap);if(manual)manual.disabled=!eligible};
  $('.time-user-id',wrap)?.addEventListener('change',updateSessionControls);updateSessionControls();
  if(['Administrador','Jefatura','Jefe de mantenimiento'].includes(state.user.role)){
    const rows=wrap.querySelectorAll('.operation-card:nth-child(2) .timeline-item');
    o.time_entries.forEach((entry,index)=>{if(!entry.finished_at||!rows[index])return;const button=document.createElement('button');button.type='button';button.className='order-action';button.textContent='Corregir intervalo';rows[index].append(button);button.onclick=()=>{wrap.remove();modal('Corregir intervalo de '+esc(entry.user_name),`<div class="field"><label>Inicio</label><input name="started_at" type="datetime-local" value="${dt(entry.started_at)}" required></div><div class="field"><label>Fin</label><input name="finished_at" type="datetime-local" value="${dt(entry.finished_at)}" required></div><div class="field full"><label>Motivo de corrección</label><textarea name="reason" required></textarea></div>`,data=>api(`/api/orders/${id}/time-entries/${entry.id}`,{method:'PATCH',body:JSON.stringify({...data,version:o.version})}));};});
  }
  wrap.querySelector('.modal-head').insertAdjacentHTML('afterend',preventiveExecutionPanel(o));
  if(o.status==='Pendiente de validación'&&['Administrador','Jefatura','Jefe de mantenimiento'].includes(state.user.role))wrap.querySelector('.order-attention .section-title').insertAdjacentHTML('beforeend',`<button type="button" class="btn btn-primary validate-order" data-id="${o.id}" data-version="${o.version}">Validar y cerrar OT</button>`);
  if(o.status==='Pendiente de validaci\u00f3n'){const validateButton=$('.validate-order',wrap);if(validateButton)validateButton.textContent='Validar y cerrar OT'}
  let dirty=false;const markDirty=event=>{if(!event.target.closest('.order-attention'))dirty=true};wrap.querySelector('form').addEventListener('input',markDirty);wrap.querySelector('form').addEventListener('change',markDirty);
   wrap.addEventListener('click',e=>{if(dirty&&e.target.closest('.validate-order,.save-inline-time,.save-inline-material,.time-action,.generate-order-pdf')){e.preventDefault();e.stopImmediatePropagation();toast('Guarda los cambios de la orden antes de ejecutar esta acción.');}},true);
  if(['Completada','Cancelada','Pendiente de validación'].includes(o.status)){
    wrap.querySelectorAll('form input,form select,form textarea').forEach(el=>el.disabled=true);
    const saveButton=wrap.querySelector('form .form-actions .btn-primary');
    if(saveButton)saveButton.hidden=true;
    if(['Completada','Cancelada'].includes(o.status)&&['Administrador','Jefatura','Jefe de mantenimiento'].includes(state.user.role)){
      wrap.querySelector('.order-attention .section-title').insertAdjacentHTML('beforeend',`<button type="button" class="btn btn-secondary reopen-order" data-id="${o.id}" data-version="${o.version}">Reabrir orden</button>`);
    }
  }
  const refresh=async()=>{wrap.remove();await openOrderDetail(id);render();};
   $('.order-state-select',wrap)?.addEventListener('change',e=>{$('.apply-order-state',wrap).textContent=transitionButtonLabel(e.target.value)});
   $('.apply-order-state',wrap)?.addEventListener('click',async e=>{const button=e.currentTarget,to=$('.order-state-select',wrap).value;let reason='',material_disposition='';if(to==='Cancelada'){reason=window.prompt('Motivo de cancelación');if(!reason)return;if(o.materials.length){material_disposition=window.prompt('Tratamiento de materiales consumidos (se conservan en el historial)');if(!material_disposition)return}}button.disabled=true;try{if(dirty){await saveOrderChanges(Object.fromEntries(new FormData(wrap.querySelector('form'))));dirty=false}await api(`/api/orders/${id}/transitions`,{method:'POST',body:JSON.stringify({to,version:currentVersion,reason,material_disposition})});toast('Estado de la orden actualizado');await refresh()}catch(error){const message=$('.form-error',wrap);if(message){message.textContent=error.message;message.hidden=false;message.focus()}else toast(error.message);button.disabled=false}});
   wrap.querySelectorAll('.time-action').forEach(button=>button.addEventListener('click',async()=>{button.disabled=true;try{const action=button.dataset.action;await api(`/api/orders/${id}/time-entries/actions`,{method:'POST',body:JSON.stringify({action,version:o.version,user_id:$('.time-user-id',wrap)?.value,reason:$('.time-pause-reason',wrap).value})});toast(action==='start'?'Sesión iniciada':action==='pause'?'Sesión pausada':'Sesión terminada');await refresh()}catch(error){toast(error.message);button.disabled=false}}));
   $('.save-inline-time',wrap)?.addEventListener('click',async e=>{const button=e.currentTarget;button.disabled=true;try{await api(`/api/orders/${id}/time-entries`,{method:'POST',body:JSON.stringify({started_at:$('.inline-time-start',wrap).value,finished_at:$('.inline-time-finish',wrap).value,pause_reason:$('.inline-time-note',wrap).value,user_id:$('.time-user-id',wrap)?.value,version:o.version})});toast('Tiempo registrado');await refresh()}catch(error){toast(error.message);button.disabled=false}});
  $('.save-inline-material',wrap)?.addEventListener('click',async e=>{const button=e.currentTarget,item=inventory.find(row=>row.id===Number($('.inline-material-item',wrap).value));if(!item){toast('Selecciona un material');return}button.disabled=true;try{await api(`/api/inventory/${item.id}/movement`,{method:'POST',body:JSON.stringify({type:'Salida',quantity:$('.inline-material-quantity',wrap).value,notes:$('.inline-material-note',wrap).value,version:item.version,request_key:makeRequestKey(),work_order_id:id})});state.catalogs=null;toast('Material agregado a la orden');await refresh()}catch(error){toast(error.message);button.disabled=false}});
}
function assetFields(a={}){const operational=a.operational_status||'Sin información';return `<div class="field"><label>Código de negocio</label><input name="code" required value="${esc(a.code||'')}" placeholder="MAQ-001"><span class="subtle">Identificador vigente de la planta.</span></div><div class="field"><label>Nombre del activo</label><input name="name" required value="${esc(a.name||'')}"></div><div class="field"><label>Tipo de activo</label><select name="asset_type">${['Maquinaria','Infraestructura','Unidad móvil','Fixture','Herramental'].map(x=>`<option ${x===(a.asset_type||a.category)?'selected':''}>${x}</option>`).join('')}</select></div><div class="field"><label>Categoría histórica</label><select name="category">${['Maquinaria','Infraestructura','Unidad móvil'].map(x=>`<option ${x===a.category?'selected':''}>${x}</option>`).join('')}</select><span class="subtle">Se conserva para compatibilidad con registros previos.</span></div><div class="field"><label>Área / ubicación</label><input name="area" required value="${esc(a.area||'')}"></div><div class="field"><label>Código original</label><input name="original_code" value="${esc(a.original_code||'')}" placeholder="Código del Excel o placa"></div><div class="field full"><label>Alias o códigos equivalentes</label><input name="alias_codes" value="${esc(a.alias_codes||'')}" placeholder="Separar con comas"><span class="subtle">No fusiona duplicados automáticamente; solo conserva equivalencias para revisión.</span></div><div class="field"><label>Marca</label><input name="brand" value="${esc(a.brand||'')}"></div><div class="field"><label>Modelo</label><input name="model" value="${esc(a.model||'')}"></div><div class="field"><label>Voltaje / alimentación</label><input name="voltage" value="${esc(a.voltage||'')}"></div><div class="field"><label>Código de serie</label><input name="serial_code" value="${esc(a.serial_code||'')}"></div><div class="field"><label>Horas de operación</label><input name="operating_hours" type="number" min="0" step="0.1" value="${a.operating_hours||0}"></div><div class="field"><label>Estado operativo</label><select name="operational_status">${['Operativa','Parada','En mantenimiento','Operación restringida','Sin información'].map(x=>`<option ${x===operational?'selected':''}>${x}</option>`).join('')}</select></div><div class="field"><label>Causa del estado</label><input name="operational_status_cause" value="${esc(a.operational_status_cause||'')}" placeholder="Falla, ajuste, dato pendiente…"></div><div class="field"><label>Estado administrativo</label><select name="administrative_status">${['Activo','Inactivo','Baja pendiente'].map(x=>`<option ${x===(a.administrative_status||'Activo')?'selected':''}>${x}</option>`).join('')}</select></div><div class="field"><label>Criticidad</label><select name="critical"><option value="" ${!a.critical?'selected':''}>Normal</option><option value="1" ${a.critical?'selected':''}>Crítico</option></select><span class="subtle">La criticidad no cambia por una parada o por la prioridad de una OT.</span></div><div class="field full"><label>Observaciones</label><textarea name="observations">${esc(a.observations||'')}</textarea></div>`}
function assetPlacementFields(a={}){const lines=state.catalogs?.lines||[];const choices=a.line&&!lines.includes(a.line)?[a.line,...lines]:lines;return `<div class="field"><label>Línea</label>${choices.length?`<select name="line"><option value="">Sin línea</option>${choices.map(value=>`<option ${value===a.line?'selected':''}>${esc(value)}</option>`).join('')}</select>`:`<input name="line" value="${esc(a.line||'')}" placeholder="Configura líneas en Catálogos">`}</div><div class="field"><label>Ubicación detallada</label><input name="location_detail" value="${esc(a.location_detail||'')}" placeholder="Nave, celda o posición"></div>`}
async function openAsset(){await catalogs();modal('Nueva máquina o equipo',assetFields()+assetPlacementFields(),d=>api('/api/assets',{method:'POST',body:JSON.stringify(d)}).then(()=>state.catalogs=null));}
async function editAsset(a,previous){await catalogs();previous?.remove();modal(`Editar ficha · ${esc(a.code)}`,assetFields(a)+assetPlacementFields(a),d=>api(`/api/assets/${a.id}`,{method:'PATCH',body:JSON.stringify(d)}).then(()=>state.catalogs=null));}
async function openAssetDetail(id){const a=await api(`/api/assets/${id}`);const history=a.maintenances.length?`<div class="table-wrap"><table><thead><tr><th>Folio</th><th>Fecha</th><th>Tipo</th><th>Responsable</th><th>Estado</th><th></th></tr></thead><tbody>${a.maintenances.map(m=>`<tr><td class="folio">${esc(m.folio)}</td><td>${fmtDate(m.requested_at)}</td><td>${esc(m.classification)}</td><td>${esc(m.technician_name||'Sin asignar')}</td><td>${badge(m.status)}</td><td><button class="order-action order-detail" data-id="${m.id}">Abrir</button> <a class="order-action" href="/print.html?id=${m.id}" target="_blank">Imprimir</a></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">Esta máquina todavía no tiene mantenimientos.</div>';const wrap=readModal(`${a.code} · ${a.name}`,`<div class="detail-summary"><div class="detail-box"><span>Estado</span><strong>${badge(a.status)}</strong></div><div class="detail-box"><span>Mantenimientos</span><strong>${a.metrics.maintenance_count}</strong><small>MTTR ${a.metrics.mttr==null?'Sin datos suficientes':Number(a.metrics.mttr).toFixed(1)+' h'}</small></div><div class="detail-box"><span>Gasto en materiales</span><strong>${money(a.metrics.material_cost)}</strong><small>Último: ${fmtDate(a.metrics.last_maintenance)}</small></div></div><div class="machine-sheet"><h3>Ficha técnica</h3><div class="machine-grid">${[['Máquina / equipo',a.name],['Código',a.code],['Marca',a.brand],['Modelo',a.model],['Voltaje',a.voltage],['Código de serie',a.serial_code],['Área',a.area],['Categoría',a.category],['Horas de operación',a.operating_hours],['Criticidad',a.critical?'Crítico':'Normal']].map(x=>`<div><span>${x[0]}</span><strong>${esc(x[1]||'—')}</strong></div>`).join('')}</div><div class="detail-box" style="margin-top:12px"><span>Observaciones</span>${esc(a.observations||'Sin observaciones')}</div><button class="btn btn-secondary edit-asset" style="margin-top:14px">Editar ficha técnica</button></div><div class="table-head" style="padding-left:0;padding-right:0;margin-top:20px"><h3>Historial de mantenimiento</h3><button class="btn btn-primary new-machine-order">+ Agregar mantenimiento</button></div>${history}`);$('.edit-asset',wrap).onclick=()=>editAsset(a,wrap);$('.new-machine-order',wrap).onclick=()=>{wrap.remove();openOrderForAsset(a)}}
async function openPreventive(plan=null){const c=await catalogs();const edit=Boolean(plan);const wrap=modal(edit?'Editar preventivo':'Programar mantenimiento',`${edit?`<input type="hidden" name="version" value="${plan.version||1}">`:''}${edit?'':`<div class="field full"><label>Activo</label><select name="asset_id" required><option value="">Seleccionar…</option>${options(c.assets,'id','name')}</select></div>`}<div class="field full"><label>Actividad preventiva</label><input name="title" required value="${esc(plan?.title||'')}"></div><div class="field"><label>Frecuencia</label><input name="frequency" required placeholder="1 mes" value="${esc(plan?.frequency||'')}"></div><div class="field"><label>Próxima fecha</label><input name="next_date" type="date" required value="${esc(plan?.next_date||'')}"></div><div class="field"><label>Responsable</label><select name="responsible_id"><option value="">Sin asignar</option>${options(c.users.filter(x=>x.role==='Técnico'))}</select></div><div class="field"><label>Estado</label><select name="status"><option>Programado</option><option>Próximo</option><option>Reprogramado</option></select></div><div class="field"><label>Código de plantilla</label><input name="template_code" value="${esc(plan?.template_code||'')}" placeholder="PM-001"></div><div class="field"><label>Aplicabilidad</label><input name="applies_when" value="${esc(plan?.applies_when||'')}" placeholder="Cada turno / si supera 500 h"></div><div class="field full"><label>Instrucciones</label><textarea name="instructions" placeholder="Pasos o criterio de aceptación">${esc(plan?.instructions||'')}</textarea></div>`,d=>api(edit?`/api/preventives/${plan.id}`:'/api/preventives',{method:edit?'PATCH':'POST',body:JSON.stringify(d)}));
  if(!edit){const templates=await api('/api/preventive-templates');const grid=wrap.querySelector('.form-grid');const field=document.createElement('div');field.className='field full';field.innerHTML='<label>Plantilla por familia (opcional)</label><select name="template_id"><option value="">Sin plantilla</option>'+templates.map(t=>'<option value="'+t.id+'">'+esc(t.code)+' · '+esc(t.family)+' · '+esc(t.title)+'</option>').join('')+'</select><span class="subtle">La plantilla se aplicará al guardar si corresponde al tipo de activo.</span>';grid.prepend(field);const form=wrap.querySelector('form');form.addEventListener('submit',async event=>{if(!form.querySelector('[name="template_id"]').value)return;event.preventDefault();event.stopImmediatePropagation();const data=Object.fromEntries(new FormData(form)),templateId=Number(data.template_id);delete data.template_id;const error=wrap.querySelector('.form-error'),submit=form.querySelector('button:not([type="button"])');try{const created=await api('/api/preventives',{method:'POST',body:JSON.stringify(data)});await api('/api/preventives/'+created.id+'/apply-template',{method:'POST',body:JSON.stringify({template_id:templateId,version:1})});wrap.remove();toast('Preventivo creado desde plantilla');render()}catch(failure){error.textContent=failure.message;error.hidden=false;error.focus()}finally{submit.disabled=false;submit.textContent='Guardar'}},true)}
  if(edit){
    const responsible=$('[name="responsible_id"]',wrap);
    const selectedId=String(plan.responsible_id??'');
    if(selectedId&&![...responsible.options].some(option=>option.value===selectedId)){
      const option=document.createElement('option');option.value=selectedId;option.textContent=plan.responsible_name||('Responsable #'+selectedId+' (fuera del catálogo activo)');responsible.append(option);
    }
    responsible.value=selectedId;
    const status=$('[name="status"]',wrap);
    if(![...status.options].some(option=>option.value===plan.status)){
      const option=document.createElement('option');option.value=plan.status;option.textContent=plan.status;status.append(option);
    }
    status.value=plan.status;
  }
}
async function openPreventiveHistory(id){
  const revisions=await api('/api/preventives/'+id+'/revisions');
  const date=value=>{const parsed=new Date(value.includes('T')?value:value.replace(' ','T')+'Z');return Number.isNaN(parsed.getTime())?'Fecha no disponible':new Intl.DateTimeFormat('es-MX',{dateStyle:'medium',timeStyle:'short'}).format(parsed)};
  const content=revisions.map((revision,index)=>{
    const p=revision.snapshot;
    const fields=[['Actividad',p.title],['Código de plantilla',p.template_code],['Aplicabilidad declarada',p.applies_when||'Configuración pendiente'],['Frecuencia',p.frequency],['Fecha programada',p.next_date],['Responsable',p.responsible_id?'Usuario #'+p.responsible_id:'Sin asignar'],['Estado',p.status],['Instrucciones',p.instructions],['Motivo',revision.reason||'Sin motivo registrado']];
    return '<details class="detail-box"'+(index===0?' open':'')+'><summary>Revisión '+esc(revision.version)+' · '+esc(date(revision.recorded_at))+'</summary><p class="subtle">'+(revision.source==='migration-baseline'?'Registro disponible al migrar; autor e historial anterior no disponibles.':'Registrada por usuario #'+esc(revision.user_id))+'</p><dl>'+fields.map(([label,value])=>'<dt><b>'+esc(label)+'</b></dt><dd style="white-space:pre-wrap;overflow-wrap:anywhere;margin:4px 0 12px">'+esc(value||'Sin información')+'</dd>').join('')+'</dl></details>';
  }).join('');
  readModal('Historial preventivo #'+esc(id),content||'<p class="empty">No hay revisiones disponibles.</p>');
}

async function openTemplateCatalog(){const templates=await api('/api/preventive-templates');readModal('Plantillas por familia',templates.length?'<div class="table-wrap"><table><thead><tr><th>Código</th><th>Familia</th><th>Nombre</th><th>Tareas</th></tr></thead><tbody>'+templates.map(t=>'<tr><td>'+esc(t.code)+'</td><td>'+esc(t.family)+'</td><td>'+esc(t.title)+'</td><td>'+esc(t.tasks.length)+'</td></tr>').join('')+'</tbody></table></div>':'<p>No hay plantillas disponibles.</p>')}
const templateObserver=new MutationObserver(()=>{if(state.view==='preventives'&&!$('#template-catalog')){const anchor=$('#new-preventive');if(anchor){anchor.insertAdjacentHTML('afterend',' <button class="btn btn-secondary" id="template-catalog">Plantillas</button>');$('#template-catalog').onclick=openTemplateCatalog}}});templateObserver.observe($('#content'),{childList:true});
async function renderDowntime(){
  const [events,c,agenda]=await Promise.all([api('/api/downtime-events'),catalogs(),api('/api/agenda')]);
  const open=events.filter(x=>!x.finished_at);
  let agendaMode=localStorage.getItem('mesa-agenda-mode')||'calendar';
  let calendarAnchor=new Date();calendarAnchor.setDate(1);calendarAnchor.setHours(12,0,0,0);
  const renderOrder=o=>`<div class="timeline-item"><div><b>${esc(o.folio)}</b> · ${esc(o.asset_name||o.location||'Sin ubicación')}</div><span class="subtle">${fmtDate(o.scheduled_at||o.requested_at)} · ${esc(o.technician_name||'Sin asignar')}</span>${badge(o.status)}</div>`;
  const cards=agenda.technicians.map(t=>{const rows=agenda.orders.filter(o=>o.technician_id===t.id);return `<article class="card detail-box"><span>Técnico</span><h3>${esc(`${t.name} ${t.last_name||''}`.trim())}</h3><strong>${rows.length} OT abiertas</strong>${rows.length?`<div class="timeline">${rows.map(renderOrder).join('')}</div>`:'<p class="subtle">Sin trabajo pendiente.</p>'}</article>`}).join('');
  const unassigned=agenda.orders.filter(o=>!o.technician_id);
  const orderDay=order=>(order.scheduled_at||order.requested_at||'').slice(0,10);
  const agendaPanel=()=>agendaMode==='list'?`<section class="machine-grid">${cards}${unassigned.length?`<article class="card detail-box"><span>Técnico</span><h3>Sin asignar</h3><strong>${unassigned.length} OT abiertas</strong><div class="timeline">${unassigned.map(renderOrder).join('')}</div></article>`:''}</section>`:(()=>{const first=new Date(calendarAnchor.getFullYear(),calendarAnchor.getMonth(),1,12),offset=(first.getDay()+6)%7;first.setDate(first.getDate()-offset);const days=Array.from({length:42},(_,index)=>{const day=new Date(first);day.setDate(first.getDate()+index);const key=`${day.getFullYear()}-${String(day.getMonth()+1).padStart(2,'0')}-${String(day.getDate()).padStart(2,'0')}`;const items=agenda.orders.filter(order=>orderDay(order)===key);return `<div class="month-day ${day.getMonth()===calendarAnchor.getMonth()?'':'outside-month'} ${day.toDateString()===new Date().toDateString()?'today-cell':''}"><span class="month-day-number">${day.getDate()}</span>${items.slice(0,3).map(order=>`<button class="month-event ${order.priority==='Paro de máquina'?'agenda-critical':''}" data-id="${order.id}" title="${esc(order.folio+' · '+(order.asset_name||order.location||''))}"><b>${esc(order.folio)}</b><span>${esc(order.asset_name||order.location||'Sin activo')}</span></button>`).join('')}${items.length>3?`<span class="month-more">+${items.length-3} más</span>`:''}</div>`});return `<section class="card month-calendar"><div class="month-weekdays">${['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'].map(day=>`<span>${day}</span>`).join('')}</div><div class="month-grid">${days.join('')}</div><div class="agenda-legend"><span><i class="agenda-dot"></i> Mantenimiento programado o solicitado</span><span><i class="agenda-dot agenda-dot-critical"></i> Prioridad paro de máquina</span></div></section>`})()
  $('#content').innerHTML=`<div class="section-head"><div><h2>Paros y agenda operativa</h2><p>Indisponibilidad de activos y carga actual por técnico</p></div><div class="toolbar"><a class="btn btn-secondary" href="/api/downtime-events/export.xlsx">Exportar paros XLSX</a><button class="btn btn-primary" id="new-downtime">+ Registrar paro</button></div></div><section class="metrics"><div class="metric-card"><div class="metric-icon">!</div><div><div class="metric-value">${open.length}</div><span class="subtle">Paros abiertos</span></div></div><div class="metric-card"><div class="metric-icon">◴</div><div><div class="metric-value">${agenda.orders.length}</div><span class="subtle">OT pendientes</span></div></div></section><section class="card table-card"><div class="table-head"><h3>Historial de paros</h3><span class="subtle">${events.length} registrados</span></div><div class="table-wrap"><table><thead><tr><th>Activo</th><th>Causa</th><th>Inicio</th><th>Fin</th><th>OT relacionadas</th><th></th></tr></thead><tbody>${events.map(event=>`<tr><td><b>${esc(event.asset_name)}</b><div class="subtle">${esc(event.asset_code)}</div></td><td>${esc(event.cause)}</td><td>${fmtDate(event.started_at)}</td><td>${event.finished_at?fmtDate(event.finished_at):badge('Detenido')}</td><td>${event.order_count||0}</td><td>${event.finished_at?'—':`<button class="order-action close-downtime" data-id="${event.id}">Cerrar paro</button>`}</td></tr>`).join('')||'<tr><td colspan="6" class="empty">Todavía no hay paros registrados.</td></tr>'}</tbody></table></div></section><div class="agenda-toolbar"><div><h3>Agenda de mantenimientos</h3><p class="subtle">Cada OT aparece en la fecha programada o solicitada.</p></div><div class="view-switch" role="group" aria-label="Diseño de agenda"><button type="button" data-agenda-mode="calendar" aria-pressed="${agendaMode==='calendar'}">Calendario</button><button type="button" data-agenda-mode="list" aria-pressed="${agendaMode==='list'}">Lista</button></div></div><div id="agenda-calendar-nav" ${agendaMode==='list'?'hidden':''}><button class="btn btn-secondary" id="month-prev" aria-label="Mes anterior">←</button><strong id="month-title"></strong><button class="btn btn-secondary" id="month-next" aria-label="Mes siguiente">→</button><button class="btn btn-secondary" id="month-today">Hoy</button></div><div id="agenda-panel">${agendaPanel()}</div>`;
  const wireAgendaOrders=()=>document.querySelectorAll('.month-event').forEach(button=>button.onclick=()=>openOrderDetail(Number(button.dataset.id)));
  const paintCalendar=()=>{$('#agenda-panel').innerHTML=agendaPanel();$('#month-title').textContent=calendarAnchor.toLocaleDateString('es-MX',{month:'long',year:'numeric'});wireAgendaOrders()};
  $('#month-prev').onclick=()=>{calendarAnchor.setMonth(calendarAnchor.getMonth()-1);paintCalendar()};$('#month-next').onclick=()=>{calendarAnchor.setMonth(calendarAnchor.getMonth()+1);paintCalendar()};$('#month-today').onclick=()=>{calendarAnchor=new Date();calendarAnchor.setDate(1);calendarAnchor.setHours(12,0,0,0);paintCalendar()};$('#month-title').textContent=calendarAnchor.toLocaleDateString('es-MX',{month:'long',year:'numeric'});
  document.querySelectorAll('[data-agenda-mode]').forEach(button=>button.onclick=()=>{agendaMode=button.dataset.agendaMode;localStorage.setItem('mesa-agenda-mode',agendaMode);$('[data-agenda-mode="calendar"]').setAttribute('aria-pressed',String(agendaMode==='calendar'));$('[data-agenda-mode="list"]').setAttribute('aria-pressed',String(agendaMode==='list'));$('#agenda-calendar-nav').hidden=agendaMode==='list';$('#agenda-panel').innerHTML=agendaPanel();if(agendaMode==='calendar')$('#month-title').textContent=calendarAnchor.toLocaleDateString('es-MX',{month:'long',year:'numeric'});wireAgendaOrders()});
  $('#new-downtime').onclick=async()=>{const now=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);modal('Registrar paro',`<div class="field full"><label>Activo</label><select name="asset_id" required><option value="">Seleccionar…</option>${options(c.assets,'id','name')}</select></div><div class="field full"><label>Causa</label><input name="cause" required placeholder="Falla, ajuste o espera"></div><div class="field"><label>Inicio</label><input name="started_at" type="datetime-local" value="${now}" required></div><div class="field"><label>Fin</label><input name="finished_at" type="datetime-local"></div><div class="field full"><label>OT relacionadas</label><select name="work_order_ids" multiple size="5">${options(agenda.orders,'id','folio')}</select><span class="subtle">Solo se pueden vincular OT del mismo activo.</span></div>`,d=>api('/api/downtime-events',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({...d,work_order_ids:d.work_order_ids||[]})}));};
  document.querySelectorAll('.close-downtime').forEach(button=>button.onclick=()=>modal('Cerrar paro',`<div class="field"><label>Fecha de fin</label><input name="finished_at" type="datetime-local" required></div><div class="field full"><label>Motivo del cierre</label><textarea name="reason" required minlength="5" placeholder="Qué confirmó la liberación del activo"></textarea></div>`,d=>api(`/api/downtime-events/${button.dataset.id}`,{method:'PATCH',body:JSON.stringify(d)})));
}

async function renderAudit(){
  const params=new URLSearchParams();Object.entries(state.auditFilters).forEach(([key,value])=>{if(value)params.set(key,value)});
  const exportHref='/api/audit/export.xlsx'+(params.size?'?'+params.toString():''),query=new URLSearchParams(params);query.set('page',state.auditPage);
  const data=await api('/api/audit?'+query.toString());
  $('#content').innerHTML=`<div class="section-head"><div><h2>Historial de auditoría</h2><p>${data.total} cambios en el corte · página ${data.page}</p></div><a class="btn btn-secondary" href="${exportHref}">Exportar XLSX del filtro</a></div><section class="card" style="margin-bottom:18px"><form id="audit-filters" class="toolbar"><label>Desde <input type="date" name="from" value="${esc(state.auditFilters.from)}"></label><label>Hasta <input type="date" name="to" value="${esc(state.auditFilters.to)}"></label><label>Entidad <input name="entity_type" value="${esc(state.auditFilters.entity_type)}" placeholder="work_order"></label><label>ID entidad <input name="entity_id" type="number" min="1" value="${esc(state.auditFilters.entity_id||'')}"></label><label>Acción <input name="action" value="${esc(state.auditFilters.action)}" placeholder="transition"></label><label>Buscar <input name="q" value="${esc(state.auditFilters.q)}" placeholder="Usuario, motivo o entidad"></label><button class="btn btn-secondary" type="submit">Filtrar</button><button class="btn btn-secondary" id="audit-reset" type="button">Limpiar</button></form></section><section class="card table-card"><div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Usuario</th><th>Entidad</th><th>Acción</th><th>Motivo</th><th></th></tr></thead><tbody>${data.items.map(row=>`<tr><td>${new Intl.DateTimeFormat('es-MX',{dateStyle:'medium',timeStyle:'short'}).format(new Date(row.created_at))}</td><td>${esc(row.user_name)}</td><td>${esc(row.entity_type)}${row.entity_id?` · #${row.entity_id}`:''}</td><td>${esc(row.action)}</td><td>${esc(row.reason||'—')}</td><td><button class="order-action audit-detail" data-id="${row.id}">Ver cambio</button></td></tr>`).join('')||'<tr><td colspan="6" class="empty">No hay cambios para estos filtros.</td></tr>'}</tbody></table></div><div class="form-actions"><button class="btn btn-secondary" id="audit-prev" ${data.page<=1?'disabled':''}>Anterior</button><button class="btn btn-secondary" id="audit-next" ${data.page*data.page_size>=data.total?'disabled':''}>Siguiente</button></div></section>`;
  $('#audit-filters').onsubmit=event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));state.auditFilters=values;state.auditPage=1;renderAudit()};
  $('#audit-reset').onclick=()=>{state.auditFilters={from:'',to:'',entity_type:'',entity_id:'',action:'',q:''};state.auditPage=1;renderAudit()};
  $('#audit-prev').onclick=()=>{state.auditPage=Math.max(1,state.auditPage-1);renderAudit()};$('#audit-next').onclick=()=>{state.auditPage++;renderAudit()};
  document.querySelectorAll('.audit-detail').forEach(button=>button.onclick=()=>{const row=data.items.find(item=>item.id===Number(button.dataset.id));readModal(`Cambio #${row.id}`,`<p><b>${esc(row.entity_type)} ${row.entity_id?'#'+row.entity_id:''} · ${esc(row.action)}</b></p><p>Usuario: ${esc(row.user_name)} · ${esc(new Intl.DateTimeFormat('es-MX',{dateStyle:'medium',timeStyle:'short'}).format(new Date(row.created_at)))}</p><p>Motivo: ${esc(row.reason||'Sin motivo')}</p><div class="grid-2"><div class="detail-box"><b>Antes</b><pre style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:40vh;overflow:auto">${esc(JSON.stringify(row.before,null,2)||'—')}</pre></div><div class="detail-box"><b>Después</b><pre style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:40vh;overflow:auto">${esc(JSON.stringify(row.after,null,2)||'—')}</pre></div></div>`)});
}

async function renderImports(){
  const batches=await api('/api/imports');
  $('#content').innerHTML='<section class="card" style="padding:24px"><h2>Revisar libro Excel</h2><p>Se conserva un lote de revisión por archivo. Esta operación no modifica activos, órdenes ni inventario y no ejecuta macros.</p><form id="import-preview-form"><label>Libro XLSX o XLSM <input type="file" name="file" accept=".xlsx,.xlsm" required></label> <button class="btn btn-primary" type="submit">Ver vista previa</button></form><div id="import-preview-result" aria-live="polite"></div></section><section class="card table-card" style="margin-top:20px"><div class="table-head"><h3>Lotes revisados</h3><span class="subtle">'+batches.length+' registrados</span></div><div class="table-wrap"><table><thead><tr><th>Archivo</th><th>Fecha</th><th>Contenido</th><th>Estado</th><th></th></tr></thead><tbody>'+(batches.map(batch=>`<tr><td><b>${esc(batch.filename)}</b><div class="subtle">SHA-256: ${esc(batch.content_hash.slice(0,12))}…</div></td><td>${fmtDate(batch.created_at)}</td><td>${batch.sheet_count} hojas · ${batch.row_count} filas · ${batch.visible_conflict_count} conflictos visibles</td><td>${esc(batch.status)}</td><td><button type="button" class="order-action import-detail" data-id="${batch.id}">Revisar</button>${batch.status==='Revision'?` <button type="button" class="order-action import-discard" data-id="${batch.id}">Descartar</button>`:''}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">Todavía no hay lotes revisados.</td></tr>')+'</tbody></table></div></section>';
  $('#import-preview-form').onsubmit=async event=>{
    event.preventDefault();
    const form=event.currentTarget,button=form.querySelector('button'),result=$('#import-preview-result');
    button.disabled=true;result.textContent='Leyendo hojas…';
    try{
      const data=await api('/api/imports/preview',{method:'POST',body:new FormData(form)});
      await renderImports();
      $('#import-preview-result').innerHTML='<h3>'+esc(data.filename)+'</h3><p>'+(data.duplicate?'Este archivo ya tenía un lote registrado. ':'Lote de revisión registrado. ')+'No se modificaron datos operativos.</p>'+importPreviewHtml(data);
      if(!data.duplicate)toast('Lote registrado para revisión');
    }catch(error){result.textContent=error.message}
    finally{button.disabled=false}
  };
  document.querySelectorAll('.import-detail').forEach(button=>button.onclick=()=>openImportBatch(button.dataset.id));
  document.querySelectorAll('.import-discard').forEach(button=>button.onclick=()=>modal('Descartar lote',`<div class="field full"><label>Motivo del descarte</label><textarea name="reason" minlength="5" required placeholder="Indica por qué este archivo no debe usarse"></textarea></div>`,data=>api(`/api/imports/${button.dataset.id}`,{method:'PATCH',body:JSON.stringify(data)})));
}
function importPreviewHtml(data){return data.sheets.map(sheet=>'<details class="detail-box" style="margin:12px 0"><summary><b>'+esc(sheet.name)+'</b> · '+sheet.rows+' filas con datos · '+sheet.conflicts.length+' conflictos visibles</summary><h4>Primeras filas</h4><ol>'+sheet.preview.map(row=>'<li>Fila '+row.row+': '+Object.entries(row.cells).map(([cell,value])=>'<b>'+esc(cell)+'</b> '+esc(value)).join(' · ')+'</li>').join('')+'</ol>'+(sheet.conflicts.length?'<h4>Códigos por revisar</h4><ul>'+sheet.conflicts.map(row=>'<li>Fila '+row.row+' · '+esc(row.code)+' · '+esc(row.reason)+'</li>').join('')+'</ul>':'<p>No se detectaron códigos repetidos en las columnas revisadas.</p>')+'</details>').join('')}
const importFieldLabels={source_id:'ID de origen',code:'Código',code_key:'Código comparado',name:'Nombre',brand:'Marca',model:'Modelo',voltage:'Voltaje',serial_code:'Serie',observations:'Observaciones',area:'Área',material:'Material',line:'Línea',description:'Descripción',unit:'Unidad',stock_raw:'Existencia original',unit_cost_raw:'Costo unitario original',source_asset_id:'ID de activo de origen',event_date_raw:'Fecha original',event_time_raw:'Hora original',classification_raw:'Clasificación original',responsible_raw:'Responsable original',performed_raw:'Realizado original',repair_time_raw:'Tiempo de reparación original',delivery_date_raw:'Fecha de entrega original',labor_cost_raw:'Costo de mano de obra original',material_cost_raw:'Costo de materiales original',asset_name_raw:'Nombre de activo original',source_maintenance_id:'ID de mantenimiento de origen',source_item_code:'Código de material de origen',quantity_raw:'Cantidad original',cost_raw:'Costo original',folio:'Folio',requester_raw:'Solicitante original',priority_raw:'Prioridad original',specialty_raw:'Especialidad original',location_raw:'Ubicación original',reported_failure:'Falla reportada',actions:'Acciones',technician_raw:'Técnico original',start_time_raw:'Hora inicial original',end_time_raw:'Hora final original',labor_hours_raw:'Horas hombre originales',status_raw:'Estado original',validator_raw:'Validador original',source_item:'Ítem de origen',comments:'Comentarios'};
const importTypeLabels={text:'texto original',date_candidate:'fecha candidata',time_candidate:'hora candidata',decimal_candidate:'número candidato'};
function importCellNote(detail){if(!detail)return '';if(['date','datetime','time'].includes(detail.kind))return ` <small class="subtle">${detail.iso?'Interpretado: '+esc(detail.iso):'Fecha/hora no interpretable'} · sistema ${esc(detail.date_system)}</small>`;if(detail.kind==='error')return ' <small class="subtle">Error de Excel</small>';if(detail.kind==='boolean')return ` <small class="subtle">Booleano: ${detail.value?'verdadero':'falso'}</small>`;return ''}
async function openImportBatch(id){
  try{
    const data=await api(`/api/imports/${id}`);
    const sheetButtons=data.preview.sheets.map(sheet=>`<button type="button" class="btn btn-secondary import-sheet" data-sheet="${esc(sheet.name)}">${esc(sheet.name)} · ${sheet.rows} filas</button>`).join(' ');
    const wrap=readModal(`Lote #${data.batch.id} · ${esc(data.batch.filename)}`,`<p><b>Estado:</b> ${esc(data.batch.status)} · <b>Registró:</b> ${esc(data.batch.uploaded_by)} · <b>Sistema de fechas:</b> ${esc(data.preview.date_system||'No registrado')}</p><p><b>SHA-256:</b> <code>${esc(data.batch.content_hash)}</code></p>${data.batch.discard_reason?`<p><b>Motivo de descarte:</b> ${esc(data.batch.discard_reason)}</p>`:''}<h3>Conciliación de códigos de activos</h3><p>Compara las filas de MAQUINAS, BASE DE DATOS y CALENDARIO con códigos vigentes y equivalencias aprobadas. Las coincidencias requieren revisión humana.</p><button type="button" class="btn btn-secondary import-reconciliation">Ver conciliación</button><div class="import-reconciliation-result" aria-live="polite"></div><h3>Prevalidación técnica del lote</h3><p>Resume decisiones y problemas de lectura en filas no excluidas. No carga datos ni sustituye la aprobación de planta.</p><button type="button" class="btn btn-secondary import-readiness">Evaluar lote</button> <a class="btn btn-secondary" href="/api/imports/${data.batch.id}/readiness/export.xlsx">Descargar resumen XLSX</a><div class="import-readiness-result" aria-live="polite"></div><h3>Filas de origen</h3><p>La revisión registra decisiones y propuestas; no modifica datos operativos. Selecciona una hoja.</p><div class="form-actions">${sheetButtons}</div><div class="import-rows" aria-live="polite"></div><h3>Vista previa y conflictos visibles</h3>${importPreviewHtml(data.preview)}`);
    async function showReconciliation(page){
      const target=$('.import-reconciliation-result',wrap);target.textContent='Comparando códigos…';
      try{
        const result=await api(`/api/imports/${id}/reconciliation?page=${page}`);
        target.innerHTML=`<p>${result.total} códigos · ${result.source_rows_with_code} filas con código · ${result.source_rows_without_code} filas sin código desde el inicio de datos</p>`+result.groups.map(group=>`<details class="detail-box" style="margin:8px 0"><summary><b>${esc(group.code)}</b> · ${group.source_row_count} filas · ${group.asset_matches.length?group.asset_matches.length+' coincidencia(s) en Django':'Sin coincidencia en Django'}${group.repeated_within_sheet?' · Repetido en una hoja':''}</summary><p><b>Hojas:</b> ${Object.entries(group.sheet_counts).map(([name,count])=>esc(name)+' ('+count+')').join(' · ')}</p><p><b>Revisión:</b> ${Object.entries(group.review_counts).map(([status,count])=>esc(status)+' '+count).join(' · ')}</p><p><b>Activos coincidentes:</b> ${group.asset_matches.map(match=>esc(match.code)+' ('+esc(match.via)+')').join(' · ')||'Ninguno'}</p>${Object.keys(group.attribute_variants).length?`<p><b>Valores distintos por revisar:</b> ${Object.entries(group.attribute_variants).map(([name,values])=>esc(importFieldLabels[name]||name)+': '+values.map(esc).join(' / ')).join(' · ')}</p>`:''}<p><b>Procedencia:</b> ${group.rows.map(row=>esc(row.sheet)+' #'+row.source_row+' ('+esc(row.status)+')').join(' · ')}${group.more_rows?' · y '+group.more_rows+' filas más':''}</p></details>`).join('')+`<div class="form-actions"><button type="button" class="btn btn-secondary import-reconciliation-prev" ${page<=1?'disabled':''}>Anterior</button><button type="button" class="btn btn-secondary import-reconciliation-next" ${page*result.page_size>=result.total?'disabled':''}>Siguiente</button></div>`;
        $('.import-reconciliation-prev',target).onclick=()=>showReconciliation(page-1);
        $('.import-reconciliation-next',target).onclick=()=>showReconciliation(page+1);
      }catch(error){target.textContent=error.message}
    }
    $('.import-reconciliation',wrap).onclick=()=>showReconciliation(1);
    $('.import-readiness',wrap).onclick=async()=>{
      const target=$('.import-readiness-result',wrap);target.textContent='Evaluando filas no excluidas…';
      try{
        const result=await api(`/api/imports/${id}/readiness`);
        const labels={pending_review_rows:'Filas pendientes de decisión',proposed_link_rows:'Vínculos aún en propuesta',unmapped_rows:'Filas sin mapeo',mapping_issue_rows:'Filas con observaciones del mapeo',field_type_issue_rows:'Filas con tipo de dato por confirmar',source_issue_rows:'Filas con incidencias de lectura',excel_error_cells:'Celdas con error de Excel',uninterpreted_temporal_cells:'Fechas candidatas sin interpretación',formula_without_value_cells:'Fórmulas sin valor guardado',unresolved_reference_count:'Referencias sin coincidencia, ambiguas o vacías',duplicate_reference_key_count:'Claves duplicadas dentro de una hoja',batch_not_in_review:'Lote no disponible para revisión'};
        const blockers=Object.entries(result.blocking_counts).filter(([,count])=>count>0);
        const refLabels={maintenance_asset:'Activo de mantenimiento → MAQUINAS',material_maintenance:'Renglón PM → mantenimiento',material_item:'Renglón PM → ALMACEN'};
        target.innerHTML=`<p><b>${result.technical_precheck_clear?'Prevalidación técnica sin bloqueos detectados':'La revisión técnica tiene pendientes'}</b> · ${result.total_rows} filas; ${result.mapped_rows} mapeadas y ${result.unmapped_rows} sin mapeo.</p>${blockers.length?`<ul>${blockers.map(([key,count])=>`<li>${esc(labels[key]||key)}: ${count}</li>`).join('')}</ul>`:'<p>No quedan bloqueos técnicos en las filas no excluidas.</p>'}<p class="subtle">Importación operativa: no disponible. Este resultado no aprueba el origen, los campos provisionales ni la carga.</p><details><summary>Conteo por tipo de fila</summary><ul>${Object.entries(result.by_kind).map(([kind,value])=>`<li>${esc(kind)}: ${value.rows} · pendientes ${value.pending}, propuestas ${value.proposed}, excluidas ${value.excluded}</li>`).join('')||'<li>Sin filas</li>'}</ul></details><details><summary>Estado de referencias (filas no excluidas)</summary><ul>${Object.entries(result.reference_counts).map(([kind,counts])=>`<li>${esc(refLabels[kind]||kind)}: ${Object.entries(counts).map(([status,count])=>`${esc(status)} ${count}`).join(' · ')}</li>`).join('')||'<li>Sin referencias entre hojas</li>'}</ul></details>`;
        target.insertAdjacentHTML('beforeend',`<details open><summary>Condiciones pendientes para autorizar una importación</summary><ul>${result.operational_import_blockers.map(item=>`<li><b>${esc(item.decision)}:</b> ${esc(item.message)}</li>`).join('')}</ul></details>`);
      }catch(error){target.textContent=error.message}
    };
    const incidentPanel=document.createElement('section');incidentPanel.innerHTML='<h3>Incidencias de lectura</h3><p>Errores de Excel y fechas numéricas que no pudieron interpretarse. Abre la fila de origen para registrar una decisión con motivo.</p><button type="button" class="btn btn-secondary import-incidents">Revisar incidencias</button><div class="import-incidents-result" aria-live="polite"></div>';
    $('.modal .form',wrap).append(incidentPanel);
    if(data.preview.sheets.some(sheet=>sheet.name==='MANTENIMIENTOS')&&data.preview.sheets.some(sheet=>sheet.name==='PM')){
      const referencePanel=document.createElement('section');referencePanel.innerHTML='<h3>Referencias del historial</h3><p>Comprueba IDs de activos, mantenimientos y materiales dentro de este libro.</p><button type="button" class="btn btn-secondary import-references">Revisar referencias</button><div class="import-references-result" aria-live="polite"></div>';
      $('.modal .form',wrap).append(referencePanel);
      $('.import-references',referencePanel).onclick=async()=>{
        const target=$('.import-references-result',referencePanel);target.textContent='Revisando referencias…';
        try{
          const result=await api(`/api/imports/${id}/reconciliation/references`);
          const counts=values=>Object.entries(values).map(([status,count])=>esc(status)+': '+count).join(' · ');
          const matchHtml=match=>`${esc(match.sheet)} #${match.source_row}${match.code?' · '+esc(match.code):''}${match.name?' · '+esc(match.name):''}${match.candidate_review?`<div class="subtle">También aparece en: ${match.candidate_review.source_rows.map(source=>`${esc(source.sheet)} #${source.source_row}${source.name?' · '+esc(source.name):''}`).join(' · ')||'ninguna hoja' }${match.candidate_review.more_source_rows?' · y '+match.candidate_review.more_source_rows+' más':''}${match.candidate_review.repeated_within_sheet?' · código repetido dentro de una hoja':''}${Object.keys(match.candidate_review.attribute_variants).length?' · Valores distintos: '+Object.entries(match.candidate_review.attribute_variants).map(([field,values])=>`${esc(importFieldLabels[field]||field)} ${values.map(esc).join(' / ')}`).join('; '):''}</div>`:''}`;
          const refRows=(rows,key)=>rows.map(row=>{const ref=row[key];return `<tr><td>${row.source_row}</td><td>${esc(ref.value||'—')}</td><td>${esc(ref.status)}</td><td>${ref.matches.map(matchHtml).join('<br>')||'—'}${ref.more_matches?' · y '+ref.more_matches+' coincidencias más':''}</td></tr>`}).join('')||'<tr><td colspan="4">Sin filas legibles para esta referencia.</td></tr>';
          const table=(title,values,rows,key)=>`<h4>${title}</h4><p>${counts(values)}</p><div class="table-wrap"><table><thead><tr><th>Fila de origen</th><th>Referencia</th><th>Resultado</th><th>Coincidencias</th></tr></thead><tbody>${refRows(rows,key)}</tbody></table></div>`;
          const duplicateSummary=result.duplicate_keys.length?`<h4>Claves repetidas dentro de una hoja</h4><div class="table-wrap"><table><thead><tr><th>Tipo de clave</th><th>Valor</th><th>Filas</th></tr></thead><tbody>${result.duplicate_keys.map(item=>`<tr><td>${esc(item.kind)}</td><td>${esc(item.key)}</td><td>${item.rows.map(row=>esc(row.sheet)+' #'+row.source_row).join(' · ')}${item.more_rows?' · y '+item.more_rows+' más':''}</td></tr>`).join('')}</tbody></table></div>`:'<h4>Claves repetidas dentro de una hoja</h4><p>No se encontraron IDs, códigos de almacén ni folios repetidos en estas hojas.</p>';
          target.innerHTML=`<p>${result.maintenance_count} mantenimientos históricos · ${result.material_history_count} renglones de material · ${result.duplicate_key_count} claves repetidas</p>`+table('Activo de mantenimiento → MAQUINAS',result.maintenance_asset_counts,result.maintenance_asset_references,'source_asset_id')+table('Renglón PM → mantenimiento',result.material_maintenance_counts,result.material_maintenance_references,'source_maintenance_id')+table('Renglón PM → almacén',result.material_item_counts,result.material_item_references,'source_item_code')+duplicateSummary;
        }catch(error){target.textContent=error.message}
      };
    }
    async function showRows(sheet,page){
      const target=$('.import-rows',wrap);target.textContent='Cargando filas…';
      try{
        const result=await api(`/api/imports/${id}/rows?sheet=${encodeURIComponent(sheet)}&page=${page}`);
        target.innerHTML=`<h4>${esc(sheet)} · ${result.total} filas · página ${result.page}</h4>`+(result.rows.map(row=>`<details class="detail-box" style="margin:8px 0"><summary>Fila ${row.source_row}${row.source_code?' · '+esc(row.source_code):''} · ${esc(row.review_status)}${row.issues.length?' · '+esc(row.issues.join(', ')):''}</summary><p><b>Revisión:</b> ${esc(row.review_status)}${row.proposed_asset_code?' · Vinculación propuesta: '+esc(row.proposed_asset_code):''}${row.review_note?' · '+esc(row.review_note):''}</p>${row.mapping.kind!=='unmapped'?`<p><b>Campos identificados (provisionales):</b> ${Object.entries(row.mapping.fields).map(([name,value])=>esc(importFieldLabels[name]||name)+' ['+esc(importTypeLabels[row.mapping.field_types[name]||'text'])+']: '+esc(value)).join(' · ')}</p>`:''}${row.mapping.issues.length?`<p><b>Por revisar:</b> ${row.mapping.issues.map(esc).join(' · ')}</p>`:''}${row.mapping.type_issues?.length?`<p><b>Tipo/formato pendiente:</b> ${row.mapping.type_issues.map(issue=>esc(issue.message)).join(' · ')}</p>`:''}${data.batch.status==='Revision'?`<button type="button" class="btn btn-secondary import-review" data-id="${row.id}">Registrar decisión</button>`:''}<dl>${Object.entries(row.cells).map(([cell,value])=>`<dt><b>${esc(cell)}</b></dt><dd>${esc(value)}${importCellNote(row.cell_details[cell])}${row.formulas[cell]?` <small class="subtle">Fórmula: ${esc(row.formulas[cell])}</small>`:''}</dd>`).join('')}${Object.entries(row.formulas).filter(([cell])=>!Object.hasOwn(row.cells,cell)).map(([cell,formula])=>`<dt><b>${esc(cell)}</b></dt><dd>Fórmula sin valor guardado: ${esc(formula)}</dd>`).join('')}</dl></details>`).join('')||'<p>No hay filas en esta hoja.</p>')+`<div class="form-actions"><button type="button" class="btn btn-secondary import-prev" ${page<=1?'disabled':''}>Anterior</button><button type="button" class="btn btn-secondary import-next" ${page*result.page_size>=result.total?'disabled':''}>Siguiente</button></div>`;
        $('.import-prev',target).onclick=()=>showRows(sheet,page-1);
        $('.import-next',target).onclick=()=>showRows(sheet,page+1);
        document.querySelectorAll('.import-review',target).forEach(button=>button.onclick=async()=>{
          const row=result.rows.find(item=>item.id===Number(button.dataset.id));
          const canPropose=!!row.source_code&&['MAQUINAS','BASE DE DATOS','CALENDARIO'].includes(row.sheet.toUpperCase());
          let assets=[];
          if(canPropose){try{assets=await api('/api/assets')}catch(error){toast(error.message);return}}
          const fields=`<div class="field full"><label>Decisión</label><select name="status" required><option value="Pendiente" ${row.review_status==='Pendiente'?'selected':''}>Pendiente</option><option value="Excluida" ${row.review_status==='Excluida'?'selected':''}>Excluida</option>${canPropose?`<option value="Propuesta" ${row.review_status==='Propuesta'?'selected':''}>Propuesta de vínculo</option>`:''}</select></div>${canPropose?`<div class="field full import-proposal-asset"><label>Activo existente</label><select name="asset_id"><option value="">Seleccionar…</option>${assets.map(asset=>`<option value="${asset.id}" ${row.proposed_asset_id===asset.id?'selected':''}>${esc(asset.code)} · ${esc(asset.name)}</option>`).join('')}</select><span class="subtle">La propuesta no cambia el activo ni confirma su equivalencia.</span></div>`:''}<div class="field full"><label>Motivo</label><textarea name="reason" minlength="5" required>${esc(row.review_note||'')}</textarea></div>`;
          const dialog=modal(`Revisar ${esc(row.sheet)} · fila ${row.source_row}`,fields,async values=>{
            await api(`/api/imports/${id}/rows/${row.id}`,{method:'PATCH',body:JSON.stringify({status:values.status,asset_id:values.status==='Propuesta'?values.asset_id:null,reason:values.reason,version:row.version})});
            await showRows(sheet,page);
          });
          const status=$('[name="status"]',dialog),proposal=$('.import-proposal-asset',dialog);
          if(proposal){const toggle=()=>{proposal.hidden=status.value!=='Propuesta';$('[name="asset_id"]',proposal).required=!proposal.hidden};status.onchange=toggle;toggle()}
        });
      }catch(error){target.textContent=error.message}
    }
    async function showIncidents(page){
      const target=$('.import-incidents-result',incidentPanel);target.textContent='Buscando incidencias…';
      try{
        const result=await api(`/api/imports/${id}/incidents?page=${page}`);
        const kindLabel={error:'Error de Excel',invalid_temporal:'Fecha sin interpretación'};
        target.innerHTML=`<p>${result.total} filas con incidencias · ${result.excel_error_count} celdas con error · ${result.invalid_temporal_count} fechas sin interpretar</p>`+(result.incidents.map(item=>`<details class="detail-box" style="margin:8px 0"><summary>${esc(item.sheet)} · fila ${item.source_row} · ${item.cells.length} incidencia(s) · ${esc(item.review_status)}</summary><ul>${item.cells.map(cell=>`<li><b>${esc(cell.cell)} · ${esc(kindLabel[cell.kind]||cell.kind)}:</b> ${esc(cell.raw)}${cell.formula?' · Fórmula: '+esc(cell.formula):''}${cell.date_system?' · sistema '+esc(cell.date_system):''}</li>`).join('')}</ul><button type="button" class="btn btn-secondary import-open-incident" data-sheet="${esc(item.sheet)}" data-page="${item.source_page}" data-row="${item.source_row}">Abrir fila de origen</button></details>`).join('')||'<p>No se detectaron incidencias de tipo de celda en este lote.</p>')+`<div class="form-actions"><button type="button" class="btn btn-secondary import-incidents-prev" ${page<=1?'disabled':''}>Anterior</button><button type="button" class="btn btn-secondary import-incidents-next" ${page*result.page_size>=result.total?'disabled':''}>Siguiente</button></div>`;
        $('.import-incidents-prev',target).onclick=()=>showIncidents(page-1);
        $('.import-incidents-next',target).onclick=()=>showIncidents(page+1);
        document.querySelectorAll('.import-open-incident',target).forEach(button=>button.onclick=async()=>{
          const sheet=button.dataset.sheet,sourceRow=Number(button.dataset.row);
          await showRows(sheet,Number(button.dataset.page));
          const rowDetail=[...$('.import-rows',wrap).querySelectorAll('details')].find(node=>node.querySelector('summary')?.textContent.toLocaleLowerCase('es-MX').includes(`fila ${sourceRow}`));
          if(rowDetail){rowDetail.open=true;rowDetail.scrollIntoView({block:'nearest',behavior:'smooth'})}
        });
      }catch(error){target.textContent=error.message}
    }
    $('.import-incidents',incidentPanel).onclick=()=>showIncidents(1);
    document.querySelectorAll('.import-sheet',wrap).forEach(button=>button.onclick=()=>showRows(button.dataset.sheet,1));
  }catch(error){toast(error.message)}
}
async function render(){const [title,subtitle]=titles[state.view];$('#page-title').textContent=title;$('#page-subtitle').textContent=subtitle;$('#content').innerHTML='<div class="empty">Cargando…</div>';try{await ({dashboard:renderDashboard,orders:renderOrders,assets:renderAssets,catalogs:renderCatalogs,inventory:renderInventory,preventives:renderPreventives,downtime:renderDowntime,users:renderUsers,imports:renderImports,audit:renderAudit}[state.view])()}catch(err){$('#content').innerHTML=`<div class="empty">No fue posible cargar la información.<br>${esc(err.message)}</div>`}}
function navigate(view){state.view=view;document.querySelectorAll('.nav-item, .bottom-nav-item').forEach(x=>x.classList.toggle('active',x.dataset.view===view));$('#sidebar').classList.remove('open');render()}window.navigate=navigate;
function showLogin(){state.user=null;state.catalogs=null;$('#password-change-screen').classList.add('hidden');if(state.pollTimer)clearInterval(state.pollTimer);state.pollTimer=null;document.querySelectorAll('.modal-backdrop').forEach(el=>el.remove());$('#content').replaceChildren();$('#login-screen').classList.remove('hidden');}
async function pollOrders(){if(!state.user)return;try{if(state.user.role==='Solicitante'){const rows=await api('/api/orders');const signature=rows.map(x=>`${x.id}:${x.status}:${x.updated_at}`).join('|');$('#notification-count').textContent=rows.filter(x=>!['Completada','Cancelada'].includes(x.status)).length;if(state.orderSignature!==null&&signature!==state.orderSignature){toast('El estado de uno de tus reportes cambió');if(!$('.modal-backdrop')&&state.view==='orders')render()}state.orderSignature=signature;return}const d=await api('/api/dashboard');$('#notification-count').textContent=d.orders.new_orders||0;if(state.lastOrderTotal!==null&&Number(d.orders.total)>Number(state.lastOrderTotal)){toast('Llegó un nuevo reporte de mantenimiento');if(!$('.modal-backdrop')&&(state.view==='orders'||state.view==='dashboard'))render()}state.lastOrderTotal=Number(d.orders.total)}catch{}}
function enterApp(user){state.user=user;state.lastOrderTotal=null;state.orderSignature=null;$('#login-screen').classList.add('hidden');if(user.must_change_password){$('#password-change-screen').classList.remove('hidden');$('#content').replaceChildren();return}$('#password-change-screen').classList.add('hidden');const all=['Administrador','Jefe de mantenimiento'].includes(user.role);document.querySelectorAll('.nav-item, .bottom-nav-item').forEach(item=>{const permissionView=item.dataset.view==='downtime'?'orders':item.dataset.view;item.hidden=!(all||user.permissions.includes(permissionView))});const orderNav=$('[data-view="orders"]');if(orderNav&&orderNav.lastChild)orderNav.lastChild.textContent=user.role==='Solicitante'?' Mis reportes':' Órdenes de trabajo';$('#notification').hidden=false;const available=[...document.querySelectorAll('.nav-item:not([hidden])')];if(!available.some(x=>x.dataset.view===state.view))state.view=available[0]?.dataset.view||'orders';$('#session-name').textContent=`${user.name} ${user.last_name||''}`.trim();$('#session-role').textContent=user.role_name||user.role;$('#user-avatar').textContent=`${user.name[0]||''}${user.last_name?.[0]||''}`.toUpperCase();navigate(state.view);if(state.pollTimer)clearInterval(state.pollTimer);pollOrders();state.pollTimer=setInterval(pollOrders,8000)}
$('#login-form').onsubmit=async e=>{e.preventDefault();$('#login-error').textContent='';const submit=$('button',e.target);submit.disabled=true;try{const user=await api('/api/auth/login',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});e.target.reset();enterApp(user)}catch(err){$('#login-error').textContent=err.message}finally{submit.disabled=false}};
$('#password-change-form').onsubmit=async event=>{event.preventDefault();const form=event.target;const data=Object.fromEntries(new FormData(form));const error=$('#password-change-error');error.textContent='';if(data.new_password!==data.confirm_password){error.textContent='Las contraseñas nuevas no coinciden';return}const submit=form.querySelector('button[type="submit"]');submit.disabled=true;try{await api('/api/auth/change-password',{method:'POST',body:JSON.stringify({current_password:data.current_password,new_password:data.new_password})});form.reset();enterApp(await api('/api/auth/me'))}catch(failure){error.textContent=failure.message}finally{submit.disabled=false}};
const handleLogout=async()=>{try{await api('/api/auth/logout',{method:'POST'})}catch{}showLogin()};
$('#password-change-logout').onclick=handleLogout;
const logoutBtn=$('#logout');if(logoutBtn)logoutBtn.onclick=handleLogout;
const mobileLogoutBtn=$('#mobile-logout');if(mobileLogoutBtn)mobileLogoutBtn.onclick=handleLogout;
$('#notification').onclick=()=>navigate('orders');document.addEventListener('click',async e=>{const order=e.target.closest('.order-detail');if(order)openOrderDetail(Number(order.dataset.id));const asset=e.target.closest('.asset-detail');if(asset)openAssetDetail(Number(asset.dataset.id));const transition=e.target.closest('.transition-order');if(transition){transition.disabled=true;try{await api(`/api/orders/${transition.dataset.id}/transitions`,{method:'POST',body:JSON.stringify({to:transition.dataset.to,version:Number(transition.dataset.version)})});toast('Estado de la orden actualizado');document.querySelector('.modal-backdrop')?.remove();render()}catch(error){toast(error.message)}finally{transition.disabled=false}}const validate=e.target.closest('.validate-order');if(validate){validate.disabled=true;try{await api(`/api/orders/${validate.dataset.id}/validate`,{method:'POST',body:JSON.stringify({version:Number(validate.dataset.version)})});toast('Cierre validado');document.querySelector('.modal-backdrop')?.remove();render()}catch(error){toast(error.message)}finally{validate.disabled=false}}});
$('#nav').onclick=e=>{const b=e.target.closest('[data-view]');if(b&&!b.hidden)navigate(b.dataset.view)};
const bottomNav=$('#bottom-nav');if(bottomNav)bottomNav.onclick=e=>{const b=e.target.closest('[data-view]');if(b&&!b.hidden)navigate(b.dataset.view)};
const mobileOrderObserver=new MutationObserver(()=>{if(state.user?.role==='Solicitante'&&!$('#mobile-new-order')){$('#bottom-nav')?.insertAdjacentHTML('beforeend','<button class="bottom-nav-item mobile-new-order" id="mobile-new-order" type="button" aria-label="Levantar reporte"><span class="nav-icon">＋</span><span class="nav-label">Nuevo reporte</span></button>')}});mobileOrderObserver.observe(document.body,{childList:true,subtree:true});
const fabBtn=$('#fab-new-order');if(fabBtn)fabBtn.onclick=null;
document.addEventListener('click',e=>{const button=e.target.closest('#fab-new-order,#new-order,#mobile-new-order');if(!button)return;e.preventDefault();e.stopImmediatePropagation();if(button.dataset.opening)return;button.dataset.opening='1';button.disabled=true;openOrder().catch(error=>toast(error.message)).finally(()=>{button.disabled=false;delete button.dataset.opening})},true);
$('#menu').onclick=()=>$('#sidebar').classList.toggle('open');$('#today').textContent=fmtDate(new Date());
(async()=>{try{enterApp(await api('/api/auth/me'))}catch{showLogin()}})();
document.addEventListener('click',e=>{const time=e.target.closest('.time-entry-order');if(time){document.querySelector('.modal-backdrop')?.remove();openTimeEntry(Number(time.dataset.id));}});
document.addEventListener('click',e=>{const b=e.target.closest('.issue-order-material');if(b){document.querySelector('.modal-backdrop')?.remove();openOrderMaterial(Number(b.dataset.id));}const r=e.target.closest('.inventory-return');if(r)openInventoryMovement({id:Number(r.dataset.id)},null,true);});
document.addEventListener('click',e=>{const b=e.target.closest('.reopen-order');if(b){const id=Number(b.dataset.id),version=Number(b.dataset.version);document.querySelector('.modal-backdrop')?.remove();modal('Reabrir orden',`<div class="field full"><label>Motivo de reapertura</label><textarea name="reason" required></textarea><span class="subtle">Se conservarán la validación anterior y los consumos.</span></div>`,d=>api(`/api/orders/${id}/transitions`,{method:'POST',body:JSON.stringify({...d,to:'Abierta',version})}));}});
