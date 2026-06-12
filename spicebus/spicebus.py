#!/usr/bin/env python3
"""
SpiceBus ☕ — AOS Multi-Agent Communication Bus (Cloud Edition)
================================================================
3 Active Agents + 1 Human Director + 1 Neutral Monitor

Cloud-ready: auto-init, env-based config, gunicorn-compatible.
"Minimum In, Maximum Out — That's AOS Communication!"
"""

import json
import sqlite3
import uuid
import hashlib
import secrets
import os
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, request, jsonify, g

# ═══════════════════════════════════════════
# Configuration (env-based for cloud)
# ═══════════════════════════════════════════

SPICEBUS_DIR = Path(os.environ.get("SPICEBUS_DIR", str(Path.home() / ".spicebus")))
SPICEBUS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = SPICEBUS_DIR / "spicebus.db"
TOKENS_PATH = SPICEBUS_DIR / "tokens.json"

ROLE_DIRECTOR = "director"
ROLE_AGENT = "agent"
ROLE_MONITOR = "monitor"

CH_WORK = "work"
CH_MONITOR = "monitor"
CH_ALERTS = "alerts"

STATE_NEW = "new"
STATE_CLAIMED = "claimed"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_REVIEWED = "reviewed"

app = Flask(__name__)

# ═══════════════════════════════════════════
# Homepage
# ═══════════════════════════════════════════

@app.route("/")
def homepage():
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>☕ SpiceBus</title>
<style>
  body{font-family:monospace;background:#1a1a2e;color:#e0e0e0;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}
  .box{background:#16213e;border:2px solid #0f3460;border-radius:12px;padding:40px;max-width:600px;text-align:center}
  h1{color:#e94560;font-size:2em} h2{color:#0f3460} a{color:#e94560;text-decoration:none}
  .api{text-align:left;background:#0a0a1a;padding:15px;border-radius:8px;margin:15px 0}
  .g{color:#4ecca3} .y{color:#f0c040}
  .status{display:inline-block;background:#4ecca3;color:#0a0a1a;padding:4px 12px;border-radius:20px;font-weight:bold;margin:10px 0}
</style></head><body><div class="box">
<h1>☕ SpiceBus</h1>
<p><em>AOS Multi-Agent Communication Bus</em></p>
<div class="status">🟢 ONLINE</div>
<p>🦅 Director &nbsp;|&nbsp; 🐻🤖🆕 Agents &nbsp;|&nbsp; 👁️ Monitor</p>
<div class="api">
<p class="g">API Endpoints:</p>
<p>GET  <a href="/api/health">/api/health</a> — Health check</p>
<p>GET  <a href="/api/agents">/api/agents</a> — List agents</p>
<p>GET  <a href="/api/work">/api/work</a> — List tasks</p>
<p>GET  <a href="/api/monitor/status">/api/monitor/status</a> — System status</p>
</div>
<p class="y">"Minimum In, Maximum Out — That's AOS Communication!"</p>
<p>🐻 + 🤖 = Coherence INSIDE Harmony 🟩⬜⬛</p>
<p style="font-size:0.8em;color:#555">☁️ Cloud Edition — Powered by AOS</p>
</div></body></html>"""

# ═══════════════════════════════════════════
# Database
# ═══════════════════════════════════════════

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(str(DB_PATH))
    db.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('director', 'agent', 'monitor')),
            token_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            last_seen TEXT,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS messages (
            msg_id TEXT PRIMARY KEY,
            channel TEXT NOT NULL CHECK(channel IN ('work', 'monitor', 'alerts')),
            from_agent TEXT NOT NULL,
            to_agent TEXT,
            msg_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            state TEXT DEFAULT 'new',
            claimed_by TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (from_agent) REFERENCES agents(agent_id),
            FOREIGN KEY (claimed_by) REFERENCES agents(agent_id)
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            agent_id TEXT NOT NULL,
            action TEXT NOT NULL,
            channel TEXT,
            msg_id TEXT,
            details TEXT
        );
        CREATE TABLE IF NOT EXISTS deliverables (
            deliv_id TEXT PRIMARY KEY,
            msg_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            reviewed INTEGER DEFAULT 0,
            review_notes TEXT,
            FOREIGN KEY (msg_id) REFERENCES messages(msg_id),
            FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
        );
        CREATE INDEX IF NOT EXISTS idx_msg_channel ON messages(channel);
        CREATE INDEX IF NOT EXISTS idx_msg_state ON messages(state);
        CREATE INDEX IF NOT EXISTS idx_msg_to ON messages(to_agent);
        CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log(agent_id);
        CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_deliv_msg ON deliverables(msg_id);
    """)
    db.commit()
    db.close()

# ═══════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════

def load_tokens():
    if TOKENS_PATH.exists():
        return json.loads(TOKENS_PATH.read_text())
    return {}

def save_tokens(tokens):
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))

def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()

def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-SpiceBus-Token", "")
        if not token:
            return jsonify({"error": "Missing token"}), 401
        db = get_db()
        agent = db.execute(
            "SELECT * FROM agents WHERE token_hash = ? AND active = 1",
            (hash_token(token),)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Invalid token"}), 401
        db.execute("UPDATE agents SET last_seen = datetime('now') WHERE agent_id = ?", (agent["agent_id"],))
        db.commit()
        g.agent = dict(agent)
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if g.agent["role"] not in roles:
                audit(g.agent["agent_id"], "ACCESS_DENIED", details={"required": list(roles), "got": g.agent["role"]})
                return jsonify({"error": f"Role {g.agent['role']} not authorized"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def audit(agent_id, action, channel=None, msg_id=None, details=None):
    db = get_db()
    db.execute(
        "INSERT INTO audit_log (agent_id, action, channel, msg_id, details) VALUES (?, ?, ?, ?, ?)",
        (agent_id, action, channel, msg_id, json.dumps(details) if details else None)
    )
    db.commit()

# ═══════════════════════════════════════════
# API Routes
# ═══════════════════════════════════════════

@app.route("/api/health")
def health():
    return jsonify({"status": "alive", "service": "SpiceBus ☕", "version": "0.00", "edition": "cloud", "motto": "Minimum In, Maximum Out!"})

# --- Agent Management ---

@app.route("/api/agents", methods=["POST"])
@auth_required
@role_required(ROLE_DIRECTOR)
def register_agent():
    data = request.json
    name = data.get("name")
    role = data.get("role", ROLE_AGENT)
    if not name:
        return jsonify({"error": "Name required"}), 400
    if role not in (ROLE_DIRECTOR, ROLE_AGENT, ROLE_MONITOR):
        return jsonify({"error": f"Invalid role: {role}"}), 400
    agent_id = f"aos-{name.lower().replace(' ', '-')}"
    token = secrets.token_urlsafe(32)
    db = get_db()
    try:
        db.execute("INSERT INTO agents (agent_id, name, role, token_hash) VALUES (?, ?, ?, ?)", (agent_id, name, role, hash_token(token)))
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Agent {agent_id} already exists"}), 409
    tokens = load_tokens()
    tokens[agent_id] = token
    save_tokens(tokens)
    audit(g.agent["agent_id"], "REGISTER_AGENT", details={"new_agent": agent_id, "role": role})
    return jsonify({"agent_id": agent_id, "name": name, "role": role, "token": token, "message": f"☕ Welcome to SpiceBus, {name}!"}), 201

@app.route("/api/agents", methods=["GET"])
@auth_required
def list_agents():
    db = get_db()
    agents = db.execute("SELECT agent_id, name, role, last_seen, active FROM agents").fetchall()
    audit(g.agent["agent_id"], "LIST_AGENTS")
    return jsonify({"agents": [dict(a) for a in agents]})

# --- Work Channel ---

@app.route("/api/work", methods=["POST"])
@auth_required
@role_required(ROLE_DIRECTOR)
def post_task():
    data = request.json
    msg_id = str(uuid.uuid4())[:8]
    to_agent = data.get("to")
    db = get_db()
    db.execute("INSERT INTO messages (msg_id, channel, from_agent, to_agent, msg_type, payload, state) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (msg_id, CH_WORK, g.agent["agent_id"], to_agent, "task", json.dumps(data.get("task", {})), STATE_NEW))
    db.commit()
    audit(g.agent["agent_id"], "POST_TASK", CH_WORK, msg_id, {"to": to_agent})
    return jsonify({"msg_id": msg_id, "state": STATE_NEW, "message": "☕ Task posted to /work"}), 201

@app.route("/api/work", methods=["GET"])
@auth_required
@role_required(ROLE_DIRECTOR, ROLE_AGENT, ROLE_MONITOR)
def get_tasks():
    db = get_db()
    if g.agent["role"] == ROLE_AGENT:
        tasks = db.execute("SELECT * FROM messages WHERE channel = ? AND (to_agent = ? OR to_agent IS NULL) ORDER BY created_at DESC", (CH_WORK, g.agent["agent_id"])).fetchall()
    else:
        tasks = db.execute("SELECT * FROM messages WHERE channel = ? ORDER BY created_at DESC", (CH_WORK,)).fetchall()
    audit(g.agent["agent_id"], "READ_WORK", CH_WORK)
    return jsonify({"tasks": [dict(t) for t in tasks]})

@app.route("/api/work/<msg_id>/claim", methods=["POST"])
@auth_required
@role_required(ROLE_AGENT)
def claim_task(msg_id):
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE msg_id = ?", (msg_id,)).fetchone()
    if not msg:
        return jsonify({"error": "Task not found"}), 404
    if msg["state"] != STATE_NEW:
        return jsonify({"error": f"Task already {msg['state']}"}), 409
    if msg["to_agent"] and msg["to_agent"] != g.agent["agent_id"]:
        return jsonify({"error": "Task assigned to another agent"}), 403
    db.execute("UPDATE messages SET state = ?, claimed_by = ?, updated_at = datetime('now') WHERE msg_id = ?", (STATE_CLAIMED, g.agent["agent_id"], msg_id))
    db.commit()
    audit(g.agent["agent_id"], "CLAIM_TASK", CH_WORK, msg_id)
    return jsonify({"msg_id": msg_id, "state": STATE_CLAIMED, "message": "☕ Task claimed!"})

@app.route("/api/work/<msg_id>/deliver", methods=["POST"])
@auth_required
@role_required(ROLE_AGENT)
def deliver_task(msg_id):
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE msg_id = ?", (msg_id,)).fetchone()
    if not msg:
        return jsonify({"error": "Task not found"}), 404
    if msg["claimed_by"] != g.agent["agent_id"]:
        return jsonify({"error": "Not your task"}), 403
    data = request.json
    deliv_id = str(uuid.uuid4())[:8]
    db.execute("INSERT INTO deliverables (deliv_id, msg_id, agent_id, content) VALUES (?, ?, ?, ?)", (deliv_id, msg_id, g.agent["agent_id"], json.dumps(data.get("content", {}))))
    db.execute("UPDATE messages SET state = ?, updated_at = datetime('now') WHERE msg_id = ?", (STATE_DONE, msg_id))
    db.commit()
    audit(g.agent["agent_id"], "DELIVER", CH_WORK, msg_id, {"deliv_id": deliv_id})
    return jsonify({"deliv_id": deliv_id, "msg_id": msg_id, "state": STATE_DONE, "message": "☕ Delivered!"})

# --- Monitor ---

@app.route("/api/monitor/audit", methods=["GET"])
@auth_required
@role_required(ROLE_MONITOR, ROLE_DIRECTOR)
def get_audit_log():
    db = get_db()
    limit = request.args.get("limit", 100, type=int)
    since = request.args.get("since", "")
    if since:
        logs = db.execute("SELECT * FROM audit_log WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?", (since, limit)).fetchall()
    else:
        logs = db.execute("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    audit(g.agent["agent_id"], "READ_AUDIT", CH_MONITOR)
    return jsonify({"audit": [dict(l) for l in logs]})

@app.route("/api/monitor/status", methods=["GET"])
@auth_required
@role_required(ROLE_MONITOR, ROLE_DIRECTOR)
def get_status():
    db = get_db()
    stats = {
        "agents_active": db.execute("SELECT COUNT(*) as c FROM agents WHERE active=1").fetchone()["c"],
        "tasks_total": db.execute("SELECT COUNT(*) as c FROM messages WHERE channel='work'").fetchone()["c"],
        "tasks_new": db.execute("SELECT COUNT(*) as c FROM messages WHERE channel='work' AND state='new'").fetchone()["c"],
        "tasks_claimed": db.execute("SELECT COUNT(*) as c FROM messages WHERE channel='work' AND state='claimed'").fetchone()["c"],
        "tasks_done": db.execute("SELECT COUNT(*) as c FROM messages WHERE channel='work' AND state='done'").fetchone()["c"],
        "tasks_failed": db.execute("SELECT COUNT(*) as c FROM messages WHERE channel='work' AND state='failed'").fetchone()["c"],
        "deliverables": db.execute("SELECT COUNT(*) as c FROM deliverables").fetchone()["c"],
        "audit_entries": db.execute("SELECT COUNT(*) as c FROM audit_log").fetchone()["c"],
    }
    audit(g.agent["agent_id"], "STATUS_CHECK", CH_MONITOR)
    return jsonify({"status": "☕ SpiceBus ALIVE", "stats": stats})

# --- Alerts ---

@app.route("/api/alerts", methods=["POST"])
@auth_required
@role_required(ROLE_MONITOR)
def post_alert():
    data = request.json
    msg_id = str(uuid.uuid4())[:8]
    db = get_db()
    director = db.execute("SELECT agent_id FROM agents WHERE role = 'director' LIMIT 1").fetchone()
    if not director:
        return jsonify({"error": "No director registered"}), 500
    db.execute("INSERT INTO messages (msg_id, channel, from_agent, to_agent, msg_type, payload) VALUES (?, ?, ?, ?, ?, ?)",
               (msg_id, CH_ALERTS, g.agent["agent_id"], director["agent_id"], "alert", json.dumps(data.get("alert", {}))))
    db.commit()
    audit(g.agent["agent_id"], "POST_ALERT", CH_ALERTS, msg_id)
    return jsonify({"msg_id": msg_id, "message": "⚠️ Alert sent to Director"}), 201

@app.route("/api/alerts", methods=["GET"])
@auth_required
@role_required(ROLE_DIRECTOR)
def get_alerts():
    db = get_db()
    alerts = db.execute("SELECT * FROM messages WHERE channel = ? ORDER BY created_at DESC", (CH_ALERTS,)).fetchall()
    return jsonify({"alerts": [dict(a) for a in alerts]})

# --- Inter-agent messaging ---

@app.route("/api/message", methods=["POST"])
@auth_required
def send_message():
    data = request.json
    to_agent = data.get("to")
    if not to_agent:
        return jsonify({"error": "Recipient required"}), 400
    if g.agent["role"] == ROLE_MONITOR:
        db = get_db()
        director = db.execute("SELECT agent_id FROM agents WHERE role = 'director' LIMIT 1").fetchone()
        if not director or to_agent != director["agent_id"]:
            return jsonify({"error": "Monitor can only message Director"}), 403
    msg_id = str(uuid.uuid4())[:8]
    db = get_db()
    db.execute("INSERT INTO messages (msg_id, channel, from_agent, to_agent, msg_type, payload) VALUES (?, ?, ?, ?, ?, ?)",
               (msg_id, CH_WORK, g.agent["agent_id"], to_agent, "message", json.dumps(data.get("content", {}))))
    db.commit()
    audit(g.agent["agent_id"], "SEND_MESSAGE", CH_WORK, msg_id, {"to": to_agent})
    return jsonify({"msg_id": msg_id, "message": "☕ Message sent via SpiceBus"})

# ═══════════════════════════════════════════
# Auto-init & Director setup
# ═══════════════════════════════════════════

def auto_init():
    """Auto-initialize DB and Director on first run."""
    init_db()
    if not TOKENS_PATH.exists() or "aos-director" not in load_tokens():
        # Check env for pre-set Director token, otherwise generate
        director_token = os.environ.get("SPICEBUS_DIRECTOR_TOKEN", secrets.token_urlsafe(32))
        db = sqlite3.connect(str(DB_PATH))
        try:
            db.execute("INSERT INTO agents (agent_id, name, role, token_hash) VALUES (?, ?, ?, ?)",
                       ("aos-director", "Director", ROLE_DIRECTOR, hash_token(director_token)))
            db.commit()
        except sqlite3.IntegrityError:
            pass
        db.close()
        tokens = load_tokens()
        tokens["aos-director"] = director_token
        save_tokens(tokens)
        print(f"☕ SpiceBus auto-initialized!")
        print(f"🔑 Director token: {director_token}")
        print(f"📂 Data dir: {SPICEBUS_DIR}")

# Run auto-init on import (for gunicorn)
auto_init()

# ═══════════════════════════════════════════
# Main (local dev)
# ═══════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5555))
    print(f"""
╔══════════════════════════════════════╗
║       ☕ SpiceBus v0.00 ☁️           ║
║   AOS Multi-Agent Communication     ║
║   Port: {port:<29}║
║   DB: {str(DB_PATH):<31}║
║   "Minimum In, Maximum Out!"        ║
╚══════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=port, debug=False)
