'use strict';
const fs=require('node:fs'),path=require('node:path');
const {DatabaseSync}=require('node:sqlite');
const source=path.resolve(process.argv[2]||'data/mantenimiento.db');
if(!fs.existsSync(source))throw Error('No existe la base de origen');
const destination=path.resolve(process.argv[3]||path.join('backups',`mesa-${new Date().toISOString().replace(/[:.]/g,'-')}.db`));
if(fs.existsSync(destination))throw Error('El destino ya existe; no se sobrescribe');
fs.mkdirSync(path.dirname(destination),{recursive:true});
const db=new DatabaseSync(source,{readOnly:true});
try{db.exec(`VACUUM INTO '${destination.replaceAll("'","''")}'`);}finally{db.close();}
const copy=new DatabaseSync(destination,{readOnly:true});
try{if(copy.prepare('PRAGMA integrity_check').get().integrity_check!=='ok')throw Error('La copia no pasó la verificación');console.log(JSON.stringify({backup:destination,integrity:'ok',orders:copy.prepare('SELECT COUNT(*) n FROM work_orders').get().n}));}finally{copy.close();}
