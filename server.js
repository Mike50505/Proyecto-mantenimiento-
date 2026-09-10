'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { promisify } = require('node:util');
const { DatabaseSync } = require('node:sqlite');
const scrypt = promisify(crypto.scrypt);
const { operatorOrder } = require('./lib/order-access');
const { hoursBetween } = require('./lib/time');
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
  CREATE TABLE IF NOT EXISTS folio_sequences (
    year INTEGER PRIMARY KEY,
    next_number INTEGER NOT NULL CHECK(next_number > 0)
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
    version INTEGER NOT NULL DEFAULT 1,
    template_code TEXT,
    instructions TEXT,
    applies_when TEXT,
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
addColumn('assets', 'original_code TEXT');
addColumn('assets', 'alias_codes TEXT');
addColumn('assets', "asset_type TEXT NOT NULL DEFAULT 'Maquinaria'");
addColumn('assets', "operational_status TEXT NOT NULL DEFAULT 'Sin informaciÃ³n'");
addColumn('assets', 'operational_status_cause TEXT');
addColumn('assets', 'operational_status_updated_at TEXT');
addColumn('assets', "administrative_status TEXT NOT NULL DEFAULT 'Activo'");
db.prepare("UPDATE assets SET asset_type=category WHERE asset_type IS NULL OR asset_type='Maquinaria' AND category<>'Maquinaria'").run();
db.prepare("UPDATE assets SET operational_status=CASE status WHEN 'Disponible' THEN 'Operativa' WHEN 'Detenido' THEN 'Parada' WHEN 'En mantenimiento' THEN 'En mantenimiento' WHEN 'Fuera de servicio' THEN 'Sin informaciÃ³n' ELSE 'Sin informaciÃ³n' END, operational_status_updated_at=COALESCE(operational_status_updated_at,created_at) WHERE operational_status='Sin informaciÃ³n'").run();
addColumn('work_orders', 'labor_cost REAL NOT NULL DEFAULT 0');
addColumn('work_orders', "validation_status TEXT NOT NULL DEFAULT 'No aplica'");
addColumn('work_orders', 'closed_at TEXT');
addColumn('work_orders', 'close_reason TEXT');
addColumn('work_orders', 'version INTEGER NOT NULL DEFAULT 1');
addColumn('work_orders', 'idempotency_key TEXT');
addColumn('work_orders', 'location TEXT');
addColumn('work_orders', 'scheduled_at TEXT');
addColumn('work_orders', 'closure_notes TEXT');
addColumn('work_orders', 'closure_document_code TEXT');
addColumn('work_orders', 'closure_document_revision TEXT');
addColumn('work_orders', 'autonomous_checklist TEXT');

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
  CREATE TABLE IF NOT EXISTS work_order_time_entries (
    id INTEGER PRIMARY KEY,
    work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    pause_reason TEXT,
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','timer')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (finished_at IS NULL OR finished_at >= started_at)
  );
  CREATE INDEX IF NOT EXISTS idx_time_entries_order ON work_order_time_entries(work_order_id,started_at);
  CREATE TABLE IF NOT EXISTS work_order_participants (
    work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL DEFAULT 'Colaborador',
    PRIMARY KEY (work_order_id,user_id)
  );
  CREATE TABLE IF NOT EXISTS downtime_events (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id),
    cause TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (finished_at IS NULL OR finished_at >= started_at)
  );
  CREATE TABLE IF NOT EXISTS downtime_work_orders (
    downtime_id INTEGER NOT NULL REFERENCES downtime_events(id) ON DELETE CASCADE,
    work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    PRIMARY KEY (downtime_id,work_order_id)
  );
  CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS user_action_permissions (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    allowed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, action)
  );
  CREATE TABLE IF NOT EXISTS user_area_permissions (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    area TEXT NOT NULL,
    allowed INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, area)
  );
`);
db.exec("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_idempotency ON work_orders(idempotency_key) WHERE idempotency_key IS NOT NULL");
const permissionsSchema = db.prepare("SELECT sql FROM sqlite_master WHERE type='table' AND name='user_permissions'").get();
if (permissionsSchema && !permissionsSchema.sql.includes("'inventory'")) {
  db.exec(`
    ALTER TABLE user_permissions RENAME TO user_permissions_old;
    CREATE TABLE user_permissions (
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      module TEXT NOT NULL CHECK (module IN ('dashboard','orders','assets','preventives','inventory','users')),
      allowed INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (user_id,module)
    );
    INSERT INTO user_permissions (user_id,module,allowed) SELECT user_id,module,allowed FROM user_permissions_old;
    DROP TABLE user_permissions_old;
  `);
}
addColumn('maintenance_materials', 'inventory_item_id INTEGER REFERENCES inventory_items(id)');
addColumn('preventive_plans', 'version INTEGER NOT NULL DEFAULT 1');
addColumn('preventive_plans', 'template_code TEXT');
addColumn('preventive_plans', 'instructions TEXT');
addColumn('preventive_plans', 'applies_when TEXT');

db.exec(`
  CREATE TABLE IF NOT EXISTS inventory_items (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Refacción',
    unit TEXT NOT NULL DEFAULT 'pieza',
    stock REAL NOT NULL DEFAULT 0 CHECK(stock >= 0),
    min_stock REAL NOT NULL DEFAULT 0 CHECK(min_stock >= 0),
    max_stock REAL NOT NULL DEFAULT 0 CHECK(max_stock >= 0),
    unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost >= 0),
    location TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS inventory_movements (
    id INTEGER PRIMARY KEY,
    inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id),
    type TEXT NOT NULL CHECK(type IN ('Entrada','Salida','Ajuste')),
    quantity REAL NOT NULL CHECK(quantity > 0),
    unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost >= 0),
    work_order_id INTEGER REFERENCES work_orders(id),
    user_id INTEGER REFERENCES users(id),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_inventory_movements_item ON inventory_movements(inventory_item_id,created_at);
`);

require('./lib/business-migrations')(db);
const stockCommand = require('./lib/stock-commands');

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
if(process.env.MESA_DEMO==='1')seed();
const preventiveHistory=require('./lib/preventive-history');
const preventiveTasks=require('./lib/preventive-tasks');
preventiveTasks.migrate(db);
preventiveHistory.migrate(db);
const preventiveOccurrences=require('./lib/preventive-occurrences');
preventiveOccurrences.migrate(db);
const preventiveExecution=require('./lib/preventive-execution');
const preventiveCompliance=require('./lib/preventive-compliance');
const assetMeter=require('./lib/asset-meter');
const preventiveChecklists=require('./lib/preventive-checklists');
const preventiveTemplates=require('./lib/preventive-templates');
preventiveExecution.migrate(db);
assetMeter.migrate(db);
preventiveChecklists.migrate(db);
preventiveTemplates.migrate(db);
function seedInventory() {
  if (db.prepare('SELECT COUNT(*) total FROM inventory_items').get().total) return;
  const item = db.prepare(`INSERT INTO inventory_items
    (code,name,category,unit,stock,min_stock,max_stock,unit_cost,location) VALUES (?,?,?,?,?,?,?,?,?)`);
  item.run('MAT-DEMO-001','Tornillo hexagonal 8 mm','Tornillería','pieza',24,10,50,3.5,'Anaquel A-01');
  item.run('MAT-DEMO-002','Aceite hidráulico ISO 68','Lubricantes','litro',8,5,20,145,'Anaquel B-02');
  item.run('MAT-DEMO-003','Luminaria LED industrial','Eléctrico','pieza',2,2,8,450,'Anaquel C-01');
}
if(process.env.MESA_DEMO==='1')seedInventory();

function parseCSVText(text) {
  const clean = text.replace(/^\uFEFF/, '');
  const lines = clean.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n').filter(l => l.trim().length > 0);
  if (lines.length < 2) return [];
  const parseLine = line => {
    const values = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"' && line[i + 1] === '"') { current += '"'; i++; }
      else if (char === '"') { inQuotes = !inQuotes; }
      else if ((char === ',' || char === ';') && !inQuotes) { values.push(current.trim()); current = ''; }
      else { current += char; }
    }
    values.push(current.trim());
    return values;
  };
  const headers = parseLine(lines[0]).map(h => h.replace(/^["']|["']$/g, '').trim());
  const result = [];
  for (let i = 1; i < lines.length; i++) {
    const vals = parseLine(lines[i]);
    if (vals.some(v => v.length > 0)) {
      const obj = {};
      headers.forEach((h, idx) => {
        let val = vals[idx] || '';
        val = val.replace(/^["']|["']$/g, '').trim();
        obj[h] = val;
      });
      result.push(obj);
    }
  }
  return result;
}

const MODULES = ['dashboard','orders','assets','preventives','inventory','users'];
const ACTIONS = ['orders.create','orders.read','orders.edit','orders.edit_dates','orders.assign','orders.transition','orders.validate','orders.time','assets.read','assets.edit','preventives.read','preventives.edit','inventory.read','inventory.move','inventory.adjust','users.manage','audit.read'];
function roleName(role) {
  return role === 'Administrador' ? 'Administrador' : role === 'Solicitante' ? 'Operador' : 'Personal de mantenimiento';
}
function roleModules(role) {
  if (role === 'Administrador') return MODULES;
  if (role === 'Solicitante') return ['orders'];
  return ['dashboard','orders','assets','preventives','inventory'];
}
function roleActions(role) {
  if (role === 'Administrador') return ACTIONS;
  if (role === 'Jefatura') return ACTIONS.filter(action => !['users.manage'].includes(action));
  if (role === 'TÃ©cnico') return ACTIONS.filter(action => ['orders.read','orders.edit','orders.transition','orders.time','assets.read','preventives.read','inventory.read'].includes(action));
  return ['orders.create','orders.read'];
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
  const user = db.prepare(`SELECT u.id,u.employee_number,u.name,u.last_name,u.username,u.role,u.active,u.password_hash,u.must_change_password,s.expires_at
    FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>datetime('now') AND u.active=1`).get(tokenHash);
  if (!user) return null;
  const configured=db.prepare('SELECT module FROM user_permissions WHERE user_id=? AND allowed=1 ORDER BY module').all(user.id).map(row=>row.module);
  user.permissions = configured.length ? configured : roleModules(user.role);
  user.actions = userActions(user);
  user.areas = userAreas(user);
  return user;
}
function publicUser(user) {
  return { id:user.id,employee_number:user.employee_number,name:user.name,last_name:user.last_name||'',username:user.username,role:user.role,role_name:roleName(user.role),permissions:user.permissions||roleModules(user.role),actions:user.actions||roleActions(user.role),areas:user.areas||[],must_change_password:Boolean(user.must_change_password) };
}
function requirePermission(req, module) {
  const user = currentUser(req);
  if (!user) throw Object.assign(new Error('Sesión requerida'), { status: 401 });
  const allowed = (user.role !== 'Solicitante' && user.permissions.includes(module))
    || (user.role === 'Solicitante' && module === 'orders' && ['GET','POST'].includes(req.method));
  if (!allowed) throw Object.assign(new Error('Tu rol no tiene acceso a este apartado'), { status: 403 });
  return user;
}
function userActions(user) {
  const configured = db.prepare('SELECT action FROM user_action_permissions WHERE user_id=? AND allowed=1 ORDER BY action').all(user.id).map(row=>row.action);
  return configured.length ? configured : roleActions(user.role);
}
function userAreas(user) {
  return db.prepare('SELECT area FROM user_area_permissions WHERE user_id=? AND allowed=1 ORDER BY area').all(user.id).map(row=>row.area);
}
function hasAction(user, action) {
  return user.role === 'Administrador' || userActions(user).includes(action);
}
function hasArea(user, area) {
  const areas = userAreas(user);
  return !areas.length || !area || areas.includes(area);
}
function requireAction(user, action, area = null) {
  if (!hasAction(user, action)) throw Object.assign(new Error('Tu usuario no tiene permiso para esta acción'), { status: 403 });
  if (!hasArea(user, area)) throw Object.assign(new Error('Tu usuario no tiene permiso para esta área'), { status: 403 });
}
function validatePassword(password) {
  if (typeof password !== 'string' || password.length < 8) throw Object.assign(new Error('La contraseña debe tener al menos 8 caracteres'), { status: 400 });
}
function audit(userId, entityType, entityId, action, before, after, reason=null) {
  db.prepare(`INSERT INTO audit_log (user_id,entity_type,entity_id,action,before_json,after_json,reason)
    VALUES (?,?,?,?,?,?,?)`).run(userId,entityType,entityId,action,before?JSON.stringify(before):null,after?JSON.stringify(after):null,reason);
}
function orderLaborHours(orderId) {
  const rows=db.prepare('SELECT started_at,finished_at FROM work_order_time_entries WHERE work_order_id=? AND finished_at IS NOT NULL').all(orderId);
  return Math.round(rows.reduce((total,row)=>total+hoursBetween(row.started_at,row.finished_at),0)*100)/100;
}

function dashboard() {
  const orders = db.prepare(`SELECT COUNT(*) total,
    SUM(status='Completada') completed, SUM(status NOT IN ('Completada','Cancelada')) pending,
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

function listOrders(requesterId = null, filters = {}) {
  const where=['(? IS NULL OR wo.requester_id=?)'];
  const params=[requesterId,requesterId];
  if(filters.status){where.push('wo.status=?');params.push(filters.status);}
  if(filters.priority){where.push('wo.priority=?');params.push(filters.priority);}
  if(filters.area){where.push('a.area=?');params.push(filters.area);}
  if(filters.technician_id){where.push('wo.technician_id=?');params.push(Number(filters.technician_id));}
  if(filters.asset_id){where.push('wo.asset_id=?');params.push(Number(filters.asset_id));}
  if(filters.from){where.push('wo.requested_at>=?');params.push(filters.from);}
  if(filters.to){where.push('wo.requested_at<=?');params.push(filters.to);}
  if(filters.q){where.push('(wo.folio LIKE ? OR a.code LIKE ? OR a.name LIKE ? OR wo.reported_failure LIKE ? OR (u.name||\' \'||COALESCE(u.last_name,\'\')) LIKE ?)');params.push(...Array(5).fill(`%${filters.q}%`));}
  return db.prepare(`SELECT wo.*, a.code asset_code,a.name asset_name,a.area asset_area,(u.name||' '||COALESCE(u.last_name,'')) requester_name,(t.name||' '||COALESCE(t.last_name,'')) technician_name
    FROM work_orders wo JOIN users u ON u.id=wo.requester_id LEFT JOIN users t ON t.id=wo.technician_id
    LEFT JOIN assets a ON a.id=wo.asset_id WHERE ${where.join(' AND ')} ORDER BY wo.requested_at DESC`).all(...params);
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
  order.materials = db.prepare('SELECT id,inventory_item_id,code,description,quantity,returned_quantity,unit_cost,movement_id,((quantity-returned_quantity)*unit_cost) total FROM maintenance_materials WHERE work_order_id=? ORDER BY id').all(id);
  order.time_entries = db.prepare(`SELECT t.*, (u.name||' '||COALESCE(u.last_name,'')) user_name
    FROM work_order_time_entries t JOIN users u ON u.id=t.user_id WHERE t.work_order_id=? ORDER BY t.started_at`).all(id);
  order.downtime = db.prepare(`SELECT d.* FROM downtime_events d JOIN downtime_work_orders dw ON dw.downtime_id=d.id WHERE dw.work_order_id=? ORDER BY d.started_at`).all(id);
  const preventiveRevision=db.prepare(`SELECT r.* FROM preventive_order_revisions o
    JOIN preventive_plan_revisions r ON r.plan_id=o.plan_id AND r.version=o.version WHERE o.work_order_id=?`).get(id);
  order.preventive_revision=preventiveRevision ? {...preventiveRevision,snapshot:JSON.parse(preventiveRevision.snapshot_json),snapshot_json:undefined} : null;
  order.preventive_execution=preventiveExecution.read(db,id);
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

function nextFolio(ownTransaction=true) {
  const year = new Date().getFullYear();
  if(ownTransaction)db.exec('BEGIN IMMEDIATE');
  try {
    const row=db.prepare('SELECT next_number FROM folio_sequences WHERE year=?').get(year);
    const next=row?.next_number||1;
    if(row) db.prepare('UPDATE folio_sequences SET next_number=? WHERE year=?').run(next+1,year);
    else db.prepare('INSERT INTO folio_sequences (year,next_number) VALUES (?,?)').run(year,next+1);
    if(ownTransaction)db.exec('COMMIT');
    return `OT-${year}-${String(next).padStart(4,'0')}`;
  } catch(error){if(ownTransaction)db.exec('ROLLBACK');throw error;}
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
  if (req.method === 'POST' && url.pathname === '/api/auth/change-password') {
    const user = currentUser(req);
    if (!user) throw Object.assign(new Error('SesiÃ³n requerida'), { status: 401 });
    const b = await body(req);
    if (!(await verifyPassword(String(b.current_password||''), user.password_hash))) throw Object.assign(new Error('La contraseÃ±a actual no es correcta'), { status: 403 });
    validatePassword(b.new_password);
    db.prepare('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?').run(await hashPassword(b.new_password),user.id);
    audit(user.id,'user',user.id,'password_changed',null,{must_change_password:0});
    return json(res,200,{ok:true});
  }
  if (req.method === 'GET' && url.pathname === '/api/auth/me') {
    const user = currentUser(req);
    if (!user) throw Object.assign(new Error('Sesión requerida'), { status: 401 });
    return json(res,200,publicUser(user));
  }
  const routeModule = url.pathname.startsWith('/api/orders') ? 'orders'
    : url.pathname.startsWith('/api/agenda') ? 'orders'
    : url.pathname.startsWith('/api/assets') ? 'assets'
    : url.pathname.startsWith('/api/preventives') ? 'preventives'
    : url.pathname.startsWith('/api/inventory') ? 'inventory'
    : url.pathname.startsWith('/api/users') ? 'users' : 'dashboard';
  const authUser = url.pathname === '/api/catalogs' ? currentUser(req) : requirePermission(req,routeModule);
  if (!authUser) throw Object.assign(new Error('Sesión requerida'), { status: 401 });

  if (req.method === 'GET' && url.pathname === '/api/users') {
    requireAction(authUser, 'users.manage');
    return json(res,200,db.prepare(`SELECT id,employee_number,name,last_name,username,role,active,created_at
      FROM users ORDER BY role='Administrador' DESC,name,last_name`).all().map(user=>({...publicUser({...user,actions:userActions(user),areas:userAreas(user)}),active:user.active,created_at:user.created_at})));
  }
  if (req.method === 'POST' && url.pathname === '/api/users') {
    requireAction(authUser, 'users.manage');
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
    requireAction(authUser, 'users.manage');
    const id=Number(url.pathname.split('/').pop()); const b=await body(req);
    const target=db.prepare('SELECT * FROM users WHERE id=?').get(id);
    if(!target) throw Object.assign(new Error('Usuario no encontrado'),{status:404});
    if(target.username==='administrator' && b.active===false) throw Object.assign(new Error('No se puede desactivar al administrador principal'),{status:400});
    db.exec('BEGIN');
    try {
      if(Object.hasOwn(b,'active')) db.prepare('UPDATE users SET active=? WHERE id=?').run(b.active?1:0,id);
      if(b.role && target.role!=='Administrador') db.prepare('UPDATE users SET role=? WHERE id=?').run(b.role==='Mantenimiento'?'Técnico':'Solicitante',id);
      if(b.password){validatePassword(b.password);db.prepare('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?').run(await hashPassword(b.password),id);db.prepare('DELETE FROM sessions WHERE user_id=?').run(id);}
      if (Array.isArray(b.actions)) {
        const actions = [...new Set(b.actions.filter(action => ACTIONS.includes(action)))];
        db.prepare('DELETE FROM user_action_permissions WHERE user_id=?').run(id);
        const grant = db.prepare('INSERT INTO user_action_permissions (user_id,action,allowed) VALUES (?,?,1)');
        actions.forEach(action => grant.run(id,action));
      }
      if (Array.isArray(b.areas)) {
        const areas = [...new Set(b.areas.map(area => String(area).trim()).filter(Boolean))];
        db.prepare('DELETE FROM user_area_permissions WHERE user_id=?').run(id);
        const grant = db.prepare('INSERT INTO user_area_permissions (user_id,area,allowed) VALUES (?,?,1)');
        areas.forEach(area => grant.run(id,area));
      }
      db.exec('COMMIT');return json(res,200,{ok:true});
    }catch(error){db.exec('ROLLBACK');throw error;}
  }
  if (req.method === 'GET' && url.pathname === '/api/inventory/template.csv') {
    const csv = '\uFEFF' + [
      '"Código","Descripción","Categoría","Unidad","Existencia","StockMínimo","StockMáximo","CostoUnitario","Ubicación"',
      '"MAT-101","Tornillo Hexagonal 8mm","Tornillería","pieza","50","10","100","3.50","Anaquel A-01"',
      '"MAT-102","Aceite Hidráulico ISO 68","Lubricantes","litro","15","5","30","145.00","Anaquel B-02"'
    ].join('\r\n');
    res.writeHead(200, {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': 'attachment; filename="plantilla-inventario.csv"'
    });
    res.end(csv);
    return true;
  }
  if (req.method === 'GET' && url.pathname === '/api/inventory/export.csv') {
    const rows = db.prepare('SELECT code, name, category, unit, stock, min_stock, max_stock, unit_cost, location FROM inventory_items WHERE active = 1 ORDER BY name').all();
    const cell = value => {
      let text = String(value ?? '');
      if (/^[=+\-@]/.test(text)) text = `'${text}`;
      return `"${text.replaceAll('"', '""')}"`;
    };
    const headers = ['Código', 'Descripción', 'Categoría', 'Unidad', 'Existencia', 'StockMínimo', 'StockMáximo', 'CostoUnitario', 'Ubicación'];
    const csv = '\uFEFF' + [
      headers.map(cell).join(','),
      ...rows.map(r => [r.code, r.name, r.category, r.unit, r.stock, r.min_stock, r.max_stock, r.unit_cost, r.location].map(cell).join(','))
    ].join('\r\n');
    res.writeHead(200, {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': 'attachment; filename="base-de-datos-inventario.csv"'
    });
    res.end(csv);
    return true;
  }
  if (req.method === 'POST' && url.pathname === '/api/inventory/preview-import') {
    requireAction(authUser, 'inventory.move');
    const b = await body(req);
    let items = Array.isArray(b.items) ? b.items : [];
    if (typeof b.csvText === 'string' && b.csvText.trim()) {
      items = parseCSVText(b.csvText);
    }
    const existing = new Map(db.prepare('SELECT id, code, name, stock FROM inventory_items').all().map(x => [x.code.toUpperCase(), x]));
    let newCount = 0, updateCount = 0, errorCount = 0;
    const parsedRows = items.map((item, idx) => {
      const code = String(item.code || item['Código'] || item['codigo'] || item['CÓDIGO'] || '').trim().toUpperCase();
      const name = String(item.name || item['Descripción'] || item['descripcion'] || item['DESCRIPCIÓN'] || item['Nombre'] || '').trim();
      const category = String(item.category || item['Categoría'] || item['categoria'] || item['CATEGORÍA'] || 'Refacción').trim();
      const unit = String(item.unit || item['Unidad'] || item['unidad'] || item['UNIDAD'] || 'pieza').trim();
      const stock = Math.max(Number(item.stock ?? item['Existencia'] ?? item['existencia'] ?? item['EXISTENCIA'] ?? 0) || 0, 0);
      const min_stock = Math.max(Number(item.min_stock ?? item['StockMínimo'] ?? item['stock_minimo'] ?? item['Stock Mínimo'] ?? 0) || 0, 0);
      const max_stock = Math.max(Number(item.max_stock ?? item['StockMáximo'] ?? item['stock_maximo'] ?? item['Stock Máximo'] ?? 0) || 0, 0);
      const unit_cost = Math.max(Number(item.unit_cost ?? item['CostoUnitario'] ?? item['costo_unitario'] ?? item['Costo Unitario'] ?? 0) || 0, 0);
      const location = String(item.location || item['Ubicación'] || item['ubicacion'] || item['UBICACIÓN'] || '').trim() || null;

      let status = 'new';
      let error = null;

      if (!code) {
        status = 'error';
        error = 'Falta el código';
      } else if (!name) {
        status = 'error';
        error = 'Falta la descripción/nombre';
      } else if (existing.has(code)) {
        status = 'update';
        updateCount++;
      } else {
        status = 'new';
        newCount++;
      }

      if (status === 'error') errorCount++;

      // Include current stock so frontend can compute 'add' result
      const currentStock = status === 'update' ? (existing.get(code)?.stock ?? null) : null;

      return { rowNum: idx + 1, code, name, category, unit, stock, min_stock, max_stock, unit_cost, location, status, error, currentStock };
    });

    return json(res, 200, {
      total: parsedRows.length,
      newCount,
      updateCount,
      errorCount,
      validCount: newCount + updateCount,
      rows: parsedRows
    });
  }
  if (req.method === 'POST' && url.pathname === '/api/inventory/import') {
    requireAction(authUser, 'inventory.move');
    const b = await body(req);
    const rows = Array.isArray(b.rows) ? b.rows.filter(r => r.status !== 'error' && r.code && r.name) : [];
    if (!rows.length) throw Object.assign(new Error('No hay registros válidos para importar'), { status: 400 });
    const stockMode = b.stockMode === 'add' ? 'add' : 'replace'; // 'replace' is default

    const insertStmt = db.prepare(`INSERT INTO inventory_items (code, name, category, unit, stock, min_stock, max_stock, unit_cost, location)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`);
    const updateStmt = db.prepare(`UPDATE inventory_items SET name=?, category=?, unit=?, stock=?, min_stock=?, max_stock=?, unit_cost=?, location=?, active=1
      WHERE code=?`);
    const findStmt = db.prepare('SELECT id, code, stock FROM inventory_items WHERE code=?');
    const movementStmt = db.prepare(`INSERT INTO inventory_movements (inventory_item_id, type, quantity, unit_cost, user_id, notes)
      VALUES (?, ?, ?, ?, ?, ?)`);

    db.exec('BEGIN');
    try {
      let imported = 0;
      for (const r of rows) {
        const itemCode = String(r.code).trim().toUpperCase();
        const existing = findStmt.get(itemCode);
        const fileStock = Math.max(Number(r.stock) || 0, 0);
        const fileCategory = r.category || 'Refacción';
        const fileUnit = r.unit || 'pieza';
        const fileMinStock = Math.max(Number(r.min_stock) || 0, 0);
        const fileMaxStock = Math.max(Number(r.max_stock) || 0, 0);
        const fileUnitCost = Math.max(Number(r.unit_cost) || 0, 0);
        const fileLocation = r.location || null;

        if (existing) {
          const currentStock = Number(existing.stock) || 0;
          const newStock = stockMode === 'add' ? currentStock + fileStock : fileStock;
          updateStmt.run(r.name, fileCategory, fileUnit, newStock, fileMinStock, fileMaxStock, fileUnitCost, fileLocation, itemCode);
          // Record movement: Ajuste for replace, Entrada for add
          if (stockMode === 'add' && fileStock > 0) {
            movementStmt.run(existing.id, 'Entrada', fileStock, fileUnitCost, authUser.id, 'Carga masiva desde Excel/CSV (Sumar)');
          } else {
            movementStmt.run(existing.id, 'Ajuste', Math.max(newStock, 0.01), fileUnitCost, authUser.id, 'Carga masiva desde Excel/CSV (Reemplazar)');
          }
        } else {
          const resIns = insertStmt.run(itemCode, r.name, fileCategory, fileUnit, fileStock, fileMinStock, fileMaxStock, fileUnitCost, fileLocation);
          const newId = Number(resIns.lastInsertRowid);
          if (fileStock > 0) movementStmt.run(newId, 'Entrada', fileStock, fileUnitCost, authUser.id, 'Carga masiva desde Excel/CSV (Nuevo)');
        }
        imported++;
      }
      db.exec('COMMIT');
      return json(res, 200, { ok: true, importedCount: imported, stockMode });
    } catch (error) {
      db.exec('ROLLBACK');
      throw error;
    }
  }
  if (req.method === 'GET' && url.pathname === '/api/inventory') {
    requireAction(authUser, 'inventory.read');
    const rows = db.prepare(`SELECT i.*, COALESCE(SUM(CASE WHEN m.type IN ('Entrada','Devolución','Inventario inicial') THEN m.quantity WHEN m.type='Salida' THEN -m.quantity ELSE 0 END),0) movement_total
      FROM inventory_items i LEFT JOIN inventory_movements m ON m.inventory_item_id=i.id
      GROUP BY i.id ORDER BY i.name`).all();
    return json(res,200,rows.map(item=>({...item,low_stock:item.stock<=item.min_stock}))); 
  }
  if (req.method === 'GET' && /^\/api\/inventory\/\d+\/movements$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/')[3]);
    requireAction(authUser, 'inventory.read');
    return json(res,200,db.prepare(`SELECT m.*, (u.name||' '||COALESCE(u.last_name,'')) user_name,wo.folio
      FROM inventory_movements m LEFT JOIN users u ON u.id=m.user_id LEFT JOIN work_orders wo ON wo.id=m.work_order_id
      WHERE m.inventory_item_id=? ORDER BY m.created_at DESC,m.id DESC`).all(id));
  }
  if (req.method === 'POST' && url.pathname === '/api/inventory') {
    requireAction(authUser, 'inventory.move');
    const b=await body(req);
    for(const key of ['code','name','category','unit']) if(!String(b[key]||'').trim()) throw Object.assign(new Error(`Falta el campo ${key}`),{status:400});
    const result=db.prepare(`INSERT INTO inventory_items (code,name,category,unit,stock,min_stock,max_stock,unit_cost,location)
      VALUES (?,?,?,?,?,?,?,?,?)`).run(String(b.code).trim().toUpperCase(),String(b.name).trim(),b.category,b.unit,Math.max(Number(b.stock)||0,0),Math.max(Number(b.min_stock)||0,0),Math.max(Number(b.max_stock)||0,0),Math.max(Number(b.unit_cost)||0,0),b.location||null);
    return json(res,201,{id:Number(result.lastInsertRowid)});
  }
  if (req.method === 'PATCH' && /^\/api\/inventory\/\d+$/.test(url.pathname)) {
    requireAction(authUser, 'inventory.move');
    const id=Number(url.pathname.split('/').pop()); const b=await body(req);
    const allowed=['code','name','category','unit','min_stock','max_stock','unit_cost','location','active'];
    const keys=allowed.filter(key=>Object.hasOwn(b,key));
    if(!keys.length) throw Object.assign(new Error('No hay campos válidos'),{status:400});
    const current=db.prepare('SELECT * FROM inventory_items WHERE id=?').get(id);
    if(!current)throw Object.assign(new Error('Insumo no encontrado'),{status:404});
    const minimum=Number(b.min_stock??current.min_stock),maximum=Number(b.max_stock??current.max_stock);
    if(!Number.isFinite(minimum)||!Number.isFinite(maximum)||minimum<0||maximum<minimum)throw Object.assign(new Error('Máximo debe ser mayor o igual al mínimo; ambos deben ser válidos'),{status:400});
    const result=db.prepare(`UPDATE inventory_items SET ${keys.map(key=>`${key}=?`).join(',')},version=version+1 WHERE id=?`).run(...keys.map(key=>key==='active'?(b[key]?1:0):b[key]),id);
    if(!result.changes) throw Object.assign(new Error('Insumo no encontrado'),{status:404});
    return json(res,200,{ok:true});
  }
  if (req.method === 'POST' && /^\/api\/inventory\/\d+\/movement$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/')[3]);const b=await body(req);
    requireAction(authUser, b.type === 'Ajuste' ? 'inventory.adjust' : 'inventory.move');
    return json(res,201,stockCommand(db,authUser,id,{...b,request_key:b.request_key||req.headers['idempotency-key']}));
  }
  if (req.method === 'GET' && url.pathname === '/api/dashboard') return json(res, 200, dashboard());
  if (req.method === 'GET' && url.pathname === '/api/orders/export.csv') {
    if(authUser.role==='Solicitante') throw Object.assign(new Error('Tu rol no puede exportar órdenes'),{status:403});
    requireAction(authUser, 'orders.read');
    const filters=Object.fromEntries(['status','priority','area','technician_id','asset_id','from','to','q'].map(key=>[key,url.searchParams.get(key)||'']));
    const rows=listOrders(null,filters).filter(order=>hasArea(authUser,order.asset_area));
    const columns=[['Folio','folio'],['Fecha solicitud','requested_at'],['Solicitante','requester_name'],['Prioridad','priority'],['Clasificación','classification'],['Especialidad','specialty'],['Activo','asset_name'],['Falla reportada','reported_failure'],['Acciones','actions'],['Técnico','technician_name'],['Inicio','started_at'],['Fin','finished_at'],['Horas hombre','labor_hours'],['Material utilizado','material_summary'],['Costo materiales','material_cost'],['Estado','status']];
    const cell=value=>{let text=String(value??'');if(/^[=+\-@]/.test(text))text=`'${text}`;return `"${text.replaceAll('"','""')}"`};
    const csv='\uFEFF'+[columns.map(x=>cell(x[0])).join(','),...rows.map(row=>columns.map(x=>cell(row[x[1]])).join(','))].join('\r\n');
    res.writeHead(200,{'Content-Type':'text/csv; charset=utf-8','Content-Disposition':'attachment; filename="ordenes-mantenimiento.csv"'});res.end(csv);return true;
  }
  if (req.method === 'GET' && url.pathname === '/api/orders') {
    requireAction(authUser, 'orders.read');
    const filters=Object.fromEntries(['status','priority','area','technician_id','asset_id','from','to','q'].map(key=>[key,url.searchParams.get(key)||'']));
    const rows=listOrders(authUser.role==='Solicitante'?authUser.id:null,filters).filter(order=>hasArea(authUser,order.asset_area));
    return json(res,200,authUser.role==='Solicitante'?rows.map(operatorOrder):rows);
  }
  if (req.method === 'GET' && /^\/api\/orders\/\d+$/.test(url.pathname)) {
    const order=orderDetails(Number(url.pathname.split('/').pop()));
    if(!order) throw Object.assign(new Error('Orden no encontrada'),{status:404});
    requireAction(authUser, 'orders.read', order.asset_area);
    if(authUser.role==='Solicitante'&&order.requester_id!==authUser.id) throw Object.assign(new Error('No puedes consultar reportes de otro operador'),{status:403});
    return json(res,200,authUser.role==='Solicitante'?operatorOrder(order):order);
  }
  if (req.method === 'GET' && /^\/api\/orders\/\d+\/time-entries$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/')[3]);
    const owner=db.prepare('SELECT requester_id FROM work_orders WHERE id=?').get(id);
    if(!owner) throw Object.assign(new Error('Orden no encontrada'),{status:404});
    if(authUser.role==='Solicitante'&&owner.requester_id!==authUser.id) throw Object.assign(new Error('No puedes consultar reportes de otro operador'),{status:403});
    return json(res,200,db.prepare(`SELECT t.*, (u.name||' '||COALESCE(u.last_name,'')) user_name
      FROM work_order_time_entries t JOIN users u ON u.id=t.user_id WHERE t.work_order_id=? ORDER BY t.started_at`).all(id));
  }
  if (req.method === 'POST' && /^\/api\/orders\/\d+\/time-entries$/.test(url.pathname)) {
    if(authUser.role==='Solicitante') throw Object.assign(new Error('Tu rol no puede registrar tiempos'),{status:403});
    const id=Number(url.pathname.split('/')[3]); const b=await body(req);
    const userId=Number(b.user_id)||authUser.id; const startedAt=String(b.started_at||''); const finishedAt=b.finished_at?String(b.finished_at):null;
    const work=db.prepare('SELECT * FROM work_orders WHERE id=?').get(id);
    if(!work)throw Object.assign(new Error('Orden no encontrada'),{status:404});
    requireAction(authUser, 'orders.time', work.asset_id ? db.prepare('SELECT area FROM assets WHERE id=?').get(work.asset_id)?.area : null);
    if(['Completada','Cancelada','Pendiente de validación'].includes(work.status))throw Object.assign(new Error('Reabre la orden antes de registrar tiempo'),{status:409});
    if(!['Administrador','Jefatura'].includes(authUser.role)&&(work.technician_id!==authUser.id||userId!==authUser.id))throw Object.assign(new Error('Solo puedes registrar tu tiempo en las órdenes asignadas a ti'),{status:403});
    if(!Number.isFinite(Date.parse(startedAt)))throw Object.assign(new Error('La fecha de inicio no es válida'),{status:400});
    if(!startedAt) throw Object.assign(new Error('La hora inicial es obligatoria'),{status:400});
    if(finishedAt) hoursBetween(startedAt,finishedAt);
    const overlap=db.prepare(`SELECT 1 FROM work_order_time_entries WHERE user_id=? AND finished_at IS NULL OR (user_id=? AND started_at<? AND COALESCE(finished_at,'9999-12-31')>?) LIMIT 1`).get(userId,userId,finishedAt||'9999-12-31',startedAt);
    if(overlap) throw Object.assign(new Error('La persona ya tiene un intervalo de trabajo traslapado'),{status:409});
    db.exec('BEGIN');
    try {
      db.prepare(`INSERT INTO work_order_time_entries (work_order_id,user_id,started_at,finished_at,pause_reason,source) VALUES (?,?,?,?,?,?)`).run(id,userId,startedAt,finishedAt,b.pause_reason||null,b.source==='timer'?'timer':'manual');
      const total=orderLaborHours(id);db.prepare('UPDATE work_orders SET labor_hours=?,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?').run(total,id);
      db.prepare('INSERT INTO work_order_events (work_order_id,user_id,event,details) VALUES (?,?,?,?)').run(id,authUser.id,'Tiempo registrado',`${total} horas hombre acumuladas`);
      audit(authUser.id,'work_order',id,'time_entry_created',null,{user_id:userId,started_at:startedAt,finished_at:finishedAt});
      db.exec('COMMIT');return json(res,201,{ok:true,labor_hours:total});
    } catch(error){db.exec('ROLLBACK');throw error;}
  }
  if (req.method === 'POST' && /^\/api\/orders\/\d+\/(transitions|validate)$/.test(url.pathname)) {
    if(authUser.role==='Solicitante')throw Object.assign(new Error('Sin permiso para atender la orden'),{status:403});
    const b=await body(req);const id=Number(url.pathname.split('/')[3]);
    const work=db.prepare('SELECT asset_id FROM work_orders WHERE id=?').get(id);
    const area=work?.asset_id ? db.prepare('SELECT area FROM assets WHERE id=?').get(work.asset_id)?.area : null;
    requireAction(authUser, url.pathname.endsWith('/validate') ? 'orders.validate' : 'orders.transition', area);
    return json(res,200,require('./lib/order-commands')(db,authUser,id,b,url.pathname.endsWith('/validate')));
  }
  if (req.method === 'GET' && url.pathname === '/api/downtime-events') {
    if(!['Administrador','Jefatura','Técnico'].includes(authUser.role)) throw Object.assign(new Error('Solo Mantenimiento puede consultar paros'),{status:403});
    return json(res,200,db.prepare(`SELECT d.*,a.code asset_code,a.name asset_name,
      (SELECT COUNT(*) FROM downtime_work_orders dw WHERE dw.downtime_id=d.id) order_count
      FROM downtime_events d JOIN assets a ON a.id=d.asset_id ORDER BY d.started_at DESC`).all());
  }
  if (req.method === 'GET' && url.pathname === '/api/agenda') {
    requireAction(authUser, 'orders.read');
    const rows=db.prepare(`SELECT wo.id,wo.folio,wo.status,wo.priority,wo.scheduled_at,wo.requested_at,wo.asset_id,wo.location,wo.technician_id,a.name asset_name,a.area asset_area,(u.name||' '||COALESCE(u.last_name,'')) technician_name
      FROM work_orders wo LEFT JOIN assets a ON a.id=wo.asset_id LEFT JOIN users u ON u.id=wo.technician_id
      WHERE wo.status NOT IN ('Completada','Cancelada') ORDER BY COALESCE(wo.scheduled_at,wo.requested_at),technician_name`).all().filter(row=>hasArea(authUser,row.asset_area));
      return json(res,200,{orders:rows,technicians:db.prepare("SELECT id,name,last_name FROM users WHERE role='Técnico' AND active=1 ORDER BY name").all()});
  }
  if (req.method === 'POST' && url.pathname === '/api/downtime-events') {
    if(authUser.role==='Solicitante') throw Object.assign(new Error('Tu rol no puede registrar paros'),{status:403});
    const b=await body(req); for(const key of ['asset_id','cause','started_at']) if(!b[key]) throw Object.assign(new Error(`Falta el campo ${key}`),{status:400});
    const asset=db.prepare('SELECT id FROM assets WHERE id=?').get(Number(b.asset_id));if(!asset)throw Object.assign(new Error('Activo no encontrado'),{status:404});
    const key=String(b.request_key||req.headers['idempotency-key']||'').trim();if(!key)throw Object.assign(new Error('El paro requiere un identificador de petición'),{status:400});
    const duplicate=db.prepare("SELECT id FROM downtime_events WHERE source=? AND created_by=?").get(`request:${key}`,authUser.id);if(duplicate)return json(res,200,{id:duplicate.id,replayed:true});
    if(!Number.isFinite(Date.parse(String(b.started_at))))throw Object.assign(new Error('La fecha de inicio no es válida'),{status:400});
    if(b.finished_at) hoursBetween(b.started_at,b.finished_at);
    db.exec('BEGIN');
    try { const ids=Array.isArray(b.work_order_ids)?b.work_order_ids.map(Number):[];for(const orderId of ids){const order=db.prepare('SELECT asset_id FROM work_orders WHERE id=?').get(orderId);if(!order||Number(order.asset_id)!==Number(b.asset_id))throw Object.assign(new Error('Todas las OT vinculadas deben pertenecer al mismo activo'),{status:400});} const result=db.prepare('INSERT INTO downtime_events (asset_id,cause,started_at,finished_at,source,created_by) VALUES (?,?,?,?,?,?)').run(b.asset_id,String(b.cause).trim(),b.started_at,b.finished_at||null,`request:${key}`,authUser.id); const id=Number(result.lastInsertRowid); for(const orderId of ids) db.prepare('INSERT OR IGNORE INTO downtime_work_orders (downtime_id,work_order_id) VALUES (?,?)').run(id,orderId); if(!b.finished_at)db.prepare("UPDATE assets SET status='Detenido' WHERE id=?").run(b.asset_id); audit(authUser.id,'downtime_event',id,'created',null,{...b,request_key:key}); db.exec('COMMIT'); return json(res,201,{id}); }
    catch(error){db.exec('ROLLBACK');throw error;}
  }
  if (req.method === 'PATCH' && /^\/api\/downtime-events\/\d+$/.test(url.pathname)) {
    if(authUser.role==='Solicitante') throw Object.assign(new Error('Tu rol no puede cerrar paros'),{status:403});
    const id=Number(url.pathname.split('/').pop()); const b=await body(req); const before=db.prepare('SELECT * FROM downtime_events WHERE id=?').get(id); if(!before) throw Object.assign(new Error('Paro no encontrado'),{status:404});
    if(!before.finished_at&&!b.finished_at)throw Object.assign(new Error('Indica la fecha de cierre del paro'),{status:400});
    if(b.finished_at) hoursBetween(before.started_at,b.finished_at);if(!String(b.reason||'').trim())throw Object.assign(new Error('Cerrar o corregir un paro requiere motivo'),{status:400});
    db.exec('BEGIN');try{db.prepare('UPDATE downtime_events SET finished_at=? WHERE id=?').run(b.finished_at||null,id);if(b.finished_at&&!db.prepare('SELECT 1 FROM downtime_events WHERE asset_id=? AND finished_at IS NULL AND id<>?').get(before.asset_id,id)&&!db.prepare("SELECT 1 FROM work_orders WHERE asset_id=? AND status IN ('Abierta','Programada','En proceso','Pausada','Espera de material','Pendiente de validación')").get(before.asset_id))db.prepare("UPDATE assets SET status='Disponible' WHERE id=?").run(before.asset_id);audit(authUser.id,'downtime_event',id,'updated',before,{...before,finished_at:b.finished_at||null},b.reason);db.exec('COMMIT');return json(res,200,{ok:true});}catch(error){db.exec('ROLLBACK');throw error;}
  }
  if (req.method === 'GET' && url.pathname === '/api/audit') {
    requireAction(authUser, 'audit.read');
    if(!['Administrador','Jefatura'].includes(authUser.role)) throw Object.assign(new Error('No tienes permiso para consultar auditoría'),{status:403});
    return json(res,200,db.prepare(`SELECT a.*, (u.name||' '||COALESCE(u.last_name,'')) user_name FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.created_at DESC,a.id DESC LIMIT 500`).all());
  }
  if (req.method === 'GET' && url.pathname === '/api/assets') { requireAction(authUser, 'assets.read'); return json(res, 200, db.prepare('SELECT * FROM assets ORDER BY name').all().filter(asset=>hasArea(authUser,asset.area))); }
  if (req.method === 'GET' && /^\/api\/assets\/\d+$/.test(url.pathname)) {
    const asset=assetDetails(Number(url.pathname.split('/').pop()));
    if(!asset) throw Object.assign(new Error('Activo no encontrado'),{status:404});
    requireAction(authUser, 'assets.read', asset.area);
    return json(res,200,asset);
  }
  if (['GET','POST'].includes(req.method) && /^\/api\/assets\/\d+\/meter-readings$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/')[3]),asset=db.prepare('SELECT id,area,operating_hours FROM assets WHERE id=?').get(id);
    if(!asset)throw Object.assign(new Error('Activo no encontrado'),{status:404});
    const input=req.method==='POST'?await body(req):null;requireAction(authUser,input?'assets.edit':'assets.read',asset.area);
    if(!input)return json(res,200,{asset_id:id,current_reading:Number(asset.operating_hours||0),readings:db.prepare(`SELECT r.*,u.name recorded_by_name FROM asset_meter_readings r JOIN users u ON u.id=r.recorded_by WHERE r.asset_id=? ORDER BY r.recorded_at DESC,r.id DESC`).all(id)});
    const result=assetMeter.record(db,id,input,authUser.id);audit(authUser.id,'asset_meter_reading',result.id,'created',null,result);return json(res,201,result);
  }
  if(['GET','POST'].includes(req.method)&&url.pathname==='/api/preventive-templates'){
    const input=req.method==='POST'?await body(req):null;requireAction(authUser,input?'preventives.edit':'preventives.read');if(!input)return json(res,200,db.prepare('SELECT * FROM preventive_templates WHERE active=1 ORDER BY family,code').all().map(preventiveTemplates.parse));return json(res,201,preventiveTemplates.create(db,input,authUser.id));
  }
  if (req.method === 'GET' && url.pathname === '/api/preventives') { requireAction(authUser, 'preventives.read'); return json(res, 200, db.prepare(`SELECT p.*,a.code asset_code,a.name asset_name,a.area asset_area,u.name responsible_name FROM preventive_plans p JOIN assets a ON a.id=p.asset_id LEFT JOIN users u ON u.id=p.responsible_id ORDER BY p.next_date`).all().filter(plan=>hasArea(authUser,plan.asset_area))); }
  if (req.method === 'GET' && url.pathname === '/api/catalogs') return json(res, 200, {
    users: authUser.role === 'Solicitante'
      ? [{id:authUser.id,employee_number:authUser.employee_number,name:`${authUser.name} ${authUser.last_name||''}`.trim(),role:authUser.role}]
      : db.prepare('SELECT id,employee_number,name,role FROM users WHERE active=1 ORDER BY name').all(),
    assets: db.prepare('SELECT id,code,name,category,area,status FROM assets ORDER BY name').all(),
    priorities: ['Paro de máquina','Alta','Media','Baja'],
    classifications: ['Mantenimiento Preventivo','Mantenimiento Correctivo','Mantenimiento Autónomo','Apoyo para ajuste de máquina','Daño de Herramental','Daño de Fixture','Proyecto Kaizen'],
    specialties: ['Eléctrico','Mecánica','Soldadura','Hidráulica / Neumática','Modificación de pieza','Reparación de activo']
    ,inventory: authUser.role==='Solicitante'?[]:db.prepare('SELECT id,code,name,unit,stock,unit_cost FROM inventory_items WHERE active=1 ORDER BY name').all()
  });
  if (req.method === 'POST' && url.pathname === '/api/orders') {
    const b = await body(req);
    requireAction(authUser, 'orders.create');
    const idempotencyKey=String(b.idempotency_key||req.headers['idempotency-key']||'').trim()||null;
    if(idempotencyKey){const existing=db.prepare('SELECT id,folio FROM work_orders WHERE idempotency_key=?').get(idempotencyKey);if(existing)return json(res,200,{id:existing.id,folio:existing.folio,replayed:true});}
    if (authUser.role === 'Solicitante') {
      b.requester_id = authUser.id;
      b.specialty = null; b.actions = null; b.technician_id = null;
      b.started_at = null; b.finished_at = null; b.labor_hours = 0;
      b.material_summary = null; b.material_cost = 0; b.status = 'Abierta';
    }
    if (!b.asset_id && !String(b.location||'').trim()) throw Object.assign(new Error('Indica un activo o una ubicación de atención'), { status: 400 });
    for (const key of ['requester_id','priority','classification','reported_failure']) if (!b[key]) throw Object.assign(new Error(`Falta el campo ${key}`), { status: 400 });
    const folio = nextFolio();
    const result = db.prepare(`INSERT INTO work_orders (folio,requested_at,requester_id,priority,classification,specialty,asset_id,location,reported_failure,actions,technician_id,started_at,finished_at,labor_hours,material_summary,material_cost,status,idempotency_key)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(folio,b.requested_at||new Date().toISOString(),b.requester_id,b.priority,b.classification,b.specialty||null,b.asset_id||null,String(b.location||'').trim()||null,b.reported_failure,b.actions||null,b.technician_id||null,b.started_at||null,b.finished_at||null,Number(b.labor_hours)||0,b.material_summary||null,Number(b.material_cost)||0,b.status||'Abierta',idempotencyKey);
    if(b.classification==='Mantenimiento Autónomo'&&String(b.autonomous_checklist||'').trim())db.prepare('UPDATE work_orders SET autonomous_checklist=? WHERE id=?').run(String(b.autonomous_checklist).trim().slice(0,2000),result.lastInsertRowid);
    db.prepare('INSERT INTO work_order_events (work_order_id,user_id,event,details) VALUES (?,?,?,?)').run(result.lastInsertRowid,authUser.id,'Reporte creado',`Prioridad: ${b.priority}`);
    audit(authUser.id,'work_order',Number(result.lastInsertRowid),'created',null,{folio,status:b.status||'Abierta'});
    return json(res, 201, { id: Number(result.lastInsertRowid), folio });
  }
  if (req.method === 'PATCH' && /^\/api\/orders\/\d+$/.test(url.pathname)) {
    const id = Number(url.pathname.split('/').pop()); const b = await body(req);
    const allowed = ['priority','classification','specialty','asset_id','location','reported_failure','actions','technician_id','labor_cost','material_summary','requested_at','scheduled_at','closure_notes','closure_document_code','closure_document_revision'];
    const keys = allowed.filter(k => Object.hasOwn(b,k));
    if(Array.isArray(b.materials))throw Object.assign(new Error('Los materiales se registran con Confirmar salida o Registrar devolución'),{status:400});
    if (!keys.length) throw Object.assign(new Error('No hay campos válidos'), { status: 400 });
    const before=db.prepare('SELECT * FROM work_orders WHERE id=?').get(id);
    if(!before) throw Object.assign(new Error('Orden no encontrada'),{status:404});
    const area=before.asset_id ? db.prepare('SELECT area FROM assets WHERE id=?').get(before.asset_id)?.area : null;
    requireAction(authUser, 'orders.edit', area);
    if (Object.hasOwn(b,'technician_id')) requireAction(authUser, 'orders.assign', area);
    const dateChanged = ['requested_at','scheduled_at'].some(key=>Object.hasOwn(b,key)&&String(b[key]||'')!==String(before[key]||''));
    if (dateChanged) {
      requireAction(authUser, 'orders.edit_dates', area);
      if (!String(b.date_change_reason||'').trim()) throw Object.assign(new Error('Cambiar una fecha requiere un motivo'),{status:400});
    }
    if (!before.asset_id && Object.hasOwn(b,'location') && !String(b.location||'').trim()) throw Object.assign(new Error('Una OT sin activo debe conservar su ubicación'),{status:400});
    if(!['Administrador','Jefatura'].includes(authUser.role)&&before.technician_id!==authUser.id)throw Object.assign(new Error('Solo puedes editar las órdenes asignadas a ti'),{status:403});
    if(['Completada','Cancelada','Pendiente de validación'].includes(before.status))throw Object.assign(new Error('Reabre la orden antes de editar una intervención cerrada o en validación'),{status:409});
    if(Object.hasOwn(b,'technician_id')&&!['Administrador','Jefatura'].includes(authUser.role)&&Number(b.technician_id)!==before.technician_id)throw Object.assign(new Error('La asignación requiere permiso de Jefatura'),{status:403});
    if(!Object.hasOwn(b,'version')||Number(b.version)!==before.version) throw Object.assign(new Error('La orden cambió en otra sesión. Recarga para revisar los cambios.'),{status:409});
    if(b.status&&b.status!==before.status) throw Object.assign(new Error('Usa Terminar trabajo para cerrar la orden y pasarla a validación'),{status:400});
    if(['started_at','finished_at','labor_hours','material_cost'].some(key=>Object.hasOwn(b,key)))throw Object.assign(new Error('Los tiempos y materiales se registran mediante sus acciones específicas'),{status:400});
    db.exec('BEGIN IMMEDIATE');
    try {
    const result = db.prepare(`UPDATE work_orders SET ${keys.map(k=>`${k}=?`).join(',')},version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?`).run(...keys.map(k=>b[k] === '' ? null : b[k]),id);
    if (!result.changes) throw Object.assign(new Error('Orden no encontrada'), { status: 404 });
    const changes=keys.filter(key=>String(before[key]??'')!==String(b[key]??'')).map(key=>key==='status'?`Estado: ${before.status} → ${b.status}`:key==='technician_id'?'Técnico asignado actualizado':key==='actions'?'Acciones de trabajo actualizadas':key).join(' · ');
    db.prepare('INSERT INTO work_order_events (work_order_id,user_id,event,details) VALUES (?,?,?,?)').run(id,authUser.id,'Orden actualizada',changes||null);
    audit(authUser.id,'work_order',id,'updated',before,{...before,...b,version:before.version+1},b.date_change_reason||null);
    db.exec('COMMIT');
    return json(res, 200, { ok: true });
    } catch(error){db.exec('ROLLBACK');throw error;}
  }
  if (req.method === 'POST' && url.pathname === '/api/assets') {
    const b=await body(req); requireAction(authUser, 'assets.edit', b.area); for(const key of ['code','name','category','area']) if(!b[key]) throw Object.assign(new Error(`Falta el campo ${key}`),{status:400});
    const operationalStatus=b.operational_status||'Sin información';
    const legacyStatus=operationalStatus==='Operativa'?'Disponible':operationalStatus==='Parada'?'Detenido':operationalStatus==='En mantenimiento'?'En mantenimiento':'Fuera de servicio';
    const result=db.prepare('INSERT INTO assets (code,name,category,area,brand,model,status,critical,voltage,serial_code,observations,operating_hours,original_code,alias_codes,asset_type,operational_status,operational_status_cause,operational_status_updated_at,administrative_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)').run(b.code.trim().toUpperCase(),b.name,b.category,b.area,b.brand||null,b.model||null,legacyStatus,b.critical?1:0,b.voltage||null,b.serial_code||null,b.observations||null,Number(b.operating_hours)||0,b.original_code||null,b.alias_codes||null,b.asset_type||b.category,operationalStatus,b.operational_status_cause||null,new Date().toISOString(),b.administrative_status||'Activo');
    return json(res,201,{id:Number(result.lastInsertRowid)});
  }
  if (req.method === 'PATCH' && /^\/api\/assets\/\d+$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/').pop());const b=await body(req);
    const allowed=['code','name','category','area','brand','model','status','critical','voltage','serial_code','observations','operating_hours','original_code','alias_codes','asset_type','operational_status','operational_status_cause','administrative_status'];
    const current=db.prepare('SELECT area FROM assets WHERE id=?').get(id); requireAction(authUser, 'assets.edit', b.area||current?.area);
    const keys=allowed.filter(key=>Object.hasOwn(b,key));if(!keys.length)throw Object.assign(new Error('No hay campos válidos'),{status:400});
    if(Object.hasOwn(b,'operating_hours'))throw Object.assign(new Error('El horómetro se registra mediante meter-readings'),{status:400});
    const values=keys.map(key=>key==='critical'?(b[key]?1:0):b[key]===''?null:b[key]);
    if(Object.hasOwn(b,'operational_status')) { const index=keys.indexOf('operational_status'); if(index>=0) values[index]=b.operational_status; }
    const result=db.prepare(`UPDATE assets SET ${keys.map(key=>`${key}=?`).join(',')}${Object.hasOwn(b,'operational_status')?',operational_status_updated_at=CURRENT_TIMESTAMP':''} WHERE id=?`).run(...values,id);
    if(!result.changes)throw Object.assign(new Error('Activo no encontrado'),{status:404});return json(res,200,{ok:true});
  }
  if (req.method === 'POST' && url.pathname === '/api/preventives') {
    const b=await body(req); const assetArea=db.prepare('SELECT area FROM assets WHERE id=?').get(Number(b.asset_id))?.area; requireAction(authUser, 'preventives.edit', assetArea); for(const key of ['asset_id','title','frequency','next_date']) if(!b[key]) throw Object.assign(new Error(`Falta el campo ${key}`),{status:400});
    db.exec('BEGIN IMMEDIATE');
    try {
      const result=db.prepare('INSERT INTO preventive_plans (asset_id,title,frequency,next_date,responsible_id,status,template_code,instructions,applies_when) VALUES (?,?,?,?,?,?,?,?,?)').run(b.asset_id,b.title,b.frequency,b.next_date,b.responsible_id||null,b.status||'Programado',b.template_code||null,b.instructions||null,b.applies_when||null);
      const id=Number(result.lastInsertRowid);
      preventiveHistory.record(db,id,authUser.id,'created');
      audit(authUser.id,'preventive_plan',id,'created',null,{...b,version:1});
      db.exec('COMMIT'); return json(res,201,{id});
    } catch(error) {db.exec('ROLLBACK');throw error;}
  }
  if (['GET','POST'].includes(req.method) && /^\/api\/preventives\/\d+\/tasks$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/')[3]);
    const input=req.method==='POST'?await body(req):null;
    const plan=db.prepare('SELECT p.*,a.area FROM preventive_plans p JOIN assets a ON a.id=p.asset_id WHERE p.id=?').get(id);
    if(!plan)throw Object.assign(new Error('Preventivo no encontrado'),{status:404});
    requireAction(authUser,input?'preventives.edit':'preventives.read',plan.area);
    if(!input)return json(res,200,db.prepare('SELECT * FROM preventive_tasks WHERE plan_id=? ORDER BY id').all(id));
    preventiveTasks.validate(input);
    if(input.version!==plan.version)throw Object.assign(new Error('Recarga la versión del preventivo'),{status:409});
    if(plan.work_order_id)throw Object.assign(new Error('El plan con OT generada conserva su contenido histórico'),{status:409});
    db.exec('BEGIN IMMEDIATE');
    try {
      const result=db.prepare('INSERT INTO preventive_tasks (plan_id,title,interval_unit,interval_value,anchor_date,created_by) VALUES (?,?,?,?,?,?)').run(id,input.title.trim(),input.interval_unit,input.interval_value,input.anchor_date,authUser.id);
      db.prepare('UPDATE preventive_plans SET version=version+1 WHERE id=?').run(id);
      preventiveHistory.record(db,id,authUser.id,'task-created');
      audit(authUser.id,'preventive_task',Number(result.lastInsertRowid),'created',null,{...input,plan_id:id});
      db.exec('COMMIT');return json(res,201,{id:Number(result.lastInsertRowid),version:plan.version+1});
    }catch(error){db.exec('ROLLBACK');throw error;}
  }
  if(['GET','POST'].includes(req.method) && /^\/api\/preventives\/\d+\/tasks\/\d+\/checklist$/.test(url.pathname)){
    const parts=url.pathname.split('/'),planId=Number(parts[3]),taskId=Number(parts[5]),input=req.method==='POST'?await body(req):null;
    const plan=db.prepare('SELECT p.version,a.area FROM preventive_plans p JOIN assets a ON a.id=p.asset_id WHERE p.id=?').get(planId);if(!plan)throw Object.assign(new Error('Preventivo no encontrado'),{status:404});
    const task=db.prepare('SELECT id FROM preventive_tasks WHERE id=? AND plan_id=?').get(taskId,planId);if(!task)throw Object.assign(new Error('Tarea no encontrada'),{status:404});
    requireAction(authUser,input?'preventives.edit':'preventives.read',plan.area);
    if(!input)return json(res,200,db.prepare('SELECT * FROM preventive_checklist_items WHERE task_id=? ORDER BY position').all(taskId));
    return json(res,201,preventiveChecklists.addItem(db,taskId,input,authUser.id));
  }
  if(['GET','POST'].includes(req.method) && /^\/api\/preventives\/\d+\/occurrences\/\d+\/checklist$/.test(url.pathname)){
    const parts=url.pathname.split('/'),planId=Number(parts[3]),occurrenceId=Number(parts[5]),input=req.method==='POST'?await body(req):null;
    const occurrence=db.prepare(`SELECT o.id,p.id plan_id,a.area FROM preventive_occurrences o JOIN preventive_plans p ON p.id=o.plan_id JOIN assets a ON a.id=p.asset_id WHERE o.id=? AND o.plan_id=?`).get(occurrenceId,planId);if(!occurrence)throw Object.assign(new Error('Ocurrencia no encontrada'),{status:404});
    requireAction(authUser,input?'preventives.edit':'preventives.read',occurrence.area);
    if(!input)return json(res,200,{occurrence_id:occurrenceId,items:db.prepare(`SELECT i.*,an.answer,an.notes,an.recorded_by,an.recorded_at FROM preventive_checklist_items i LEFT JOIN preventive_checklist_answers an ON an.item_id=i.id AND an.occurrence_id=? WHERE i.task_id=(SELECT task_id FROM preventive_occurrences WHERE id=?) ORDER BY i.position`).all(occurrenceId,occurrenceId)});
    const result=preventiveChecklists.saveAnswers(db,occurrenceId,input.answers,authUser.id);audit(authUser.id,'preventive_checklist',occurrenceId,'answered',null,{answers:input.answers});return json(res,200,result);
  }
  if(req.method==='POST' && /^\/api\/preventives\/\d+\/apply-template$/.test(url.pathname)){
    const id=Number(url.pathname.split('/')[3]),input=await body(req),plan=db.prepare('SELECT p.*,a.area,a.asset_type,a.category FROM preventive_plans p JOIN assets a ON a.id=p.asset_id WHERE p.id=?').get(id);if(!plan)throw Object.assign(new Error('Preventivo no encontrado'),{status:404});requireAction(authUser,'preventives.edit',plan.area);const template=db.prepare('SELECT * FROM preventive_templates WHERE id=? AND active=1').get(Number(input.template_id));if(!template)throw Object.assign(new Error('Plantilla no encontrada'),{status:404});if(![plan.asset_type,plan.category].includes(template.family))throw Object.assign(new Error('La plantilla no corresponde a la familia del activo'),{status:409});if(plan.work_order_id||db.prepare('SELECT 1 FROM preventive_tasks WHERE plan_id=?').get(id))throw Object.assign(new Error('Solo puedes aplicar la plantilla a un preventivo sin tareas ni OT'),{status:409});if(Number(input.version)!==plan.version)throw Object.assign(new Error('El preventivo cambió en otra sesión'),{status:409});const value=preventiveTemplates.parse(template);db.exec('BEGIN IMMEDIATE');try{db.prepare("UPDATE preventive_plans SET title=?,instructions=?,template_code=?,version=version+1 WHERE id=? AND version=?").run(value.title,value.instructions,value.code,id,plan.version);const insert=db.prepare('INSERT INTO preventive_tasks (plan_id,title,interval_unit,interval_value,anchor_date,created_by) VALUES (?,?,?,?,?,?)');for(const task of value.tasks)insert.run(id,task.title,task.interval_unit,task.interval_value,task.anchor_date,authUser.id);preventiveHistory.record(db,id,authUser.id,'template-applied');audit(authUser.id,'preventive_plan',id,'template-applied',plan,{...plan,template_code:value.code,version:plan.version+1});db.exec('COMMIT');return json(res,200,{ok:true,version:plan.version+1,template_id:value.id,tasks:value.tasks.length});}catch(error){db.exec('ROLLBACK');throw error;}
  }
  if(req.method==='GET' && /^\/api\/preventives\/\d+\/calendar$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/')[3]);
    const plan=db.prepare('SELECT p.id,a.area FROM preventive_plans p JOIN assets a ON a.id=p.asset_id WHERE p.id=?').get(id);
    if(!plan)throw Object.assign(new Error('Preventivo no encontrado'),{status:404});
    requireAction(authUser,'preventives.read',plan.area);
    const from=url.searchParams.get('from'),to=url.searchParams.get('to');
    // Validate the requested horizon even when the plan has no configured tasks.
    preventiveTasks.project({title:'horizonte',interval_unit:'days',interval_value:1,anchor_date:from},from,to);
    const tasks=db.prepare('SELECT * FROM preventive_tasks WHERE plan_id=? ORDER BY id').all(id);
    const occurrences=tasks.flatMap(task=>preventiveTasks.project(task,from,to)).sort((a,b)=>a.base_date.localeCompare(b.base_date)||a.task_id-b.task_id);
    return json(res,200,{configuration_pending:tasks.length===0,projection_only:true,occurrences});
  }
  if(['GET','POST'].includes(req.method)&&/^\/api\/preventives\/\d+\/occurrences$/.test(url.pathname)){
    const id=Number(url.pathname.split('/')[3]);
    const input=req.method==='POST'?await body(req):null;
    const plan=db.prepare('SELECT p.id,a.area FROM preventive_plans p JOIN assets a ON a.id=p.asset_id WHERE p.id=?').get(id);
    if(!plan)throw Object.assign(new Error('Preventivo no encontrado'),{status:404});
    requireAction(authUser,input?'preventives.edit':'preventives.read',plan.area);
    if(!input)return json(res,200,db.prepare(`SELECT o.*,w.folio,w.status order_status FROM preventive_occurrences o JOIN work_orders w ON w.id=o.work_order_id WHERE o.plan_id=? ORDER BY o.base_date,o.id`).all(id).map(o=>({...o,execution:preventiveExecution.read(db,o.work_order_id)})));
    requireAction(authUser,'orders.create',plan.area);
    const result=preventiveOccurrences.generate(db,id,input,authUser.id,()=>nextFolio(false),audit);
    return json(res,result.replayed?200:201,result);
  }
  if(req.method==='POST' && /^\/api\/preventives\/\d+\/occurrences\/group$/.test(url.pathname)){
    const id=Number(url.pathname.split('/')[3]),input=await body(req);
    const plan=db.prepare('SELECT p.id,a.area FROM preventive_plans p JOIN assets a ON a.id=p.asset_id WHERE p.id=?').get(id);
    if(!plan)throw Object.assign(new Error('Preventivo no encontrado'),{status:404});
    requireAction(authUser,'preventives.edit',plan.area);requireAction(authUser,'orders.create',plan.area);
    const result=preventiveOccurrences.generateGroup(db,id,input,authUser.id,()=>nextFolio(false),audit);
    return json(res,result.replayed?200:201,result);
  }
  if(req.method==='GET' && /^\/api\/preventives\/\d+\/compliance$/.test(url.pathname)){
    const id=Number(url.pathname.split('/')[3]);
    const plan=db.prepare('SELECT p.id,a.area FROM preventive_plans p JOIN assets a ON a.id=p.asset_id WHERE p.id=?').get(id);
    if(!plan)throw Object.assign(new Error('Preventivo no encontrado'),{status:404});
    requireAction(authUser,'preventives.read',plan.area);
    const from=preventiveCompliance.day(url.searchParams.get('from'),'fecha inicial');
    const to=preventiveCompliance.day(url.searchParams.get('to'),'fecha final');
    const asOf=preventiveCompliance.day(url.searchParams.get('as_of')||new Date().toISOString().slice(0,10),'fecha de cálculo');
    if(from>to)throw Object.assign(new Error('El período está invertido'),{status:400});
    const rows=db.prepare(`SELECT o.id,o.task_id,o.occurrence_index,o.base_date,w.scheduled_at,o.work_order_id,w.folio,w.status order_status
      FROM preventive_occurrences o JOIN work_orders w ON w.id=o.work_order_id WHERE o.plan_id=? AND o.base_date BETWEEN ? AND ? ORDER BY o.base_date,o.id`).all(id,from,to).map(row=>{
        const execution=preventiveExecution.read(db,row.work_order_id);return preventiveCompliance.classify({...row,scheduled_date:row.scheduled_at,execution_state:execution?.state,executed_at:execution?.executed_at},asOf);
      });
    return json(res,200,{plan_id:id,from,to,as_of:asOf,definition:'T=ejecutada en fecha base; D=ejecutada después; V=vencida sin ejecución; P=pendiente; R=cancelada excluida',...preventiveCompliance.summarize(rows),occurrences:rows});
  }
  if(req.method==='POST' && /^\/api\/preventives\/\d+\/occurrences\/\d+\/reschedule$/.test(url.pathname)){
    const parts=url.pathname.split('/'),planId=Number(parts[3]),occurrenceId=Number(parts[5]),input=await body(req);const row=db.prepare(`SELECT o.id,o.base_date,o.work_order_id,w.scheduled_at,w.version,a.area FROM preventive_occurrences o JOIN work_orders w ON w.id=o.work_order_id JOIN assets a ON a.id=(SELECT asset_id FROM preventive_plans WHERE id=o.plan_id) WHERE o.id=? AND o.plan_id=?`).get(occurrenceId,planId);
    if(!row)throw Object.assign(new Error('Ocurrencia no encontrada'),{status:404});requireAction(authUser,'orders.edit_dates',row.area);const scheduled=preventiveCompliance.day(input.scheduled_at,'fecha reprogramada');if(!String(input.reason||'').trim())throw Object.assign(new Error('Reprogramar requiere un motivo'),{status:400});if(Number(input.version)!==row.version)throw Object.assign(new Error('La OT cambió en otra sesión'),{status:409});
    db.exec('BEGIN IMMEDIATE');try{db.prepare('UPDATE work_orders SET scheduled_at=?,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND version=?').run(scheduled,row.work_order_id,row.version);db.prepare('INSERT INTO work_order_events (work_order_id,user_id,event,details) VALUES (?,?,?,?)').run(row.work_order_id,authUser.id,'OT preventiva reprogramada',`Fecha operativa: ${row.scheduled_at||'sin fecha'} → ${scheduled}. Motivo: ${String(input.reason).trim()}`);audit(authUser.id,'preventive_occurrence',occurrenceId,'rescheduled',row,{...row,scheduled_at:scheduled},String(input.reason).trim());db.exec('COMMIT');return json(res,200,{ok:true,occurrence_id:occurrenceId,base_date:row.base_date,scheduled_at:scheduled,version:row.version+1});}catch(error){db.exec('ROLLBACK');throw error;}
  }
  if(req.method==='GET' && /^\/api\/preventives\/\d+\/upcoming$/.test(url.pathname)){
    const id=Number(url.pathname.split('/')[3]),plan=db.prepare('SELECT p.id,a.area FROM preventive_plans p JOIN assets a ON a.id=p.asset_id WHERE p.id=?').get(id);if(!plan)throw Object.assign(new Error('Preventivo no encontrado'),{status:404});requireAction(authUser,'preventives.read',plan.area);const from=preventiveCompliance.day(url.searchParams.get('from')||new Date().toISOString().slice(0,10),'fecha inicial'),to=preventiveCompliance.day(url.searchParams.get('to')||new Date(Date.now()+30*86400000).toISOString().slice(0,10),'fecha final');if(from>to)throw Object.assign(new Error('El período está invertido'),{status:400});const tasks=db.prepare('SELECT * FROM preventive_tasks WHERE plan_id=? ORDER BY id').all(id),saved=new Map(db.prepare('SELECT task_id,occurrence_index,work_order_id FROM preventive_occurrences WHERE plan_id=?').all(id).map(row=>[row.task_id+':'+row.occurrence_index,row]));const occurrences=tasks.flatMap(task=>preventiveTasks.project(task,from,to)).map(item=>({...item,persisted:saved.has(item.task_id+':'+item.occurrence_index),work_order_id:saved.get(item.task_id+':'+item.occurrence_index)?.work_order_id||null}));return json(res,200,{plan_id:id,from,to,projection_only:true,occurrences});
  }
  if (req.method === 'GET' && /^\/api\/preventives\/\d+\/revisions$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/')[3]);
    const plan=db.prepare('SELECT p.id,a.area FROM preventive_plans p JOIN assets a ON a.id=p.asset_id WHERE p.id=?').get(id);
    if(!plan) throw Object.assign(new Error('Preventivo no encontrado'),{status:404});
    requireAction(authUser,'preventives.read',plan.area);
    const rows=db.prepare('SELECT * FROM preventive_plan_revisions WHERE plan_id=? ORDER BY version DESC').all(id);
    return json(res,200,rows.map(({snapshot_json,...row})=>({...row,snapshot:JSON.parse(snapshot_json)})));
  }
  if (req.method === 'PATCH' && /^\/api\/preventives\/\d+$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/').pop()); const b=await body(req); const before=db.prepare('SELECT * FROM preventive_plans WHERE id=?').get(id);
    if(!before) throw Object.assign(new Error('Preventivo no encontrado'),{status:404});
    const area=db.prepare('SELECT area FROM assets WHERE id=?').get(before.asset_id)?.area; requireAction(authUser,'preventives.edit',area);
    if(!Object.hasOwn(b,'version')||Number(b.version)!==before.version) throw Object.assign(new Error('El preventivo cambió en otra sesión. Recarga para revisar los cambios.'),{status:409});
    if(before.work_order_id) throw Object.assign(new Error('Un preventivo con OT generada se conserva como versión histórica'),{status:409});
    const allowed=['title','frequency','next_date','responsible_id','status','template_code','instructions','applies_when']; const keys=allowed.filter(key=>Object.hasOwn(b,key));
    if(!keys.length) throw Object.assign(new Error('No hay campos válidos'),{status:400});
    for(const key of ['title','frequency','next_date']) if(Object.hasOwn(b,key)&&!String(b[key]).trim()) throw Object.assign(new Error(`Falta el campo ${key}`),{status:400});
    db.exec('BEGIN IMMEDIATE');
    try {
    const result=db.prepare(`UPDATE preventive_plans SET ${keys.map(key=>`${key}=?`).join(',')},version=version+1 WHERE id=? AND version=?`).run(...keys.map(key=>b[key]===''?null:b[key]),id,b.version);
    if(!result.changes) throw Object.assign(new Error('El preventivo cambió en otra sesión'),{status:409});
    preventiveHistory.record(db,id,authUser.id,'updated',b.reason||null);
    audit(authUser.id,'preventive_plan',id,'updated',before,{...before,...b,version:before.version+1},b.reason||null);
    db.exec('COMMIT'); return json(res,200,{ok:true,version:before.version+1});
    } catch(error) {db.exec('ROLLBACK');throw error;}
  }
  if (req.method === 'POST' && /^\/api\/preventives\/\d+\/order$/.test(url.pathname)) {
    const id=Number(url.pathname.split('/')[3]);
    const plan=db.prepare('SELECT * FROM preventive_plans WHERE id=?').get(id);
    if(!plan) throw Object.assign(new Error('Preventivo no encontrado'),{status:404});
    requireAction(authUser, 'preventives.edit', db.prepare('SELECT area FROM assets WHERE id=?').get(plan.asset_id)?.area);
    if(plan.work_order_id) return json(res,200,{id:plan.work_order_id,already_exists:true});
    if(db.prepare('SELECT 1 FROM preventive_occurrences WHERE plan_id=?').get(id))throw Object.assign(new Error('Este plan usa ocurrencias; genera la OT desde la ocurrencia correspondiente'),{status:409});
    const folio=nextFolio();db.exec('BEGIN');
    try{
      const detail=[plan.title,plan.instructions].filter(Boolean).join(' · ');
      const result=db.prepare(`INSERT INTO work_orders (folio,requested_at,requester_id,priority,classification,specialty,asset_id,reported_failure,technician_id,status)
        VALUES (?,datetime('now'),?,'Media','Mantenimiento Preventivo','Mecánica',?,?,?,'Abierta')`).run(folio,authUser.id,plan.asset_id,detail,plan.responsible_id);
      db.prepare("UPDATE preventive_plans SET work_order_id=?,status='Próximo' WHERE id=?").run(result.lastInsertRowid,id);
      db.prepare('INSERT INTO preventive_order_revisions (work_order_id,plan_id,version) VALUES (?,?,?)').run(result.lastInsertRowid,id,plan.version);
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
if (require.main === module) {
  ensureAdministrator().then(() => {
    db.prepare("DELETE FROM sessions WHERE expires_at<=datetime('now')").run();
    server.listen(PORT,HOST,()=>console.log(`MESA Mantenimiento disponible en http://localhost:${PORT}`));
  }).catch(error => { console.error('No fue posible iniciar:',error); process.exitCode=1; });
}

function shutdown() {
  server.close(() => { db.close(); process.exit(0); });
  setTimeout(() => process.exit(1), 5000).unref();
}
process.on('SIGTERM',shutdown);
process.on('SIGINT',shutdown);

module.exports={server,db,hoursBetween,orderLaborHours,nextFolio};
