#!/usr/bin/env python3
"""AGILLM4.1 central network monitor.

GET /api/status -> JSON snapshot of the whole network (agentic monitor).
GET /           -> auto-refreshing HTML dashboard (human website).
Collects training heartbeats, the points economy, inference-stage health,
node reachability, and disk - all best-effort, never crashes on a dead source.
"""
from __future__ import annotations
import json, os, socket, subprocess, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HB_DIR = Path("/root/agillm41_opportunistic/heartbeats")
LEDGER = Path("/root/agillm41_public_join/points_ledger.json")
STAGES = [("geth", "127.0.0.1", 9210, "0-7"), ("mcp", "10.0.1.20", 9211, "7-14"),
          ("prime", "10.0.1.30", 9212, "14-21"), ("communist-web", "10.0.1.1", 9213, "21-28"),
          ("v100-gpu", "127.0.0.1", 9215, "0-28(gpu)")]
NODES = [("geth", "127.0.0.1"), ("mcp", "10.0.1.20"), ("prime", "10.0.1.30"), ("communist-web", "10.0.1.1")]

def tcp_up(host, port, t=2.0):
    try:
        with socket.create_connection((host, port), timeout=t):
            return True
    except Exception:
        return False

def jget(url, t=3):
    try:
        with urllib.request.urlopen(url, timeout=t) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return None

def disk():
    out = {}
    for mnt in ("/", "/mnt/geth-vol1"):
        try:
            s = os.statvfs(mnt)
            tot = s.f_blocks * s.f_frsize; free = s.f_bavail * s.f_frsize
            out[mnt] = {"total_gb": round(tot/1e9, 1), "free_gb": round(free/1e9, 1),
                        "used_pct": round(100*(tot-free)/tot, 1) if tot else None}
        except Exception:
            pass
    return out

def heartbeats():
    out = {}
    if HB_DIR.is_dir():
        for f in HB_DIR.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                age = round(time.time() - f.stat().st_mtime, 1)
                d["_age_sec"] = age; d["_fresh"] = age < 600
                out[f.stem] = d
            except Exception:
                pass
    return out

def economy():
    try:
        d = json.loads(LEDGER.read_text() or "{}")
        return {"contributors": len(d),
                "points_outstanding": round(sum(v.get("points", 0) for v in d.values()), 2),
                "points_earned_total": round(sum(v.get("earned", 0) for v in d.values()), 2),
                "accepted_total": sum(v.get("accepted", 0) for v in d.values())}
    except Exception:
        return {"contributors": 0}

JOIN_SPOOL = Path("/root/agillm41_public_join/spool")

def joiners():
    led = {}
    try: led = json.loads(LEDGER.read_text() or "{}")
    except Exception: pass
    now = time.time()
    parts = []
    for pid, v in led.items():
        last = v.get("last") or v.get("first_seen") or 0
        parts.append({"id": (pid[:14] + "\u2026") if len(pid) > 14 else pid,
                      "points": round(v.get("points", 0), 1), "accepted": v.get("accepted", 0),
                      "rejected": v.get("rejected", 0), "age_min": round((now - last)/60, 1) if last else None})
    parts.sort(key=lambda r: (-(r["points"] or 0), r["age_min"] if r["age_min"] is not None else 1e9))
    active = []
    try:
        for f in sorted((JOIN_SPOOL/"leased").glob("*.json")):
            try:
                d = json.loads(f.read_text()); caps = d.get("capabilities", {}) or {}
                m = caps.get("machine", {}) or {}
                active.append({"node": d.get("node_id", "?"),
                               "device": m.get("device") or caps.get("device") or "?",
                               "gpu": m.get("gpu", ""), "lease": d.get("lease_id", f.stem)[:10],
                               "age_min": round((now - d.get("leased_at", now))/60, 1)})
            except Exception: pass
    except Exception: pass
    g=lambda d: len(list((JOIN_SPOOL/d).glob("*.json"))) if (JOIN_SPOOL/d).is_dir() else 0
    return {"participants": parts[:50], "active_leases": active,
            "counts": {"participants": len(parts), "active_now": len(active),
                       "leases_available": g("available"), "accepted": g("accepted"),
                       "quarantine": g("quarantine"), "rejected": g("rejected")}}

def snapshot():
    stages = [{"name": n, "layers": L, "host": h, "port": p, "up": tcp_up(h, p)} for n, h, p, L in STAGES]
    nodes = [{"name": n, "host": h, "reachable": tcp_up(h, 22) or tcp_up(h, 80) or h == "127.0.0.1"} for n, h in NODES]
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "training": heartbeats(),
        "economy": economy(),
        "join_network": jget("http://127.0.0.1:8787/api/v1/stats") or {"status": "coordinator down"},
        "inference_coordinator": {"up": tcp_up("127.0.0.1", 9200)},
        "inference_stages": stages,
        "stages_up": sum(1 for s in stages if s["up"]),
        "nodes": nodes,
        "disk": disk(),
        "joiners": joiners(),
    }

HTML = """<!doctype html><html><head><meta charset=utf-8><title>AGILLM4.1 Network</title>
<meta http-equiv=refresh content=15><style>
body{background:#0b0e14;color:#cdd6f4;font:14px/1.5 ui-monospace,monospace;margin:0;padding:24px}
h1{color:#89b4fa;font-size:20px}h2{color:#a6e3a1;font-size:15px;border-bottom:1px solid #313244;padding-bottom:4px;margin-top:24px}
.grid{display:flex;flex-wrap:wrap;gap:12px}.card{background:#11141c;border:1px solid #313244;border-radius:8px;padding:12px;min-width:200px}
.up{color:#a6e3a1}.down{color:#f38ba8}.dim{color:#6c7086}.big{font-size:22px;color:#fab387}
table{border-collapse:collapse}td{padding:2px 12px 2px 0}h3{color:#94e2d5;font-size:13px;margin:14px 0 4px}</style></head><body>
<h1>AGILLM4.1 Network Monitor <span class=dim id=ts></span></h1><div id=app>loading…</div>
<script>
async function load(){let d=await (await fetch('/api/status')).json();render(d)}
function chip(b){return b?'<span class=up>● up</span>':'<span class=down>● down</span>'}
function render(d){document.getElementById('ts').textContent=d.ts;
let h='';
h+='<h2>Inference ('+d.stages_up+'/'+d.inference_stages.length+' stages up, coordinator '+(d.inference_coordinator.up?'up':'down')+')</h2><div class=grid>';
for(let s of d.inference_stages)h+='<div class=card><b>'+s.name+'</b> '+chip(s.up)+'<br><span class=dim>layers '+s.layers+' · '+s.host+':'+s.port+'</span></div>';
h+='</div><h2>Economy</h2><div class=grid><div class=card>contributors<div class=big>'+d.economy.contributors+'</div></div><div class=card>points outstanding<div class=big>'+(d.economy.points_outstanding||0)+'</div></div><div class=card>accepted contributions<div class=big>'+(d.economy.accepted_total||0)+'</div></div></div>';
h+='<h2>Training</h2><div class=grid>';
for(let k in d.training){let t=d.training[k];h+='<div class=card><b>'+k+'</b> '+chip(t._fresh)+'<br><span class=dim>'+(t.status||'?')+(t.gpu?' · '+t.gpu:'')+(t.block_id!==undefined?' · block '+t.block_id:'')+'<br>'+Math.round(t._age_sec)+'s ago</span></div>';}
h+='</div><h2>Disk</h2><div class=grid>';
for(let m in d.disk){let x=d.disk[m];h+='<div class=card><b>'+m+'</b><br>'+x.free_gb+' GB free / '+x.total_gb+' GB <span class=dim>('+x.used_pct+'% used)</span></div>';}
var j=d.joiners||{counts:{},participants:[],active_leases:[]};
h+='</div><h2>Joiners — who\'s on the network ('+(j.counts.active_now||0)+' active, '+(j.counts.participants||0)+' total)</h2>';
h+='<div class=grid><div class=card>active now<div class=big>'+(j.counts.active_now||0)+'</div></div><div class=card>participants<div class=big>'+(j.counts.participants||0)+'</div></div><div class=card>accepted contribs<div class=big>'+(j.counts.accepted||0)+'</div></div><div class=card>leases available<div class=big>'+(j.counts.leases_available||0)+'</div></div></div>';
h+='<h3>Active right now</h3><table>';
for(let a of (j.active_leases||[]))h+='<tr><td class=up>\u25cf</td><td>'+a.node+'</td><td class=dim>'+(a.gpu||a.device||'?')+'</td><td class=dim>'+a.age_min+'m</td></tr>';
if(!(j.active_leases||[]).length)h+='<tr><td class=dim>nobody training a lease this moment</td></tr>';
h+='</table><h3>Top contributors</h3><table><tr><td class=dim>id</td><td class=dim>points</td><td class=dim>accepted</td><td class=dim>last seen</td></tr>';
for(let pp of (j.participants||[]).slice(0,15))h+='<tr><td>'+pp.id+'</td><td class=up>'+pp.points+'</td><td>'+pp.accepted+'</td><td class=dim>'+(pp.age_min!=null?pp.age_min+'m ago':'?')+'</td></tr>';
if(!(j.participants||[]).length)h+='<tr><td class=dim>no participants yet</td></tr>';
h+='</table>';
h+='</div><h2>Join network</h2><pre class=dim>'+JSON.stringify(d.join_network,null,1)+'</pre>';
document.getElementById('app').innerHTML=h;}
load();setInterval(load,15000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith("/api/status"):
            self._send(200, json.dumps(snapshot(), indent=2), "application/json")
        elif self.path == "/healthz":
            self._send(200, '{"ok":true}', "application/json")
        else:
            self._send(200, HTML, "text/html; charset=utf-8")
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(os.environ.get("AGILLM41_MONITOR_PORT", "8788"))
    print(f"monitor on :{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
