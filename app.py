# -*- coding: utf-8 -*-
"""성장하는 도시를 위한 도시계획 — 원고 검수 웹서비스 (Flask backend).

기능: 이메일 로그인 / 역할(관리자·집필자·감수) / 원고 본문·이미지 열람 / 메모(코멘트).
실행: python3 app.py   →  http://localhost:8000
배포: gunicorn -w 4 -b 0.0.0.0:8000 app:app
"""
import os, json, sqlite3, secrets, datetime, time, copy, io, base64
from functools import wraps
from flask import (Flask, request, session, jsonify, send_from_directory,
                   render_template, g, abort, redirect, send_file)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH', os.path.join(HERE, 'book.db'))   # local SQLite file
DATABASE_URL = os.environ.get('DATABASE_URL')   # set → use Postgres (Neon) in cloud
IS_PG = bool(DATABASE_URL)
DATA = os.path.join(HERE, 'data.json')
SECRET_FILE = os.path.join(HERE, 'secret.key')
PUBLIC = os.environ.get('PUBLIC', '0') == '1'   # 외부 공개(HTTPS) 모드 → Secure 쿠키
REG_OPEN = os.environ.get('REG_OPEN', '1') == '1'  # 감수자 자가가입 허용 여부
if IS_PG:
    import psycopg2, psycopg2.extras

app = Flask(__name__, static_folder='static', template_folder='templates')
# behind cloudflare / render / tunnel proxy: trust 1 hop for scheme/host/ip
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
# secret key: env (stable across cloud deploys) → file → generated
if os.environ.get('SECRET_KEY'):
    app.secret_key = os.environ['SECRET_KEY']
elif os.path.exists(SECRET_FILE):
    app.secret_key = open(SECRET_FILE).read().strip()
else:
    k = secrets.token_hex(32)
    try: open(SECRET_FILE, 'w').write(k)
    except OSError: pass
    app.secret_key = k
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  SESSION_COOKIE_SECURE=PUBLIC, MAX_CONTENT_LENGTH=16 * 1024 * 1024,
                  PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=14))

# --- simple in-memory login rate limiter (brute-force 완화) ---
_login_fails = {}
def _client_ip():
    return request.remote_addr or 'unknown'
def _rl_ok(ip):
    now = time.time(); arr = [t for t in _login_fails.get(ip, []) if now - t < 300]
    _login_fails[ip] = arr
    return len(arr) < 8   # 5분 내 8회 실패 시 차단
def _rl_fail(ip):
    _login_fails.setdefault(ip, []).append(time.time())

ROLES = {'superadmin': '수퍼관리자', 'admin': '관리자', 'author': '집필자', 'reviewer': '감수자'}
ADMIN_ROLES = ('admin', 'superadmin')   # 관리자급
# 4개 서브시스템: code -> (국문, 영문, 상태)  status: 'open'|'soon'|'link'
SYSTEMS = {
    'worldcities':   ('세계도시 연구 데이터베이스', 'World Cities Research Database', 'open'),
    'urbanrobotics': ('도시로봇·HRI 연구 데이터베이스', 'Urban Robotics & HRI Research Database', 'open'),
    'wpsc':   ('세계대도시협력', 'World Metropolitan Cooperation', 'link'),
    'book':   ('영문단행본 「성장하는 도시를 위한 도시계획」', 'Urban Planning for Growing Cities', 'open'),
}
# 연구 DB 서브시스템 ↔ 라우트/페이지 매핑
DB_SUBSYSTEMS = {'worldcities', 'urbanrobotics'}
BOOK = json.load(open(DATA, encoding='utf-8'))

# ---------------- DB (SQLite local / Postgres cloud) ----------------
class DB:
    """Thin wrapper so the same `?`-placeholder SQL runs on both backends.
    Rows support positional (row[0]) and key (row['col']) access on both."""
    def __init__(self):
        if IS_PG:
            kw = {}
            if 'sslmode=' not in DATABASE_URL:
                kw['sslmode'] = os.environ.get('PGSSLMODE', 'require')
            self.conn = psycopg2.connect(DATABASE_URL, **kw)
        else:
            self.conn = sqlite3.connect(DB_PATH); self.conn.row_factory = sqlite3.Row
    def execute(self, sql, params=()):
        if IS_PG:
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(sql.replace('?', '%s'), params)
            return cur
        return self.conn.execute(sql, params)
    def insert(self, sql, params=()):
        """INSERT and return the new row id (both backends)."""
        if IS_PG:
            cur = self.conn.cursor()
            cur.execute(sql.replace('?', '%s') + ' RETURNING id', params)
            return cur.fetchone()[0]
        return self.conn.execute(sql, params).lastrowid
    def commit(self): self.conn.commit()
    def rollback(self):
        try: self.conn.rollback()
        except Exception: pass
    def close(self): self.conn.close()

def db():
    if 'db' not in g: g.db = DB()
    return g.db

@app.teardown_appcontext
def _close(exc):
    d = g.pop('db', None)
    if d: d.close()

# 집필진·감수진 (위 배정표 기준). 로그인 ID = 이름, 초기 비밀번호 123456.
AUTHORS = [
    ('권원용', '서장 소개말'),
    ('강명구', '1장 20세기 중반 · 2장 밀도 · 3장 중심 · 15장 거버넌스 · 종장 맺음말'),
    ('유영호', '4장 가로 · 5장 공공교통 · 6장 공공공간 · 7장 자연공간'),
    ('이동건', '8장 물'),
    ('류예승', '9장 쓰레기 · 10장 에너지 · 11장 홍수·가뭄'),
    ('전백찬', '12장 경제 · 13장 동네 · 14장 주거'),
    ('최준영', '16장 도시계획 정보체계와 전자정부'),
]
REVIEWERS = [
    ('김상일', '서장 소개말 · 3장 중심'), ('김학진', '1장 20세기 중반'),
    ('이주일', '2장 밀도 · 15장 거버넌스'), ('이창', '4장 가로'),
    ('고준호', '5장 공공교통'), ('최창규', '6장 공공공간'),
    ('김형규', '7장 자연공간'), ('최영준', '8장 물 · 11장 홍수·가뭄'),
    ('유기영', '9장 쓰레기'), ('방설아', '10장 에너지'),
    ('김묵한', '12장 경제'), ('양재섭', '13장 동네'),
    ('김광중', '14장 주거'), ('최봉문', '16장 정보체계'),
    ('이인근', '종장 맺음말'),
]
# 배정표 → 장(order) 목록. order: 0=서장,1~16=장,17=종장
ASSIGN_SEED = {
    '권원용': [0], '강명구': [1, 2, 3, 15, 17], '유영호': [4, 5, 6, 7], '이동건': [8],
    '류예승': [9, 10, 11], '전백찬': [12, 13, 14], '최준영': [16],
    '김상일': [0, 3], '김학진': [1], '이주일': [2, 15], '이창': [4], '고준호': [5],
    '최창규': [6], '김형규': [7], '최영준': [8, 11], '유기영': [9], '방설아': [10],
    '김묵한': [12], '양재섭': [13], '김광중': [14], '최봉문': [16], '이인근': [17],
}

def init_db():
    con = DB()
    if IS_PG:
        con.execute('''CREATE TABLE IF NOT EXISTS users(
          email TEXT PRIMARY KEY, name TEXT, role TEXT, pw TEXT, created TEXT, assigned TEXT)''')
        con.execute('''CREATE TABLE IF NOT EXISTS comments(
          id SERIAL PRIMARY KEY, chapter INTEGER, block TEXT, anchor TEXT, body TEXT,
          email TEXT, name TEXT, role TEXT, created TEXT, resolved INTEGER DEFAULT 0,
          parent_id INTEGER)''')
    else:
        con.conn.executescript('''
        CREATE TABLE IF NOT EXISTS users(
          email TEXT PRIMARY KEY, name TEXT, role TEXT, pw TEXT, created TEXT, assigned TEXT);
        CREATE TABLE IF NOT EXISTS comments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          chapter INTEGER, block TEXT, anchor TEXT, body TEXT,
          email TEXT, name TEXT, role TEXT, created TEXT, resolved INTEGER DEFAULT 0,
          parent_id INTEGER);''')
        cols = [r[1] for r in con.execute('PRAGMA table_info(comments)')]
        if 'parent_id' not in cols:
            con.execute('ALTER TABLE comments ADD COLUMN parent_id INTEGER')
    # 권한 배정 / 본문 편집 오버라이드 / 편집 로그
    if IS_PG:
        con.execute('CREATE TABLE IF NOT EXISTS assignments(email TEXT, chapter INTEGER, PRIMARY KEY(email,chapter))')
        con.execute('''CREATE TABLE IF NOT EXISTS overrides(
          chapter INTEGER, blk INTEGER, value TEXT, editor TEXT, ts TEXT, PRIMARY KEY(chapter,blk))''')
        con.execute('''CREATE TABLE IF NOT EXISTS editlog(
          id SERIAL PRIMARY KEY, chapter INTEGER, blk INTEGER, oldv TEXT, newv TEXT,
          editor TEXT, name TEXT, role TEXT, ts TEXT, undone INTEGER DEFAULT 0)''')
        con.execute('CREATE TABLE IF NOT EXISTS chorder(chapter INTEGER PRIMARY KEY, seq TEXT)')
        con.execute('''CREATE TABLE IF NOT EXISTS images(
          id SERIAL PRIMARY KEY, chapter INTEGER, blk INTEGER, mime TEXT, data TEXT, editor TEXT, ts TEXT)''')
        con.execute('''CREATE TABLE IF NOT EXISTS dbrecords(
          id SERIAL PRIMARY KEY, subsystem TEXT, kind TEXT, slug TEXT, title TEXT, data TEXT,
          updated TEXT, UNIQUE(subsystem, slug))''')
        try: con.execute('ALTER TABLE editlog ADD COLUMN IF NOT EXISTS undone INTEGER DEFAULT 0'); con.commit()
        except Exception: con.rollback()
    else:
        con.conn.executescript('''
          CREATE TABLE IF NOT EXISTS assignments(email TEXT, chapter INTEGER, PRIMARY KEY(email,chapter));
          CREATE TABLE IF NOT EXISTS overrides(chapter INTEGER, blk INTEGER, value TEXT, editor TEXT, ts TEXT, PRIMARY KEY(chapter,blk));
          CREATE TABLE IF NOT EXISTS editlog(id INTEGER PRIMARY KEY AUTOINCREMENT, chapter INTEGER, blk INTEGER,
            oldv TEXT, newv TEXT, editor TEXT, name TEXT, role TEXT, ts TEXT, undone INTEGER DEFAULT 0);
          CREATE TABLE IF NOT EXISTS chorder(chapter INTEGER PRIMARY KEY, seq TEXT);
          CREATE TABLE IF NOT EXISTS images(id INTEGER PRIMARY KEY AUTOINCREMENT, chapter INTEGER, blk INTEGER, mime TEXT, data TEXT, editor TEXT, ts TEXT);
          CREATE TABLE IF NOT EXISTS dbrecords(id INTEGER PRIMARY KEY AUTOINCREMENT, subsystem TEXT, kind TEXT,
            slug TEXT, title TEXT, data TEXT, updated TEXT, UNIQUE(subsystem, slug));''')
        if 'undone' not in [r[1] for r in con.execute('PRAGMA table_info(editlog)')]:
            con.execute('ALTER TABLE editlog ADD COLUMN undone INTEGER DEFAULT 0')
    # users.systems 컬럼(서브시스템 접근권한, 콤마구분 코드)
    try:
        if IS_PG: con.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS systems TEXT'); con.commit()
        elif 'systems' not in [r[1] for r in con.execute('PRAGMA table_info(users)')]:
            con.execute('ALTER TABLE users ADD COLUMN systems TEXT')
    except Exception: con.rollback()
    ignore = 'ON CONFLICT (email) DO NOTHING' if IS_PG else 'OR IGNORE'
    ins = ('INSERT OR IGNORE INTO users VALUES(?,?,?,?,?,?)' if not IS_PG
           else 'INSERT INTO users VALUES(?,?,?,?,?,?) ON CONFLICT (email) DO NOTHING')
    if con.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        admin_id = os.environ.get('ADMIN_EMAIL', 'junyoung.choi@si.re.kr').lower()
        admin_pw = os.environ.get('ADMIN_PASSWORD', '2969')
        con.execute(ins, (admin_id, '관리자', 'admin', generate_password_hash(admin_pw), now(), '단행본 전체'))
        for name, assigned in AUTHORS:
            con.execute(ins, (name, name, 'author', generate_password_hash('123456'), now(), assigned))
        for name, assigned in REVIEWERS:
            con.execute(ins, (name, name, 'reviewer', generate_password_hash('123456'), now(), assigned))
        print(f'[seed] 관리자 {admin_id}/{admin_pw}, 집필 {len(AUTHORS)}명·감수 {len(REVIEWERS)}명 ({"PG" if IS_PG else "SQLite"})')
    # 배정 시드(비어 있을 때 1회)
    if con.execute('SELECT COUNT(*) FROM assignments').fetchone()[0] == 0:
        ains = ('INSERT INTO assignments VALUES(?,?) ON CONFLICT DO NOTHING' if IS_PG
                else 'INSERT OR IGNORE INTO assignments VALUES(?,?)')
        for email, chs in ASSIGN_SEED.items():
            for ch in chs:
                con.execute(ains, (email, ch))
    # systems 기본값: 수퍼관리자=전체, 그 외=book (비어 있는 계정만)
    allsys = ','.join(SYSTEMS.keys())
    con.execute("UPDATE users SET systems=? WHERE role='superadmin' AND (systems IS NULL OR systems='')", (allsys,))
    con.execute("UPDATE users SET systems='book' WHERE role<>'superadmin' AND (systems IS NULL OR systems='')")
    # 연구 DB(세계도시·도시로봇) 시드: dbrecords 비어 있을 때 1회
    try:
        seed_dbrecords(con)
    except Exception as e:
        print('[dbseed] skip:', e); con.rollback()
    con.commit(); con.close()

def seed_dbrecords(con):
    """세계도시·도시로봇 연구 DB 초기 데이터 적재(비어 있을 때만)."""
    import dbseed, json as _json
    n = con.execute('SELECT COUNT(*) FROM dbrecords').fetchone()[0]
    if n > 0: return
    ins = ('INSERT INTO dbrecords(subsystem,kind,slug,title,data,updated) VALUES(?,?,?,?,?,?) '
           + ('ON CONFLICT (subsystem,slug) DO NOTHING' if IS_PG else ''))
    if not IS_PG:
        ins = 'INSERT OR IGNORE INTO dbrecords(subsystem,kind,slug,title,data,updated) VALUES(?,?,?,?,?,?)'
    cnt = 0
    for rec in dbseed.RECORDS:
        con.execute(ins, (rec['subsystem'], rec['kind'], rec['slug'], rec['title'],
                          _json.dumps(rec['data'], ensure_ascii=False), now()))
        cnt += 1
    print(f'[dbseed] {cnt} records seeded ({"PG" if IS_PG else "SQLite"})')

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

# ---------------- auth helpers ----------------
def current():
    em = session.get('email')
    if not em: return None
    r = db().execute('SELECT email,name,role,assigned,systems FROM users WHERE email=?', (em,)).fetchone()
    return dict(r) if r else None

def user_systems(u):
    if u['role'] == 'superadmin': return list(SYSTEMS.keys())
    return [s for s in (u.get('systems') or '').split(',') if s in SYSTEMS]

def can_access_system(u, sys):
    return u['role'] == 'superadmin' or sys in user_systems(u)

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not current(): return jsonify(error='로그인이 필요합니다.'), 401
        return f(*a, **k)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        u = current()
        if not u or u['role'] not in ADMIN_ROLES: return jsonify(error='관리자 권한이 필요합니다.'), 403
        return f(*a, **k)
    return w

def super_required(f):
    @wraps(f)
    def w(*a, **k):
        u = current()
        if not u or u['role'] != 'superadmin': return jsonify(error='수퍼관리자만 가능합니다.'), 403
        return f(*a, **k)
    return w

# ---------------- permissions ----------------
def assigned_chapters(email):
    return {r[0] for r in db().execute('SELECT chapter FROM assignments WHERE email=?', (email,)).fetchall()}

def can_view(u, ch):
    # 관리자급은 전체 열람, 집필자·감수자는 '배정된 장'만 열람
    if u['role'] in ADMIN_ROLES: return True
    return ch in assigned_chapters(u['email'])

def can_edit(u, ch):
    # 관리자급은 전체 편집, 집필자는 배정 장만, 감수자는 편집 불가
    if u['role'] in ADMIN_ROLES: return True
    if u['role'] == 'author': return ch in assigned_chapters(u['email'])
    return False

def block_field(b):
    if b['t'] == 'h': return 'kr'
    if b['t'] == 'img': return 'src'
    if b['t'] in ('p', 'cap', 'ref', 'note'): return 'text'
    return None

# ---------------- pages ----------------
@app.route('/')
def portal():
    return render_template('portal.html')

@app.route('/architecture')
@app.route('/about')
def architecture_page():
    return render_template('architecture.html')   # 공개(로그인 불필요) 아키텍처 안내

@app.route('/book')
def book_app():
    return render_template('index.html')   # 영문단행본 감수 시스템 SPA

@app.route('/wpsc')
def wpsc_page():
    u = current()
    if not u: return redirect('/?sys=wpsc')
    if not can_access_system(u, 'wpsc'): return redirect('/?denied=wpsc')
    return send_file(os.path.join(HERE, 'wpsc.html'))

@app.route('/worldcities')
@app.route('/world-cities')
def worldcities_page():
    u = current()
    if not u: return redirect('/?sys=worldcities')
    if not can_access_system(u, 'worldcities'): return redirect('/?denied=worldcities')
    return render_template('worldcities.html')

@app.route('/urbanrobotics')
@app.route('/urban-robotics')
def urbanrobotics_page():
    u = current()
    if not u: return redirect('/?sys=urbanrobotics')
    if not can_access_system(u, 'urbanrobotics'): return redirect('/?denied=urbanrobotics')
    return render_template('urbanrobotics.html')

@app.route('/static/img/<path:p>')
def img(p):
    return send_from_directory(os.path.join(HERE, 'static', 'img'), p)

# ---------------- research DB API (세계도시 · 도시로봇) ----------------
def _db_guard(subsystem):
    """연구 DB 접근 가드: 로그인 + 해당 서브시스템 권한. (u, error_response) 반환."""
    if subsystem not in DB_SUBSYSTEMS:
        return None, (jsonify(error='알 수 없는 데이터베이스입니다.'), 404)
    u = current()
    if not u: return None, (jsonify(error='로그인이 필요합니다.'), 401)
    if not can_access_system(u, subsystem):
        return None, (jsonify(error='접근 권한이 없습니다.'), 403)
    return u, None

def _load_records(subsystem):
    import json as _json
    rows = db().execute('SELECT id,kind,slug,title,data,updated FROM dbrecords WHERE subsystem=? ORDER BY kind,title',
                        (subsystem,)).fetchall()
    out = []
    for r in rows:
        d = dict(r); data = {}
        try: data = _json.loads(d['data'] or '{}')
        except Exception: data = {}
        rec = {'id': d['id'], 'kind': d['kind'], 'slug': d['slug'], 'title': d['title'], 'updated': d['updated']}
        rec.update(data)
        out.append(rec)
    return out

@app.get('/api/db/<subsystem>')
def db_list(subsystem):
    u, err = _db_guard(subsystem)
    if err: return err
    recs = _load_records(subsystem)
    kind = request.args.get('kind')
    q = (request.args.get('q') or '').strip().lower()
    counts = {}
    for r in recs: counts[r['kind']] = counts.get(r['kind'], 0) + 1
    if kind: recs = [r for r in recs if r['kind'] == kind]
    if q:
        def hit(r):
            blob = json.dumps(r, ensure_ascii=False).lower()
            return q in blob
        recs = [r for r in recs if hit(r)]
    meta = SYSTEMS[subsystem]
    return jsonify(subsystem=subsystem, kr=meta[0], en=meta[1], counts=counts, records=recs)

@app.get('/api/db/<subsystem>/<slug>')
def db_detail(subsystem, slug):
    u, err = _db_guard(subsystem)
    if err: return err
    recs = _load_records(subsystem)
    rec = next((r for r in recs if r['slug'] == slug), None)
    if not rec: return jsonify(error='항목을 찾을 수 없습니다.'), 404
    # 교차참조 해석: 같은 서브시스템 + worldcities↔urbanrobotics 상호 슬러그/제목 매핑
    allrecs = recs[:]
    try:
        other = 'urbanrobotics' if subsystem == 'worldcities' else 'worldcities'
        if can_access_system(u, other):
            allrecs += _load_records(other)
    except Exception: pass
    index = {r['slug']: {'slug': r['slug'], 'title': r['title'], 'kind': r['kind'], 'subsystem':
                         (subsystem if r in recs else ('urbanrobotics' if subsystem == 'worldcities' else 'worldcities'))}
             for r in allrecs}
    return jsonify(subsystem=subsystem, record=rec, index=index)

@app.post('/api/generate/<tool>')
@login_required
def db_generate(tool):
    import dbgen
    j = request.get_json(force=True) or {}
    fn = {'hri-study-design': dbgen.gen_hri_study_design,
          'observation-codebook': dbgen.gen_observation_codebook,
          'experiment-protocol': dbgen.gen_experiment_protocol}.get(tool)
    if not fn: return jsonify(error='알 수 없는 생성기입니다.'), 404
    try:
        md = fn(j)
    except Exception as e:
        return jsonify(error=f'생성 오류: {e}'), 400
    return jsonify(ok=True, markdown=md)

# ---------- 지식기반 적재(로컬 빌드 → 발행) ----------
def _upsert_record(con, rec):
    """dbrecords UPSERT(subsystem,slug 기준, 멱등). 반환: 'inserted'|'updated'|'skipped'."""
    import json as _json
    sub = rec.get('subsystem'); slug = rec.get('slug')
    if sub not in DB_SUBSYSTEMS or not slug:
        return 'skipped'
    kind = rec.get('kind'); title = rec.get('title') or slug
    data = rec.get('data')
    if not isinstance(data, dict): data = {}
    if rec.get('body') is not None and 'body' not in data:   # 서술형 위키 본문
        data['body'] = rec['body']
    payload = _json.dumps(data, ensure_ascii=False)
    ex = con.execute('SELECT id FROM dbrecords WHERE subsystem=? AND slug=?', (sub, slug)).fetchone()
    if ex:
        con.execute('UPDATE dbrecords SET kind=?,title=?,data=?,updated=? WHERE subsystem=? AND slug=?',
                    (kind, title, payload, now(), sub, slug))
        return 'updated'
    con.execute('INSERT INTO dbrecords(subsystem,kind,slug,title,data,updated) VALUES(?,?,?,?,?,?)',
                (sub, kind, slug, title, payload, now()))
    return 'inserted'

@app.post('/api/admin/import')
@super_required
def admin_import():
    """로컬 Obsidian 빌드 결과(records.json)를 발행. prune=true면 페이로드에 포함된
    서브시스템 한정으로 누락 슬러그를 삭제(전체 동기화)."""
    j = request.get_json(force=True) or {}
    recs = j.get('records')
    if not isinstance(recs, list):
        return jsonify(error="'records' 배열이 필요합니다."), 400
    con = db()
    res = {'inserted': 0, 'updated': 0, 'skipped': 0, 'deleted': 0}
    for rec in recs:
        try:
            res[_upsert_record(con, rec)] += 1
        except Exception:
            res['skipped'] += 1
    if j.get('prune'):
        from collections import defaultdict
        bysub = defaultdict(set)
        for rec in recs:
            if rec.get('subsystem') in DB_SUBSYSTEMS and rec.get('slug'):
                bysub[rec['subsystem']].add(rec['slug'])
        for sub, slugs in bysub.items():   # 페이로드에 등장한 서브시스템만 prune(빈 입력 전체삭제 방지)
            for row in con.execute('SELECT slug FROM dbrecords WHERE subsystem=?', (sub,)).fetchall():
                if row[0] not in slugs:
                    con.execute('DELETE FROM dbrecords WHERE subsystem=? AND slug=?', (sub, row[0]))
                    res['deleted'] += 1
    con.commit()
    return jsonify(ok=True, total=len(recs), **res)

@app.get('/api/admin/export')
@super_required
def admin_export():
    """현재 dbrecords 전체를 JSON으로 내보내기(백업·round-trip)."""
    import json as _json
    rows = db().execute('SELECT subsystem,kind,slug,title,data,updated FROM dbrecords ORDER BY subsystem,kind,slug').fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try: data = _json.loads(d['data'] or '{}')
        except Exception: data = {}
        out.append({'subsystem': d['subsystem'], 'kind': d['kind'], 'slug': d['slug'],
                    'title': d['title'], 'data': data, 'updated': d['updated']})
    return jsonify(records=out, count=len(out))

# ---------------- auth API ----------------
@app.post('/api/login')
def login():
    ip = _client_ip()
    if not _rl_ok(ip):
        return jsonify(error='로그인 시도가 너무 많습니다. 5분 후 다시 시도하세요.'), 429
    j = request.get_json(force=True)
    email = (j.get('email') or '').strip().lower()
    pw = j.get('password') or ''
    r = db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    if not r or not check_password_hash(r['pw'], pw):
        _rl_fail(ip)
        return jsonify(error='이메일/이름 또는 비밀번호가 올바르지 않습니다.'), 401
    system = j.get('system')   # 포털에서 선택한 서브시스템(선택)
    if system and system in SYSTEMS:
        u0 = dict(r)
        if r['role'] != 'superadmin' and system not in [s for s in (u0.get('systems') or '').split(',') if s]:
            return jsonify(error=f"'{SYSTEMS[system][0]}' 접근 권한이 없습니다."), 403
        session['system'] = system
    session.permanent = True; session['email'] = email
    return jsonify(ok=True, system=system, user={'email': r['email'], 'name': r['name'],
                                  'role': r['role'], 'roleName': ROLES.get(r['role'], r['role'])})

@app.post('/api/register')
def register():
    """집필자·감수자 자가 가입: 최초 1회 이메일·이름·비밀번호 설정."""
    if not REG_OPEN:
        return jsonify(error='자가 가입이 비활성화되어 있습니다. 관리자에게 계정을 요청하세요.'), 403
    j = request.get_json(force=True)
    email = (j.get('email') or '').strip().lower()
    name = (j.get('name') or '').strip()
    pw = j.get('password') or ''
    role = j.get('role', 'reviewer')
    if '@' not in email: return jsonify(error='올바른 이메일을 입력하세요.'), 400
    if not name: return jsonify(error='이름을 입력하세요.'), 400
    if len(pw) < 6: return jsonify(error='비밀번호는 6자 이상이어야 합니다.'), 400
    if role not in ('author', 'reviewer'): return jsonify(error='역할을 선택하세요(집필자·감수자).'), 400
    con = db()
    exists = con.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone()
    if exists:
        return jsonify(error='이미 등록된 이메일입니다. 로그인해 주세요.'), 400
    con.execute('INSERT INTO users VALUES(?,?,?,?,?,?)',
                (email, name, role, generate_password_hash(pw), now(), '')); con.commit()
    session.permanent = True; session['email'] = email
    return jsonify(ok=True, user={'email': email, 'name': name, 'role': role,
                                  'roleName': ROLES.get(role, role)})

@app.post('/api/logout')
def logout():
    session.clear(); return jsonify(ok=True)

@app.get('/api/me')
def me():
    u = current()
    if not u: return jsonify(user=None)
    u['roleName'] = ROLES.get(u['role'], u['role'])
    u['assigned'] = sorted(assigned_chapters(u['email']))
    u['canEditAny'] = (u['role'] in ADMIN_ROLES or u['role'] == 'author')
    u['isSuper'] = (u['role'] == 'superadmin')
    u['systems'] = user_systems(u)
    return jsonify(user=u, roles=ROLES)

@app.get('/api/systems')
def systems_list():
    return jsonify(systems={k: {'kr': v[0], 'en': v[1], 'status': v[2]} for k, v in SYSTEMS.items()})

@app.post('/api/password')
@login_required
def change_pw():
    j = request.get_json(force=True); u = current()
    old, new = j.get('old', ''), j.get('new', '')
    r = db().execute('SELECT pw FROM users WHERE email=?', (u['email'],)).fetchone()
    if not check_password_hash(r['pw'], old):
        return jsonify(error='현재 비밀번호가 올바르지 않습니다.'), 400
    if len(new) < 6: return jsonify(error='새 비밀번호는 6자 이상이어야 합니다.'), 400
    db().execute('UPDATE users SET pw=? WHERE email=?', (generate_password_hash(new), u['email'])); db().commit()
    return jsonify(ok=True)

# ---------------- book data ----------------
def load_overrides():
    return {(r['chapter'], r['blk']): r['value']
            for r in db().execute('SELECT chapter,blk,value FROM overrides').fetchall()}

def load_order():
    return {r['chapter']: json.loads(r['seq']) for r in db().execute('SELECT chapter,seq FROM chorder').fetchall()}

@app.get('/api/data')
@login_required
def data():
    u = current()
    ov = load_overrides(); orders = load_order()
    chs = []
    for c in BOOK['chapters']:
        if not can_view(u, c['order']): continue          # 감수자: 배정 장만
        n = len(c['content'])
        seq = orders.get(c['order'])
        if not seq: seq = list(range(n))
        else:                                              # 누락/초과 보정(원고 재추출 대비)
            seq = [i for i in seq if 0 <= i < n] + [i for i in range(n) if i not in set(seq)]
        cc = copy.deepcopy(c); cc['content'] = []
        for oi in seq:
            b = copy.deepcopy(c['content'][oi]); b['oi'] = oi
            key = (c['order'], oi)
            if key in ov:
                f = block_field(b)
                if f: b[f] = ov[key]; b['edited'] = True
            cc['content'].append(b)
        cc['canEdit'] = can_edit(u, c['order'])
        chs.append(cc)
    return jsonify({'chapters': chs, 'meta': BOOK['meta']})

@app.post('/api/order')
@login_required
def set_order():
    u = current(); j = request.get_json(force=True)
    ch = int(j.get('chapter', -1)); seq = [int(x) for x in j.get('order', [])]
    if not can_edit(u, ch): return jsonify(error='이 장을 편집할 권한이 없습니다.'), 403
    chap = next((c for c in BOOK['chapters'] if c['order'] == ch), None)
    if not chap: return jsonify(error='장을 찾을 수 없습니다.'), 404
    con = db()
    cur = con.execute('SELECT seq FROM chorder WHERE chapter=?', (ch,)).fetchone()
    oldseq = cur['seq'] if cur else json.dumps(list(range(len(chap['content']))))
    if IS_PG:
        con.execute('''INSERT INTO chorder(chapter,seq) VALUES(?,?)
                       ON CONFLICT (chapter) DO UPDATE SET seq=excluded.seq''', (ch, json.dumps(seq)))
    else:
        con.execute('INSERT OR REPLACE INTO chorder(chapter,seq) VALUES(?,?)', (ch, json.dumps(seq)))
    con.execute('INSERT INTO editlog(chapter,blk,oldv,newv,editor,name,role,ts) VALUES(?,?,?,?,?,?,?,?)',
                (ch, -1, oldseq, json.dumps(seq), u['email'], u['name'], u['role'], now()))
    con.commit()
    return jsonify(ok=True)

@app.post('/api/undo')
@login_required
def undo_edit():
    u = current(); j = request.get_json(force=True); ch = int(j.get('chapter', -1))
    if not can_edit(u, ch): return jsonify(error='권한이 없습니다.'), 403
    con = db()
    e = con.execute('SELECT * FROM editlog WHERE chapter=? AND undone=0 ORDER BY id DESC LIMIT 1', (ch,)).fetchone()
    if not e: return jsonify(ok=True, nothing=True, remaining=0)
    chap = next((c for c in BOOK['chapters'] if c['order'] == ch), None)
    if e['blk'] == -1:        # 순서 이동 되돌리기 → 이전 seq 복원
        oldseq = json.loads(e['oldv']) if e['oldv'] else list(range(len(chap['content'])))
        if oldseq == list(range(len(chap['content']))):
            con.execute('DELETE FROM chorder WHERE chapter=?', (ch,))
        elif IS_PG:
            con.execute('''INSERT INTO chorder(chapter,seq) VALUES(?,?)
                           ON CONFLICT (chapter) DO UPDATE SET seq=excluded.seq''', (ch, json.dumps(oldseq)))
        else:
            con.execute('INSERT OR REPLACE INTO chorder(chapter,seq) VALUES(?,?)', (ch, json.dumps(oldseq)))
    else:                     # 텍스트 편집 되돌리기 → 이전 값(원본이면 override 삭제)
        b = chap['content'][e['blk']] if chap and 0 <= e['blk'] < len(chap['content']) else None
        orig = b.get(block_field(b)) if b and block_field(b) else None
        if e['oldv'] == orig:
            con.execute('DELETE FROM overrides WHERE chapter=? AND blk=?', (ch, e['blk']))
        elif IS_PG:
            con.execute('''INSERT INTO overrides(chapter,blk,value,editor,ts) VALUES(?,?,?,?,?)
                           ON CONFLICT (chapter,blk) DO UPDATE SET value=excluded.value''',
                        (ch, e['blk'], e['oldv'], u['email'], now()))
        else:
            con.execute('INSERT OR REPLACE INTO overrides(chapter,blk,value,editor,ts) VALUES(?,?,?,?,?)',
                        (ch, e['blk'], e['oldv'], u['email'], now()))
    con.execute('UPDATE editlog SET undone=1 WHERE id=?', (e['id'],))
    con.commit()
    remaining = con.execute('SELECT COUNT(*) FROM editlog WHERE chapter=? AND undone=0', (ch,)).fetchone()[0]
    return jsonify(ok=True, remaining=remaining)

@app.get('/api/undocount')
@login_required
def undo_count():
    ch = int(request.args.get('chapter', -1))
    n = db().execute('SELECT COUNT(*) FROM editlog WHERE chapter=? AND undone=0', (ch,)).fetchone()[0]
    return jsonify(count=n)

@app.post('/api/edit')
@login_required
def edit_block():
    u = current(); j = request.get_json(force=True)
    ch = int(j.get('chapter', -1)); blk = int(j.get('blk', -1))
    val = (j.get('value') or '').strip()
    if not can_edit(u, ch):
        return jsonify(error='이 장을 편집할 권한이 없습니다.'), 403
    chap = next((c for c in BOOK['chapters'] if c['order'] == ch), None)
    if not chap or blk < 0 or blk >= len(chap['content']):
        return jsonify(error='대상 블록을 찾을 수 없습니다.'), 404
    b = chap['content'][blk]; f = block_field(b)
    if not f: return jsonify(error='편집할 수 없는 블록입니다.'), 400
    ov = load_overrides().get((ch, blk))
    oldv = ov if ov is not None else b[f]
    if val == oldv: return jsonify(ok=True, unchanged=True)
    con = db()
    if IS_PG:
        con.execute('''INSERT INTO overrides(chapter,blk,value,editor,ts) VALUES(?,?,?,?,?)
                       ON CONFLICT (chapter,blk) DO UPDATE SET value=excluded.value,editor=excluded.editor,ts=excluded.ts''',
                    (ch, blk, val, u['email'], now()))
    else:
        con.execute('INSERT OR REPLACE INTO overrides(chapter,blk,value,editor,ts) VALUES(?,?,?,?,?)',
                    (ch, blk, val, u['email'], now()))
    con.execute('INSERT INTO editlog(chapter,blk,oldv,newv,editor,name,role,ts) VALUES(?,?,?,?,?,?,?,?)',
                (ch, blk, oldv, val, u['email'], u['name'], u['role'], now()))
    con.commit()
    return jsonify(ok=True)

def _set_override(con, ch, blk, val, editor):
    if IS_PG:
        con.execute('''INSERT INTO overrides(chapter,blk,value,editor,ts) VALUES(?,?,?,?,?)
                       ON CONFLICT (chapter,blk) DO UPDATE SET value=excluded.value,editor=excluded.editor,ts=excluded.ts''',
                    (ch, blk, val, editor, now()))
    else:
        con.execute('INSERT OR REPLACE INTO overrides(chapter,blk,value,editor,ts) VALUES(?,?,?,?,?)',
                    (ch, blk, val, editor, now()))

@app.post('/api/upload-image')
@login_required
def upload_image():
    from PIL import Image
    u = current()
    try:
        ch = int(request.form.get('chapter', -1)); blk = int(request.form.get('blk', -1))
    except (TypeError, ValueError):
        return jsonify(error='잘못된 요청입니다.'), 400
    if not can_edit(u, ch): return jsonify(error='이 장을 편집할 권한이 없습니다.'), 403
    chap = next((c for c in BOOK['chapters'] if c['order'] == ch), None)
    if not chap or blk < 0 or blk >= len(chap['content']) or chap['content'][blk]['t'] != 'img':
        return jsonify(error='이미지 블록이 아닙니다.'), 400
    f = request.files.get('file')
    if not f: return jsonify(error='이미지 파일을 선택하세요.'), 400
    try:
        im = Image.open(f.stream); im.load()
    except Exception:
        return jsonify(error='유효한 이미지 파일이 아닙니다.'), 400
    fmt = (im.format or 'PNG').upper()
    if fmt not in ('PNG', 'JPEG', 'JPG', 'GIF', 'WEBP'): fmt = 'PNG'
    if im.mode in ('P', 'RGBA', 'LA') and fmt in ('JPEG', 'JPG'): im = im.convert('RGB')
    if im.width > 1600:
        im = im.resize((1600, max(1, round(im.height * 1600 / im.width))))
    buf = io.BytesIO(); im.save(buf, format='PNG' if fmt == 'GIF' else fmt)
    mime = 'image/jpeg' if fmt in ('JPEG', 'JPG') else 'image/png' if fmt == 'PNG' else 'image/webp'
    data_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    b = chap['content'][blk]
    oldv = load_overrides().get((ch, blk)) or b.get('src')
    con = db()
    img_id = con.insert('INSERT INTO images(chapter,blk,mime,data,editor,ts) VALUES(?,?,?,?,?,?)',
                        (ch, blk, mime, data_b64, u['email'], now()))
    newsrc = f'/api/image/{img_id}'
    _set_override(con, ch, blk, newsrc, u['email'])
    con.execute('INSERT INTO editlog(chapter,blk,oldv,newv,editor,name,role,ts) VALUES(?,?,?,?,?,?,?,?)',
                (ch, blk, oldv, newsrc, u['email'], u['name'], u['role'], now()))   # 실제 src 저장 → 되돌리기 복원
    con.commit()
    return jsonify(ok=True, src=newsrc)

@app.get('/api/image/<int:img_id>')
def serve_image(img_id):
    r = db().execute('SELECT mime,data FROM images WHERE id=?', (img_id,)).fetchone()
    if not r: abort(404)
    from flask import Response
    resp = Response(base64.b64decode(r['data']), mimetype=r['mime'] or 'image/png')
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp

@app.post('/api/revert-block')
@login_required
def revert_block():
    """해당 블록의 편집(그림 교체 포함)을 취소하고 원본으로 복원."""
    u = current(); j = request.get_json(force=True)
    ch = int(j.get('chapter', -1)); blk = int(j.get('blk', -1))
    if not can_edit(u, ch): return jsonify(error='권한이 없습니다.'), 403
    chap = next((c for c in BOOK['chapters'] if c['order'] == ch), None)
    if not chap or blk < 0 or blk >= len(chap['content']): return jsonify(error='대상을 찾을 수 없습니다.'), 404
    con = db()
    cur = load_overrides().get((ch, blk))
    if cur is None: return jsonify(ok=True, unchanged=True)
    b = chap['content'][blk]; orig = b.get(block_field(b))
    con.execute('DELETE FROM overrides WHERE chapter=? AND blk=?', (ch, blk))
    con.execute('INSERT INTO editlog(chapter,blk,oldv,newv,editor,name,role,ts) VALUES(?,?,?,?,?,?,?,?)',
                (ch, blk, cur, orig, u['email'], u['name'], u['role'], now()))   # oldv=직전(교체) src → 되돌리기로 재복원 가능
    con.commit()
    return jsonify(ok=True, src=orig)

@app.get('/api/editlog')
@admin_required
def editlog():
    ch = request.args.get('chapter')
    q = 'SELECT * FROM editlog'; args = []
    if ch is not None: q += ' WHERE chapter=?'; args.append(int(ch))
    q += ' ORDER BY id DESC LIMIT 300'
    rows = [dict(r) for r in db().execute(q, args).fetchall()]
    label = {c['order']: c['label'] for c in BOOK['chapters']}
    for r in rows: r['chapterLabel'] = label.get(r['chapter'], str(r['chapter']))
    return jsonify(log=rows)

# ---------------- comments ----------------
@app.get('/api/comments')
@login_required
def list_comments():
    u = current()
    ch = request.args.get('chapter')
    q = 'SELECT * FROM comments'; args = []
    if ch is not None: q += ' WHERE chapter=?'; args.append(int(ch))
    q += ' ORDER BY id'
    rows = [dict(r) for r in db().execute(q, args).fetchall()]
    # 가시성: 감수자는 '자신이 시작한 스레드'(본인 뿌리메모+그 답글)만, 관리자·집필자는 전체
    if u['role'] == 'reviewer':
        byid = {r['id']: r for r in rows}
        def root_email(r):
            seen = set()
            while r.get('parent_id') and r['parent_id'] in byid and r['id'] not in seen:
                seen.add(r['id']); r = byid[r['parent_id']]
            return r['email']
        rows = [r for r in rows if root_email(r) == u['email']]
    for r in rows:
        r['roleName'] = ROLES.get(r['role'], r['role'])
        r['mine'] = (r['email'] == u['email'])
        r['canDelete'] = r['mine'] or u['role'] in ADMIN_ROLES
    return jsonify(comments=rows, canSeeAll=(u['role'] in ADMIN_ROLES or u['role'] == 'author'))

@app.post('/api/comments')
@login_required
def add_comment():
    u = current(); j = request.get_json(force=True)
    body = (j.get('body') or '').strip()
    if not body: return jsonify(error='메모 내용을 입력하세요.'), 400
    parent_id = j.get('parent_id')
    chapter = int(j.get('chapter', 0)); block = j.get('block', ''); anchor = (j.get('anchor') or '')[:200]
    if parent_id:   # 답글(댓글·대댓글·대대댓글…): 뿌리 메모의 위치를 상속
        p = db().execute('SELECT chapter,block,anchor FROM comments WHERE id=?', (parent_id,)).fetchone()
        if not p: return jsonify(error='원 메모를 찾을 수 없습니다.'), 404
        chapter, block, anchor = p['chapter'], p['block'], p['anchor']
    if not can_view(u, chapter):   # 감수자: 배정된 장에만 메모 가능
        return jsonify(error='이 장에 메모할 권한이 없습니다.'), 403
    nid = db().insert(
        'INSERT INTO comments(chapter,block,anchor,body,email,name,role,created,parent_id) VALUES(?,?,?,?,?,?,?,?,?)',
        (chapter, block, anchor, body, u['email'], u['name'], u['role'], now(), parent_id))
    db().commit()
    return jsonify(ok=True, id=nid)

@app.post('/api/comments/<int:cid>/resolve')
@login_required
def resolve_comment(cid):
    u = current()
    if u['role'] not in ADMIN_ROLES and u['role'] != 'author': return jsonify(error='권한이 없습니다.'), 403
    j = request.get_json(force=True)
    db().execute('UPDATE comments SET resolved=? WHERE id=?', (1 if j.get('resolved') else 0, cid)); db().commit()
    return jsonify(ok=True)

@app.delete('/api/comments/<int:cid>')
@login_required
def del_comment(cid):
    u = current()
    r = db().execute('SELECT email FROM comments WHERE id=?', (cid,)).fetchone()
    if not r: return jsonify(error='없는 메모입니다.'), 404
    if u['role'] not in ADMIN_ROLES and r['email'] != u['email']:
        return jsonify(error='본인 메모만 삭제할 수 있습니다.'), 403
    # 답글이 달린 메모를 지우면 하위 답글(대댓글·대대댓글…)까지 함께 삭제
    con = db(); to_del = [cid]; frontier = [cid]
    while frontier:
        kids = [row[0] for row in con.execute(
            'SELECT id FROM comments WHERE parent_id IN (%s)' % ','.join('?' * len(frontier)), frontier).fetchall()]
        to_del += kids; frontier = kids
    con.execute('DELETE FROM comments WHERE id IN (%s)' % ','.join('?' * len(to_del)), to_del)
    con.commit()
    return jsonify(ok=True, deleted=len(to_del))

# ---------------- user management (admin) ----------------
@app.get('/api/users')
@admin_required
def users():
    actor = current(); asys = set(user_systems(actor))
    rows = db().execute('SELECT email,name,role,assigned,systems,created FROM users ORDER BY role,email').fetchall()
    out = []
    for r in rows:
        d = dict(r); d['systems'] = [s for s in (d.get('systems') or '').split(',') if s in SYSTEMS]
        # 개별 시스템 관리자는 자기 시스템의 사용자만 조회(수퍼관리자는 전체)
        if actor['role'] != 'superadmin' and not (set(d['systems']) & asys):
            continue
        d['roleName'] = ROLES.get(r['role'], r['role'])
        d['comments'] = db().execute('SELECT COUNT(*) FROM comments WHERE email=?', (r['email'],)).fetchone()[0]
        d['chapters'] = sorted(assigned_chapters(r['email']))
        out.append(d)
    chapters = [{'order': c['order'], 'label': c['label'], 'titleKR': c['titleKR']} for c in BOOK['chapters']]
    sysmeta = {k: {'kr': v[0], 'en': v[1]} for k, v in SYSTEMS.items()}
    return jsonify(users=out, roles=ROLES, chapters=chapters, systems=sysmeta, isSuper=(actor['role'] == 'superadmin'))

@app.put('/api/usersystems/<email>')
@super_required
def set_user_systems(email):
    j = request.get_json(force=True); email = email.lower()
    syss = ','.join([s for s in j.get('systems', []) if s in SYSTEMS])
    db().execute('UPDATE users SET systems=? WHERE email=?', (syss, email)); db().commit()
    return jsonify(ok=True, systems=syss)

@app.put('/api/assignments/<email>')
@admin_required
def set_assignments(email):
    j = request.get_json(force=True); email = email.lower()
    tgt = db().execute('SELECT role FROM users WHERE email=?', (email,)).fetchone()
    if tgt and tgt['role'] in ADMIN_ROLES and current()['role'] != 'superadmin':
        return jsonify(error='관리자 계정은 수퍼관리자만 변경할 수 있습니다.'), 403
    chs = sorted({int(x) for x in j.get('chapters', [])})
    con = db()
    con.execute('DELETE FROM assignments WHERE email=?', (email,))
    for ch in chs:
        con.execute('INSERT INTO assignments VALUES(?,?)', (email, ch))
    con.commit()
    return jsonify(ok=True, chapters=chs)

@app.post('/api/users')
@admin_required
def add_user():
    j = request.get_json(force=True)
    email = (j.get('email') or '').strip().lower()
    name = (j.get('name') or '').strip() or email.split('@')[0]
    role = j.get('role', 'reviewer'); pw = j.get('password') or ''
    assigned = (j.get('assigned') or '').strip()
    if '@' not in email: return jsonify(error='올바른 이메일을 입력하세요.'), 400
    if role not in ROLES: return jsonify(error='역할이 올바르지 않습니다.'), 400
    if role in ADMIN_ROLES and current()['role'] != 'superadmin':
        return jsonify(error='관리자 계정 생성은 수퍼관리자만 가능합니다.'), 403
    if len(pw) < 6: return jsonify(error='비밀번호는 6자 이상이어야 합니다.'), 400
    if db().execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
        return jsonify(error='이미 등록된 이메일입니다.'), 400
    db().execute('INSERT INTO users VALUES(?,?,?,?,?,?)',
                 (email, name, role, generate_password_hash(pw), now(), assigned))
    defsys = ','.join(SYSTEMS.keys()) if role == 'superadmin' else (','.join(j.get('systems')) if j.get('systems') else 'book')
    db().execute('UPDATE users SET systems=? WHERE email=?', (defsys, email)); db().commit()
    return jsonify(ok=True)

@app.put('/api/users/<email>')
@admin_required
def update_user(email):
    j = request.get_json(force=True); email = email.lower(); con = db()
    u = con.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    if not u: return jsonify(error='없는 계정입니다.'), 404
    actor = current()
    if u['role'] in ADMIN_ROLES and actor['role'] != 'superadmin':
        return jsonify(error='관리자 계정은 수퍼관리자만 변경할 수 있습니다.'), 403
    if 'role' in j and j['role'] in ADMIN_ROLES and actor['role'] != 'superadmin':
        return jsonify(error='관리자 권한 부여/변경은 수퍼관리자만 가능합니다.'), 403
    # 아이디(이메일/로그인ID) 변경 → 모든 참조 cascade
    new_email = (j.get('email') or '').strip().lower()
    if new_email and new_email != email:
        if con.execute('SELECT 1 FROM users WHERE email=?', (new_email,)).fetchone():
            return jsonify(error='이미 사용 중인 아이디입니다.'), 400
        con.execute('UPDATE users SET email=? WHERE email=?', (new_email, email))
        con.execute('UPDATE comments SET email=? WHERE email=?', (new_email, email))
        con.execute('UPDATE assignments SET email=? WHERE email=?', (new_email, email))
        con.execute('UPDATE overrides SET editor=? WHERE editor=?', (new_email, email))
        con.execute('UPDATE editlog SET editor=? WHERE editor=?', (new_email, email))
        email = new_email
    fields, args = [], []
    if 'role' in j and j['role'] in ROLES: fields.append('role=?'); args.append(j['role'])
    if 'name' in j and j['name'].strip():
        nm = j['name'].strip(); fields.append('name=?'); args.append(nm)
        con.execute('UPDATE comments SET name=? WHERE email=?', (nm, email))   # 메모 표시 이름 동기화
        con.execute('UPDATE editlog SET name=? WHERE editor=?', (nm, email))
    if j.get('password'):
        if len(j['password']) < 6: return jsonify(error='비밀번호는 6자 이상.'), 400
        fields.append('pw=?'); args.append(generate_password_hash(j['password']))
    if fields:
        args.append(email)
        con.execute(f'UPDATE users SET {",".join(fields)} WHERE email=?', args)
    con.commit()
    return jsonify(ok=True, email=email)

@app.delete('/api/users/<email>')
@admin_required
def del_user(email):
    u = current(); email = email.lower()
    if email == u['email']: return jsonify(error='본인 계정은 삭제할 수 없습니다.'), 400
    tgt = db().execute('SELECT role FROM users WHERE email=?', (email,)).fetchone()
    if tgt and tgt['role'] in ADMIN_ROLES and u['role'] != 'superadmin':
        return jsonify(error='관리자 계정은 수퍼관리자만 삭제할 수 있습니다.'), 403
    db().execute('DELETE FROM users WHERE email=?', (email,)); db().commit()
    return jsonify(ok=True)

# seed/migrate on import too, so production servers (gunicorn) initialize the DB
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f'▶ 성장하는 도시를 위한 도시계획 — 검수 웹서비스  http://localhost:{port}  (PUBLIC={PUBLIC})')
    app.run(host='0.0.0.0', port=port, debug=False)
