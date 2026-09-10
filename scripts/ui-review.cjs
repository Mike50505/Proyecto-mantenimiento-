'use strict';
// Revisión reproducible en Chrome local, con base y perfil desechables.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
async function main(){
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'mesa-ui-'));
 process.env.DB_PATH=path.join(temp,'review.db');
 process.env.MESA_DEMO='1';
 const {server,db}=require('../server');
 db.prepare("UPDATE users SET role='Administrador' WHERE id=1").run();
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base=`http://127.0.0.1:${server.address().port}`;
 const token=crypto.randomBytes(32).toString('hex');
 db.prepare("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (?,?,datetime('now','+1 hour'))").run(crypto.createHash('sha256').update(token).digest('hex'),1);
 const browser=spawn(process.env.CHROME_PATH||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${path.join(temp,'chrome')}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
 let socket;
 try{
  const portFile=path.join(temp,'chrome','DevToolsActivePort');
  for(let i=0;i<100&&!fs.existsSync(portFile);i++)await new Promise(r=>setTimeout(r,100));
  if(!fs.existsSync(portFile))throw Error('Chrome no abrió el puerto de revisión');
  const port=fs.readFileSync(portFile,'utf8').split('\n')[0];
  const targets=await(await fetch(`http://127.0.0.1:${port}/json`)).json();
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
  let seq=0;const pending=new Map();
  socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(m.error)p.reject(Error(m.error.message));else p.resolve(m.result);}};
  const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text+': '+r.exceptionDetails.exception?.description);return r.result.value;};
  const until=async exp=>{for(let i=0;i<80;i++){if(await evaluate(exp))return;await new Promise(r=>setTimeout(r,100));}throw Error('Timeout: '+exp);};
  await call('Network.enable');await call('Page.enable');
  await call('Network.setCookie',{name:'mesa_session',value:token,url:base,httpOnly:true,sameSite:'Strict'});
  await call('Page.navigate',{url:base});
  await until("document.querySelector('.metric') !== null");
  if(!await evaluate("fmtDate('2026-09-08 15:39:43')!=='Fecha no disponible' && fmtDate('fecha corrupta')==='Fecha no disponible' && fmtDate(null)==='—'"))throw Error('Formateo de fechas no tolerante');
  // Regression: editing unrelated instructions must retain assignment and status,
  // including a responsible person absent from the active technician catalog.
  await evaluate(`(async()=>{
    const created=await api('/api/preventives',{method:'POST',body:JSON.stringify({asset_id:1,title:'Prueba de historial',frequency:'1 mes',next_date:'2026-10-01',responsible_id:1,status:'Vencido'})});
    window.reviewPlanId=created.id;
    const plan=(await api('/api/preventives')).find(p=>p.id===created.id);
    await openPreventive(plan);
    const form=document.querySelector('.modal form');
    if(form.elements.responsible_id.value!=='1'||form.elements.status.value!=='Vencido')throw Error('La edición perdió responsable o estado');
    form.elements.instructions.value='Instrucciones revisadas <script>texto</script>';
    form.requestSubmit();
  })()`);
  await until("document.querySelector('.modal-backdrop') === null");
  await evaluate(`(async()=>{
    const plan=(await api('/api/preventives')).find(p=>p.id===window.reviewPlanId);
    if(plan.responsible_id!==1||plan.status!=='Vencido')throw Error('Guardar modificó responsable o estado');
    await openPreventiveHistory(plan.id);
    if(document.querySelectorAll('.modal details').length!==2)throw Error('Faltan revisiones');
    if(document.querySelector('.modal script'))throw Error('Contenido histórico sin escapar');
  })()`);
  for(const width of [390,768,1440]){
    await call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
    const fits=await evaluate("document.querySelector('.modal').getBoundingClientRect().width<=innerWidth && document.documentElement.scrollWidth<=innerWidth");
    if(!fits)throw Error('Historial desbordado: '+width);
  }
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await until("document.querySelector('.modal-backdrop') === null");
  console.log('Preventivos: responsable/estado conservados al guardar; revisiones y texto seguro; historial adaptable.');
  if(process.env.MESA_REVIEW_PREVENTIVES_ONLY==='1')return;
  await evaluate("openPreventiveTasks(window.reviewPlanId)");
  await evaluate(`(()=>{
    const form=document.querySelector('[data-task-form]');form.closest('details').open=true;
    form.elements.title.value='Mensual <script>texto</script>';
    form.elements.anchor_date.value='2026-01-31';form.requestSubmit();
  })()`);
  await until("document.querySelector('[data-task-list]').textContent.includes('Mensual')");
  await until("!document.querySelector('[data-task-form] button').disabled");
  await evaluate(`(()=>{
    const form=document.querySelector('[data-task-form]');
    form.elements.title.value='Trimestral';form.elements.interval_value.value='3';form.elements.anchor_date.value='2026-01-31';form.requestSubmit();
  })()`);
  await until("document.querySelector('[data-task-list]').textContent.includes('Trimestral')");
  await until("!document.querySelector('[data-task-form] button').disabled");
  await evaluate(`(()=>{
    const form=document.querySelector('[data-calendar-form]');form.elements.from.value='2026-02-01';form.elements.to.value='2026-04-30';form.requestSubmit();
  })()`);
  await until("document.querySelectorAll('[data-calendar-result] li').length===4");
  if(await evaluate("!!document.querySelector('.modal script')"))throw Error('Tareas sin escape de HTML');
  for(const width of [390,768,1440]){
    await call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
    if(!await evaluate("document.querySelector('.modal').getBoundingClientRect().width<=innerWidth && document.documentElement.scrollWidth<=innerWidth"))throw Error('Tareas desbordadas: '+width);
  }
  await evaluate(`(async()=>{
    const current=(await api('/api/preventives')).find(p=>p.id===window.reviewPlanId);
    await api('/api/preventives/'+current.id,{method:'PATCH',body:JSON.stringify({version:current.version,title:current.title})});
    const form=document.querySelector('[data-task-form]');form.elements.title.value='Captura conservada';form.elements.anchor_date.value='2026-01-31';form.requestSubmit();
  })()`);
  await until("!document.querySelector('[data-task-error]').hidden");
  if(!await evaluate("document.querySelector('[data-task-form]').elements.title.value==='Captura conservada'"))throw Error('Se perdió la captura tras conflicto');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await until("document.querySelector('.modal-backdrop') === null");
  await evaluate(`(async()=>{
    await api('/api/preventives/'+window.reviewPlanId+'/order',{method:'POST'});
    await openPreventiveTasks(window.reviewPlanId);
    if(document.querySelector('[data-task-form]'))throw Error('El plan con OT permite capturar tareas');
  })()`);
  await until("document.querySelector('[role=dialog]').contains(document.activeElement)");
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await until("document.querySelector('.modal-backdrop') === null");
  console.log('Tareas: dos altas consecutivas, calendario mensual/trimestral, captura conservada tras conflicto y bloqueo con OT; 390/768/1440 px.');
  if(process.env.MESA_REVIEW_TASKS_ONLY==='1')return;
  await evaluate(`(async()=>{
    const p=await api('/api/preventives',{method:'POST',body:JSON.stringify({asset_id:1,title:'OT desde agenda',frequency:'1 mes',next_date:'2026-01-31'})});
    window.occurrenceReviewPlan=p.id;
    await api('/api/preventives/'+p.id+'/tasks',{method:'POST',body:JSON.stringify({title:'Revisión mensual',interval_unit:'months',interval_value:1,anchor_date:'2026-01-31',version:1})});
    await openPreventiveTasks(p.id);
    const form=document.querySelector('[data-calendar-form]');form.elements.from.value='2026-02-01';form.elements.to.value='2026-03-31';form.requestSubmit();
  })()`);
  await until("document.querySelectorAll('[data-generate-task]').length===2");
  await evaluate("document.querySelector('[data-generate-task]').click();document.querySelector('[data-generate-task]').click()");
  await until("document.querySelectorAll('[data-occurrence-order]').length===1");
  await evaluate(`(async()=>{
    const rows=await api('/api/preventives/'+window.occurrenceReviewPlan+'/occurrences');
    if(rows.length!==1)throw Error('El doble clic duplicó la OT');
    window.occurrenceReviewOrder=rows[0].work_order_id;
    document.querySelector('[data-occurrence-order]').click();
  })()`);
  await until("document.querySelector('[role=tablist]') !== null && document.querySelectorAll('.modal-backdrop').length===1");
  if(!await evaluate("!!document.querySelector('.preventive-execution')"))throw Error('La OT no muestra ejecución preventiva');
  if(!await evaluate("document.querySelector('.preventive-execution').textContent.includes('Fecha base')"))throw Error('La OT no muestra fecha base');
  await until("document.querySelector('[role=dialog]').contains(document.activeElement)");
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await until("document.querySelector('.modal-backdrop') === null");
  await evaluate(`(async()=>{
    await openPreventiveTasks(window.occurrenceReviewPlan);
    const form=document.querySelector('[data-calendar-form]');form.elements.from.value='2026-02-01';form.elements.to.value='2026-03-31';form.requestSubmit();
  })()`);
  await until("document.querySelectorAll('[data-occurrence-order]').length===1 && document.querySelectorAll('[data-generate-task]').length===1");
  for(const width of [390,768,1440]){
    await call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
    if(!await evaluate("document.documentElement.scrollWidth<=innerWidth && document.querySelector('.modal').getBoundingClientRect().width<=innerWidth"))throw Error('Ocurrencias desbordadas: '+width);
  }
  await evaluate("document.querySelector('.close-read').click()");
  console.log('Ocurrencias: generar sin duplicados, abrir OT, reabrir agenda con folio persistido; 390/768/1440 px.');
  if(process.env.MESA_REVIEW_OCCURRENCES_ONLY==='1')return;
  const output=path.resolve('docs','visual-review');fs.mkdirSync(output,{recursive:true});
  const report=[];
  for(const width of [390,768,1440]){
   await call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
   for(const view of ['dashboard','orders','assets','inventory','preventives','users']){
    await evaluate(`navigate('${view}')`);await until("!document.querySelector('#content').textContent.includes('Cargando…')");
    const result=await evaluate(`({width:${width},view:'${view}',viewport:innerWidth,scroll:document.documentElement.scrollWidth,body:document.body.scrollWidth,error:document.querySelector('#content').textContent.includes('No fue posible'),font:getComputedStyle(document.body).fontFamily,background:getComputedStyle(document.body).backgroundColor})`);
    report.push(result);
    if(result.scroll>width||result.body>width||result.error)throw Error(JSON.stringify(result));
    if(['dashboard','orders','inventory'].includes(view)){const shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,`${view}-${width}.png`),Buffer.from(shot.data,'base64'));}
   }
   await evaluate("openOrder()");await until("document.querySelector('[role=dialog]') !== null");
   await until("document.querySelector('[role=dialog]').contains(document.activeElement)");
   const dialog=await evaluate("({label:document.querySelector('[role=dialog]').getAttribute('aria-labelledby'),focused:document.querySelector('[role=dialog]').contains(document.activeElement),width:document.querySelector('.modal').getBoundingClientRect().width,viewport:innerWidth})");
   if(!dialog.label||!dialog.focused||dialog.width>width)throw Error(JSON.stringify(dialog));
   const shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,`request-${width}.png`),Buffer.from(shot.data,'base64'));
   await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
   await until("document.querySelector('.modal-backdrop') === null");
  }
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await evaluate("navigate('orders')");await until("document.querySelector('.order-detail') !== null");
  await evaluate("document.querySelector('.order-detail').click()");await until("document.querySelector('[role=tablist]') !== null");
  await evaluate("document.querySelector('[data-section=work]').click()");
  const detailShot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,'order-detail-1440.png'),Buffer.from(detailShot.data,'base64'));
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await until("document.querySelector('.modal-backdrop') === null");
  await evaluate("document.documentElement.style.zoom='2'");
  const zoom=await evaluate("({zoom:getComputedStyle(document.documentElement).zoom,scroll:document.documentElement.scrollWidth,width:innerWidth})");
  if(zoom.scroll>zoom.width)throw Error('Desbordamiento con zoom: '+JSON.stringify(zoom));
  await evaluate("document.documentElement.style.zoom='1'");
  const operatorToken=crypto.randomBytes(32).toString('hex');
  db.prepare("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (?,?,datetime('now','+1 hour'))").run(crypto.createHash('sha256').update(operatorToken).digest('hex'),4);
  await call('Network.setCookie',{name:'mesa_session',value:operatorToken,url:base,httpOnly:true,sameSite:'Strict'});
  await call('Page.navigate',{url:base});await until("document.querySelector('#new-order') !== null");
  await call('Emulation.setDeviceMetricsOverride',{width:390,height:1000,deviceScaleFactor:1,mobile:false});
  await evaluate("document.querySelector('#new-order').click()");await until("document.querySelector('[role=dialog]') !== null");
  await until("document.querySelector('[role=dialog]').contains(document.activeElement)");
  if(await evaluate("!!document.querySelector('[name=actions],[name=labor_cost]')"))throw Error('El reporte pide datos técnicos');
  const operatorShot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,'operator-request-390.png'),Buffer.from(operatorShot.data,'base64'));
  await evaluate("document.querySelector('[name=reported_failure]').value='Reporte sintético desde prueba de navegador';document.querySelector('.modal form').requestSubmit()");
  await until("document.querySelector('.modal-backdrop') === null");
  if(!db.prepare("SELECT 1 FROM work_orders WHERE reported_failure='Reporte sintético desde prueba de navegador' AND requester_id=4").get())throw Error('No persistió el reporte móvil');
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({screens:report,zoom,operatorRequestPersisted:true},null,2));
  console.log(JSON.stringify({screens:report.length,overflow:0,dialogKeyboard:true,output}));
 }finally{socket?.close();browser.kill();await new Promise(r=>server.close(r));db.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
