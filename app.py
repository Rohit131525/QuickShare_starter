from __future__ import annotations

import ipaddress
import os
import secrets
import socket
from pathlib import Path
from datetime import datetime

from flask import Flask, request, session, redirect, url_for, render_template_string, flash
from werkzeug.utils import secure_filename

APP_NAME = "RShare"
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GiB per file for this first version
RECEIVE_DIR = Path.home() / "Downloads" / "RShare Received"
RECEIVE_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE + (10 * 1024 * 1024)
PAIRING_PIN = f"{secrets.randbelow(1_000_000):06d}"

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RShare</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 680px; margin: 32px auto; padding: 0 16px; color: #17202a; }
    .card { border: 1px solid #d7dce2; border-radius: 16px; padding: 22px; margin: 18px 0; }
    h1 { margin-bottom: 4px; } .muted { color: #566573; }
    input, button { font: inherit; padding: 10px; margin-top: 8px; }
    input[type=file] { display:block; width:100%; box-sizing:border-box; }
    button { border:0; border-radius:9px; background:#1769aa; color:white; cursor:pointer; }
    .pin { font-size: 1.8rem; letter-spacing: .15em; font-weight: 700; }
    .message { background:#edf7ed; padding:10px; border-radius:8px; margin:8px 0; }
    .error { background:#fff0f0; }
  </style>
</head>
<body>
  <h1>RShare</h1>
  <p class="muted">Send files from a phone or another device on your local Wi-Fi.</p>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
      <div class="message {{ 'error' if category == 'error' else '' }}">{{ message }}</div>
    {% endfor %}
  {% endwith %}
  {% if not paired %}
    <div class="card">
      <h2>Pair with this computer</h2>
      <p>Enter the six-digit PIN shown in the RShare receiver window.</p>
      <form method="post" action="{{ url_for('pair') }}">
        <label for="pin">Pairing PIN</label><br>
        <input id="pin" name="pin" inputted="numeric" pattern="[0-9]{6}" maxlength="6" required>
        <br><button type="submit">Pair device</button>
      </form>
    </div>
  {% else %}
    <div class="card">
      <h2>Send files</h2>
      <p class="muted">Files will be saved to <strong>Downloads/RShare Received</strong> on the computer.</p>
      <form method="post" action="{{ url_for('upload') }}" enctype="multipart/form-data">
        <input type="file" name="files" multiple required>
        <button type="submit">Send selected files</button>
      </form>
      <p class="muted">First version limit: 2 GiB per file. Keep both devices on a trusted private Wi-Fi network.</p>
      <form method="post" action="{{ url_for('unpair') }}"><button type="submit">Disconnect this browser</button></form>
    </div>
  {% endif %}
  <div class="card">
    <h3>Receiver status</h3>
    <p>Ready to receive files while this RShare window is running.</p>
  </div>
</body>
</html>
"""

def local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = item[4][0]
            if not ip.startswith("127."):
                addresses.add(ip)
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            ip = sock.getsockname()[0]
            if not ip.startswith("127."):
                addresses.add(ip)
    except OSError:
        pass
    return sorted(addresses)

@app.errorhandler(413)
def too_large(_error):
    flash("The upload is too large for this first version. Maximum file size is 2 GiB.", "error")
    return redirect(url_for("home")), 303

@app.get("/")
def home():
    return render_template_string(PAGE, paired=session.get("paired") is True)

@app.post("/pair")
def pair():
    supplied = request.form.get("pin", "").strip()
    if secrets.compare_digest(supplied, PAIRING_PIN):
        session["paired"] = True
        flash("This browser is paired with QuickShare.", "success")
    else:
        flash("Incorrect PIN. Check the PIN shown on the receiver computer.", "error")
    return redirect(url_for("home"))

@app.post("/unpair")
def unpair():
    session.clear()
    flash("This browser has been disconnected.", "success")
    return redirect(url_for("home"))

@app.post("/upload")
def upload():
    if session.get("paired") is not True:
        flash("Pair this browser before sending files.", "error")
        return redirect(url_for("home"))

    files = request.files.getlist("files")
    if not files or all(not item.filename for item in files):
        flash("Choose at least one file.", "error")
        return redirect(url_for("home"))

    saved = 0
    for item in files:
        if not item.filename:
            continue
        safe_name = secure_filename(Path(item.filename).name)
        if not safe_name:
            safe_name = "received-file"
        destination = RECEIVE_DIR / safe_name
        if destination.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            destination = RECEIVE_DIR / f"{destination.stem}_{stamp}{destination.suffix}"
        # Save directly to the receiver folder; the browser filename is sanitized.
        item.save(destination)
        saved += 1

    flash(f"Received {saved} file(s).", "success")
    return redirect(url_for("home"))

def main():
    addresses = local_ipv4_addresses()
    print("\n" + "=" * 52)
    print("QuickShare receiver is starting")
    print(f"Pairing PIN: {PAIRING_PIN}")
    print(f"Save folder: {RECEIVE_DIR}")
    if addresses:
        print("Open one of these addresses on your phone:")
        for address in addresses:
            print(f"  http://{address}:8765")
    else:
        print("Could not detect your Wi-Fi IP automatically.")
        print("Run ipconfig in PowerShell and use your IPv4 address:")
        print("  http://YOUR-PC-IP:8765")
    print("\nOnly use this first version on a trusted private Wi-Fi network.")
    print("Do not forward port 8765 to the internet. Press Ctrl+C to stop.")
    print("=" * 52 + "\n")
    # LAN access is needed for the phone to connect. Flask's development server
    # is acceptable only for this local prototype, not for public deployment.
    app.run(host="0.0.0.0", port=8765, debug=False, threaded=True)

if __name__ == "__main__":
    main()
