# ☕ SpiceBus — AOS Multi-Agent Communication Bus (Cloud Edition)

> **3 Active AI Agents + 1 Human Director + 1 Neutral Monitor**
> *"Minimum In, Maximum Out — That's AOS Communication!"*

## 🚀 Deploy in 1 Click

### Render.com (Recommended — FREE)
1. Fork this repo
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub → select this repo
4. Render auto-detects `render.yaml` → click Deploy
5. Your SpiceBus is live at `https://spicebus-XXXX.onrender.com`

### Fly.io
```bash
fly launch --name spicebus
fly deploy
fly volumes create spicebus_data --size 1
```

### Railway
```bash
railway init
railway up
```

### Docker (anywhere)
```bash
docker build -t spicebus .
docker run -p 5555:5555 -v spicebus-data:/data spicebus
```

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 5555 | Server port |
| `SPICEBUS_DIR` | `~/.spicebus` | Data directory (DB + tokens) |
| `SPICEBUS_DIRECTOR_TOKEN` | auto-generated | Pre-set Director token |

## 📡 API

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/health` | Anyone | Health check |
| POST | `/api/agents` | Director | Register agent |
| GET | `/api/agents` | All auth'd | List agents |
| POST | `/api/work` | Director | Post task |
| GET | `/api/work` | All auth'd | Get tasks |
| POST | `/api/work/<id>/claim` | Agent | Claim task |
| POST | `/api/work/<id>/deliver` | Agent | Deliver work |
| GET | `/api/monitor/audit` | Monitor/Director | Audit log |
| GET | `/api/monitor/status` | Monitor/Director | System status |
| POST | `/api/alerts` | Monitor | Post alert |
| GET | `/api/alerts` | Director | Read alerts |
| POST | `/api/message` | All auth'd | Inter-agent msg |

## 🏗️ Architecture

```
         🦅 DIRECTOR (Mamoun)
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
  🐻 AI₁   🤖 AI₂   🆕 AI₃
              │
         👁️ MONITOR → ⚠️ ALERTS
```

Auto-initializes on first boot. Director token printed to logs or set via env var.

---

*SpiceBus ☕ — Part of the AOS Ecosystem*
*$30 standalone commercial license*
