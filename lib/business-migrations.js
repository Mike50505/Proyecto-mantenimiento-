'use strict';
module.exports=function migrate(db){
 db.exec('CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)');
 if(db.prepare('SELECT 1 FROM schema_migrations WHERE version=?').get('001-integrity'))return;
 // Rebuild CHECK constraints without renaming referenced tables or losing indexes.
 db.exec('PRAGMA foreign_keys=OFF; BEGIN IMMEDIATE');
 try{
  const rebuild=(table,transform)=>{
   const sql=db.prepare('SELECT sql FROM sqlite_master WHERE type=\'table\' AND name=?').get(table).sql;
   const indexes=db.prepare('SELECT sql FROM sqlite_master WHERE type=\'index\' AND tbl_name=? AND sql IS NOT NULL').all(table);
   db.exec(transform(sql).replace(`CREATE TABLE ${table}`,`CREATE TABLE ${table}_replacement`));
   db.exec(`INSERT INTO ${table}_replacement SELECT * FROM ${table}; DROP TABLE ${table}; ALTER TABLE ${table}_replacement RENAME TO ${table}`);
   indexes.forEach(i=>db.exec(i.sql));
  };
  rebuild('work_orders',sql=>sql.replace("'Abierta','En proceso','Espera de material','Completada','Cancelada'","'Abierta','Programada','En proceso','Pausada','Espera de material','Pendiente de validación','Completada','Cancelada'"));
  rebuild('inventory_movements',sql=>sql.replace("'Entrada','Salida','Ajuste'","'Entrada','Salida','Devolución','Ajuste','Inventario inicial'").replace('CHECK(quantity > 0)','CHECK(quantity >= 0)'));
  db.exec(`ALTER TABLE inventory_items ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
   ALTER TABLE inventory_movements ADD COLUMN return_of INTEGER REFERENCES inventory_movements(id);
   ALTER TABLE inventory_movements ADD COLUMN request_key TEXT;
   ALTER TABLE inventory_movements ADD COLUMN request_hash TEXT;
   ALTER TABLE maintenance_materials ADD COLUMN movement_id INTEGER REFERENCES inventory_movements(id);
   ALTER TABLE maintenance_materials ADD COLUMN returned_quantity REAL NOT NULL DEFAULT 0;
   CREATE UNIQUE INDEX idx_stock_request_key ON inventory_movements(user_id,request_key) WHERE request_key IS NOT NULL;
   UPDATE work_orders SET status='Pendiente de validación',closed_at=NULL WHERE status='Completada' AND validation_status='Pendiente';`);
  if(db.prepare('PRAGMA foreign_key_check').all().length)throw Error('La migración detectó referencias inválidas');
  db.prepare('INSERT INTO schema_migrations(version) VALUES (?)').run('001-integrity');db.exec('COMMIT');
 }catch(e){db.exec('ROLLBACK');throw e;}finally{db.exec('PRAGMA foreign_keys=ON');}
};
