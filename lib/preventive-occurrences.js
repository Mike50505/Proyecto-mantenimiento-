'use strict';
const {dueDate}=require('./preventive-tasks');
const error=(message,status=400)=>Object.assign(new Error(message),{status});
function migrate(db){
  const existing=db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='preventive_occurrences'").get();
  if(existing){
    const uniqueWorkOrder=db.prepare("SELECT 1 FROM pragma_index_list('preventive_occurrences') i JOIN pragma_index_info(i.name) x ON x.seqno=0 WHERE i.[unique]=1 AND x.name='work_order_id'").get();
    if(uniqueWorkOrder){
      db.exec(`PRAGMA foreign_keys=OFF; DROP TRIGGER IF EXISTS occurrence_base_immutable; DROP TRIGGER IF EXISTS occurrence_no_delete; ALTER TABLE preventive_occurrences RENAME TO preventive_occurrences_legacy;`);
      db.exec(`CREATE TABLE preventive_occurrences (
        id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES preventive_tasks(id), occurrence_index INTEGER NOT NULL CHECK(occurrence_index>=0),
        base_date TEXT NOT NULL, plan_id INTEGER NOT NULL, plan_version INTEGER NOT NULL, work_order_id INTEGER NOT NULL REFERENCES work_orders(id),
        created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(task_id,occurrence_index),
        FOREIGN KEY(plan_id,plan_version) REFERENCES preventive_plan_revisions(plan_id,version));
        INSERT INTO preventive_occurrences SELECT * FROM preventive_occurrences_legacy;
        DROP TABLE preventive_occurrences_legacy; PRAGMA foreign_keys=ON;`);
    }
  }
  db.exec(`CREATE TABLE IF NOT EXISTS preventive_occurrences (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES preventive_tasks(id),
    occurrence_index INTEGER NOT NULL CHECK(occurrence_index>=0),
    base_date TEXT NOT NULL,
    plan_id INTEGER NOT NULL,
    plan_version INTEGER NOT NULL,
    work_order_id INTEGER NOT NULL REFERENCES work_orders(id),
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id,occurrence_index),
    FOREIGN KEY(plan_id,plan_version) REFERENCES preventive_plan_revisions(plan_id,version)
  ); CREATE INDEX IF NOT EXISTS idx_occurrences_plan ON preventive_occurrences(plan_id,base_date);
  CREATE TRIGGER IF NOT EXISTS occurrence_base_immutable BEFORE UPDATE OF task_id,occurrence_index,base_date,plan_id,plan_version,work_order_id ON preventive_occurrences
    BEGIN SELECT RAISE(ABORT,'La identidad y fecha base de la ocurrencia son inmutables'); END;
  CREATE TRIGGER IF NOT EXISTS occurrence_no_delete BEFORE DELETE ON preventive_occurrences
    BEGIN SELECT RAISE(ABORT,'La ocurrencia debe conservarse'); END;`);
}
function generate(db,planId,input,userId,nextFolio,audit){
  if(!Number.isSafeInteger(input.task_id)||!Number.isSafeInteger(input.occurrence_index)||input.occurrence_index<0)throw error('Indica tarea e índice de ocurrencia válidos');
  db.exec('BEGIN IMMEDIATE');
  try{
    const plan=db.prepare('SELECT * FROM preventive_plans WHERE id=?').get(planId);
    const task=db.prepare('SELECT * FROM preventive_tasks WHERE id=? AND plan_id=?').get(input.task_id,planId);
    if(!task)throw error('Tarea no encontrada en el plan',404);
    const existing=db.prepare(`SELECT o.*,w.folio FROM preventive_occurrences o JOIN work_orders w ON w.id=o.work_order_id
      WHERE o.task_id=? AND o.occurrence_index=?`).get(task.id,input.occurrence_index);
    if(existing){db.exec('COMMIT');return {...existing,replayed:true};}
    if(plan.work_order_id)throw error('El plan ya tiene una OT del flujo anterior; requiere conciliación antes de generar ocurrencias',409);
    if(input.version!==plan.version)throw error('Recarga la versión del preventivo',409);
    const baseDate=dueDate(task,input.occurrence_index),folio=nextFolio();
    const result=db.prepare(`INSERT INTO work_orders
      (folio,requested_at,requester_id,priority,classification,asset_id,reported_failure,technician_id,status,scheduled_at)
      VALUES (?,?,?,?,?,?,?,?,?,?)`).run(folio,new Date().toISOString(),userId,'Media','Mantenimiento Preventivo',plan.asset_id,
        [task.title,plan.instructions].filter(Boolean).join(' · '),plan.responsible_id,'Programada',baseDate);
    const orderId=Number(result.lastInsertRowid);
    db.prepare('INSERT INTO preventive_order_revisions (work_order_id,plan_id,version) VALUES (?,?,?)').run(orderId,planId,plan.version);
    const occurrence=db.prepare(`INSERT INTO preventive_occurrences
      (task_id,occurrence_index,base_date,plan_id,plan_version,work_order_id,created_by) VALUES (?,?,?,?,?,?,?)`)
      .run(task.id,input.occurrence_index,baseDate,planId,plan.version,orderId,userId);
    const id=Number(occurrence.lastInsertRowid);
    db.prepare('INSERT INTO work_order_events (work_order_id,user_id,event,details) VALUES (?,?,?,?)')
      .run(orderId,userId,'Ocurrencia preventiva programada',`Tarea #${task.id}, fecha base ${baseDate}, revisión ${plan.version}`);
    audit(userId,'preventive_occurrence',id,'created',null,{task_id:task.id,base_date:baseDate,work_order_id:orderId,plan_version:plan.version});
    db.exec('COMMIT');return {id,work_order_id:orderId,folio,base_date:baseDate,replayed:false};
  }catch(failure){db.exec('ROLLBACK');throw failure;}
}
function generateGroup(db,planId,input,userId,nextFolio,audit){
  if(!Array.isArray(input.occurrences)||input.occurrences.length<2)throw error('Indica al menos dos tareas para agrupar');
  db.exec('BEGIN IMMEDIATE');
  try{
    const plan=db.prepare('SELECT * FROM preventive_plans WHERE id=?').get(planId);
    if(!plan)throw error('Preventivo no encontrado',404);
    if(plan.work_order_id)throw error('El plan ya tiene una OT del flujo anterior; requiere conciliación',409);
    if(input.version!==plan.version)throw error('Recarga la versión del preventivo',409);
    const items=input.occurrences.map(item=>{
      if(!Number.isSafeInteger(item.task_id)||!Number.isSafeInteger(item.occurrence_index)||item.occurrence_index<0)throw error('Cada tarea debe indicar un índice válido');
      const task=db.prepare('SELECT * FROM preventive_tasks WHERE id=? AND plan_id=?').get(item.task_id,planId);
      if(!task)throw error('Tarea no encontrada en el plan',404);
      const existing=db.prepare('SELECT work_order_id FROM preventive_occurrences WHERE task_id=? AND occurrence_index=?').get(task.id,item.occurrence_index);
      return {task,occurrence_index:item.occurrence_index,baseDate:dueDate(task,item.occurrence_index),existing};
    });
    if(new Set(items.map(item=>item.task.id+':'+item.occurrence_index)).size!==items.length)throw error('No repitas tareas en el grupo');
    if(new Set(items.map(item=>item.baseDate)).size!==1)throw error('Las tareas agrupadas deben compartir fecha base');
    const existing=items.filter(item=>item.existing);
    if(existing.length){
      if(existing.length===items.length&&new Set(existing.map(item=>item.existing.work_order_id)).size===1){
        const order=db.prepare('SELECT folio FROM work_orders WHERE id=?').get(existing[0].existing.work_order_id);
        db.exec('COMMIT');return {work_order_id:existing[0].existing.work_order_id,folio:order.folio,replayed:true};
      }
      throw error('Una o más tareas ya tienen una OT incompatible',409);
    }
    const baseDate=items[0].baseDate,folio=nextFolio();
    const detail=[plan.title,...items.map(item=>item.task.title),plan.instructions].filter(Boolean).join(' · ');
    const result=db.prepare(`INSERT INTO work_orders
      (folio,requested_at,requester_id,priority,classification,asset_id,reported_failure,technician_id,status,scheduled_at)
      VALUES (?,?,?,?,?,?,?,?,?,?)`).run(folio,new Date().toISOString(),userId,'Media','Mantenimiento Preventivo',plan.asset_id,detail,plan.responsible_id,'Programada',baseDate);
    const orderId=Number(result.lastInsertRowid);
    db.prepare('INSERT INTO preventive_order_revisions (work_order_id,plan_id,version) VALUES (?,?,?)').run(orderId,planId,plan.version);
    const insert=db.prepare(`INSERT INTO preventive_occurrences
      (task_id,occurrence_index,base_date,plan_id,plan_version,work_order_id,created_by) VALUES (?,?,?,?,?,?,?)`),ids=[];
    for(const item of items){const row=insert.run(item.task.id,item.occurrence_index,baseDate,planId,plan.version,orderId,userId);ids.push(Number(row.lastInsertRowid));audit(userId,'preventive_occurrence',ids.at(-1),'created',null,{task_id:item.task.id,base_date:baseDate,work_order_id:orderId,plan_version:plan.version,grouped:true});}
    db.prepare('INSERT INTO work_order_events (work_order_id,user_id,event,details) VALUES (?,?,?,?)').run(orderId,userId,'Ocurrencias preventivas agrupadas',`${items.length} tareas, fecha base ${baseDate}, revisión ${plan.version}`);
    db.exec('COMMIT');return {work_order_id:orderId,folio,base_date:baseDate,occurrence_ids:ids,replayed:false};
  }catch(failure){db.exec('ROLLBACK');throw failure;}
}
module.exports={migrate,generate,generateGroup};
