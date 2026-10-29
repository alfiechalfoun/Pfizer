# UAT Untangled — collaborative Pfizer challenge prototype

Three pages, **one shared SQLite database**:

- **Tester:** submit feedback and see report status
- **Manager:** review, edit, approve or dismiss suggested tickets
- **Developer:** see approved tickets, update progress, add developer notes

Rule-based categorisation and possible-duplicate suggestions are included. No external AI API or paid service is required.

## Start in VS Code (Mac / Windows / Linux)

1. Open this **whole folder** in VS Code.
2. Open VS Code > Terminal > New Terminal.
3. Run: `python3 server.py` (Mac/Linux) or `py server.py` (Windows).
4. In your browser, visit:
   - http://localhost:8000/tester
   - http://localhost:8000/manager
   - http://localhost:8000/developer

**Don't use Live Server** for this project. Run `server.py`, which handles the database and API.

The shared database is created automatically as `uat_data.sqlite3` in this folder. It stays saved after the server restarts. Do not commit this database to a public GitHub repository.

## Test across two computers on the same trusted Wi-Fi

1. Start `server.py` on **one** computer (the host). Leave it running.
2. On that computer, find its local IP address (for example `192.168.1.42`). On macOS you can check System Settings > Wi-Fi > Details > TCP/IP. On Windows, run `ipconfig`.
3. On a second computer on the **same network**, visit `http://192.168.1.42:8000/tester` (replace that IP with the host computer's actual address). Manager and Developer use `/manager` and `/developer`.
4. If connections fail, check the host firewall and whether the network isolates devices. Do not expose the port to the public internet.

The host machine must remain awake and running. All users share the same database, located **only on the host computer**.

## Different locations / internet access

To use this from different networks, **deploy the Python server on a trusted web host with HTTPS and real login/role-based access controls**. This student demo intentionally has **no authentication**, so anyone who can reach its URL can read and change reports. Do not make it publicly accessible as-is or submit real sensitive/company/health information.

For production, use a real deployment (for example a hosted Python service + managed database), secret management, HTTPS, proper account/role permissions, auditing and backups. SQLite is appropriate for a small single-server student demonstration, not an automatically shared cloud database.

## Files

- `server.py`: HTTP API, rules and SQLite persistence
- `templates/tester.html`: tester page
- `templates/manager.html`: manager page
- `templates/developer.html`: developer page
- `static/style.css`: common styling
- `static/app.js`: browser logic shared by all three pages

The duplicate suggestion highlights possible overlap **without deleting the new feedback**; a manager can confirm whether it is truly a duplicate. Decisions and updates are saved to SQLite. This is a demo of a human-in-the-loop workflow, not an official Pfizer app.
