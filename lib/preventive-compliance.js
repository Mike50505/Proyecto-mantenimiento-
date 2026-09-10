'use strict';
const fail=message=>{throw Object.assign(new Error(message),{status:400})};
function day(value,label='fecha'){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))fail(`La ${label} debe usar YYYY-MM-DD`);
  const parsed=new Date(value+'T00:00:00Z');
  if(!Number.isFinite(parsed.getTime())||parsed.toISOString().slice(0,10)!==value)fail(`${label} calendario inválida`);
  return value;
}
function classify(item,asOf){
  const today=day(asOf,'fecha de cálculo'),base=day(item.base_date,'fecha base');
  const scheduled=item.scheduled_date?day(String(item.scheduled_date).slice(0,10),'fecha programada'):base;
  const executed=item.executed_at?String(item.executed_at).slice(0,10):null;
  const state=item.execution_state||'Sin ejecución registrada';
  if(state==='Cancelada')return {...item,status:'R',eligible:false,reason:'Cancelada'};
  if(executed){
    const status=executed<=base?'T':'D';
    return {...item,status,eligible:true,reason:status==='T'?'Ejecutada dentro de la fecha base':'Ejecutada después de la fecha base',executed_date:executed,scheduled_date:scheduled};
  }
  if(base<today)return {...item,status:'V',eligible:true,reason:'Vencida sin ejecución',scheduled_date:scheduled};
  return {...item,status:'P',eligible:true,reason:scheduled<today?'Programada después de la fecha base':'Pendiente dentro del plazo',scheduled_date:scheduled};
}
function summarize(rows){
  const counts={P:0,T:0,D:0,V:0,R:0};rows.forEach(row=>{counts[row.status]=(counts[row.status]||0)+1});
  const eligible=rows.filter(row=>row.eligible),done=eligible.filter(row=>['T','D'].includes(row.status));
  return {counts,eligible:eligible.length,executed:done.length,compliance_percent:eligible.length?Math.round(done.filter(row=>row.status==='T').length/eligible.length*10000)/100:null};
}
module.exports={day,classify,summarize};
