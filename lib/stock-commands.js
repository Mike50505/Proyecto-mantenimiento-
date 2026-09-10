'use strict';
const crypto=require('node:crypto');
const fail=(message,status=400)=>{throw Object.assign(new Error(message),{status});};
module.exports=function stockCommand(db,user,itemId,b){
 const key=String(b.request_key||'').trim();if(!key||key.length>160)fail('El movimiento requiere un identificador de petición');
 const hash=crypto.createHash('sha256').update(JSON.stringify([itemId,b.type,b.quantity,b.unit_cost,b.work_order_id,b.return_of,b.notes])).digest('hex');
 db.exec('BEGIN IMMEDIATE');
 try{
  const replay=db.prepare('SELECT * FROM inventory_movements WHERE user_id=? AND request_key=?').get(user.id,key);
  if(replay){if(replay.request_hash!==hash)fail('La petición ya se utilizó con otro contenido',409);db.exec('COMMIT');return {id:replay.id,replayed:true};}
  const item=db.prepare('SELECT * FROM inventory_items WHERE id=? AND active=1').get(itemId);if(!item)fail('Insumo no encontrado',404);
  if(!Number.isInteger(Number(b.version))||Number(b.version)!==item.version)fail('La existencia cambió. Consulta el saldo actual antes de confirmar.',409);
  const type=b.type,quantity=Number(b.quantity);if(!['Entrada','Salida','Devolución','Ajuste'].includes(type)||!Number.isFinite(quantity)||quantity<0||(quantity===0&&type!=='Ajuste'))fail('Indica un tipo y una cantidad válidos');
  if(type==='Ajuste'&&!String(b.notes||'').trim())fail('El ajuste requiere un motivo');
  let orderId=b.work_order_id?Number(b.work_order_id):null,origin=null,cost=item.unit_cost;
  if(type==='Devolución'){
   origin=db.prepare("SELECT * FROM inventory_movements WHERE id=? AND inventory_item_id=? AND type='Salida'").get(Number(b.return_of),itemId);
   if(!origin)fail('Selecciona la salida original para la devolución');
   const returned=db.prepare("SELECT COALESCE(SUM(quantity),0) n FROM inventory_movements WHERE return_of=? AND type='Devolución'").get(origin.id).n;
   if(quantity>origin.quantity-returned)fail('La devolución supera la cantidad pendiente de devolver');
   cost=origin.unit_cost;orderId=origin.work_order_id;
  }
  if(type==='Entrada'){cost=Number(b.unit_cost);if(b.unit_cost==null||b.unit_cost===''||!Number.isFinite(cost)||cost<0)fail('Indica el costo de entrada; cero debe ser explícito');}
  const order=orderId?db.prepare('SELECT * FROM work_orders WHERE id=?').get(orderId):null;
  if(orderId&&!order)fail('Orden no encontrada',404);
  if(order&&!['Administrador','Jefatura'].includes(user.role)&&order.technician_id!==user.id)fail('Solo puedes entregar material a tus órdenes asignadas',403);
  if(type==='Salida'&&order&&['Completada','Cancelada','Pendiente de validación'].includes(order.status))fail('La orden debe estar abierta para recibir material');
  const next=type==='Salida'?item.stock-quantity:type==='Ajuste'?quantity:item.stock+quantity;if(next<0)fail(`Existencia insuficiente. Disponible: ${item.stock} ${item.unit}`);
  // Keep quantities/costs rounded at storage boundaries. Full decimal storage is pending.
  const round=n=>Math.round((n+Number.EPSILON)*10000)/10000;
  const movement=db.prepare(`INSERT INTO inventory_movements(inventory_item_id,type,quantity,unit_cost,work_order_id,user_id,notes,return_of,request_key,request_hash) VALUES(?,?,?,?,?,?,?,?,?,?)`).run(itemId,type,type==='Ajuste'?Math.abs(next-item.stock):quantity,cost,orderId,user.id,type==='Ajuste'?`${b.notes} · Saldo ${item.stock} → ${next}`:b.notes||null,origin?.id||null,key,hash);
  const movementId=Number(movement.lastInsertRowid);
  const average=type==='Entrada'&&next>0?round((item.stock*item.unit_cost+quantity*cost)/next):item.unit_cost;
  db.prepare('UPDATE inventory_items SET stock=?,unit_cost=?,version=version+1 WHERE id=?').run(round(next),average,itemId);
  if(order&&type==='Salida')db.prepare('INSERT INTO maintenance_materials(work_order_id,inventory_item_id,code,description,quantity,unit_cost,movement_id) VALUES(?,?,?,?,?,?,?)').run(order.id,itemId,item.code,item.name,quantity,cost,movementId);
  if(origin&&order)db.prepare('UPDATE maintenance_materials SET returned_quantity=returned_quantity+? WHERE movement_id=?').run(quantity,origin.id);
  if(order){const difference=(type==='Salida'?1:type==='Devolución'?-1:0)*quantity*cost;db.prepare('UPDATE work_orders SET material_cost=MAX(0,ROUND(material_cost+?,2)),version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?').run(difference,order.id);}
  db.prepare('INSERT INTO audit_log(user_id,entity_type,entity_id,action,before_json,after_json,reason) VALUES(?,?,?,?,?,?,?)').run(user.id,'inventory_item',itemId,type,JSON.stringify({stock:item.stock,version:item.version}),JSON.stringify({stock:round(next),movement_id:movementId,version:item.version+1}),b.notes||null);
  db.exec('COMMIT');return {id:movementId,stock:round(next),version:item.version+1};
 }catch(e){db.exec('ROLLBACK');throw e;}
};
