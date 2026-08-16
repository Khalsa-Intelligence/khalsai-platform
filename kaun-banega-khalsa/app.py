import socket
import io
import base64
import json
import os
import time
from flask import Flask, render_template_string, send_file, request, jsonify
import qrcode

app = Flask(__name__)
LEADERBOARD_FILE = 'leaderboard.json'

# Helper to load scores from local disk
def load_scores():
    if os.path.exists(LEADERBOARD_FILE):
        try:
            with open(LEADERBOARD_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []

# Helper to save scores to local disk
def save_score(player_data):
    scores = load_scores()
    # Assign a unique timestamp/id if not present to distinguish identical names
    if 'id' not in player_data:
        player_data['id'] = int(time.time() * 1000)
        
    scores.append(player_data)
    # Sort descending by Level reached, then by Score
    scores = sorted(scores, key=lambda x: (x.get('level', 0), x.get('score', 0)), reverse=True)
    with open(LEADERBOARD_FILE, 'w') as f:
        json.dump(scores, f, indent=2)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def generate_qr_base64(data):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')

# Landing / QR Start Screen
@app.route('/')
def index():
    local_ip = get_local_ip()
    port = 5000
    target_url = f"http://{local_ip}:{port}/game"
    qr_b64 = generate_qr_base64(target_url)

    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Kaun Banega Khalsa v2 Host</title>
        <style>
            body { font-family: sans-serif; background: #0d1117; color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
            .card { background: #161b22; padding: 2rem; border-radius: 12px; text-align: center; border: 1px solid #30363d; width: 90%; max-width: 400px; }
            .qr-container { background: #fff; padding: 10px; border-radius: 8px; display: inline-block; margin: 1rem 0; }
            .qr-container img { width: 200px; height: 200px; display: block; }
            .btn { display: inline-block; padding: 10px 20px; color: #fff; background: #238636; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 0.5rem; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Kaun Banega Khalsa</h2>
            <p>A Khalsa Intelligence Initiative</p>
            <p>Scan to join on mobile:</p>
            <p>{ GSW WoolwichSE18 }</p>
            <div class="qr-container">
                <img src="data:image/png;base64,""" + qr_b64 + """" alt="QR Code">
            </div>
            <br>
            <a href="/game" class="btn">Play Here</a> | 
            <a href="/leaderboard" class="btn" style="background:#1f6feb;">View Leaderboard</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_template)

# Serve the Main Game File
@app.route('/game')
def game():
    return send_file('Kaun Banega Khalsa v2.html')

# API Route: Save Player Score from Browser
@app.route('/api/submit_score', methods=['POST'])
def submit_score():
    data = request.json
    if not data or 'name' not in data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400
    
    save_score(data)
    return jsonify({"status": "success", "message": "Score saved to local machine!"})

# API Route: Reset / Clear entire leaderboard (Password Protected)
@app.route('/api/reset_leaderboard', methods=['POST'])
def reset_leaderboard():
    data = request.get_json() or {}
    if data.get('password') != '6789':
        return jsonify({"status": "error", "message": "Incorrect password."}), 403

    with open(LEADERBOARD_FILE, 'w') as f:
        json.dump([], f)
    return jsonify({"status": "success", "message": "Leaderboard reset successfully."})

# API Route: Delete a specific player entry by unique ID (Password Protected)
@app.route('/api/delete_score', methods=['POST'])
def delete_score():
    data = request.get_json()
    if data.get('password') != '6789':
        return jsonify({"status": "error", "message": "Incorrect password."}), 403

    target_id = data.get('id')
    
    if os.path.exists(LEADERBOARD_FILE):
        with open(LEADERBOARD_FILE, 'r') as f:
            leaderboard = json.load(f)
            
        # Filter out strictly the entry matching the unique record ID
        leaderboard = [entry for entry in leaderboard if entry.get('id') != target_id]
        
        with open(LEADERBOARD_FILE, 'w') as f:
            json.dump(leaderboard, f, indent=4)
            
        return jsonify({"status": "success", "message": "Entry deleted successfully."})
    
    return jsonify({"status": "error", "message": "Leaderboard file not found."}), 404

# Ranked Leaderboard Display Route
@app.route('/leaderboard')
def leaderboard():
    scores = load_scores()
    
    rows_html = ""
    for rank, entry in enumerate(scores, 1):
        name = entry.get('name', 'Anonymous')
        age = entry.get('age', '-')
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
            <a href="/game" class="back-btn">← Play Again</a>
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
    return render_template_string(html)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
