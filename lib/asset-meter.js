'use strict';
const fail=(message,status=400)=>{throw Object.assign(new Error(message),{status})};
function migrate(db){db.exec(`CREATE TABLE IF NOT EXISTS asset_meter_readings (
  id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id), reading REAL NOT NULL CHECK(reading>=0),
  recorded_by INTEGER NOT NULL REFERENCES users(id), recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, note TEXT
); CREATE INDEX IF NOT EXISTS idx_asset_meter_asset_date ON asset_meter_readings(asset_id,recorded_at);`)}
function validate(input){
  const reading=Number(input.reading);
  if(!Number.isFinite(reading)||reading<0)fail('El horómetro debe ser un número mayor o igual a cero');
  if(reading>1000000000)fail('El horómetro excede el rango permitido');
  return {reading,note:input.note?String(input.note).trim().slice(0,500):null};
}
function record(db,assetId,input,userId){
  const value=validate(input);db.exec('BEGIN IMMEDIATE');
  try{
    const asset=db.prepare('SELECT operating_hours FROM assets WHERE id=?').get(assetId);if(!asset)fail('Activo no encontrado',404);
    if(value.reading<Number(asset.operating_hours||0))fail('El horómetro no puede disminuir');
    const row=db.prepare('INSERT INTO asset_meter_readings (asset_id,reading,recorded_by,note) VALUES (?,?,?,?)').run(assetId,value.reading,userId,value.note);
    db.prepare('UPDATE assets SET operating_hours=? WHERE id=?').run(value.reading,assetId);db.exec('COMMIT');
    return {id:Number(row.lastInsertRowid),asset_id:assetId,reading:value.reading,note:value.note};
  }catch(error){db.exec('ROLLBACK');throw error;}
}
module.exports={migrate,record,validate};
