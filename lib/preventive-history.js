'use strict';

function record(db, id, userId, source, reason=null) {
  const plan=db.prepare('SELECT * FROM preventive_plans WHERE id=?').get(id);
  plan.tasks=db.prepare('SELECT * FROM preventive_tasks WHERE plan_id=? ORDER BY id').all(id);
  db.prepare(`INSERT INTO preventive_plan_revisions
    (plan_id,version,snapshot_json,user_id,source,reason) VALUES (?,?,?,?,?,?)`)
    .run(id,plan.version,JSON.stringify(plan),userId,source,reason);
}

function migrate(db) {
  db.exec('BEGIN IMMEDIATE');
  try {
    db.exec(`CREATE TABLE IF NOT EXISTS preventive_plan_revisions (
      plan_id INTEGER NOT NULL REFERENCES preventive_plans(id),
      version INTEGER NOT NULL,
      snapshot_json TEXT NOT NULL,
      user_id INTEGER REFERENCES users(id),
      source TEXT NOT NULL,
      reason TEXT,
      recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(plan_id,version)
    );
    CREATE TRIGGER IF NOT EXISTS preventive_revision_no_update
      BEFORE UPDATE ON preventive_plan_revisions BEGIN SELECT RAISE(ABORT,'La revisión es inmutable'); END;
    CREATE TRIGGER IF NOT EXISTS preventive_revision_no_delete
      BEFORE DELETE ON preventive_plan_revisions BEGIN SELECT RAISE(ABORT,'La revisión es inmutable'); END;
    CREATE TABLE IF NOT EXISTS preventive_order_revisions (
      work_order_id INTEGER PRIMARY KEY REFERENCES work_orders(id),
      plan_id INTEGER NOT NULL,
      version INTEGER NOT NULL,
      FOREIGN KEY(plan_id,version) REFERENCES preventive_plan_revisions(plan_id,version)
    );
    CREATE TRIGGER IF NOT EXISTS preventive_order_revision_no_update
      BEFORE UPDATE ON preventive_order_revisions BEGIN SELECT RAISE(ABORT,'La referencia es inmutable'); END;
    CREATE TRIGGER IF NOT EXISTS preventive_order_revision_no_delete
      BEFORE DELETE ON preventive_order_revisions BEGIN SELECT RAISE(ABORT,'La referencia es inmutable'); END;`);
    // Only preserve the version actually available; do not invent earlier revisions
    // or associate legacy orders with an unverified historical snapshot.
    const missing=db.prepare(`SELECT p.id FROM preventive_plans p WHERE NOT EXISTS
      (SELECT 1 FROM preventive_plan_revisions r WHERE r.plan_id=p.id AND r.version=p.version)`).all();
    missing.forEach(p=>record(db,p.id,null,'migration-baseline'));
    db.exec('COMMIT');
  } catch(error) { db.exec('ROLLBACK'); throw error; }
}

module.exports={migrate,record};
