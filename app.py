# archmc_dashboard.py
import os
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from dotenv import load_dotenv
import uvicorn

# ---------------------
# Load API key
# ---------------------
load_dotenv()
ARCH_API_KEY = os.getenv("ARCH_API_KEY")
if not ARCH_API_KEY:
    raise RuntimeError("ARCH_API_KEY missing in .env")

API_BASE = "https://api.arch.mc/v1"

# ---------------------
# FastAPI setup
# ---------------------
app = FastAPI(title="ArchMC Stats Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ---------------------
# Simple in-memory cache
# ---------------------
cache = {}
CACHE_TTL = 120  # seconds

def get_cached(key: str):
    entry = cache.get(key)
    if entry and datetime.utcnow() < entry["expires"]:
        return entry["data"]
    return None

def set_cache(key: str, data):
    cache[key] = {
        "data": data,
        "expires": datetime.utcnow() + timedelta(seconds=CACHE_TTL)
    }

# ---------------------
# Helper: fetch from PIGDI
# ---------------------
async def fetch_from_arch(endpoint: str):
    headers = {"X-API-KEY": ARCH_API_KEY}
    url = f"{API_BASE}{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

# ---------------------
# Process player data for readable display
# ---------------------
def process_player_data(username, data):
    highlights = []
    if "wins:global:casual:lifetime" in data:
        highlights.append(f"Wins: {data['wins:global:casual:lifetime']}")
    if "elo:nodebuff:ranked:lifetime" in data:
        highlights.append(f"ELO: {data['elo:nodebuff:ranked:lifetime']}")
    modes = {k: v for k, v in data.items() if isinstance(v, dict)}
    return {
        "username": username,
        "highlights": highlights if highlights else ["No highlights available"],
        "modes": modes
    }

# ---------------------
# API endpoints
# ---------------------
@app.get("/api/player/{username}")
async def player_stats(username: str):
    cached = get_cached(f"player:{username}")
    if cached:
        return cached
    raw_data = await fetch_from_arch(f"/players/username/{username}/statistics")
    processed = process_player_data(username, raw_data)
    set_cache(f"player:{username}", processed)
    return processed

@app.get("/api/economy/{username}")
async def economy(username: str):
    cached = get_cached(f"economy:{username}")
    if cached:
        return cached
    data = await fetch_from_arch(f"/economy/player/username/{username}")
    set_cache(f"economy:{username}", data)
    return data

@app.get("/api/guild/{username}")
async def guild(username: str):
    cached = get_cached(f"guild:{username}")
    if cached:
        return cached
    data = await fetch_from_arch(f"/guilds/player/username/{username}")
    set_cache(f"guild:{username}", data)
    return data

# ---------------------
# Web interface with Radium Lite style
# ---------------------
@app.get("/", response_class=HTMLResponse)
async def home():
    html_content = """
<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ArchMC Stats Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
:root {
  --bg: #050505;
  --glass: rgba(255, 255, 255, 0.02);
  --border: rgba(255, 255, 255, 0.08);
  --accent: #3b82f6;
}
body { background-color: var(--bg); color: #fff; font-family:'Inter',sans-serif; }
.holo-card { background: rgba(12,12,12,0.6); backdrop-filter: blur(12px); border:1px solid var(--border); border-radius:16px; padding:1.5rem; margin:2rem auto; max-width:900px; }
table { width:100%; border-collapse: collapse; margin-top:1rem; }
th { text-left; padding:0.75rem; background:var(--accent); color:white; }
td { padding:0.75rem; border-top:1px solid rgba(255,255,255,0.1); }
tr:nth-child(even){ background: rgba(255,255,255,0.05); }
.collapsible { cursor: pointer; background-color:rgba(255,255,255,0.05); padding:0.5rem; margin-top:0.5rem; border-radius:8px;}
.content { display: none; margin-left:20px; }
input, button { padding:0.5rem; margin:0.3rem; border-radius:8px; background:#111; color:#fff; border:1px solid var(--border); }
button:hover { background: var(--accent); color:#fff; transition:0.2s; }
</style>
</head>
<body>
<div class="holo-card">
<h2 class="text-3xl font-bold mb-4">ArchMC Stats Dashboard</h2>
<div>
<input type="text" id="username" placeholder="Enter username">
<button onclick="getPlayer()">Player Stats</button>
<button onclick="getEconomy()">Economy</button>
<button onclick="getGuild()">Guild</button>
</div>
<div id="stats" class="mt-6"></div>
</div>

<script>
async function fetchJSON(url) {
    const res = await fetch(url);
    if(!res.ok) throw new Error('Error fetching data');
    return await res.json();
}

async function getPlayer() {
    const username = document.getElementById('username').value;
    try {
        const data = await fetchJSON(`/api/player/${username}`);
        displayPlayer(data);
    } catch(e) { document.getElementById('stats').innerText = e; }
}

async function getEconomy() {
    const username = document.getElementById('username').value;
    try {
        const data = await fetchJSON(`/api/economy/${username}`);
        displayTable("Economy", data);
    } catch(e) { document.getElementById('stats').innerText = e; }
}

async function getGuild() {
    const username = document.getElementById('username').value;
    try {
        const data = await fetchJSON(`/api/guild/${username}`);
        displayTable("Guild", data);
    } catch(e) { document.getElementById('stats').innerText = e; }
}

function displayPlayer(data){
    let html = `<h3 class="text-2xl font-bold">${data.username}</h3>`;
    html += "<h4 class='mt-2 font-semibold'>Highlights:</h4><ul>";
    data.highlights.forEach(h => html += `<li>${h}</li>`);
    html += "</ul>";

    if(data.modes && Object.keys(data.modes).length>0){
        html += "<h4 class='mt-2 font-semibold'>Modes:</h4>";
        for(const mode in data.modes){
            html += `<div class="collapsible">${mode}</div>`;
            html += `<div class="content">` + generateTable(data.modes[mode]) + `</div>`;
        }
    } else { html += "<p>No mode stats available</p>"; }

    document.getElementById('stats').innerHTML = html;
    const coll = document.getElementsByClassName("collapsible");
    for(let i=0;i<coll.length;i++){
        coll[i].onclick = function(){
            this.classList.toggle("active");
            const content = this.nextElementSibling;
            content.style.display = (content.style.display==="block")?"none":"block";
        }
    }
}

function generateTable(obj){
    let html = "<table><tr><th>Key</th><th>Value</th></tr>";
    for(const key in obj){
        let value = obj[key];
        if(typeof value==="object" && value!==null){ value = JSON.stringify(value, null, 2); }
        html += `<tr><td>${key}</td><td><pre>${value}</pre></td></tr>`;
    }
    html += "</table>";
    return html;
}

function displayTable(title, data){
    let html = `<h3 class='text-2xl font-bold mt-4'>${title}</h3>` + generateTable(data);
    document.getElementById('stats').innerHTML = html;
}
</script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

# ---------------------
# Run server
# ---------------------
if __name__ == "__main__":
    uvicorn.run("archmc_dashboard:app", host="0.0.0.0", port=3000, reload=True)
