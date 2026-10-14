const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const sandbox = {window:{}};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname, '..', 'static', 'user-permissions.js'), 'utf8'), sandbox);
const editor = sandbox.window.MesaPermissions;
const schema = {
  modules:['orders','assets','users'], actions:['orders.read','orders.create','assets.read','users.manage'], areas:['Prensas','Corte'],
  defaults:{Solicitante:{permissions:['orders'],actions:['orders.read','orders.create']}, 'Jefe de mantenimiento':{permissions:['orders','assets','users'],actions:['orders.read','orders.create','assets.read','users.manage']}},
};
function fixture(user={}) {
  const html = editor.markup(schema,user);
  const inputs = [...html.matchAll(/<input ([^>]+)>/g)].map(match => {
    const attributes=match[1];
    return {name:attributes.match(/name="([^"]+)"/)?.[1],value:attributes.match(/value="([^"]*)"/)?.[1],checked:/\bchecked\b/.test(attributes),disabled:false,allAreas:attributes.includes('data-all-areas')};
  });
  const role={value:user.role||'Operador'};
  const summary={};
  const groups=schema.modules.map(()=>({disabled:false}));
  const listeners={};
  const wrap={
    querySelector(selector) {if(selector==='[name="role"]')return role;if(selector==='[data-all-areas]')return inputs.find(input=>input.allAreas);if(selector==='[data-permission-summary]')return summary;return inputs.find(input=>input.name===selector.match(/name="([^"]+)"/)?.[1]);},
    querySelectorAll(selector) {if(selector==='[data-permission-group]')return groups;return inputs.filter(input=>input.name===selector.match(/name="([^"]+)"/)?.[1]);},
    addEventListener(type, callback){listeners[type]=callback;},
  };
  const collect=editor.bind(wrap,schema);
  const change=(input,checked)=>{input.checked=checked;listeners.change({target:input});};
  const toggle=(key,value,checked)=>change(inputs.find(input=>input.name===key&&input.value===value),checked);
  return {html,collect,inputs,role,summary,listeners,change,toggle,mode:inputs.find(input=>input.name==='custom_permissions'),all:inputs.find(input=>input.allAreas)};
}
const plain = value => JSON.parse(JSON.stringify(value));
let form=fixture();
assert.deepEqual(plain(form.collect()),{custom_permissions:false});
assert(!form.html.includes('actions_text')&&!form.html.includes('areas_text'));
form.change(form.mode,true);
form.toggle('permissions','assets',true);
assert(form.collect().actions.includes('assets.read'));
assert(form.collect().permissions.includes('assets'));
form.listeners.click({target:{closest:()=>({dataset:{clear:'permissions'}})}});
assert.deepEqual(plain(form.collect().permissions),[]);
assert.equal(form.collect().custom_permissions,true);
assert(form.summary.textContent.includes('no tendrá ventanas'));
form.change(form.all,false);
assert.throws(()=>form.collect(),/Selecciona al menos un área/);
form.toggle('areas','Prensas',true);
assert.deepEqual(plain(form.collect().areas),['Prensas']);
form.change(form.all,true);
assert.deepEqual(plain(form.collect().areas),[]);
form.change(form.mode,false);
assert.deepEqual(plain(form.collect()),{custom_permissions:false});
form=fixture({id:2,role:'Jefe de mantenimiento',custom_permissions:true,permissions:['assets'],actions:['assets.read'],areas:['Corte']});
assert.deepEqual(plain(form.collect()),{custom_permissions:true,permissions:['assets'],actions:['assets.read'],areas:['Corte']});
form.role.value='Mantenimiento';form.listeners.change({target:form.role});
assert.deepEqual(plain(form.collect().permissions),['assets']);
form=fixture({id:3,role:'Solicitante',permissions:['orders'],actions:['orders.read'],areas:[]});
assert.equal(form.mode.checked,true,'Las selecciones anteriores deben conservarse al editar');
const hostile=editor.markup({...schema,areas:['<script>alert(1)</script>']},{custom_permissions:true,areas:[]});
assert(!hostile.includes('<script>'));
assert(hostile.includes('&lt;script&gt;'));
console.log('Selección por casillas: valores por rol, consulta automática, selección vacía, áreas, jefe limitado, cambios de rol y escape de etiquetas OK.');
