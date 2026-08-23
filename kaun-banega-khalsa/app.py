from workers import WorkerEntrypoint, Response
from urllib.parse import urlparse
import json
import time

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url_str = request.url
        parsed_url = urlparse(url_str)
        path = parsed_url.path
        method = request.method
        env = self.env

        # -------------------------------------------------------------
        # 1. LANDING PAGE WITH QR CODE: GET /
        # -------------------------------------------------------------
        if method == "GET" and path == "/":
            html = """
            <!DOCTYPE html>
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
                    
                    <div class="qr-container">
                        <img src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=https://khalsai.com/game" alt="Scan to Play at khalsai.com/game">
                    </div>
                    
                    <p style="font-size: 0.9rem; color: #8b949e;">Scan QR code or click below to play/view scores</p>
                    
                    <div class="btn-group">
                        <a href="/game" class="btn">Play Here</a>
                        <a href="/leaderboard" class="btn btn-blue">View Leaderboard</a>
                    </div>
                </div>
            </body>
            </html>
            """
            return Response(html, headers={"Content-Type": "text/html; charset=utf-8"})

        # -------------------------------------------------------------
        # 2. GAME ROUTE: GET /game
        # -------------------------------------------------------------
        if method == "GET" and path == "/game":
            # Fetches index.html from static assets asset directory
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

                query = "INSERT INTO leaderboard (id, name, age, level, score) VALUES (?, ?, ?, ?, ?)"
                await env.DB.prepare(query).bind(record_id, name, age, level, score).run()

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
                stmt = env.DB.prepare("SELECT * FROM leaderboard ORDER BY level DESC, score DESC")
                res = await stmt.all()
                scores = res.results.to_py()

                rows_html = ""
                for rank, entry in enumerate(scores, 1):
                    name = entry.get('name') or 'Anonymous'
                    age = entry.get('age') if entry.get('age') is not None else '-'
                    level = entry.get('level', 1)
                    record_id = entry.get('id', '')
                    rows_html += f"""
                        <tr>
                            <td>#{rank}</td>
                            <td>{name}</td>
                            <td>{age}</td>
                            <td>Level {level}</td>
                            <td><button class="delete-btn" onclick="deleteEntry('{record_id}', '{name}')">Delete</button></td>
                        </tr>
                    """

                html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Ranked Leaderboard</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body {{ font-family: sans-serif; background: #0d1117; color: #fff; padding: 2rem; max-width: 650px; margin: 0 auto; }}
                        h1 {{ text-align: center; color: #58a6ff; }}
                        .actions-bar {{ display: flex; justify-content: flex-end; margin-bottom: 1rem; }}
                        .reset-btn {{ background: #da3633; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-weight: bold; }}
                        .reset-btn:hover {{ background: #b62324; }}
                        table {{ width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden; }}
                        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #30363d; }}
                        th {{ background: #21262d; color: #8b949e; }}
                        tr:first-child td {{ font-weight: bold; color: #f2cc60; }}
                        .delete-btn {{ background: transparent; border: 1px solid #da3633; color: #da3633; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }}
                        .delete-btn:hover {{ background: #da3633; color: white; }}
                        .nav-links {{ display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; }}
                        .back-btn {{ color: #58a6ff; text-decoration: none; }}
                    </style>
                </head>
                <body>
                    <h1>🏆 Leaderboard</h1>
                    
                    <div class="actions-bar">
                        <button class="reset-btn" onclick="resetLeaderboard()">Reset All Scores</button>
                    </div>

                    <table>
                        <thead>
                            <tr>
                                <th>Rank</th>
                                <th>Name</th>
                                <th>Age</th>
                                <th>Level Reached</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                    
                    <div class="nav-links">
                        <a href="/game" class="back-btn">&larr; Play Again</a>
                    </div>

                    <script>
                        function deleteEntry(recordId, playerName) {{
                            const password = prompt("Enter admin password to delete score for " + playerName + ":");
                            if (password === null) return;

                            fetch('/api/delete_score', {{
                                method: 'POST',
                                headers: {{ 'Content-Type': 'application/json' }},
                                body: JSON.stringify({{ id: Number(recordId), password: password }})
                            }})
                            .then(res => res.json())
                            .then(data => {{
                                if (data.status === "success") {{
                                    location.reload();
                                }} else {{
                                    alert(data.message || "Incorrect password or error deleting entry.");
                                }}
                            }})
                            .catch(err => alert("Error communicating with server"));
                        }}

                        function resetLeaderboard() {{
                            const password = prompt("WARNING: Enter admin password to wipe the entire leaderboard:");
                            if (password === null) return;

                            fetch('/api/reset_leaderboard', {{
                                method: 'POST',
                                headers: {{ 'Content-Type': 'application/json' }},
                                body: JSON.stringify({{ password: password }})
                            }})
                            .then(res => res.json())
                            .then(data => {{
                                if (data.status === "success") {{
                                    location.reload();
                                }} else {{
                                    alert(data.message || "Incorrect password or error resetting leaderboard.");
                                }}
                            }})
                            .catch(err => alert("Error communicating with server"));
                        }}
                    </script>
                </body>
                </html>
                """
                return Response(html, headers={"Content-Type": "text/html; charset=utf-8"})
            except Exception as e:
                return Response(f"Error loading leaderboard: {str(e)}", status=500)

        # Serve remaining static files (CSS, JS, images) via ASSETS
        return await env.ASSETS.fetch(request)
