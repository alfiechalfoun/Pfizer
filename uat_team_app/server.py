"""UAT Untangled demo server: shared SQLite data, Python standard library only.

Run: python3 server.py
Demo only: no login/role enforcement; do not put on the public internet.
"""
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('UAT_DB_PATH', ROOT / 'uat_data.sqlite3'))
LOCK = threading.RLock()
PORT = int(os.environ.get('PORT', '8000'))
HOST = os.environ.get('HOST', '0.0.0.0')


def connect():
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=20000')
    return db


def init_db():
    with connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tester TEXT NOT NULL,
                area TEXT NOT NULL,
                message TEXT NOT NULL,
                expected TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Needs review',
                duplicate_of INTEGER,
                notes TEXT NOT NULL DEFAULT '',
                ticket TEXT NOT NULL DEFAULT '',
                developer_notes TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                at TEXT NOT NULL
            );
        ''')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def terms(text):
    replacements = [(r'\b(sign[ -]?in|log[ -]?in|log[ -]?on)\b', 'login'),
                    (r"\b(can't|cannot|unable to|won't)\b", 'cannot'),
                    (r'\b(download\w*|export\w*)\b', 'export'),
                    (r"\b(doesn't work|not working|broken|fail\w*)\b", 'fail')]
    text = text.lower()
    for pat, replacement in replacements:
        text = re.sub(pat, replacement, text)
    stop = {'the','and','when','with','that','this','for','not','can','from','should','does','have','after','then','was','were','are','but','you','its','too','also','just','what','which','would','could','there','their','they','them','into','been','being','had','has','did','able'}
    return {w for w in re.findall(r'[a-z0-9]+', text) if len(w)>2 and w not in stop}


def similarity(a, b):
    x, y = terms(a), terms(b)
    return len(x & y) / ((len(x)*len(y))**0.5) if x and y else 0.0


def classify(message, expected):
    t = (message + ' ' + expected).lower()
    bug = r"error|crash|fail|broken|doesn't|does not|cannot|can't|incorrect|wrong|blank|stuck|freeze|unresponsive|missing|404|500|not working|unable|bug|issue|duplicate charge"
    question = r'\?|how do|where can|why does|is it possible|what is'
    improvement = r'could|would be nice|suggest|improve|enhancement|wish|feature request|better|add a|option to|useful'
    kind = 'Bug' if re.search(bug,t) else 'Question' if re.search(question,t) else 'Improvement' if re.search(improvement,t) else 'Needs classification'
    priority = 'High' if re.search(r"crash|data loss|security|expos|cannot login|can't login|payment|blocked|outage|critical",t) else 'Low' if re.search(r'colour|color|spacing|typo|alignment|minor|cosmetic',t) else 'Medium'
    return kind, priority


def ticket_draft(item):
    return f'''[{item['type']}] {item['area']}: {item['message'][:65]}

Category: {item['type']}
Priority: {item['priority']}
Reported by: {item['tester']}

Observed behaviour:
{item['message']}

Expected behaviour:
{item['expected'] or 'Not provided — confirm with tester.'}

Steps to reproduce:
1. Open {item['area']}.
2. Follow the tester's reported interaction (exact steps need confirmation).
3. Check whether the reported behaviour occurs.

Acceptance criteria:
- A reviewer confirms the expected behaviour.
- The issue is resolved or the request is addressed.
- The tester verifies the result.
'''


def get_reports():
    with connect() as db:
        reports = [dict(row) for row in db.execute('SELECT * FROM reports ORDER BY id DESC')]
        activity = [dict(row) for row in db.execute('SELECT * FROM activity ORDER BY id DESC LIMIT 40')]
    return {'reports': reports, 'activity': activity}


def update_report(report_id, payload):
    action = payload.get('action')
    with LOCK, connect() as db:
        row = db.execute('SELECT * FROM reports WHERE id=?', (report_id,)).fetchone()
        if not row:
            raise ValueError('Report not found')
        status = row['status']
        changes = {}
        if action == 'review':
            if status in ('Duplicate','Dismissed'):
                raise ValueError('Restore the report before reviewing it')
            for key, choices in (('type', ('Bug','Question','Improvement','Needs classification')),
                                 ('priority', ('High','Medium','Low'))):
                val = payload.get(key, row[key])
                if val not in choices:
                    raise ValueError('Invalid ' + key)
                changes[key] = val
            changes['ticket'] = clean(payload.get('ticket', row['ticket']), 15000)
            changes['notes'] = clean(payload.get('notes', row['notes']), 3000)
            next_status = payload.get('status', status)
            if next_status not in ('Needs review','Approved','Dismissed'):
                raise ValueError('Invalid status')
            changes['status'] = next_status
            if next_status == 'Dismissed':
                # Return linked duplicates to review rather than orphaning them.
                db.execute("UPDATE reports SET status='Needs review', duplicate_of=NULL,updated=? WHERE duplicate_of=?", (now(),report_id))
        elif action == 'restore':
            if status != 'Duplicate':
                raise ValueError('Only duplicates can be restored')
            changes = {'status': 'Needs review', 'duplicate_of': None}
        elif action == 'developer':
            if status not in ('Approved', 'In progress', 'Resolved'):
                raise ValueError('Manager must approve the ticket first')
            next_status = payload.get('status')
            if next_status not in ('Approved','In progress','Resolved'):
                raise ValueError('Invalid developer status')
            changes = {'status': next_status,
                       'developer_notes': clean(payload.get('developer_notes', ''), 3000)}
        else:
            raise ValueError('Invalid action')
        changes['updated'] = now()
        db.execute('UPDATE reports SET ' + ','.join(f'{k}=?' for k in changes) + ' WHERE id=?', (*changes.values(), report_id))
        db.execute('INSERT INTO activity(report_id,action,at) VALUES(?,?,?)', (report_id,action + ': ' + changes['status'],now()))
        db.commit()
    return {'ok': True}


def clean(value, maximum):
    if not isinstance(value,str):
        raise ValueError('Expected text')
    return value.strip()[:maximum]


def add_report(payload):
    tester, area, message, expected = [clean(payload.get(k, ''), n) for k,n in [('tester',80),('area',100),('message',5000),('expected',2000)]]
    if not tester or not area or len(message)<8:
        raise ValueError('Tester, feature and a description (8+ characters) are required')
    kind, priority = classify(message, expected)
    with LOCK, connect() as db:
        matches = []
        for r in db.execute("SELECT * FROM reports WHERE status NOT IN ('Dismissed','Duplicate')"):
            if area.lower() == r['area'].lower():
                score = similarity(message,r['message'])
                if score >= .2:
                    matches.append((score,r['id']))
        matches.sort(reverse=True)
        # Avoid auto-discarding important reports: mark possible duplicates for manager review.
        duplicate_of = matches[0][1] if matches and matches[0][0] >= .3 else None
        status = 'Possible duplicate' if duplicate_of else 'Needs review'
        timestamp = now()
        item = dict(tester=tester,area=area,message=message,expected=expected,type=kind,priority=priority)
        cur = db.execute('''INSERT INTO reports(tester,area,message,expected,type,priority,status,duplicate_of,ticket,created,updated)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (tester,area,message,expected,kind,priority,status,duplicate_of,ticket_draft(item),timestamp,timestamp))
        new_id = cur.lastrowid
        db.execute('INSERT INTO activity(report_id,action,at) VALUES(?,?,?)', (new_id,'Tester submitted feedback',timestamp))
        db.commit()
    return {'ok':True,'id':new_id,'status':status}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content, mime='application/json'):
        content = content.encode('utf-8') if isinstance(content,str) else content
        self.send_response(status)
        self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith(('text/','application/json')) else ''))
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(content)

    def json(self, status, obj):
        self.send(status, json.dumps(obj,ensure_ascii=False))

    def do_GET(self):
        path = urlsplit(self.path).path
        pages = {'/':'tester.html','/tester':'tester.html','/manager':'manager.html','/developer':'developer.html'}
        if path == '/api/reports':
            return self.json(200,get_reports())
        filename = pages.get(path)
        if filename:
            filepath = ROOT / 'templates' / filename
            return self.send(200,filepath.read_bytes(),'text/html')
        assets = {'/static/style.css':'style.css','/static/app.js':'app.js'}
        if path in assets:
            ext = 'text/css' if path.endswith('.css') else 'text/javascript'
            return self.send(200,(ROOT/'static'/assets[path]).read_bytes(),ext)
        return self.json(404,{'error':'Not found'})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path != '/api/reports' and not re.fullmatch(r'/api/reports/\d+',path):
            return self.json(404,{'error':'Not found'})
        try:
            length = int(self.headers.get('Content-Length','0'))
            if length > 50000:
                return self.json(413,{'error':'Request too large'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data,dict):
                raise ValueError('Invalid request')
            result = add_report(data) if path == '/api/reports' else update_report(int(path.rsplit('/',1)[1]),data)
            return self.json(200,result)
        except (ValueError,TypeError,json.JSONDecodeError) as exc:
            return self.json(400,{'error':str(exc)})


if __name__=='__main__':
    init_db()
    print(f'UAT Untangled: http://localhost:{PORT}/tester')
    print(f'Manager:       http://localhost:{PORT}/manager')
    print(f'Developer:     http://localhost:{PORT}/developer')
    print('Demo has NO AUTHENTICATION. Keep it on a trusted local network only.')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
