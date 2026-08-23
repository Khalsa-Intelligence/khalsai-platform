from workers import WorkerEntrypoint, Response
from urllib.parse import urlparse, parse_qs
import json
import time

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url_str = request.url
        parsed_url = urlparse(url_str)
        path = parsed_url.path
        method = request.method
        query_params = parse_qs(parsed_url.query)
        env = self.env

        # -------------------------------------------------------------
        # 1. LANDING PAGE WITH QR CODE: GET /
        # -------------------------------------------------------------
        if method == "GET" and path == "/":
            html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kaun Banega Khalsa v2 Host</title>
    <style>
        body { font-family: sans-serif; background: #0d1117; color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
        .card { background: #161b22; padding: 2rem; border-radius: 12px; text-align: center; border: 1px solid #30363d; width: 90%; max-width: 400px; }
        .qr-container { background: #ffffff; padding: 12px; border-radius: 8px; display: inline-block; margin: 1rem 0; }
        .qr-container img { display: block; width: 180px; height: 180px; }
        .btn-group { display: flex; gap: 10px; justify-content: center; margin-top: 1rem; }
        .btn { display: inline-block; padding: 10px 20px; color: #fff; background: #238636; text-decoration: none; border-radius: 6px; font-weight: bold; }
        .btn-blue { background: #1f6feb; }
    </style>
</head>
<body>
<div class="card">
    <h2>Kaun Banega Khalsa</h2>
    <p>A Khalsa Intelligence Initiative</p>
    
    <!-- Visible Group Display Banner -->
    <div id="groupBanner" style="display: none; margin: 10px 0 15px 0; background: #21262d; border: 1px solid #30363d; padding: 8px; border-radius: 6px; font-size: 0.95rem;">
        Cohort Group: <span id="groupNameDisplay" style="color: #f2cc60; font-weight: bold;"></span>
    </div>
    
    <div class="qr-container">
        <img id="qrImg" src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=https://khalsai.com/game" alt="Scan to Play">
    </div>
    
    <div class="btn-group">
        <a id="playBtn" href="/game" class="btn">Play Game</a>
        <a id="boardBtn" href="/leaderboard" class="btn btn-blue">Leaderboard</a>
    </div>
</div>

<script>
    const params = new URLSearchParams(window.location.search);
    const group = params.get('group') || params.get('Group'); 
    
    if (group && group.trim() !== '' && group.toUpperCase() !== 'GLOBAL') {
        const cleanGroup = group.toUpperCase();
        document.getElementById('playBtn').href = `/game?group=${encodeURIComponent(cleanGroup)}`;
        document.getElementById('boardBtn').href = `/leaderboard?group=${encodeURIComponent(cleanGroup)}`;
        document.getElementById('qrImg').src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=https://khalsai.com/game?group=${encodeURIComponent(cleanGroup)}`;
        document.getElementById('groupNameDisplay').textContent = cleanGroup;
        document.getElementById('groupBanner').style.display = 'block';
    }
</script>
</body>
</html>"""
            return Response(html, headers={"Content-Type": "text/html; charset=utf-8"})

        # -------------------------------------------------------------
        # 2. GAME ROUTE: GET /game
        # -------------------------------------------------------------
        if method == "GET" and path == "/game":
            new_req = request.clone()
            url = parsed_url._replace(path="/index.html").geturl()
            return await env.ASSETS.fetch(url)

        # -------------------------------------------------------------
        # 3. SUBMIT SCORE: POST /api/submit_score
        # -------------------------------------------------------------
        if method == "POST" and path == "/api/submit_score":
            try:
                body_text = await request.text()
                data = json.loads(body_text) if body_text else {}
                
                name = data.get("name")
                if not name:
                    return Response(json.dumps({"status": "error", "message": "Invalid data"}), status=400, headers={"Content-Type": "application/json"})

                record_id = data.get("id") or int(time.time() * 1000)
                age = data.get("age")
                level = data.get("level", 1)
                score = data.get("score", 0)
                group_code = (data.get("group_code") or "GLOBAL").strip().upper()

                query = "INSERT INTO leaderboard (id, name, age, level, score, group_code) VALUES (?, ?, ?, ?, ?, ?)"
                await env.DB.prepare(query).bind(record_id, name, age, level, score, group_code).run()

                return Response(json.dumps({"status": "success", "message": "Score saved to D1 Database!"}), headers={"Content-Type": "application/json"})
            except Exception as e:
                return Response(json.dumps({"status": "error", "message": str(e)}), status=500, headers={"Content-Type": "application/json"})

        # -------------------------------------------------------------
        # 4. DELETE SCORE: POST /api/delete_score
        # -------------------------------------------------------------
        if method == "POST" and path == "/api/delete_score":
            try:
                body_text = await request.text()
                data = json.loads(body_text) if body_text else {}

                if data.get("password") != "6789":
                    return Response(json.dumps({"status": "error", "message": "Incorrect password."}), status=403, headers={"Content-Type": "application/json"})

                target_id = data.get("id")
                query = "DELETE FROM leaderboard WHERE id = ?"
                await env.DB.prepare(query).bind(target_id).run()

                return Response(json.dumps({"status": "success", "message": "Entry deleted successfully."}), headers={"Content-Type": "application/json"})
            except Exception as e:
                return Response(json.dumps({"status": "error", "message": str(e)}), status=500, headers={"Content-Type": "application/json"})

        # -------------------------------------------------------------
        # 5. RESET LEADERBOARD: POST /api/reset_leaderboard
        # -------------------------------------------------------------
        if method == "POST" and path == "/api/reset_leaderboard":
            try:
                body_text = await request.text()
                data = json.loads(body_text) if body_text else {}

                if data.get("password") != "6789":
                    return Response(json.dumps({"status": "error", "message": "Incorrect password."}), status=403, headers={"Content-Type": "application/json"})

                query = "DELETE FROM leaderboard"
                await env.DB.prepare(query).run()

                return Response(json.dumps({"status": "success", "message": "Leaderboard reset successfully."}), headers={"Content-Type": "application/json"})
            except Exception as e:
                return Response(json.dumps({"status": "error", "message": str(e)}), status=500, headers={"Content-Type": "application/json"})

        # -------------------------------------------------------------
        # 6. DISPLAY LEADERBOARD: GET /leaderboard
        # -------------------------------------------------------------
        if method == "GET" and path == "/leaderboard":
            try:
                requested_group = query_params.get('group', ['GLOBAL'])[0].strip().upper()

                if requested_group != "GLOBAL":
                    stmt = env.DB.prepare("SELECT * FROM leaderboard WHERE UPPER(group_code) = ? ORDER BY level DESC, score DESC")
                    res = await stmt.bind(requested_group).all()
                else:
                    stmt = env.DB.prepare("SELECT * FROM leaderboard ORDER BY level DESC, score DESC")
                    res = await stmt.all()

                scores = res.results.to_py()

                group_stmt = env.DB.prepare("SELECT DISTINCT group_code FROM leaderboard")
                group_res = await group_stmt.all()
                existing_groups = [g.get('group_code') for g in group_res.results.to_py() if g.get('group_code')]

                dropdown_options = ""
                if requested_group != "GLOBAL":
                    dropdown_options = f'<option value="{requested_group}" selected>Group: {requested_group}</option>'
                    dropdown_options += '<option value="GLOBAL">Switch to Global</option>'
                else:
                    dropdown_options = '<option value="GLOBAL" selected>Global (All Scores)</option>'
                    for g in existing_groups:
                        if g.upper() != "GLOBAL":
                            dropdown_options += f'<option value="{g}">{g}</option>'

                rows_html = ""
                for rank, entry in enumerate(scores, 1):
                    name = entry.get('name') or 'Anonymous'
                    age = entry.get('age') if entry.get('age') is not None else '-'
                    level = entry.get('level', 1)
                    grp = entry.get('group_code') or 'GLOBAL'
                    record_id = entry.get('id', '')
                    rows_html += f"""
                        <tr>
                            <td>#{rank}</td>
                            <td>{name}</td>
                            <td>{age}</td>
                            <td>Level {level}</td>
                            <td><span class="group-tag">{grp}</span></td>
                            <td><button class="delete-btn" onclick="deleteEntry('{record_id}', '{name}')">Delete</button></td>
                        </tr>
                    """

                html_template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Ranked Leaderboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: sans-serif; background: #0d1117; color: #fff; padding: 2rem; max-width: 700px; margin: 0 auto; }
        h1 { text-align: center; color: #58a6ff; margin-bottom: 0.5rem; }
        .filter-bar { display: flex; justify-content: space-between; align-items: center; background: #161b22; padding: 12px; border-radius: 8px; margin-bottom: 1rem; border: 1px solid #30363d; }
        select { background: #0d1117; color: #fff; border: 1px solid #30363d; padding: 6px 12px; border-radius: 6px; font-weight: bold; }
        .actions-bar { display: flex; justify-content: flex-end; margin-bottom: 1rem; }
        .reset-btn { background: #da3633; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-weight: bold; }
        .reset-btn:hover { background: #b62324; }
        table { width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #30363d; }
        th { background: #21262d; color: #8b949e; }
        tr:first-child td { font-weight: bold; color: #f2cc60; }
        .group-tag { background: #1f6feb; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }
        .delete-btn { background: transparent; border: 1px solid #da3633; color: #da3633; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
        .delete-btn:hover { background: #da3633; color: white; }
        .nav-links { display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; }
        .back-btn { color: #58a6ff; text-decoration: none; }
    </style>
</head>
<body>
    <h1>Leaderboard</h1>

    <div class="filter-bar">
        <label for="groupSelect"><strong>Filter Group:</strong></label>
        <select id="groupSelect" onchange="window.location.href='/leaderboard?group=' + this.value">
            __DROPDOWN_OPTIONS__
        </select>
    </div>
    
    <div class="actions-bar">
        <button class="reset-btn" onclick="resetLeaderboard()">Reset All Scores</button>
    </div>

    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Name</th>
                <th>Age</th>
                <th>Level</th>
                <th>Group</th>
                <th>Action</th>
            </tr>
        </thead>
        <tbody>
            __ROWS_HTML__
        </tbody>
    </table>
    
    <div class="nav-links">
        <a id="playAgainBtn" href="/game" class="back-btn">&larr; Play Again</a>
    </div>
    
    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const group = urlParams.get('group');
        if (group && group !== 'GLOBAL') {
            document.getElementById('playAgainBtn').href = `/game?group=${encodeURIComponent(group)}`;
        }
    </script>

    <script>
        function deleteEntry(recordId, playerName) {
            const password = prompt("Enter admin password to delete score for " + playerName + ":");
            if (password === null) return;

            fetch('/api/delete_score', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: Number(recordId), password: password })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    location.reload();
                } else {
                    alert(data.message || "Incorrect password or error deleting entry.");
                }
            })
            .catch(err => alert("Error communicating with server"));
        }

        function resetLeaderboard() {
            const password = prompt("WARNING: Enter admin password to wipe the entire leaderboard:");
            if (password === null) return;

            fetch('/api/reset_leaderboard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: password })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    location.reload();
                } else {
                    alert(data.message || "Incorrect password or error resetting leaderboard.");
                }
            })
            .catch(err => alert("Error communicating with server"));
        }
    </script>
</body>
</html>"""
                
                html = html_template.replace("__DROPDOWN_OPTIONS__", dropdown_options).replace("__ROWS_HTML__", rows_html)

                return Response(html, headers={"Content-Type": "text/html; charset=utf-8"})
            except Exception as e:
                return Response(f"Error loading leaderboard: {str(e)}", status=500)

        return await env.ASSETS.fetch(request)
