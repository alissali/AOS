#!/usr/bin/env python3
"""
aos-bus ☕ — SpiceBus CLI Client
=================================
Command-line interface for SpiceBus multi-agent communication.

Usage:
  aos-bus status                    — System status
  aos-bus agents                    — List agents
  aos-bus register <name> <role>    — Register agent (Director only)
  aos-bus task <description> [--to agent-id]  — Post task
  aos-bus tasks                     — List tasks
  aos-bus claim <msg-id>            — Claim a task
  aos-bus deliver <msg-id> <content> — Deliver work
  aos-bus alert <message>           — Post alert (Monitor only)
  aos-bus alerts                    — Read alerts (Director only)
  aos-bus audit [--limit N]         — Read audit log
  aos-bus send <to> <message>       — Send message to agent
"""

import json
import sys
import os
import requests
from pathlib import Path

SPICEBUS_DIR = Path.home() / ".spicebus"
TOKENS_PATH = SPICEBUS_DIR / "tokens.json"
CONFIG_PATH = SPICEBUS_DIR / "client.json"

DEFAULT_HOST = "https://localhost:5555"

def get_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"host": DEFAULT_HOST, "agent_id": None, "token": None}

def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, indent=2))

def get_token(agent_id=None):
    config = get_config()
    if config.get("token"):
        return config["token"]
    if TOKENS_PATH.exists():
        tokens = json.loads(TOKENS_PATH.read_text())
        aid = agent_id or config.get("agent_id") or "aos-director"
        return tokens.get(aid)
    return None

def api(method, endpoint, data=None, token=None):
    config = get_config()
    host = config.get("host", DEFAULT_HOST)
    url = f"{host}/api/{endpoint}"
    headers = {"X-SpiceBus-Token": token or get_token()}
    
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        if method == "GET":
            r = requests.get(url, headers=headers, params=data, verify=False)
        else:
            r = requests.post(url, headers=headers, json=data, verify=False)
        return r.json(), r.status_code
    except requests.ConnectionError:
        return {"error": "SpiceBus not running! Start with: python spicebus.py serve"}, 0

def print_json(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    cmd = sys.argv[1]
    
    # --- Configure ---
    if cmd == "config":
        if len(sys.argv) < 4:
            print("Usage: aos-bus config <agent-id> <host>")
            config = get_config()
            print(f"Current: {json.dumps(config, indent=2)}")
            return
        config = get_config()
        config["agent_id"] = sys.argv[2]
        if len(sys.argv) > 3:
            config["host"] = sys.argv[3]
        tokens = json.loads(TOKENS_PATH.read_text()) if TOKENS_PATH.exists() else {}
        config["token"] = tokens.get(sys.argv[2])
        save_config(config)
        print(f"☕ Configured as {sys.argv[2]}")
    
    # --- Status ---
    elif cmd == "status":
        data, code = api("GET", "monitor/status")
        if code == 200:
            stats = data.get("stats", {})
            print(f"""
☕ SpiceBus Status
═══════════════════════
Agents active:   {stats.get('agents_active', '?')}
Tasks total:     {stats.get('tasks_total', 0)}
  ├── New:       {stats.get('tasks_new', 0)}
  ├── Claimed:   {stats.get('tasks_claimed', 0)}
  ├── Done:      {stats.get('tasks_done', 0)}
  └── Failed:    {stats.get('tasks_failed', 0)}
Deliverables:    {stats.get('deliverables', 0)}
Audit entries:   {stats.get('audit_entries', 0)}
""")
        else:
            print_json(data)
    
    # --- Agents ---
    elif cmd == "agents":
        data, code = api("GET", "agents")
        if code == 200:
            print("☕ Registered Agents:")
            print(f"{'ID':<25} {'Name':<15} {'Role':<10} {'Last Seen':<20} {'Active'}")
            print("─" * 85)
            for a in data.get("agents", []):
                active = "✅" if a.get("active") else "❌"
                last = a.get('last_seen') or 'never'
                print(f"{a['agent_id']:<25} {a['name']:<15} {a['role']:<10} {last:<20} {active}")
        else:
            print_json(data)
    
    # --- Register ---
    elif cmd == "register":
        if len(sys.argv) < 4:
            print("Usage: aos-bus register <name> <role>")
            print("Roles: agent, monitor")
            return
        data, code = api("POST", "agents", {"name": sys.argv[2], "role": sys.argv[3]})
        if code == 201:
            print(f"☕ Agent registered: {data['agent_id']}")
            print(f"🔑 Token: {data['token']}")
            print(f"   Role: {data['role']}")
        else:
            print_json(data)
    
    # --- Task ---
    elif cmd == "task":
        if len(sys.argv) < 3:
            print("Usage: aos-bus task <description> [--to agent-id]")
            return
        desc = sys.argv[2]
        to_agent = None
        if "--to" in sys.argv:
            idx = sys.argv.index("--to")
            if idx + 1 < len(sys.argv):
                to_agent = sys.argv[idx + 1]
        
        data, code = api("POST", "work", {"task": {"description": desc}, "to": to_agent})
        if code == 201:
            print(f"☕ Task posted: {data['msg_id']}")
            if to_agent:
                print(f"   Assigned to: {to_agent}")
        else:
            print_json(data)
    
    # --- Tasks ---
    elif cmd == "tasks":
        data, code = api("GET", "work")
        if code == 200:
            tasks = data.get("tasks", [])
            if not tasks:
                print("☕ No tasks on the bus!")
                return
            print("☕ Work Channel:")
            print(f"{'ID':<10} {'State':<10} {'From':<20} {'To':<20} {'Created'}")
            print("─" * 80)
            for t in tasks:
                payload = json.loads(t.get("payload", "{}"))
                desc = payload.get("description", "")[:40]
                print(f"{t['msg_id']:<10} {t['state']:<10} {t['from_agent']:<20} {t.get('to_agent', 'any'):<20} {t['created_at']}")
                if desc:
                    print(f"           └── {desc}")
        else:
            print_json(data)
    
    # --- Claim ---
    elif cmd == "claim":
        if len(sys.argv) < 3:
            print("Usage: aos-bus claim <msg-id>")
            return
        data, code = api("POST", f"work/{sys.argv[2]}/claim")
        print_json(data)
    
    # --- Deliver ---
    elif cmd == "deliver":
        if len(sys.argv) < 4:
            print("Usage: aos-bus deliver <msg-id> <content>")
            return
        content = " ".join(sys.argv[3:])
        data, code = api("POST", f"work/{sys.argv[2]}/deliver", {"content": {"result": content}})
        print_json(data)
    
    # --- Alert ---
    elif cmd == "alert":
        if len(sys.argv) < 3:
            print("Usage: aos-bus alert <message>")
            return
        msg = " ".join(sys.argv[2:])
        data, code = api("POST", "alerts", {"alert": {"message": msg, "severity": "warning"}})
        print_json(data)
    
    # --- Alerts ---
    elif cmd == "alerts":
        data, code = api("GET", "alerts")
        if code == 200:
            alerts = data.get("alerts", [])
            if not alerts:
                print("☕ No alerts!")
                return
            print("⚠️ Alerts:")
            for a in alerts:
                payload = json.loads(a.get("payload", "{}"))
                print(f"  [{a['created_at']}] from {a['from_agent']}: {payload.get('message', '')}")
        else:
            print_json(data)
    
    # --- Audit ---
    elif cmd == "audit":
        limit = 20
        if "--limit" in sys.argv:
            idx = sys.argv.index("--limit")
            if idx + 1 < len(sys.argv):
                limit = int(sys.argv[idx + 1])
        data, code = api("GET", "monitor/audit", {"limit": limit})
        if code == 200:
            logs = data.get("audit", [])
            print(f"☕ Audit Log (last {limit}):")
            for l in logs:
                print(f"  [{l['timestamp']}] {l['agent_id']:<20} {l['action']:<20} {l.get('channel', '')}")
        else:
            print_json(data)
    
    # --- Send ---
    elif cmd == "send":
        if len(sys.argv) < 4:
            print("Usage: aos-bus send <to-agent-id> <message>")
            return
        to = sys.argv[2]
        msg = " ".join(sys.argv[3:])
        data, code = api("POST", "message", {"to": to, "content": {"message": msg}})
        print_json(data)
    
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)

if __name__ == "__main__":
    main()
