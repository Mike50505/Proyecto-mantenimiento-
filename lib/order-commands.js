'use strict';
const fail=(message,status=400)=>{throw Object.assign(new Error(message),{status});};
module.exports=function orderCommand(db,user,id,b,validate=false){
 db.exec('BEGIN IMMEDIATE');
 try{
  const before=db.prepare('SELECT * FROM work_orders WHERE id=?').get(id);if(!before)fail('Orden no encontrada',404);
  if(!Number.isInteger(Number(b.version))||Number(b.version)!==before.version)fail('La orden cambió. Consulta la versión actual antes de continuar.',409);
  const manager=['Administrador','Jefatura'].includes(user.role);
  if(user.role==='Solicitante'||(!manager&&before.technician_id!==user.id))fail('Solo el técnico asignado o Jefatura puede atender esta orden',403);
  if(validate&&!manager)fail('Solo Jefatura o Administrador puede validar el cierre',403);
  const next=validate?'Completada':String(b.to||'');
  const transitions={Abierta:['Programada','En proceso','Cancelada'],Programada:['En proceso','Abierta','Cancelada'],'En proceso':['Pausada','Espera de material','Pendiente de validación','Cancelada'],Pausada:['En proceso','Cancelada'],'Espera de material':['En proceso','Cancelada'],'Pendiente de validación':['Completada','En proceso'],Completada:['Abierta'],Cancelada:['Abierta']};
  if(!transitions[before.status]?.includes(next)||(!validate&&next==='Completada'))fail('Usa la acción correspondiente al estado actual de la orden');
  const reopen=['Completada','Cancelada'].includes(before.status);
  if(reopen&&!manager)fail('La reapertura requiere permiso de Jefatura',403);
  if((next==='Cancelada'||reopen)&&!String(b.reason||'').trim())fail('Esta acción requiere un motivo');
  if(next==='Pendiente de validación'){
   if(!before.actions?.trim())fail('Registra las acciones realizadas antes de terminar');
   if(!String(b.closure_notes||before.closure_notes||'').trim())fail('Registra las notas documentales del cierre antes de terminar');
   if((b.closure_document_code&&!b.closure_document_revision)||(b.closure_document_revision&&!b.closure_document_code))fail('El cÃ³digo y la revisiÃ³n documental deben capturarse juntos');
   if(!before.technician_id)fail('Asigna un técnico responsable antes de terminar');
   if(!db.prepare('SELECT 1 FROM work_order_time_entries WHERE work_order_id=? LIMIT 1').get(id))fail('Registra al menos una sesión de trabajo');
   if(db.prepare('SELECT 1 FROM work_order_time_entries WHERE work_order_id=? AND finished_at IS NULL AND user_id<>?').get(id,user.id))fail('Otro participante tiene una sesión activa. Debe pausarla o terminarla.');
  }
  const now=new Date().toISOString();
  if(next==='En proceso'){
   const active=db.prepare('SELECT work_order_id FROM work_order_time_entries WHERE user_id=? AND finished_at IS NULL').get(user.id);
   if(active&&active.work_order_id!==id)fail('Ya tienes una sesión activa en otra orden',409);
   if(!active)db.prepare("INSERT INTO work_order_time_entries(work_order_id,user_id,started_at,source) VALUES(?,?,?,'timer')").run(id,user.id,now);
  }else if(['Pausada','Espera de material','Pendiente de validación','Cancelada'].includes(next)){
   db.prepare('UPDATE work_order_time_entries SET finished_at=?,pause_reason=? WHERE work_order_id=? AND finished_at IS NULL AND user_id=?').run(now,b.reason||next,id,user.id);
  }
  const rows=db.prepare('SELECT started_at,finished_at FROM work_order_time_entries WHERE work_order_id=? AND finished_at IS NOT NULL').all(id);
  const hours=Math.round(rows.reduce((sum,row)=>sum+Math.max(0,Date.parse(row.finished_at)-Date.parse(row.started_at))/3600000,0)*100)/100;
  db.prepare(`UPDATE work_orders SET status=?,validation_status=?,finished_at=?,closed_at=?,validator_id=?,validated_at=?,labor_hours=?,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?`).run(next,validate?'Validada':next==='Pendiente de validación'?'Pendiente':reopen?'No aplica':before.validation_status,next==='Pendiente de validación'?now:before.finished_at,validate?now:before.closed_at,validate?user.id:before.validator_id,validate?now:before.validated_at,hours,id);
  db.prepare('INSERT INTO work_order_events(work_order_id,user_id,event,details) VALUES(?,?,?,?)').run(id,user.id,validate?'Cierre validado':reopen?'Orden reabierta':'Cambio de estado',`${before.status} → ${next}${b.reason?' · '+b.reason:''}`);
  if(next==='Pendiente de validación') db.prepare('UPDATE work_orders SET closure_notes=COALESCE(?,closure_notes),closure_document_code=COALESCE(?,closure_document_code),closure_document_revision=COALESCE(?,closure_document_revision) WHERE id=?').run(b.closure_notes||null,b.closure_document_code||null,b.closure_document_revision||null,id);
  require('./preventive-execution').record(db,before,next,user.id,b,now);
  db.prepare('INSERT INTO audit_log(user_id,entity_type,entity_id,action,before_json,after_json,reason) VALUES(?,?,?,?,?,?,?)').run(user.id,'work_order',id,validate?'validated':'transition',JSON.stringify(before),JSON.stringify({status:next,version:before.version+1}),b.reason||null);
  // Liberar maquinaria es una acción independiente: no cambia por cerrar una OT.
  db.exec('COMMIT');return {ok:true,status:next,version:before.version+1};
 }catch(e){db.exec('ROLLBACK');throw e;}
};
