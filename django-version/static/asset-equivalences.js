const originalOpenAssetDetail = openAssetDetail;
openAssetDetail = async function (id) {
  await originalOpenAssetDetail(id);
  const asset = await api(`/api/assets/${id}`);
  const wrap = [...document.querySelectorAll('.modal-backdrop')].at(-1);
  if (!wrap || !wrap.isConnected) return;
  const plans = asset.preventive_plans || [];
  const stops = asset.downtime_events || [];
  const materials = asset.material_usage || [];
  const readings = asset.meter_readings || [];
  const canSchedule = state.user?.role === 'Administrador' || state.user?.actions?.includes('preventives.edit');
  const dossier = `<section class="machine-sheet" style="margin-top:20px">
    <div class="table-head" style="padding:0"><h3>Expediente operativo</h3>${canSchedule ? '<button class="btn btn-secondary schedule-asset-preventive">+ Programar preventivo</button>' : ''}</div>
    <div class="machine-grid">
      <div><span>Estado y causa</span><strong>${esc(asset.operational_status)}${asset.operational_status_cause ? ` · ${esc(asset.operational_status_cause)}` : ''}</strong><small>${asset.operational_status_updated_at ? fmtDate(asset.operational_status_updated_at) : 'Sin fecha de actualización'}</small></div>
      <div><span>Ubicación</span><strong>${esc(asset.area || 'Sin ubicación')}</strong></div>
      <div><span>Horas hombre</span><strong>${Number((asset.maintenances || []).reduce((total, order) => total + Number(order.labor_hours || 0), 0)).toFixed(2)} h</strong></div>
      <div><span>Material neto</span><strong>${money(asset.metrics.material_cost)}</strong></div>
    </div>
    <details style="margin-top:16px" open><summary>Preventivos (${plans.length})</summary>${plans.length ? `<div class="table-wrap"><table><thead><tr><th>Actividad</th><th>Próxima fecha</th><th>Estado</th><th>Responsable</th><th>Orden</th></tr></thead><tbody>${plans.map(plan => `<tr><td>${esc(plan.title)}<div class="subtle">${esc(plan.template_code || 'Sin plantilla')} · ${plan.task_count} tareas · v${plan.version}</div></td><td>${fmtDate(plan.next_date)}</td><td>${badge(plan.status)}</td><td>${esc(plan.responsible_name || 'Sin asignar')}</td><td>${plan.work_order_id ? `<button class="order-action order-detail" data-id="${plan.work_order_id}">Ver OT</button>` : 'Sin OT'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Este activo no tiene plan preventivo.</div>'}</details>
    <details style="margin-top:16px"><summary>Paros (${stops.length})</summary>${stops.length ? `<div class="table-wrap"><table><thead><tr><th>Inicio</th><th>Fin</th><th>Causa</th><th>Órdenes relacionadas</th></tr></thead><tbody>${stops.map(stop => `<tr><td>${fmtDate(stop.started_at)}</td><td>${stop.finished_at ? fmtDate(stop.finished_at) : 'Abierto'}</td><td>${esc(stop.cause)}${stop.close_reason ? `<div class="subtle">Cierre: ${esc(stop.close_reason)}</div>` : ''}</td><td>${stop.work_order_ids.length ? stop.work_order_ids.map(orderId => `<button class="order-action order-detail" data-id="${orderId}">OT #${orderId}</button>`).join(' ') : 'Sin OT'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No hay paros registrados.</div>'}</details>
    <details style="margin-top:16px"><summary>Materiales consumidos (${materials.length})</summary>${materials.length ? `<div class="table-wrap"><table><thead><tr><th>OT</th><th>Material</th><th>Salida</th><th>Devuelto</th><th>Neto</th><th>Costo neto</th></tr></thead><tbody>${materials.map(item => `<tr><td><button class="order-action order-detail" data-id="${item.work_order_id}">${esc(item.folio)}</button></td><td>${esc(item.code)} · ${esc(item.description)}</td><td>${item.quantity}</td><td>${item.returned_quantity}</td><td>${item.net_quantity}</td><td>${money(item.net_cost)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No hay consumos asociados a órdenes de este activo.</div>'}</details>
    <details style="margin-top:16px"><summary>Últimas lecturas de horómetro (${readings.length})</summary>${readings.length ? `<div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Lectura</th><th>Nota</th></tr></thead><tbody>${readings.map(reading => `<tr><td>${fmtDate(reading.recorded_at)}</td><td>${reading.value} h</td><td>${esc(reading.notes || '—')}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No hay lecturas registradas.</div>'}</details>
  </section>`;
  wrap.querySelector('.machine-sheet')?.insertAdjacentHTML('afterend', dossier);
  wrap.querySelector('.schedule-asset-preventive')?.addEventListener('click', async () => {
    wrap.remove();
    try {
      await openPreventive();
      const form = [...document.querySelectorAll('.modal-backdrop')].at(-1);
      const select = form?.querySelector('select[name="asset_id"]');
      if (select) select.value = String(id);
    } catch (error) { toast(error.message); }
  });
};
