'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { promisify } = require('node:util');
const { DatabaseSync } = require('node:sqlite');
const scrypt = promisify(crypto.scrypt);
const DEFAULT_ADMIN_HASH = '0820faa641cad4a7f881b2e59b94965f:c112a525a9751d2a7adc24b47196c04ba80377988b3501b3808322de1394b1ce3a913c77307b20d5c4a6537c8fb6bf68ef71f3a963ba0c76bf359e27ae593faf';

const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || '0.0.0.0';
const ROOT = __dirname;
const PUBLIC = path.join(ROOT, 'public');
const DATA = path.join(ROOT, 'data');
fs.mkdirSync(DATA, { recursive: true });

const DB_FILE = process.env.DB_PATH || path.join(DATA, 'mantenimiento.db');
const db = new DatabaseSync(DB_FILE);
db.exec('PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;');

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    employee_number TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('Administrador','Jefatura','Técnico','Solicitante')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('Maquinaria','Infraestructura','Unidad móvil')),
    area TEXT NOT NULL,
    brand TEXT,
    model TEXT,
    status TEXT NOT NULL DEFAULT 'Disponible' CHECK (status IN ('Disponible','En mantenimiento','Detenido','Fuera de servicio')),
    critical INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY,
    folio TEXT NOT NULL UNIQUE,
    requested_at TEXT NOT NULL,
    requester_id INTEGER NOT NULL REFERENCES users(id),
    priority TEXT NOT NULL CHECK (priority IN ('Paro de máquina','Alta','Media','Baja')),
    classification TEXT NOT NULL,
    specialty TEXT,
    asset_id INTEGER REFERENCES assets(id),
    reported_failure TEXT NOT NULL,
    actions TEXT,
    technician_id INTEGER REFERENCES users(id),
    started_at TEXT,
    finished_at TEXT,
    labor_hours REAL NOT NULL DEFAULT 0 CHECK (labor_hours >= 0),
    material_summary TEXT,
    material_cost REAL NOT NULL DEFAULT 0 CHECK (material_cost >= 0),
    status TEXT NOT NULL DEFAULT 'Abierta' CHECK (status IN ('Abierta','En proceso','Espera de material','Completada','Cancelada')),
    validator_id INTEGER REFERENCES users(id),
    validated_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS preventive_plans (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id),
    title TEXT NOT NULL,
    frequency TEXT NOT NULL,
    next_date TEXT NOT NULL,
    responsible_id INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'Programado' CHECK (status IN ('Programado','Próximo','Vencido','Ejecutado','Reprogramado')),
    work_order_id INTEGER REFERENCES work_orders(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_orders_status ON work_orders(status);
  CREATE INDEX IF NOT EXISTS idx_orders_asset ON work_orders(asset_id);
  CREATE INDEX IF NOT EXISTS idx_preventive_date ON preventive_plans(next_date);
`);

function addColumn(table, definition) {
  const name = definition.split(/\s+/)[0];
  const columns = db.prepare(`PRAGMA table_info(${table})`).all();
  if (!columns.some(column => column.name === name)) db.exec(`ALTER TABLE ${table} ADD COLUMN ${definition}`);
}
addColumn('users', 'last_name TEXT');
addColumn('users', 'username TEXT');
addColumn('users', 'password_hash TEXT');
addColumn('users', 'must_change_password INTEGER NOT NULL DEFAULT 0');
db.prepare('UPDATE users SET username=employee_number WHERE username IS NULL').run();
addColumn('assets', 'voltage TEXT');
addColumn('assets', 'serial_code TEXT');
addColumn('assets', 'observations TEXT');
addColumn('assets', 'operating_hours REAL NOT NULL DEFAULT 0');
addColumn('work_orders', 'labor_cost REAL NOT NULL DEFAULT 0');

db.exec(`
  CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL;
  CREATE TABLE IF NOT EXISTS user_permissions (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    module TEXT NOT NULL CHECK (module IN ('dashboard','orders','assets','preventives','users')),
    allowed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id,module)
  );
  CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
  CREATE TABLE IF NOT EXISTS work_order_events (
    id INTEGER PRIMARY KEY,
    work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    event TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_order_events_order ON work_order_events(work_order_id,created_at);
  CREATE TABLE IF NOT EXISTS maintenance_materials (
    id INTEGER PRIMARY KEY,
    work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    code TEXT,
    description TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 1 CHECK(quantity>0),
    unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost>=0)
  );
  CREATE INDEX IF NOT EXISTS idx_materials_order ON maintenance_materials(work_order_id);
`);

function seed() {
  const count = db.prepare('SELECT COUNT(*) total FROM users').get().total;
  if (count) return;
  db.exec('BEGIN');
  try {
    const user = db.prepare('INSERT INTO users (employee_number,name,role) VALUES (?,?,?)');
    user.run('252', 'Lucio Franco', 'Jefatura');
    user.run('T-101', 'Orlando Martínez', 'Técnico');
    user.run('T-102', 'Cristian López', 'Técnico');
    user.run('OP-001', 'Operador de ejemplo', 'Solicitante');

    const asset = db.prepare('INSERT INTO assets (code,name,category,area,brand,model,status,critical) VALUES (?,?,?,?,?,?,?,?)');
    asset.run('DEMO-MAQ-001', 'Cortadora de demostración', 'Maquinaria', 'Corte', 'Demo Industrial', 'CT-100', 'Disponible', 1);
    asset.run('DEMO-INF-001', 'Iluminación nave principal', 'Infraestructura', 'Nave principal', null, null, 'Disponible', 0);
    asset.run('DEMO-UNI-001', 'Montacargas de demostración', 'Unidad móvil', 'Almacén', 'Demo Motors', 'MX-20', 'En mantenimiento', 1);

    const order = db.prepare(`INSERT INTO work_orders
      (folio,requested_at,requester_id,priority,classification,specialty,asset_id,reported_failure,actions,technician_id,started_at,labor_hours,material_summary,material_cost,status)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`);
    order.run('OT-2026-001', '2026-09-01T08:15', 4, 'Alta', 'Mantenimiento Correctivo', 'Mecánica', 3, 'Fuga hidráulica detectada durante inspección', 'Diagnóstico inicial y aislamiento del equipo', 2, '2026-09-01T08:30', 1.5, 'Material de demostración', 320, 'En proceso');
    order.run('OT-2026-002', '2026-09-02T10:00', 4, 'Media', 'Proyecto Kaizen', 'Eléctrico', 2, 'Iluminación insuficiente en estación', 'Instalación de luminaria de prueba', 3, '2026-09-02T10:30', 2, 'Luminaria LED de demostración', 450, 'Completada');

    const plan = db.prepare('INSERT INTO preventive_plans (asset_id,title,frequency,next_date,responsible_id,status,work_order_id) VALUES (?,?,?,?,?,?,?)');
    plan.run(1, 'Revisión mensual de elementos mecánicos', '1 mes', '2026-09-08', 2, 'Próximo', null);
    plan.run(3, 'Inspección de sistema hidráulico e izaje', '250 horas / 1 mes', '2026-09-15', 3, 'Programado', null);
    db.exec('COMMIT');
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  }
}
seed();

const MODULES = ['dashboard','orders','assets','preventives','users'];
function roleName(role) {
  return role === 'Administrador' ? 'Administrador' : role === 'Solicitante' ? 'Operador' : 'Personal de mantenimiento';
}
function roleModules(role) {
  if (role === 'Administrador') return MODULES;
  if (role === 'Solicitante') return ['orders'];
  return ['dashboard','orders','assets','preventives'];
}
async function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const derived = await scrypt(password, salt, 64);
  return `${salt}:${derived.toString('hex')}`;
}
async function verifyPassword(password, stored) {
  if (!stored || !stored.includes(':')) return false;
  const [salt, expectedHex] = stored.split(':');
  const actual = await scrypt(password, salt, 64);
  const expected = Buffer.from(expectedHex, 'hex');
  return expected.length === actual.length && crypto.timingSafeEqual(expected, actual);
}
async function ensureAdministrator() {
  let admin = db.prepare("SELECT * FROM users WHERE username='administrator'").get();
  if (!admin) {
    const result = db.prepare(`INSERT INTO users (employee_number,name,last_name,username,password_hash,role,active)
      VALUES (?,?,?,?,?,'Administrador',1)`).run('ADMIN','Administrator','MESA','administrator',DEFAULT_ADMIN_HASH);
    admin = { id: Number(result.lastInsertRowid) };
  } else if (!admin.password_hash) {
    db.prepare('UPDATE users SET password_hash=? WHERE id=?').run(DEFAULT_ADMIN_HASH,admin.id);
  }
  const grant = db.prepare('INSERT INTO user_permissions (user_id,module,allowed) VALUES (?,?,1) ON CONFLICT(user_id,module) DO UPDATE SET allowed=1');
  for (const module of MODULES) grant.run(admin.id,module);
}

const json = (res, status, value) => {
  const body = JSON.stringify(value);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
};

async function body(req) {
  let raw = '';
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 1_000_000) throw Object.assign(new Error('Solicitud demasiado grande'), { status: 413 });
  }
  try { return raw ? JSON.parse(raw) : {}; }
  catch { throw Object.assign(new Error('JSON inválido'), { status: 400 }); }
}

function cookies(req) {
  return Object.fromEntries((req.headers.cookie || '').split(';').filter(Boolean).map(part => {
    const index = part.indexOf('=');
    return [part.slice(0,index).trim(), decodeURIComponent(part.slice(index+1).trim())];
  }));
}
function currentUser(req) {
  const token = cookies(req).mesa_session;
  if (!token) return null;
  const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
  const user = db.prepare(`SELECT u.id,u.employee_number,u.name,u.last_name,u.username,u.role,u.active,s.expires_at
    FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>datetime('now') AND u.active=1`).get(tokenHash);
  if (!user) return null;
  user.permissions = roleModules(user.role);
  return user;
}
function publicUser(user) {
  return { id:user.id,employee_number:user.employee_number,name:user.name,last_name:user.last_name||'',username:user.username,role:user.role,role_name:roleName(user.role),permissions:roleModules(user.role) };
}
function requirePermission(req, module) {
  const user = currentUser(req);
  if (!user) throw Object.assign(new Error('Sesión requerida'), { status: 401 });
  const allowed = user.role === 'Administrador'
    || (user.role !== 'Solicitante' && module !== 'users')
    || (user.role === 'Solicitante' && module === 'orders' && ['GET','POST'].includes(req.method));
  if (!allowed) throw Object.assign(new Error('Tu rol no tiene acceso a este apartado'), { status: 403 });
  return user;
}
function validatePassword(password) {
  if (typeof password !== 'string' || password.length < 8) throw Object.assign(new Error('La contraseña debe tener al menos 8 caracteres'), { status: 400 });
}

function dashboard() {
  const orders = db.prepare(`SELECT COUNT(*) total,
    SUM(status='Completada') completed, SUM(status IN ('Abierta','En proceso','Espera de material')) pending,
    SUM(status='Abierta') new_orders, SUM(status='Abierta' AND technician_id IS NULL) unassigned,
    SUM(priority='Paro de máquina' AND status NOT IN ('Completada','Cancelada')) critical,
    COALESCE(SUM(labor_hours),0) labor_hours, COALESCE(SUM(material_cost),0) material_cost FROM work_orders`).get();
  const assets = db.prepare(`SELECT COUNT(*) total, SUM(status='Detenido') stopped, SUM(status='En mantenimiento') maintenance FROM assets`).get();
  const preventives = db.prepare(`SELECT COUNT(*) total, SUM(status IN ('Próximo','Vencido')) attention FROM preventive_plans`).get();
  const byStatus = db.prepare('SELECT status label, COUNT(*) value FROM work_orders GROUP BY status ORDER BY value DESC').all();
  const byClassification = db.prepare('SELECT classification label,COUNT(*) value FROM work_orders GROUP BY classification ORDER BY value DESC LIMIT 6').all();
  const recent = db.prepare(`SELECT wo.id,wo.folio,wo.priority,wo.status,wo.requested_at,a.name asset
    FROM work_orders wo LEFT JOIN assets a ON a.id=wo.asset_id ORDER BY wo.requested_at DESC LIMIT 5`).all();
  const urgent = db.prepare(`SELECT wo.id,wo.folio,wo.priority,wo.status,wo.reported_failure,a.name asset
    FROM work_orders wo LEFT JOIN assets a ON a.id=wo.asset_id
    WHERE wo.status NOT IN ('Completada','Cancelada') ORDER BY CASE wo.priority WHEN 'Paro de máquina' THEN 1 WHEN 'Alta' THEN 2 WHEN 'Media' THEN 3 ELSE 4 END,wo.requested_at LIMIT 5`).all();
  return { orders, assets, preventives, byStatus, byClassification, recent, urgent };
}

function listOrders(requesterId = null) {
  return db.prepare(`SELECT wo.*, a.code asset_code,a.name asset_name,(u.name||' '||COALESCE(u.last_name,'')) requester_name,(t.name||' '||COALESCE(t.last_name,'')) technician_name
    FROM work_orders wo JOIN users u ON u.id=wo.requester_id LEFT JOIN users t ON t.id=wo.technician_id
    LEFT JOIN assets a ON a.id=wo.asset_id WHERE (? IS NULL OR wo.requester_id=?) ORDER BY wo.requested_at DESC`).all(requesterId,requesterId);
}

function orderDetails(id) {
  const order = db.prepare(`SELECT wo.*,a.code asset_code,a.name asset_name,a.area asset_area,a.brand asset_brand,a.model asset_model,a.voltage asset_voltage,a.serial_code asset_serial_code,
    (u.name||' '||COALESCE(u.last_name,'')) requester_name,u.employee_number requester_number,
    (t.name||' '||COALESCE(t.last_name,'')) technician_name,(v.name||' '||COALESCE(v.last_name,'')) validator_name
    FROM work_orders wo JOIN users u ON u.id=wo.requester_id LEFT JOIN users t ON t.id=wo.technician_id
    LEFT JOIN users v ON v.id=wo.validator_id LEFT JOIN assets a ON a.id=wo.asset_id WHERE wo.id=?`).get(id);
  if (!order) return null;
  order.events = db.prepare(`SELECT e.*, (u.name||' '||COALESCE(u.last_name,'')) user_name FROM work_order_events e
    LEFT JOIN users u ON u.id=e.user_id WHERE e.work_order_id=? ORDER BY e.created_at DESC,e.id DESC`).all(id);
  order.materials = db.prepare('SELECT id,code,description,quantity,unit_cost,(quantity*unit_cost) total FROM maintenance_materials WHERE work_order_id=? ORDER BY id').all(id);
  return order;
}

function assetDetails(id) {
  const asset=db.prepare('SELECT * FROM assets WHERE id=?').get(id);
  if(!asset)return null;
  asset.maintenances=db.prepare(`SELECT wo.id,wo.folio,wo.requested_at,wo.classification,wo.reported_failure,wo.actions,wo.status,
    wo.started_at,wo.finished_at,wo.labor_hours,wo.labor_cost,wo.material_cost,(u.name||' '||COALESCE(u.last_name,'')) technician_name
    FROM work_orders wo LEFT JOIN users u ON u.id=wo.technician_id WHERE wo.asset_id=? ORDER BY wo.requested_at DESC`).all(id);
  asset.metrics=db.prepare(`SELECT COUNT(*) maintenance_count,COALESCE(AVG(NULLIF(labor_hours,0)),0) mttr,
    COALESCE(SUM(labor_cost+material_cost),0) total_cost,MAX(finished_at) last_maintenance FROM work_orders WHERE asset_id=?`).get(id);
  return asset;
}

function nextFolio() {
  const year = new Date().getFullYear();
  const row = db.prepare("SELECT folio FROM work_orders WHERE folio LIKE ? ORDER BY CAST(substr(folio,-3) AS INTEGER) DESC LIMIT 1").get(`OT-${year}-%`);
  const next = row ? Number(row.folio.slice(-3)) + 1 : 1;
  return `OT-${year}-${String(next).padStart(3, '0')}`;
}

async function api(req, res, url) {
  if (req.method === 'GET' && url.pathname === '/api/health') {
    db.prepare('SELECT 1').get();
    return json(res,200,{status:'ok'});
  }
  if (req.method === 'POST' && url.pathname === '/api/auth/login') {
    const b = await body(req);
    const user = db.prepare('SELECT * FROM users WHERE username=? AND active=1').get(String(b.username||'').trim());
    if (!user || !(await verifyPassword(String(b.password||''),user.password_hash))) throw Object.assign(new Error('Usuario o contraseña incorrectos'), { status: 401 });
    const token = crypto.randomBytes(32).toString('base64url');
    const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
    db.prepare("INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,datetime('now','+12 hours'))").run(tokenHash,user.id);
    res.setHeader('Set-Cookie',`mesa_session=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200`);
    return json(res,200,publicUser(currentUser({headers:{cookie:`mesa_session=${token}`}})));
  }
  if (req.method === 'POST' && url.pathname === '/api/auth/logout') {
    const token = cookies(req).mesa_session;
    if (token) db.prepare('DELETE FROM sessions WHERE token_hash=?').run(crypto.createHash('sha256').update(token).digest('hex'));
    res.setHeader('Set-Cookie','mesa_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0');
    return json(res,200,{ok:true});
  }
  if (req.method === 'GET' && url.pathname === '/api/auth/me') {
    const user = currentUser(req);
    if (!user) throw Object.assign(new Error('Sesión requerida'), { status: 401 });
    return json(res,200,publicUser(user));
  }
  const routeModule = url.pathname.startsWith('/api/orders') ? 'orders'
    : url.pathname.startsWith('/api/assets') ? 'assets'
    : url.pathname.startsWith('/api/preventives') ? 'preventives'
    : url.pathname.startsWith('/api/users') ? 'users' : 'dashboard';
  const authUser = url.pathname === '/api/catalogs' ? currentUser(req) : requirePermission(req,routeModule);
  if (!authUser) throw Object.assign(new Error('Sesión requerida'), { status: 401 });

  if (req.method === 'GET' && url.pathname === '/api/users') {
    return json(res,200,db.prepare(`SELECT id,employee_number,name,last_name,username,role,active,created_at
      FROM users ORDER BY role='Administrador' DESC,name,last_name`).all().map(user=>({...user,role_name:roleName(user.role),permissions:roleModules(user.role)})));
  }
  if (req.method === 'POST' && url.pathname === '/api/users') {
    const b=await body(req);
    for(const key of ['employee_number','name','last_name','password']) if(!String(b[key]||'').trim()) throw Object.assign(new Error(`Falta el campo ${key}`),{status:400});
    validatePassword(b.password);
    const username=String(b.username||b.employee_number).trim();
    const role=b.role==='Mantenimiento'?'Técnico':'Solicitante';
    db.exec('BEGIN');
    try {
      const result=db.prepare(`INSERT INTO users (employee_number,name,last_name,username,password_hash,role,active,must_change_password)
        VALUES (?,?,?,?,?,?,1,1)`).run(String(b.employee_number).trim(),String(b.name).trim(),String(b.last_name).trim(),username,await hashPassword(b.password),role);
      db.exec('COMMIT'); return json(res,201,{id:Number(result.lastInsertRowid),username});
    } catch(error){db.exec('ROLLBACK');throw error;}
  }
  if (req.method === 'PATCH' && /^\/api\/users\/\d+$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/').pop()); const b=await body(req);
    const target=db.prepare('SELECT * FROM users WHERE id=?').get(id);
    if(!target) throw Object.assign(new Error('Usuario no encontrado'),{status:404});
    if(target.username==='administrator' && b.active===false) throw Object.assign(new Error('No se puede desactivar al administrador principal'),{status:400});
    db.exec('BEGIN');
    try {
      if(Object.hasOwn(b,'active')) db.prepare('UPDATE users SET active=? WHERE id=?').run(b.active?1:0,id);
      if(b.role && target.role!=='Administrador') db.prepare('UPDATE users SET role=? WHERE id=?').run(b.role==='Mantenimiento'?'Técnico':'Solicitante',id);
      if(b.password){validatePassword(b.password);db.prepare('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?').run(await hashPassword(b.password),id);db.prepare('DELETE FROM sessions WHERE user_id=?').run(id);}
      db.exec('COMMIT');return json(res,200,{ok:true});
    }catch(error){db.exec('ROLLBACK');throw error;}
  }
  if (req.method === 'GET' && url.pathname === '/api/dashboard') return json(res, 200, dashboard());
  if (req.method === 'GET' && url.pathname === '/api/orders/export.csv') {
    if(authUser.role==='Solicitante') throw Object.assign(new Error('Tu rol no puede exportar órdenes'),{status:403});
    const rows=listOrders();
    const columns=[['Folio','folio'],['Fecha solicitud','requested_at'],['Solicitante','requester_name'],['Prioridad','priority'],['Clasificación','classification'],['Especialidad','specialty'],['Activo','asset_name'],['Falla reportada','reported_failure'],['Acciones','actions'],['Técnico','technician_name'],['Inicio','started_at'],['Fin','finished_at'],['Horas hombre','labor_hours'],['Material utilizado','material_summary'],['Costo materiales','material_cost'],['Estado','status']];
    const cell=value=>{let text=String(value??'');if(/^[=+\-@]/.test(text))text=`'${text}`;return `"${text.replaceAll('"','""')}"`};
    const csv='\uFEFF'+[columns.map(x=>cell(x[0])).join(','),...rows.map(row=>columns.map(x=>cell(row[x[1]])).join(','))].join('\r\n');
    res.writeHead(200,{'Content-Type':'text/csv; charset=utf-8','Content-Disposition':'attachment; filename="ordenes-mantenimiento.csv"'});res.end(csv);return true;
  }
  if (req.method === 'GET' && url.pathname === '/api/orders') return json(res, 200, listOrders(authUser.role==='Solicitante'?authUser.id:null));
  if (req.method === 'GET' && /^\/api\/orders\/\d+$/.test(url.pathname)) {
    const order=orderDetails(Number(url.pathname.split('/').pop()));
    if(!order) throw Object.assign(new Error('Orden no encontrada'),{status:404});
    if(authUser.role==='Solicitante'&&order.requester_id!==authUser.id) throw Object.assign(new Error('No puedes consultar reportes de otro operador'),{status:403});
    return json(res,200,order);
  }
  if (req.method === 'GET' && url.pathname === '/api/assets') return json(res, 200, db.prepare('SELECT * FROM assets ORDER BY name').all());
  if (req.method === 'GET' && /^\/api\/assets\/\d+$/.test(url.pathname)) {
    const asset=assetDetails(Number(url.pathname.split('/').pop()));
    if(!asset) throw Object.assign(new Error('Activo no encontrado'),{status:404});
    return json(res,200,asset);
  }
  if (req.method === 'GET' && url.pathname === '/api/preventives') return json(res, 200, db.prepare(`SELECT p.*,a.code asset_code,a.name asset_name,u.name responsible_name FROM preventive_plans p JOIN assets a ON a.id=p.asset_id LEFT JOIN users u ON u.id=p.responsible_id ORDER BY p.next_date`).all());
  if (req.method === 'GET' && url.pathname === '/api/catalogs') return json(res, 200, {
    users: authUser.role === 'Solicitante'
      ? [{id:authUser.id,employee_number:authUser.employee_number,name:`${authUser.name} ${authUser.last_name||''}`.trim(),role:authUser.role}]
      : db.prepare('SELECT id,employee_number,name,role FROM users WHERE active=1 ORDER BY name').all(),
    assets: db.prepare('SELECT id,code,name,category,area,status FROM assets ORDER BY name').all(),
    priorities: ['Paro de máquina','Alta','Media','Baja'],
    classifications: ['Mantenimiento Preventivo','Mantenimiento Correctivo','Mantenimiento Autónomo','Apoyo para ajuste de máquina','Daño de Herramental','Daño de Fixture','Proyecto Kaizen'],
    specialties: ['Eléctrico','Mecánica','Soldadura','Hidráulica / Neumática','Modificación de pieza','Reparación de activo']
  });
  if (req.method === 'POST' && url.pathname === '/api/orders') {
    const b = await body(req);
    if (authUser.role === 'Solicitante') {
      b.requester_id = authUser.id;
      b.specialty = null; b.actions = null; b.technician_id = null;
      b.started_at = null; b.finished_at = null; b.labor_hours = 0;
      b.material_summary = null; b.material_cost = 0; b.status = 'Abierta';
    }
    for (const key of ['requester_id','priority','classification','reported_failure']) if (!b[key]) throw Object.assign(new Error(`Falta el campo ${key}`), { status: 400 });
    const folio = nextFolio();
    const result = db.prepare(`INSERT INTO work_orders (folio,requested_at,requester_id,priority,classification,specialty,asset_id,reported_failure,actions,technician_id,started_at,finished_at,labor_hours,material_summary,material_cost,status)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(folio,b.requested_at||new Date().toISOString(),b.requester_id,b.priority,b.classification,b.specialty||null,b.asset_id||null,b.reported_failure,b.actions||null,b.technician_id||null,b.started_at||null,b.finished_at||null,Number(b.labor_hours)||0,b.material_summary||null,Number(b.material_cost)||0,b.status||'Abierta');
    db.prepare('INSERT INTO work_order_events (work_order_id,user_id,event,details) VALUES (?,?,?,?)').run(result.lastInsertRowid,authUser.id,'Reporte creado',`Prioridad: ${b.priority}`);
    return json(res, 201, { id: Number(result.lastInsertRowid), folio });
  }
  if (req.method === 'PATCH' && /^\/api\/orders\/\d+$/.test(url.pathname)) {
    const id = Number(url.pathname.split('/').pop()); const b = await body(req);
    const allowed = ['priority','classification','specialty','asset_id','reported_failure','actions','technician_id','started_at','finished_at','labor_hours','labor_cost','material_summary','material_cost','status'];
    const keys = allowed.filter(k => Object.hasOwn(b,k));
    if (!keys.length) throw Object.assign(new Error('No hay campos válidos'), { status: 400 });
    const before=db.prepare('SELECT * FROM work_orders WHERE id=?').get(id);
    if(!before) throw Object.assign(new Error('Orden no encontrada'),{status:404});
    if(b.finished_at && (b.started_at||before.started_at) && !Object.hasOwn(b,'labor_hours')) {
      const elapsed=(new Date(b.finished_at)-new Date(b.started_at||before.started_at))/3600000;
      if(Number.isFinite(elapsed)&&elapsed>=0){b.labor_hours=Math.round(elapsed*100)/100;keys.push('labor_hours');}
    }
    if(b.status==='Completada'&&!b.finished_at&&!before.finished_at){b.finished_at=new Date().toISOString();keys.push('finished_at');}
    const result = db.prepare(`UPDATE work_orders SET ${keys.map(k=>`${k}=?`).join(',')},validator_id=CASE WHEN ?='Completada' THEN ? ELSE validator_id END,validated_at=CASE WHEN ?='Completada' THEN CURRENT_TIMESTAMP ELSE validated_at END,updated_at=CURRENT_TIMESTAMP WHERE id=?`).run(...keys.map(k=>b[k] === '' ? null : b[k]),b.status||'',authUser.id,b.status||'',id);
    if (!result.changes) throw Object.assign(new Error('Orden no encontrada'), { status: 404 });
    if(Array.isArray(b.materials)){
      db.prepare('DELETE FROM maintenance_materials WHERE work_order_id=?').run(id);
      const insertMaterial=db.prepare('INSERT INTO maintenance_materials (work_order_id,code,description,quantity,unit_cost) VALUES (?,?,?,?,?)');
      let total=0;for(const material of b.materials){if(!String(material.description||'').trim())continue;const quantity=Math.max(Number(material.quantity)||1,0.01);const cost=Math.max(Number(material.unit_cost)||0,0);insertMaterial.run(id,material.code||null,String(material.description).trim(),quantity,cost);total+=quantity*cost;}
      db.prepare('UPDATE work_orders SET material_cost=? WHERE id=?').run(Math.round(total*100)/100,id);
    }
    const changes=keys.filter(key=>String(before[key]??'')!==String(b[key]??'')).map(key=>key==='status'?`Estado: ${before.status} → ${b.status}`:key==='technician_id'?'Técnico asignado actualizado':key==='actions'?'Acciones de trabajo actualizadas':key).join(' · ');
    db.prepare('INSERT INTO work_order_events (work_order_id,user_id,event,details) VALUES (?,?,?,?)').run(id,authUser.id,b.status!==before.status?'Cambio de estado':'Orden actualizada',changes||null);
    const updated=db.prepare('SELECT asset_id,priority,status FROM work_orders WHERE id=?').get(id);
    if(updated.asset_id){
      if(updated.status==='En proceso'&&updated.priority==='Paro de máquina') db.prepare("UPDATE assets SET status='En mantenimiento' WHERE id=?").run(updated.asset_id);
      if(updated.status==='Completada'&&!db.prepare("SELECT 1 FROM work_orders WHERE asset_id=? AND id<>? AND status IN ('Abierta','En proceso','Espera de material') LIMIT 1").get(updated.asset_id,id)) db.prepare("UPDATE assets SET status='Disponible' WHERE id=?").run(updated.asset_id);
    }
    return json(res, 200, { ok: true });
  }
  if (req.method === 'POST' && url.pathname === '/api/assets') {
    const b=await body(req); for(const key of ['code','name','category','area']) if(!b[key]) throw Object.assign(new Error(`Falta el campo ${key}`),{status:400});
    const result=db.prepare('INSERT INTO assets (code,name,category,area,brand,model,status,critical,voltage,serial_code,observations,operating_hours) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)').run(b.code.trim().toUpperCase(),b.name,b.category,b.area,b.brand||null,b.model||null,b.status||'Disponible',b.critical?1:0,b.voltage||null,b.serial_code||null,b.observations||null,Number(b.operating_hours)||0);
    return json(res,201,{id:Number(result.lastInsertRowid)});
  }
  if (req.method === 'PATCH' && /^\/api\/assets\/\d+$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/').pop());const b=await body(req);
    const allowed=['code','name','category','area','brand','model','status','critical','voltage','serial_code','observations','operating_hours'];
    const keys=allowed.filter(key=>Object.hasOwn(b,key));if(!keys.length)throw Object.assign(new Error('No hay campos válidos'),{status:400});
    const result=db.prepare(`UPDATE assets SET ${keys.map(key=>`${key}=?`).join(',')} WHERE id=?`).run(...keys.map(key=>key==='critical'?(b[key]?1:0):b[key]===''?null:b[key]),id);
    if(!result.changes)throw Object.assign(new Error('Activo no encontrado'),{status:404});return json(res,200,{ok:true});
  }
  if (req.method === 'POST' && url.pathname === '/api/preventives') {
    const b=await body(req); for(const key of ['asset_id','title','frequency','next_date']) if(!b[key]) throw Object.assign(new Error(`Falta el campo ${key}`),{status:400});
    const result=db.prepare('INSERT INTO preventive_plans (asset_id,title,frequency,next_date,responsible_id,status) VALUES (?,?,?,?,?,?)').run(b.asset_id,b.title,b.frequency,b.next_date,b.responsible_id||null,b.status||'Programado');
    return json(res,201,{id:Number(result.lastInsertRowid)});
  }
  if (req.method === 'POST' && /^\/api\/preventives\/\d+\/order$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/')[3]);
    const plan=db.prepare('SELECT * FROM preventive_plans WHERE id=?').get(id);
    if(!plan) throw Object.assign(new Error('Preventivo no encontrado'),{status:404});
    if(plan.work_order_id) return json(res,200,{id:plan.work_order_id,already_exists:true});
    const folio=nextFolio();db.exec('BEGIN');
    try{
      const result=db.prepare(`INSERT INTO work_orders (folio,requested_at,requester_id,priority,classification,specialty,asset_id,reported_failure,technician_id,status)
        VALUES (?,datetime('now'),?,'Media','Mantenimiento Preventivo','Mecánica',?,?,?,'Abierta')`).run(folio,authUser.id,plan.asset_id,plan.title,plan.responsible_id);
      db.prepare("UPDATE preventive_plans SET work_order_id=?,status='Próximo' WHERE id=?").run(result.lastInsertRowid,id);
      db.prepare('INSERT INTO work_order_events (work_order_id,user_id,event,details) VALUES (?,?,?,?)').run(result.lastInsertRowid,authUser.id,'Orden preventiva generada',`Programa preventivo #${id}`);
      db.exec('COMMIT');return json(res,201,{id:Number(result.lastInsertRowid),folio});
    }catch(error){db.exec('ROLLBACK');throw error;}
  }
  return false;
}

const mime = { '.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.svg':'image/svg+xml','.png':'image/png' };
function staticFile(req,res,url) {
  const requested = url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname.slice(1));
  const file = path.resolve(PUBLIC, requested);
  if (!file.startsWith(PUBLIC + path.sep) && file !== path.join(PUBLIC,'index.html')) return json(res,403,{error:'Acceso denegado'});
  fs.readFile(file,(err,data)=>{
    if(err){ if(!path.extname(requested)) return fs.readFile(path.join(PUBLIC,'index.html'),(e,d)=>{if(e)return json(res,404,{error:'No encontrado'});res.writeHead(200,{'Content-Type':mime['.html']});res.end(d)}); return json(res,404,{error:'No encontrado'}); }
    res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store, no-cache, must-revalidate','Pragma':'no-cache','Expires':'0'});res.end(data);
  });
}

const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,`http://${req.headers.host||'localhost'}`);
  try { if(url.pathname.startsWith('/api/')) { const handled=await api(req,res,url); if(handled===false) json(res,404,{error:'Ruta no encontrada'}); } else staticFile(req,res,url); }
  catch(error){ const duplicate=String(error.message).includes('UNIQUE constraint'); const status=error.status||(duplicate?409:500); if(status>=500) console.error(error); json(res,status,{error:duplicate?'El registro ya existe':error.message}); }
});
ensureAdministrator().then(() => {
  db.prepare("DELETE FROM sessions WHERE expires_at<=datetime('now')").run();
  server.listen(PORT,HOST,()=>console.log(`MESA Mantenimiento disponible en http://localhost:${PORT}`));
}).catch(error => { console.error('No fue posible iniciar:',error); process.exitCode=1; });

function shutdown() {
  server.close(() => { db.close(); process.exit(0); });
  setTimeout(() => process.exit(1), 5000).unref();
}
process.on('SIGTERM',shutdown);
process.on('SIGINT',shutdown);

module.exports={server,db};
