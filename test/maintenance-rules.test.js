const test = require('node:test');
const assert = require('node:assert/strict');
const { hoursBetween } = require('../lib/time');

test('calcula horas cruzando medianoche', () => {
  assert.equal(hoursBetween('2026-09-08T23:00:00Z', '2026-09-09T01:00:00Z'), 2);
});

test('rechaza un intervalo invertido', () => {
  assert.throws(
    () => hoursBetween('2026-09-09T09:00:00Z', '2026-09-09T07:00:00Z'),
    /posterior/
  );
});

test('rechaza fechas inválidas e intervalos de duración cero',()=>{
  assert.throws(()=>hoursBetween('inválida','2026-09-09T09:00:00Z'));
  assert.throws(()=>hoursBetween('2026-09-09T09:00:00Z','2026-09-09T09:00:00Z'));
});
test('suma segundos antes de redondear: 60 sesiones de un minuto son una hora',()=>{
  assert.ok(Math.abs(Array.from({length:60},()=>hoursBetween('2026-09-09T09:00:00Z','2026-09-09T09:01:00Z')).reduce((a,b)=>a+b,0)-1)<1e-12);
});
