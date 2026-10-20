(() => {
  const canSchedule=()=>state.user?.actions?.includes('preventives.edit')&&state.user?.actions?.includes('orders.create')&&state.user?.permissions?.includes('orders');
  const dateInput=value=>{
    const date=new Date(value);return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
  };
  openPreventive=async function(plan=null){
    if(!canSchedule()){toast('Necesitas permisos para programar preventivos y crear órdenes.');return;}
    const c=await catalogs();
    const tomorrow=new Date();tomorrow.setDate(tomorrow.getDate()+1);tomorrow.setHours(9,0,0,0);
    const original=plan?.next_date?new Date(`${plan.next_date}T09:00`):null;
    const first=original&&original>new Date()?original:tomorrow;
    const technicians=c.users.filter(user=>['Técnico','Jefatura','Jefe de mantenimiento'].includes(user.role));
    const key=makeRequestKey();let saved;
    const wrap=modal(plan?'Programar como OT preventiva':'Programar OT preventiva',`
      <div class="field full"><label for="preventive-work">Trabajo a realizar</label><input id="preventive-work" name="title" required maxlength="250" value="${esc(plan?.title||'')}" placeholder="Ej. Lubricar y revisar la prensa"></div>
      <div class="field"><label for="preventive-asset">Activo</label><select id="preventive-asset" name="asset_id" required><option value="">Seleccionar activo…</option>${c.assets.map(asset=>`<option value="${asset.id}" ${asset.id===plan?.asset_id?'selected':''}>${esc(asset.name)}</option>`).join('')}</select></div>
      <div class="field"><label for="preventive-date">Primera fecha y hora</label><input id="preventive-date" name="scheduled_at" type="datetime-local" required value="${dateInput(first)}"></div>
      ${state.user.actions.includes('orders.assign')?`<div class="field"><label for="preventive-technician">Responsable</label><select id="preventive-technician" name="technician_id"><option value="">Sin asignar</option>${technicians.map(user=>`<option value="${user.id}" ${user.id===plan?.responsible_id?'selected':''}>${esc(user.name)} ${esc(user.last_name||'')}</option>`).join('')}</select></div>`:''}
      <div class="field"><label for="preventive-repeat">Repetición</label><select id="preventive-repeat" name="repeat"><option value="none">Una sola vez</option><option value="days">Cada ciertos días</option><option value="weeks">Cada ciertas semanas</option><option value="months">Cada ciertos meses</option><option value="years">Cada ciertos años</option></select></div>
      <div class="field" data-repeat-fields hidden><label for="preventive-interval">Repetir cada</label><input id="preventive-interval" name="interval" type="number" min="1" max="100" step="1" value="1" required><span class="subtle" data-repeat-unit></span></div>
      <div class="field" data-repeat-fields hidden><label for="preventive-until">Repetir hasta (opcional)</label><input id="preventive-until" name="repeat_until" type="date"><span class="subtle">Vacío mantiene la repetición hasta que la detengas.</span></div>
      <div class="field full"><p class="subtle">Al guardar se crean OT programadas. Si se repite, se programan los próximos 90 días y la agenda se amplía automáticamente.</p></div>`,async data=>{
        saved=await api('/api/preventive-orders/schedule',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({...data,...(plan?{plan_id:plan.id,version:plan.version}:{})})});
        state.preventiveCalendarAnchor=data.scheduled_at.slice(0,10);state.preventiveCalendarView='monthly';
      },async()=>{await render();toast(`${saved.folio}: ${saved.created||1} OT programada(s)`)});
    const repeat=wrap.querySelector('[name="repeat"]');
    const update=()=>{
      const repeating=repeat.value!=='none';
      wrap.querySelectorAll('[data-repeat-fields]').forEach(field=>{field.hidden=!repeating;field.querySelector('input').disabled=!repeating});
      wrap.querySelector('[data-repeat-unit]').textContent={days:'días',weeks:'semanas',months:'meses',years:'años'}[repeat.value]||'';
    };
    repeat.addEventListener('change',update);update();
  };
  openPreventivePlanner=async()=>openPreventive();

  function stopRepetition(planId,title){
    modal('Detener repetición',`<div class="field full"><p>Dejarán de crearse nuevas OT para <strong>${esc(title)}</strong>. Las OT ya programadas siguen en la agenda; puedes cancelarlas o borrarlas individualmente con sus permisos.</p><label for="stop-repetition-reason">Motivo</label><textarea id="stop-repetition-reason" name="reason" required maxlength="2000"></textarea></div>`,data=>api(`/api/preventive-orders/${planId}/stop`,{method:'POST',body:JSON.stringify(data)}));
  }

  renderPreventives=async function(){
    const data=await api('/api/preventive-orders');
    const canReadOrders=state.user.actions.includes('orders.read');
    const series=data.active_series||[];
    $('#content').innerHTML=`<div class="section-head"><div><h2>OT preventivas</h2><p>OT futuras y sus repeticiones, con todas sus fechas en el calendario.</p></div><div class="toolbar"><a class="btn btn-secondary" href="/api/orders/export.xlsx?classification=${encodeURIComponent('Mantenimiento Preventivo')}">Exportar OT</a>${canSchedule()?'<button class="btn btn-primary" id="new-preventive">+ Programar OT preventiva</button>':''}</div></div>
      <div class="agenda-toolbar preventive-mode-toolbar"><div><h3>Agenda preventiva</h3><p class="subtle">Las mismas órdenes aparecen en Órdenes de trabajo.</p></div><div class="view-switch" role="group" aria-label="Vista de preventivos"><button type="button" data-preventive-mode="calendar">Calendario</button><button type="button" data-preventive-mode="list">Lista</button></div></div>
      <section class="card table-card preventive-plan-list"><div class="table-head"><h3>Órdenes preventivas</h3><span class="subtle">Todas las fechas programadas.</span></div><div id="preventive-orders-table"></div></section>
      ${series.length&&state.user.actions.includes('preventives.edit')?`<details class="card" style="padding:20px;margin-top:18px"><summary>Repeticiones activas (${series.length})</summary><div class="table-wrap"><table><thead><tr><th>Trabajo</th><th>Activo</th><th>Repetición</th><th></th></tr></thead><tbody>${series.map(order=>`<tr><td>${esc(order.title)}</td><td>${esc(order.asset_name)}</td><td>${esc(order.frequency)}</td><td><button type="button" class="order-action" data-stop-repetition="${order.plan_id}">Detener repetición</button>${deleteSeriesButton(order.plan_id)}</td></tr>`).join('')}</tbody></table></div></details>`:''}
      ${data.legacy_plans.length?`<details class="card" style="padding:20px;margin-top:18px"><summary>Programaciones anteriores (${data.legacy_plans.length})</summary><p class="subtle">Puedes convertir las programaciones que todavía no tienen tareas en OT futuras.</p><div class="table-wrap"><table><thead><tr><th>Trabajo</th><th>Activo</th><th>Fecha anterior</th><th></th></tr></thead><tbody>${data.legacy_plans.map(plan=>`<tr><td>${esc(plan.title)}</td><td>${esc(plan.asset_name)}</td><td>${fmtDate(plan.next_date)}</td><td>${plan.can_convert&&canSchedule()?`<button type="button" class="order-action" data-convert-preventive="${plan.id}">Programar como OT</button>`:`<button type="button" class="order-action" data-old-preventive="${plan.id}">Ver programación anterior</button>`}</td></tr>`).join('')}</tbody></table></div></details>`:''}`;
    const paint=()=>{
      const orders=data.orders;
      $('#preventive-orders-table').innerHTML=`<div class="table-wrap"><table><thead><tr><th>Folio</th><th>Fecha programada</th><th>Activo</th><th>Trabajo</th><th>Repetición</th><th>Responsable</th><th>Estado</th><th></th></tr></thead><tbody>${orders.map(order=>`<tr><td class="folio">${esc(order.folio)}</td><td>${order.scheduled_at?new Intl.DateTimeFormat('es-MX',{dateStyle:'medium',timeStyle:'short'}).format(new Date(order.scheduled_at)):'Sin fecha'}</td><td>${esc(order.asset_name)}</td><td>${esc(order.title)}</td><td>${esc(order.frequency)}${order.repeating&&!order.repetition_active?'<div class="subtle">Repetición detenida</div>':''}</td><td>${esc(order.technician_name||'Sin asignar')}</td><td>${badge(order.status)}</td><td>${canReadOrders?`<button type="button" class="order-action order-detail" data-id="${order.id}">Abrir OT</button>`:''}${deleteRecordButton('orders',order.id,order.folio,order.version,order.recurrent_plan_id)}</td></tr>`).join('')||'<tr><td colspan="8" class="empty">Todavía no hay OT preventivas programadas.</td></tr>'}</tbody></table></div>`;
    };
    paint();
    $('#new-preventive')?.addEventListener('click',()=>openPreventive().catch(error=>toast(error.message)));
    document.querySelectorAll('[data-convert-preventive]').forEach(button=>button.addEventListener('click',()=>openPreventive(data.legacy_plans.find(plan=>plan.id===Number(button.dataset.convertPreventive))).catch(error=>toast(error.message))));
    document.querySelectorAll('[data-old-preventive]').forEach(button=>button.addEventListener('click',()=>openPreventiveTasks(Number(button.dataset.oldPreventive)).catch(error=>toast(error.message))));
    document.querySelectorAll('[data-stop-repetition]').forEach(button=>button.addEventListener('click',()=>{const order=series.find(order=>order.plan_id===Number(button.dataset.stopRepetition));stopRepetition(order.plan_id,order.title)}));
    const calendar=await mountPreventiveCalendar();
    const list=$('.preventive-plan-list');
    const toolbar=$('.preventive-mode-toolbar');
    if(!toolbar?.isConnected)return;
    let mode=localStorage.getItem('mesa-preventive-mode')==='list'?'list':'calendar';
    const setMode=()=>{
      calendar.hidden=mode!=='calendar';list.hidden=mode!=='list';
      toolbar.querySelectorAll('[data-preventive-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.preventiveMode===mode)));
    };
    toolbar.querySelectorAll('[data-preventive-mode]').forEach(button=>button.addEventListener('click',()=>{mode=button.dataset.preventiveMode;localStorage.setItem('mesa-preventive-mode',mode);setMode()}));
    setMode();
  };
})();
