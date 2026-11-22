from workers import WorkerEntrypoint, Response
from urllib.parse import urlparse, parse_qs
import json
import time


def _normalize_code(raw_val):
    if not raw_val:
        return ""
    return str(raw_val).lstrip("#").strip().upper()


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url_str = request.url
        parsed_url = urlparse(url_str)
        path = parsed_url.path
        method = request.method
        query_params = parse_qs(parsed_url.query)
        env = self.env

        # -------------------------------------------------------------
        # 0. PULSE DB API ROUTE: GET & POST /api/pulse
        # -------------------------------------------------------------
        if path == "/api/pulse" or path.endswith("/api/pulse"):
            db = getattr(env, "PULSE_DB", None) or getattr(env, "DB", None)
            if not db:
                return Response(
                    json.dumps({"success": False, "error": "Database binding PULSE_DB missing"}),
                    status=500,
                    headers={"Content-Type": "application/json"}
                )

            # GET: Fetch recent events by eventCode or seriesPrefix
            if method == "GET":
                try:
                    event_code_list = query_params.get("eventCode") or query_params.get("event_code")
                    series_prefix_list = query_params.get("seriesPrefix") or query_params.get("series_prefix")

                    raw_event_code = _normalize_code(event_code_list[0]) if event_code_list and event_code_list[0].strip() else ""
                    raw_series_prefix = _normalize_code(series_prefix_list[0]) if series_prefix_list and series_prefix_list[0].strip() else ""

                    if not raw_event_code and not raw_series_prefix:
                        return Response(
                            json.dumps({"success": False, "error": "eventCode or seriesPrefix parameter is required"}),
                            status=400,
                            headers={"Content-Type": "application/json"}
                        )

                    after_id_raw = (
                        query_params.get("afterId")
                        or query_params.get("after_id")
                        or query_params.get("sinceId")
                    )

                    after_id = 0
                    if after_id_raw and after_id_raw[0].strip().isdigit():
                        after_id = int(after_id_raw[0].strip())

                    page_limit = 1000
                    where_clauses = []
                    params = []

                    if raw_series_prefix:
                        where_clauses.append(
                            "TRIM(UPPER(REPLACE(COALESCE(event_code, ''), '#', ''))) LIKE ?"
                        )
                        params.append(f"{raw_series_prefix}%")
                        where_clauses.append(
                            "event_type IN ('quiz_answer', 'leaderboard_snapshot', 'leaderboard_reset')"
                        )
                    else:
                        where_clauses.append(
                            "TRIM(UPPER(REPLACE(COALESCE(event_code, ''), '#', ''))) = ?"
                        )
                        params.append(raw_event_code)

                    if after_id > 0:
                        where_clauses.append("id > ?")
                        params.append(after_id)

                    sql = (
                        "SELECT id, session_id, user_id, event_code, event_type, metadata, created_at "
                        "FROM pulse_events "
                        f"WHERE {' AND '.join(where_clauses)} "
                        f"ORDER BY id ASC LIMIT {page_limit}"
                    )

                    res = await db.prepare(sql).bind(*params).all()
                    rows = res.results.to_py() if hasattr(res.results, "to_py") else list(res.results)

                    return Response(
                        json.dumps({
                            "success": True,
                            "recent_pulses": rows,
                            "has_more": len(rows) == page_limit,
                        }),
                        headers={
                            "Content-Type": "application/json",
                            "Cache-Control": "no-store",
                        }
                    )
                except Exception as e:
                    return Response(
                        json.dumps({"success": False, "error": str(e)}),
                        status=500,
                        headers={"Content-Type": "application/json"}
                    )

            # POST: Save pre-loaded quiz questions, live releases, or responses
            if method == "POST":
                try:
                    body_text = await request.text()
                    data = json.loads(body_text) if body_text else {}

                    session_id = data.get("sessionId") or data.get("session_id") or "anon"
                    user_id = data.get("userId") or data.get("user_id")
                    event_code_raw = data.get("eventCode") or data.get("event_code")
                    event_type = data.get("eventType") or data.get("event_type")
                    metadata = data.get("metadata", {})

                    if not event_code_raw or not event_type:
                        return Response(
                            json.dumps({"success": False, "error": "eventCode and eventType are required"}),
                            status=400,
                            headers={"Content-Type": "application/json"}
                        )

                    clean_code = _normalize_code(event_code_raw)
                    metadata_str = json.dumps(metadata) if isinstance(metadata, (dict, list)) else str(metadata)

                    query = (
                        "INSERT INTO pulse_events (session_id, user_id, event_code, event_type, metadata) "
                        "VALUES (?, ?, ?, ?, ?)"
                    )
                    await db.prepare(query).bind(session_id, user_id, clean_code, event_type, metadata_str).run()

                    return Response(
                        json.dumps({"success": True}),
                        headers={"Content-Type": "application/json"}
                    )
                except Exception as e:
                    return Response(
                        json.dumps({"success": False, "error": str(e)}),
                        status=500,
                        headers={"Content-Type": "application/json"}
                    )

        # -------------------------------------------------------------
        # 1. KBK GAME ROUTE: GET /kbk (and /kbk/)
        # -------------------------------------------------------------
        if method == "GET" and path in ("/kbk", "/kbk/"):
            url = parsed_url._replace(path="/kbk/index.html").geturl()
            return await env.ASSETS.fetch(url)

        # Legacy /game redirect to /kbk (preserving query parameters)
        if method == "GET" and path == "/game":
            target = "/kbk" + (f"?{parsed_url.query}" if parsed_url.query else "")
            return Response("", status=302, headers={"Location": target})

        # -------------------------------------------------------------
        # 2. SUBMIT SANGAAT FEEDBACK: POST /api/feedback
        # -------------------------------------------------------------
        if method == "POST" and (path == "/api/feedback" or path.endswith("/api/feedback")):
            try:
                body_text = await request.text()
                data = json.loads(body_text) if body_text else {}

                session_name = data.get("session_name")
                rating = data.get("rating")
                learnt_new = data.get("learnt_new")
                touched_comment = data.get("touched_comment", "")
                encouragement_comment = data.get("encouragement_comment", "")

                if not session_name or rating is None or not learnt_new:
                    return Response(json.dumps({"success": False, "error": "Missing required fields"}), status=400, headers={"Content-Type": "application/json"})

                db = getattr(env, "FEEDBACK_DB", None) or getattr(env, "DB", None)
                if not db:
                    return Response(json.dumps({"success": False, "error": "Database binding missing"}), status=500, headers={"Content-Type": "application/json"})

                query = "INSERT INTO sangaat_feedback (session_name, rating, learnt_new, touched_comment, encouragement_comment) VALUES (?, ?, ?, ?, ?)"
                await db.prepare(query).bind(session_name, int(rating), learnt_new, touched_comment, encouragement_comment).run()

                return Response(json.dumps({"success": True}), headers={"Content-Type": "application/json"})
            except Exception as e:
                return Response(json.dumps({"success": False, "error": str(e)}), status=500, headers={"Content-Type": "application/json"})

        # -------------------------------------------------------------
        # 3. ADMIN VIEW FEEDBACK: POST /api/admin-feedback
        # -------------------------------------------------------------
        if method == "POST" and (path == "/api/admin-feedback" or path.endswith("/api/admin-feedback")):
            try:
                body_text = await request.text()
                data = json.loads(body_text) if body_text else {}

                if data.get("password") != "6789":
                    return Response(json.dumps({"success": False, "error": "Unauthorized: Invalid Password"}), status=401, headers={"Content-Type": "application/json"})

                db = getattr(env, "FEEDBACK_DB", None) or getattr(env, "DB", None)
                if not db:
                    return Response(json.dumps({"success": False, "error": "Database binding missing"}), status=500, headers={"Content-Type": "application/json"})

                stmt = db.prepare("SELECT * FROM sangaat_feedback ORDER BY created_at DESC")
                res = await stmt.all()

                rows = res.results.to_py() if hasattr(res.results, "to_py") else list(res.results)

                return Response(json.dumps({"success": True, "data": rows}), headers={"Content-Type": "application/json"})
            except Exception as e:
                return Response(json.dumps({"success": False, "error": str(e)}), status=500, headers={"Content-Type": "application/json"})

        # -------------------------------------------------------------
        # 4. ADMIN DELETE FEEDBACK: POST /api/delete-feedback
        # -------------------------------------------------------------
        if method == "POST" and (path == "/api/delete-feedback" or path.endswith("/api/delete-feedback")):
            try:
                body_text = await request.text()
                data = json.loads(body_text) if body_text else {}

                if data.get("password") != "6789":
                    return Response(json.dumps({"success": False, "error": "Unauthorized: Invalid Password"}), status=401, headers={"Content-Type": "application/json"})

                record_id = data.get("id")
                if not record_id:
                    return Response(json.dumps({"success": False, "error": "Missing record ID"}), status=400, headers={"Content-Type": "application/json"})

                db = getattr(env, "FEEDBACK_DB", None) or getattr(env, "DB", None)
                if not db:
                    return Response(json.dumps({"success": False, "error": "Database binding missing"}), status=500, headers={"Content-Type": "application/json"})

                query = "DELETE FROM sangaat_feedback WHERE id = ?"
                await db.prepare(query).bind(record_id).run()

                return Response(json.dumps({"success": True, "message": "Feedback deleted successfully"}), headers={"Content-Type": "application/json"})
            except Exception as e:
                return Response(json.dumps({"success": False, "error": str(e)}), status=500, headers={"Content-Type": "application/json"})

        # -------------------------------------------------------------
        # 5. PUBLIC TESTIMONIALS ENDPOINT: GET /api/testimonials
        # -------------------------------------------------------------
        if method == "GET" and (path == "/api/testimonials" or path.endswith("/api/testimonials")):
            try:
                db = getattr(env, "FEEDBACK_DB", None) or getattr(env, "DB", None)
                if not db:
                    return Response(json.dumps({"success": False, "error": "Database binding missing"}), status=500, headers={"Content-Type": "application/json"})

                stmt = db.prepare(
                    "SELECT id, session_name, rating, learnt_new, touched_comment, encouragement_comment, created_at "
                    "FROM sangaat_feedback ORDER BY created_at DESC"
                )
                res = await stmt.all()
                rows = res.results.to_py() if hasattr(res.results, "to_py") else list(res.results)

                return Response(
                    json.dumps({"success": True, "testimonials": rows}),
                    headers={
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*"
                    }
                )
            except Exception as e:
                return Response(json.dumps({"success": False, "error": str(e)}), status=500, headers={"Content-Type": "application/json"})

        # -------------------------------------------------------------
        # 6. SUBMIT SCORE: POST /api/submit_score
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
        # 7. DELETE SCORE: POST /api/delete_score
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
        # 8. RESET LEADERBOARD: POST /api/reset_leaderboard
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
        # 9. DISPLAY LEADERBOARD: GET /leaderboard
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
                is_global_selected = 'selected' if requested_group == "GLOBAL" else ''
                dropdown_options += f'<option value="GLOBAL" {is_global_selected}>Global (All Scores)</option>'

                for g in existing_groups:
                    if g and g.upper() != "GLOBAL":
                        is_selected = 'selected' if requested_group == g.upper() else ''
                        dropdown_options += f'<option value="{g}" {is_selected}>{g}</option>'

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
        <a id="playAgainBtn" href="/kbk" class="back-btn">&larr; Play Again</a>
    </div>

    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const group = urlParams.get('group');
        if (group && group !== 'GLOBAL') {
            document.getElementById('playAgainBtn').href = `/kbk?group=${encodeURIComponent(group)}`;
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
                headers: { 'Content-Type': "application/json" },
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
