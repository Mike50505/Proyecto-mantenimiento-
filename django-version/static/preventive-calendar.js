const preventiveLabels = {P:'Planeado', T:'Ejecutado en plazo', D:'Ejecutado fuera de plazo', V:'Vencido', Cancelada:'Cancelada'};

async function openApplicabilityReview(planId) {
  const [plans,tasks] = await Promise.all([api('/api/preventives'),api(`/api/preventives/${planId}/tasks`)]);
  const plan = plans.find(item => item.id === planId);
  if (!plan) throw Error('Plan preventivo no disponible');
  const canEdit = state.user?.role === 'Administrador' || state.user?.actions?.includes('preventives.edit');
  const wrap = readModal(`Aplicabilidad · ${esc(plan.title)}`, `<p class="subtle">Cada tarea se revisa para este activo. Una tarea pendiente o marcada No aplica no genera nuevos vencimientos.</p>${tasks.length ? `<div class="table-wrap"><table><thead><tr><th>Tarea</th><th>Decisión</th><th>Evidencia</th><th></th></tr></thead><tbody>${tasks.map(task => `<tr data-applicability-task="${task.id}"><td>${esc(task.title)}</td><td>${canEdit ? `<select data-applicability-status><option value="">Seleccionar…</option>${['Interna','Externa','No aplica'].map(status => `<option ${status === task.applicability_status ? 'selected' : ''}>${status}</option>`).join('')}</select>` : badge(task.applicability_status)}${task.validated_at ? `<div class="subtle">${fmtDate(task.validated_at)}</div>` : ''}</td><td>${canEdit ? `<input data-applicability-reason value="${esc(task.applicability_reason)}" placeholder="Motivo de la decisión">` : esc(task.applicability_reason || 'Pendiente')}</td><td>${canEdit ? `<button type="button" class="order-action" data-save-applicability="${task.id}">Guardar revisión</button>` : ''}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Agrega tareas al plan antes de revisar aplicabilidad.</div>'}<button type="button" class="btn btn-secondary" data-back-to-tasks style="margin-top:16px">Ver tareas y fechas</button>`);
  wrap.querySelectorAll('[data-save-applicability]').forEach(button => button.addEventListener('click', async () => {
    const task = tasks.find(item => item.id === Number(button.dataset.saveApplicability));
    const row = button.closest('[data-applicability-task]');
    const status = row.querySelector('[data-applicability-status]')?.value || task.applicability_status;
    const reason = row.querySelector('[data-applicability-reason]')?.value.trim();
    button.disabled = true;
    try {
      await api(`/api/preventives/${planId}/tasks/${task.id}/applicability`,{method:'PATCH',body:JSON.stringify({status,reason,version:plan.version})});
      toast('Aplicabilidad revisada');
      wrap.remove();
      await openApplicabilityReview(planId);
    } catch (error) { toast(error.message); button.disabled = false; }
  }));
  wrap.querySelector('[data-back-to-tasks]')?.addEventListener('click', async () => {wrap.remove();try{await openPreventiveTasks(planId)}catch(error){toast(error.message)}});
}

async function openPreventivePlanner() {
  const plans = await api('/api/preventives');
  const wrap = readModal('Programar OT preventiva', `<p class="subtle">Selecciona un plan y después una tarea con fecha prevista. La misma OT aparecerá en Órdenes y Preventivos.</p>${plans.length ? `<div class="field"><label>Plan preventivo</label><select data-plan-picker>${plans.map(plan => `<option value="${plan.id}">${esc(plan.asset_code)} · ${esc(plan.title)}</option>`).join('')}</select></div><button type="button" class="btn btn-primary" data-open-plan>Ver tareas y fechas</button>` : '<div class="empty">No hay planes preventivos configurados. Crea uno en Preventivos o desde la ficha del activo.</div>'}`);
  wrap.querySelector('[data-open-plan]')?.addEventListener('click', async buttonEvent => {
    const button = buttonEvent.currentTarget;
    button.disabled = true;
    try { const id = Number(wrap.querySelector('[data-plan-picker]').value); wrap.remove(); await openPreventiveTasks(id); }
    catch (error) { toast(error.message); button.disabled = false; }
  });
}

function preventiveRange(view, anchor) {
  const date = new Date(`${anchor}T12:00:00Z`);
  const format = value => value.toISOString().slice(0, 10);
  if (view === 'annual') return {from:`${date.getUTCFullYear()}-01-01`, to:`${date.getUTCFullYear()}-12-31`};
  if (view === 'monthly') return {from:format(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1, 12))), to:format(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth()+1, 0, 12)))};
  if (view === 'weekly') {
    const monday = new Date(date); monday.setUTCDate(date.getUTCDate() - (date.getUTCDay()+6)%7);
    const sunday = new Date(monday); sunday.setUTCDate(monday.getUTCDate()+6);
    return {from:format(monday), to:format(sunday)};
  }
  const end = new Date(date); end.setUTCDate(end.getUTCDate()+89);
  return {from:format(date), to:format(end)};
}

function shiftPreventiveAnchor(anchor, view, direction) {
  const date = new Date(`${anchor}T12:00:00Z`);
  if (view === 'annual') {date.setUTCDate(1);date.setUTCFullYear(date.getUTCFullYear()+direction);}
  else if (view === 'monthly') {date.setUTCDate(1);date.setUTCMonth(date.getUTCMonth()+direction);}
  else date.setUTCDate(date.getUTCDate()+(view === 'weekly' ? 7 : 90)*direction);
  return date.toISOString().slice(0, 10);
}

function renderPreventiveMonth(rows, anchor) {
  const month=new Date(`${anchor}T12:00:00`);
  const first=new Date(month.getFullYear(),month.getMonth(),1,12);
  first.setDate(first.getDate()-(first.getDay()+6)%7);
  const dayKey=day=>`${day.getFullYear()}-${String(day.getMonth()+1).padStart(2,'0')}-${String(day.getDate()).padStart(2,'0')}`;
  const today=dayKey(new Date());
  const itemsByDate=new Map();
  rows.forEach((row,index)=>{
    const date=(row.base_date||'').slice(0,10);
    if(!itemsByDate.has(date))itemsByDate.set(date,[]);
    itemsByDate.get(date).push({row,index});
  });
  const days=Array.from({length:42},(_,index)=>{
    const day=new Date(first);day.setDate(first.getDate()+index);
    const key=dayKey(day),items=itemsByDate.get(key)||[];
    return `<div class="month-day ${day.getMonth()===month.getMonth()?'':'outside-month'} ${key===today?'today-cell':''} ${items.length?'has-preventive':''}"><span class="month-day-number">${day.getDate()}</span><div class="preventive-day-events">${items.map(({row,index:rowIndex})=>`<button type="button" class="month-event preventive-month-event ${row.status==='V'?'preventive-overdue':''}" data-calendar-open="${rowIndex}" title="${esc(`${row.asset_code} · ${row.task_title} · ${preventiveLabels[row.status]||row.status}${row.reprogrammed&&row.scheduled_at?' · Fecha vigente: '+fmtDate(row.scheduled_at):''}`)}"><b>${esc(row.asset_code)}</b><span>${esc(row.task_title)}</span><small>${esc(preventiveLabels[row.status]||row.status)}${row.reprogrammed?' · Reprogramado':''}</small></button>`).join('')}</div></div>`;
  });
  return `<div class="preventive-month-heading">${month.toLocaleDateString('es-MX',{month:'long',year:'numeric'})}</div><section class="month-calendar preventive-month-calendar" aria-label="Mantenimientos preventivos del mes"><div class="month-weekdays">${['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'].map(day=>`<span>${day}</span>`).join('')}</div><div class="month-grid">${days.join('')}</div></section>`;
}

async function mountPreventiveCalendar() {
  const section = document.createElement('section');
  section.className = 'card preventive-calendar-section';
  section.hidden=localStorage.getItem('mesa-preventive-mode')==='list';
  section.style.marginBottom = '18px';
  section.innerHTML = `<div class="table-head"><div><h3>Calendario preventivo</h3><p class="subtle">P: planeado · T: en plazo · D: fuera de plazo · V: vencido · R: reprogramado</p></div></div><div class="toolbar" style="padding:0 18px 16px;flex-wrap:wrap"><button type="button" class="btn btn-secondary" data-calendar-prev aria-label="Período anterior">←</button><select data-calendar-view aria-label="Vista del calendario"><option value="monthly">Mensual</option><option value="weekly">Semanal</option><option value="agenda">Agenda de 90 días</option><option value="annual">Anual por activo</option></select><input type="date" data-calendar-anchor aria-label="Fecha del calendario"><button type="button" class="btn btn-secondary" data-calendar-next aria-label="Período siguiente">→</button></div><div data-calendar-body style="padding:0 18px 18px" aria-live="polite"></div>`;
  document.querySelector('#content .preventive-mode-toolbar')?.insertAdjacentElement('afterend', section);
  const view = section.querySelector('[data-calendar-view]');
  const anchor = section.querySelector('[data-calendar-anchor]');
  const body = section.querySelector('[data-calendar-body]');
  anchor.value = new Date(Date.now() - new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);
  const canGenerate = state.user?.role === 'Administrador' || (state.user?.actions?.includes('preventives.edit') && state.user?.actions?.includes('orders.create'));
  let rows = [];
  const load = async () => {
    const range = preventiveRange(view.value, anchor.value);
    body.innerHTML = '<div class="empty">Cargando calendario…</div>';
    try {
      const data = await api(`/api/preventive-calendar?from=${range.from}&to=${range.to}`);
      if (!section.isConnected) return;
      rows = data.occurrences;
      const coverage = data.coverage.assets_without_configured_plan;
      const incomplete = data.coverage.incomplete_plans;
      const summary = `<div class="detail-summary"><div class="detail-box"><span>Período</span><strong>${fmtDate(range.from)} · ${fmtDate(range.to)}</strong></div><div class="detail-box"><span>Planeadas / vencidas</span><strong>${data.counts.P} / ${data.counts.V}</strong></div><div class="detail-box"><span>En plazo / fuera</span><strong>${data.counts.T} / ${data.counts.D}</strong></div></div>`;
      let content;
      if (view.value === 'monthly') {
        content=renderPreventiveMonth(rows,anchor.value);
      } else if (view.value === 'annual') {
        const assets = [...new Map(rows.map(row => [row.asset_id, {id:row.asset_id, code:row.asset_code, name:row.asset_name}])).values()];
        content = assets.length ? `<div class="table-wrap"><table><thead><tr><th>Activo</th>${Array.from({length:12}, (_,index)=>`<th>${new Date(Date.UTC(2026,index,1)).toLocaleDateString('es-MX',{month:'short',timeZone:'UTC'})}</th>`).join('')}</tr></thead><tbody>${assets.map(asset => `<tr><td>${esc(asset.code)}<div class="subtle">${esc(asset.name)}</div></td>${Array.from({length:12}, (_,month) => {const matches=rows.filter(row=>row.asset_id===asset.id && Number(row.base_date.slice(5,7))===month+1);return `<td><button type="button" class="order-action" data-calendar-month="${month+1}" aria-label="Ver ${matches.length} actividades de ${esc(asset.code)} en el mes ${month+1}">${matches.length ? `${matches.length} · ${[...new Set(matches.map(row=>row.status))].join('/')}` : '—'}</button></td>`}).join('')}</tr>`).join('')}</tbody></table></div>` : '<div class="empty">No hay tareas configuradas para este año.</div>';
      } else {
        content = rows.length ? `<div class="table-wrap"><table><thead><tr><th>Fecha base</th><th>Activo</th><th>Actividad</th><th>Estado</th><th>Fecha vigente</th><th>Orden</th></tr></thead><tbody>${rows.map((row,index) => `<tr><td>${fmtDate(row.base_date)}</td><td>${esc(row.asset_code)}<div class="subtle">${esc(row.asset_name)}</div></td><td>${esc(row.task_title)}<div class="subtle">${esc(row.plan_title)}</div></td><td>${badge(preventiveLabels[row.status]||row.status)}${row.reprogrammed ? ' · R' : ''}</td><td>${row.scheduled_at ? fmtDate(row.scheduled_at) : 'Sin OT'}</td><td>${row.work_order_id ? `<button class="order-action order-detail" data-id="${row.work_order_id}">${esc(row.folio)}</button>` : canGenerate ? `<button type="button" class="order-action" data-calendar-generate="${index}">Generar OT</button>` : 'Sin OT'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No hay tareas previstas en este período.</div>';
      }
      body.innerHTML = summary + content + (coverage.length || incomplete.length ? `<details style="margin-top:16px"><summary>Configuración pendiente: ${coverage.length} activos, ${incomplete.length} planes por revisar</summary><div class="subtle">${coverage.map(asset => `${esc(asset.asset_code)} · ${esc(asset.asset_name)}`).join('<br>')}${coverage.length && incomplete.length ? '<br>' : ''}${incomplete.map(plan => `${esc(plan.asset_code)} · ${esc(plan.title)}: ${esc(plan.reason)}`).join('<br>')}</div></details>` : '');
    } catch (error) { body.innerHTML = `<div class="empty">${esc(error.message)}</div>`; }
  };
  view.addEventListener('change', load);
  anchor.addEventListener('change', load);
  section.querySelector('[data-calendar-prev]').addEventListener('click', () => {anchor.value=shiftPreventiveAnchor(anchor.value,view.value,-1);load()});
  section.querySelector('[data-calendar-next]').addEventListener('click', () => {anchor.value=shiftPreventiveAnchor(anchor.value,view.value,1);load()});
  body.addEventListener('click', async event => {
    const calendarEvent=event.target.closest('[data-calendar-open]');
    if(calendarEvent){
      const row=rows[Number(calendarEvent.dataset.calendarOpen)];
      try{if(row.work_order_id)await openOrderDetail(row.work_order_id);else await openPreventiveTasks(row.plan_id)}catch(error){toast(error.message)}
      return;
    }
    const month = event.target.closest('[data-calendar-month]');
    if (month) {anchor.value=`${anchor.value.slice(0,4)}-${String(month.dataset.calendarMonth).padStart(2,'0')}-01`;view.value='monthly';load();return;}
    const button = event.target.closest('[data-calendar-generate]');
    if (!button) return;
    const row = rows[Number(button.dataset.calendarGenerate)];
    button.disabled = true;
    try {
      const result = await api(`/api/preventives/${row.plan_id}/occurrences`, {method:'POST',body:JSON.stringify({task_id:row.task_id,occurrence_index:row.occurrence_index,version:row.plan_version})});
      toast(result.replayed ? 'La tarea ya tenía una OT' : `OT ${result.folio} generada`);
      await load();
    } catch (error) { toast(error.message); button.disabled = false; }
  });
  await load();
  return section;
}

const originalRenderPreventives = renderPreventives;
renderPreventives = async function () {
  await originalRenderPreventives();
  const planList=document.querySelector('#content > .table-card');
  planList?.classList.add('preventive-plan-list');
  let mode=localStorage.getItem('mesa-preventive-mode')==='list'?'list':'calendar';
  if(planList)planList.hidden=mode!=='list';
  const modeToolbar=document.createElement('div');
  modeToolbar.className='agenda-toolbar preventive-mode-toolbar';
  modeToolbar.innerHTML='<div><h3>Vista del programa</h3><p class="subtle">Consulta las fechas por día o administra los planes en la lista.</p></div><div class="view-switch" role="group" aria-label="Vista de preventivos"><button type="button" data-preventive-mode="calendar">Calendario</button><button type="button" data-preventive-mode="list">Lista</button></div>';
  document.querySelector('#content .section-head')?.insertAdjacentElement('afterend',modeToolbar);
  document.querySelectorAll('.preventive-tasks').forEach(button => {
    const review = document.createElement('button');
    review.type='button';review.className='order-action';review.textContent='Aplicabilidad';
    review.addEventListener('click', () => openApplicabilityReview(Number(button.dataset.id)).catch(error => toast(error.message)));
    button.after(review);
  });
  document.querySelectorAll('.generate-order').forEach(button => {
    const replacement = button.cloneNode(true);
    replacement.textContent = 'Elegir tarea y fecha';
    button.replaceWith(replacement);
    replacement.addEventListener('click', () => openPreventiveTasks(Number(replacement.dataset.id)).catch(error => toast(error.message)));
  });
  const calendarSection=await mountPreventiveCalendar();
  if(!modeToolbar.isConnected)return;
  const setMode=()=>{
    calendarSection.hidden=mode!=='calendar';
    if(planList)planList.hidden=mode!=='list';
    modeToolbar.querySelectorAll('[data-preventive-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.preventiveMode===mode)));
  };
  modeToolbar.querySelectorAll('[data-preventive-mode]').forEach(button=>button.onclick=()=>{mode=button.dataset.preventiveMode;localStorage.setItem('mesa-preventive-mode',mode);setMode()});
  setMode();
};

const originalOpenPreventiveTasks = openPreventiveTasks;
openPreventiveTasks = async function (id) {
  await originalOpenPreventiveTasks(id);
  const wrap = [...document.querySelectorAll('.modal-backdrop')].at(-1);
  if (!wrap) return;
  const tasks = await api(`/api/preventives/${id}/tasks`);
  const pending = tasks.filter(task => task.applicability_status === 'Pendiente').length;
  const action = document.createElement('div');
  action.className='detail-box';action.style.marginBottom='14px';
  action.innerHTML=`<span>Aplicabilidad por activo</span><strong>${pending ? `${pending} tarea(s) pendientes de revisión` : 'Sin tareas pendientes'}</strong> <button type="button" class="btn btn-secondary" data-review-applicability>Revisar aplicabilidad</button>`;
  wrap.querySelector('[data-task-list]')?.before(action);
  action.querySelector('button').addEventListener('click', async () => {wrap.remove();try{await openApplicabilityReview(id)}catch(error){toast(error.message)}});
};

const originalRenderOrders = renderOrders;
renderOrders = async function () {
  await originalRenderOrders();
  if (state.user?.role === 'Solicitante' || !(state.user?.role === 'Administrador' || (state.user?.actions?.includes('preventives.edit') && state.user?.actions?.includes('orders.create')))) return;
  const toolbar = document.querySelector('#content .section-head .toolbar');
  if (!toolbar) return;
  const button = document.createElement('button');
  button.type='button';button.className='btn btn-secondary';button.textContent='Programar OT preventiva';
  button.addEventListener('click', () => openPreventivePlanner().catch(error => toast(error.message)));
  toolbar.insertBefore(button, document.querySelector('#new-order'));
};

const originalOpenOrder = openOrder;
openOrder = async function (...args) {
  await originalOpenOrder(...args);
  const wrap = [...document.querySelectorAll('.modal-backdrop')].at(-1);
  const classification = wrap?.querySelector('select[name="classification"]');
  classification?.querySelectorAll('option').forEach(option => {if (option.value === 'Mantenimiento Preventivo') option.remove()});
  if (classification && (state.user?.role === 'Administrador' || state.user?.actions?.includes('preventives.edit'))) {
    classification.insertAdjacentHTML('afterend','<span class="subtle">Las OT preventivas se programan desde una tarea y fecha del plan.</span>');
  }
};
