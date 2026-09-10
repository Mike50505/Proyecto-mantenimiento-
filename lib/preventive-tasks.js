'use strict';
const fail=message=>{throw Object.assign(new Error(message),{status:400})};
function date(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))fail('La fecha debe usar YYYY-MM-DD');
  const parsed=new Date(value+'T00:00:00Z');
  if(!Number.isFinite(parsed.getTime())||parsed.toISOString().slice(0,10)!==value||value<'1900-01-01')fail('Fecha calendario inválida');
  return parsed;
}
function validate(task){
  if(typeof task.title!=='string'||!task.title.trim())fail('Indica la descripción de la tarea');
  if(!['days','months'].includes(task.interval_unit))fail('El intervalo debe ser days o months');
  if(!Number.isInteger(task.interval_value)||task.interval_value<1||task.interval_value>1200)fail('El intervalo debe ser un entero entre 1 y 1200');
  date(task.anchor_date);
}
function dueDate(task,index){
  validate(task);
  if(!Number.isSafeInteger(index)||index<0)fail('Índice de ocurrencia inválido');
  const anchor=date(task.anchor_date),offset=task.interval_value*index;
  if(task.interval_unit==='days')anchor.setUTCDate(anchor.getUTCDate()+offset);
  else {
    const day=anchor.getUTCDate();
    anchor.setUTCDate(1);anchor.setUTCMonth(anchor.getUTCMonth()+offset);
    const last=new Date(Date.UTC(anchor.getUTCFullYear(),anchor.getUTCMonth()+1,0)).getUTCDate();
    anchor.setUTCDate(Math.min(day,last));
  }
  if(!Number.isFinite(anchor.getTime())||anchor.getUTCFullYear()>9999)fail('Vencimiento fuera del rango admitido');
  return anchor.toISOString().slice(0,10);
}
function project(task,from,to){
  validate(task);const start=date(from),end=date(to),anchor=date(task.anchor_date);
  if(start>end||end-start>366*86400000)fail('El horizonte debe estar ordenado y no superar 366 días');
  const distance=task.interval_unit==='days'?(start-anchor)/86400000:(start.getUTCFullYear()-anchor.getUTCFullYear())*12+start.getUTCMonth()-anchor.getUTCMonth();
  let index=Math.max(0,Math.floor(distance/task.interval_value)-1);
  const rows=[];
  for(;;index++){
    const due=dueDate(task,index);if(due>to)break;
    if(due>=from)rows.push({task_id:task.id,occurrence_index:index,base_date:due});
  }
  return rows;
}
function migrate(db){
  db.exec(`CREATE TABLE IF NOT EXISTS preventive_tasks (
    id INTEGER PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES preventive_plans(id),
    title TEXT NOT NULL,
    interval_unit TEXT NOT NULL CHECK(interval_unit IN ('days','months')),
    interval_value INTEGER NOT NULL CHECK(interval_value BETWEEN 1 AND 1200),
    anchor_date TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  ); CREATE INDEX IF NOT EXISTS idx_preventive_tasks_plan ON preventive_tasks(plan_id);`);
}
module.exports={validate,dueDate,project,migrate};
