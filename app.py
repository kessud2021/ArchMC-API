import os
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Query
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
async def fetch_from_arch(endpoint: str, params: dict = None):
    headers = {"X-API-KEY": ARCH_API_KEY}
    url = f"{API_BASE}{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

# ---------------------
# Process player data
# ---------------------
def process_player_data(username, data):
    highlights = []
    if "wins:global:casual:lifetime" in data:
        highlights.append(f"Wins: {data['wins:global:casual:lifetime']}")
    if "elo:nodebuff:ranked:lifetime" in data:
        highlights.append(f"ELO: {data['elo:nodebuff:ranked:lifetime']}")
    modes = {k: v for k, v in data.items() if isinstance(v, dict)}
    return {"username": username, "highlights": highlights or ["No highlights available"], "modes": modes}

# ---------------------
# API endpoints
# ---------------------
@app.get("/api/player/{username}")
async def player_stats(username: str, filter: str = None):
    key = f"player:{username}:{filter}"
    cached = get_cached(key)
    if cached:
        return cached
    params = {"filter": filter} if filter else None
    raw_data = await fetch_from_arch(f"/players/username/{username}/statistics", params)
    processed = process_player_data(username, raw_data)
    set_cache(key, processed)
    return processed

@app.get("/api/economy/{username}")
async def economy(username: str = None):
    key = f"economy:{username or 'baltop'}"
    cached = get_cached(key)
    if cached:
        return cached
    if username:
        data = await fetch_from_arch(f"/economy/player/username/{username}")
    else:
        data = await fetch_from_arch("/economy/baltop")
    set_cache(key, data)
    return data

@app.get("/api/economy/baltop/{currency}")
async def baltop_currency(currency: str):
    key = f"baltop:{currency}"
    cached = get_cached(key)
    if cached:
        return cached
    data = await fetch_from_arch(f"/economy/baltop/{currency}")
    set_cache(key, data)
    return data

@app.get("/api/guilds")
async def guild_list(page: int = 0, size: int = 10):
    key = f"guilds:list:{page}:{size}"
    cached = get_cached(key)
    if cached:
        return cached
    data = await fetch_from_arch("/guilds", params={"page": page, "size": size})
    set_cache(key, data)
    return data

@app.get("/api/guilds/search")
async def guild_search(name: str = None, description: str = None):
    if name:
        return await fetch_from_arch("/guilds/search/name", params={"q": name})
    if description:
        return await fetch_from_arch("/guilds/search/description", params={"q": description})
    raise HTTPException(status_code=400, detail="Provide either name or description")

@app.get("/api/guilds/player/{username}")
async def guild_by_player(username: str):
    return await fetch_from_arch(f"/guilds/player/username/{username}")

@app.get("/api/leaderboards/{statisticId}")
async def leaderboards(statisticId: str, page: int = 0, size: int = 10):
    return await fetch_from_arch(f"/leaderboards/{statisticId}", params={"page": page, "size": size})

@app.get("/api/statistics")
async def statistics():
    return await fetch_from_arch("/statistics")

# ---------------------
# Web interface
# ---------------------
@app.get("/", response_class=HTMLResponse)
async def home():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <title>ArchMC Dashboard</title>
    <style>
        body { font-family: Arial; margin: 2rem; padding: 2rem; background:#f5f5f5; }
        input, button, select { padding:0.5rem; margin:0.3rem; border-radius:6px; border:1px solid #ccc; }
        .stats-section { margin-top:2rem; padding:1rem; background:#fff; border-radius:8px; box-shadow:0 0 10px rgba(0,0,0,0.1);}
        table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
        table, th, td { border:1px solid #aaa; padding: 5px; text-align: left; vertical-align: top; }
        th { background:#eee; }
        label { display:block; margin-top:10px; font-weight:bold; }
        pre { white-space: pre-wrap; word-wrap: break-word; }
    </style>
    </head>
    <body>
        <h2>ArchMC Stats Dashboard</h2>
        <div>
            <label for="endpoint">Select Feature:</label>
            <select id="endpoint" onchange="toggleUsername()">
                <option value="player">Player Stats</option>
                <option value="economy">Economy</option>
                <option value="baltop">Balance Top</option>
                <option value="guild_list">Guilds List</option>
                <option value="guild_search">Guild Search</option>
                <option value="guild_player">Guild by Player</option>
                <option value="leaderboards">Leaderboards</option>
                <option value="statistics">Statistics</option>
            </select>
            <div id="username-div">
                <input type="text" id="username" placeholder="Enter username">
            </div>
            <div id="extra-div"></div>
            <button onclick="fetchData()">Fetch</button>
        </div>
        <div id="stats" class="stats-section"></div>

        <script>
        function toggleUsername(){
            const endpoint = document.getElementById("endpoint").value;
            const usernameDiv = document.getElementById("username-div");
            const extraDiv = document.getElementById("extra-div");
            usernameDiv.style.display = ["player","economy","guild_player"].includes(endpoint) ? "block" : "none";
            extraDiv.innerHTML = "";
            if(endpoint === "guild_search"){
                extraDiv.innerHTML = '<input type="text" id="guild-query" placeholder="Search query">';
            }
            if(endpoint === "leaderboards"){
                extraDiv.innerHTML = '<input type="text" id="stat-id" placeholder="Statistic ID">';
            }
            if(endpoint === "baltop"){
                extraDiv.innerHTML = '<input type="text" id="currency" placeholder="Currency (optional)">';
            }
        }

        function generateTable(obj){
            if(typeof obj !== "object" || obj === null) return obj;
            let html = "<table><tr><th>Key</th><th>Value</th></tr>";
            for(const key in obj){
                let value = obj[key];
                if(typeof value === "object" && value !== null){
                    value = generateTable(value);
                }
                html += `<tr><td>${key}</td><td>${value}</td></tr>`;
            }
            return html + "</table>";
        }

        async function fetchData(){
            const endpoint = document.getElementById("endpoint").value;
            const username = document.getElementById("username")?.value;
            const statsDiv = document.getElementById("stats");
            try{
                let url;
                if(endpoint === "player") url = `/api/player/${username}`;
                else if(endpoint === "economy") url = username ? `/api/economy/${username}` : `/api/economy`;
                else if(endpoint === "baltop"){
                    const currency = document.getElementById("currency")?.value;
                    url = currency ? `/api/economy/baltop/${currency}` : `/api/economy`;
                }
                else if(endpoint === "guild_list") url = `/api/guilds`;
                else if(endpoint === "guild_search"){
                    const q = document.getElementById("guild-query").value;
                    url = `/api/guilds/search?name=${q}`;
                }
                else if(endpoint === "guild_player") url = `/api/guilds/player/${username}`;
                else if(endpoint === "leaderboards"){
                    const statId = document.getElementById("stat-id").value;
                    url = `/api/leaderboards/${statId}`;
                }
                else if(endpoint === "statistics") url = `/api/statistics`;

                const data = await fetch(url).then(r=>r.json());
                statsDiv.innerHTML = generateTable(data);
            } catch(e){
                statsDiv.innerHTML = '<pre style="color:red">' + e + '</pre>';
            }
        }
        toggleUsername();
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
