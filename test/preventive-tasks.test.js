'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {dueDate,project}=require('../lib/preventive-tasks');
const {classify,summarize}=require('../lib/preventive-compliance');
const monthly={id:1,title:'Mensual',interval_unit:'months',interval_value:1,anchor_date:'2026-01-31'};
test('recurrencia mensual conserva el día ancla después de febrero',()=>{
  assert.deepEqual([0,1,2,3].map(i=>dueDate(monthly,i)),['2026-01-31','2026-02-28','2026-03-31','2026-04-30']);
  assert.equal(dueDate({...monthly,anchor_date:'2028-01-31'},1),'2028-02-29');
});
test('días calendario atraviesan año y febrero bisiesto',()=>{
  assert.equal(dueDate({...monthly,interval_unit:'days',anchor_date:'2027-12-31'},1),'2028-01-01');
  assert.equal(dueDate({...monthly,interval_unit:'days',anchor_date:'2028-02-28'},1),'2028-02-29');
});
test('proyecciones independientes y repetibles para mensual y trimestral',()=>{
  const quarterly={...monthly,id:2,interval_value:3};
  const before=project(quarterly,'2026-02-01','2026-07-31');
  project(monthly,'2026-02-01','2026-07-31');
  assert.deepEqual(project(quarterly,'2026-02-01','2026-07-31'),before);
  assert.deepEqual(before.map(o=>o.base_date),['2026-04-30','2026-07-31']);
  assert.deepEqual(project(monthly,'2025-01-01','2025-12-31'),[]);
});
test('rechaza fechas inexistentes, intervalos ambiguos y horizontes excesivos',()=>{
  for(const anchor_date of ['2026-02-30','2026-13-01','texto'])assert.throws(()=>dueDate({...monthly,anchor_date},0));
  for(const interval_value of [0,-1,1.5,'1'])assert.throws(()=>dueDate({...monthly,interval_value},0));
  assert.throws(()=>project(monthly,'2026-02-01','2026-01-01'));
  assert.throws(()=>project(monthly,'2026-01-01','2028-01-01'));
});
test('clasifica cumplimiento conservando la fecha base',()=>{
  assert.equal(classify({base_date:'2026-09-01',scheduled_date:'2026-09-03',executed_at:'2026-09-03',execution_state:'Validada'},'2026-09-10').status,'D');
  assert.equal(classify({base_date:'2026-09-01',scheduled_date:'2026-09-01',executed_at:'2026-09-01',execution_state:'Validada'},'2026-09-10').status,'T');
  assert.equal(classify({base_date:'2026-09-01',execution_state:'Sin ejecución registrada'},'2026-09-10').status,'V');
  assert.equal(classify({base_date:'2026-09-20',execution_state:'Sin ejecución registrada'},'2026-09-10').status,'P');
  assert.equal(classify({base_date:'2026-09-01',execution_state:'Cancelada'},'2026-09-10').eligible,false);
  assert.deepEqual(summarize([{status:'T',eligible:true},{status:'D',eligible:true},{status:'V',eligible:true},{status:'R',eligible:false}]),{counts:{P:0,T:1,D:1,V:1,R:1},eligible:3,executed:2,compliance_percent:33.33});
});
