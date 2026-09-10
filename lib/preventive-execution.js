'use strict';
function migrate(db){
  db.exec(`CREATE TABLE IF NOT EXISTS preventive_execution_events (
    id INTEGER PRIMARY KEY,
    occurrence_id INTEGER NOT NULL REFERENCES preventive_occurrences(id),
    work_order_version INTEGER NOT NULL,
    event TEXT NOT NULL CHECK(event IN ('terminated','validated','returned','cancelled','reopened')),
    user_id INTEGER NOT NULL REFERENCES users(id),
    recorded_at TEXT NOT NULL,
    notes TEXT,
    reason TEXT,
    UNIQUE(occurrence_id,work_order_version)
  );
  CREATE TRIGGER IF NOT EXISTS preventive_execution_no_update BEFORE UPDATE ON preventive_execution_events
    BEGIN SELECT RAISE(ABORT,'El evento de ejecución es inmutable'); END;
  CREATE TRIGGER IF NOT EXISTS preventive_execution_no_delete BEFORE DELETE ON preventive_execution_events
    BEGIN SELECT RAISE(ABORT,'El evento de ejecución es inmutable'); END;`);
}
// Called inside the order command transaction; never commits independently.
function record(db,before,next,userId,input,now){
  const occurrences=db.prepare('SELECT id FROM preventive_occurrences WHERE work_order_id=? ORDER BY id').all(before.id);
  if(!occurrences.length)return;
  const event=next==='Pendiente de validación'?'terminated':next==='Completada'?'validated':next==='Cancelada'?'cancelled':
    ['Completada','Cancelada'].includes(before.status)?'reopened':before.status==='Pendiente de validación'&&next==='En proceso'?'returned':null;
  if(!event)return;
  const insert=db.prepare(`INSERT INTO preventive_execution_events
    (occurrence_id,work_order_version,event,user_id,recorded_at,notes,reason) VALUES (?,?,?,?,?,?,?)`)
  for(const occurrence of occurrences) insert.run(occurrence.id,before.version+1,event,userId,now,
      event==='terminated'?String(input.closure_notes||before.closure_notes||''):input.comment||null,input.reason||null);
}
function read(db,orderId){
  const occurrence=db.prepare('SELECT * FROM preventive_occurrences WHERE work_order_id=?').get(orderId);
  if(!occurrence)return null;
  const events=db.prepare('SELECT * FROM preventive_execution_events WHERE occurrence_id=? ORDER BY id').all(occurrence.id);
  const latest=events.at(-1);
  const states={terminated:'Pendiente de validación',validated:'Validada',returned:'Devuelta a trabajo',cancelled:'Cancelada',reopened:'Reabierta'};
  const items=db.prepare('SELECT id,task_id,base_date FROM preventive_occurrences WHERE work_order_id=? ORDER BY id').all(orderId);
  return {occurrence_id:occurrence.id,task_id:occurrence.task_id,base_date:occurrence.base_date,items,
    state:states[latest?.event]||'Sin ejecución registrada',
    executed_at:['terminated','validated'].includes(latest?.event)?events.findLast(e=>e.event==='terminated')?.recorded_at||null:null,
    validated_at:latest?.event==='validated'?latest.recorded_at:null,events};
}
module.exports={migrate,record,read};
