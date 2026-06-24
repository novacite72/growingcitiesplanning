# -*- coding: utf-8 -*-
"""성장하는 도시를 위한 도시계획 — 원고 검수 웹서비스 (Flask backend).

기능: 이메일 로그인 / 역할(관리자·집필자·감수) / 원고 본문·이미지 열람 / 메모(코멘트).
실행: python3 app.py   →  http://localhost:8000
배포: gunicorn -w 4 -b 0.0.0.0:8000 app:app
"""
import os, json, sqlite3, secrets, datetime, time, copy, io, base64
from functools import wraps
from flask import (Flask, request, session, jsonify, send_from_directory,
                   render_template, g, abort, redirect, send_file, Response)
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
    'worldcities':   ('글로벌 도시 연구', 'Global Urban Research', 'open'),
    'urbanrobotics': ('도시로봇·HRI 연구 데이터베이스', 'Urban Robotics & HRI Research Database', 'open'),
    'wpsc':   ('세계대도시협력', 'World Metropolitan Cooperation', 'link'),
    'book':   ('영문단행본 「성장하는 도시를 위한 도시계획」', 'Urban Planning for Growing Cities', 'open'),
    'globalbook': ('영문단행본 「Planning the Global City with AI」', 'Planning the Global City with AI', 'open'),
    'smartcity': ('단행본 「AI 시대의 스마트도시 계획과 국제협력」', 'Smart City Planning and International Cooperation in the Age of AI', 'open'),
}
# 단행본은 포털에서 'book' 카드 하나(허브)로 진입한다. 각 책의 권한은 'book'(성장하는 도시)·
# 'globalbook'(Planning the Global City)·'smartcity'(스마트도시와 국제협력)로 따로 관리한다.
BOOK_SYSTEMS = ('book', 'globalbook', 'smartcity')
# 연구 DB 서브시스템 ↔ 라우트/페이지 매핑
DB_SUBSYSTEMS = {'worldcities', 'urbanrobotics'}
BOOK = json.load(open(DATA, encoding='utf-8'))
# 두 번째 단행본(글로벌 도시 연구) — 장 order를 1000번대로 오프셋해 기존 책(0~17)·용어사전(9000)과
# 충돌 없이 comments/overrides/editlog/images/assignments 인프라를 그대로 재사용한다.
GBOOK_PATH = os.path.join(HERE, 'globalbook_data.json')
GBOOK = (json.load(open(GBOOK_PATH, encoding='utf-8'))
         if os.path.exists(GBOOK_PATH) else {'chapters': [], 'meta': {}})
# 세 번째 단행본(스마트도시와 국제협력) — 장 order를 2000번대로 오프셋(서장 2000~맺음말 2015).
SBOOK_PATH = os.path.join(HERE, 'smartcity_data.json')
SBOOK = (json.load(open(SBOOK_PATH, encoding='utf-8'))
         if os.path.exists(SBOOK_PATH) else {'chapters': [], 'meta': {}})
BOOKS = {'growing': BOOK, 'global': GBOOK, 'smart': SBOOK}
def book_by_key(k):
    return BOOKS.get(k or 'growing', BOOK)
def all_chapters():
    return BOOK['chapters'] + GBOOK['chapters'] + SBOOK['chapters']
def find_chapter(ch):
    return next((c for c in all_chapters() if c['order'] == ch), None)
# 한영 용어 사전 — 가상의 '장(chapter)'으로 취급해 기존 메모(comments)·편집(overrides) 인프라 재사용.
GLOSSARY_CH = 9000   # 본문 장(0~17)과 충돌하지 않는 센티넬 chapter id
_GLOSS_PATH = os.path.join(HERE, 'glossary.json')
GLOSSARY = json.load(open(_GLOSS_PATH, encoding='utf-8')) if os.path.exists(_GLOSS_PATH) else []

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
        con.execute('''CREATE TABLE IF NOT EXISTS intlorgs(
          id SERIAL PRIMARY KEY, uiaid TEXT UNIQUE, name TEXT, acronym TEXT,
          founded INTEGER, city TEXT, country TEXT)''')
        for ix in ('country', 'city', 'founded', 'name'):
            con.execute(f'CREATE INDEX IF NOT EXISTS idx_io_{ix} ON intlorgs({ix})')
        con.execute('''CREATE TABLE IF NOT EXISTS glossary_terms(
          id SERIAL PRIMARY KEY, en TEXT, kr TEXT, letter TEXT,
          creator_email TEXT, creator_name TEXT, ts TEXT)''')
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
            slug TEXT, title TEXT, data TEXT, updated TEXT, UNIQUE(subsystem, slug));
          CREATE TABLE IF NOT EXISTS intlorgs(id INTEGER PRIMARY KEY AUTOINCREMENT, uiaid TEXT UNIQUE,
            name TEXT, acronym TEXT, founded INTEGER, city TEXT, country TEXT);
          CREATE INDEX IF NOT EXISTS idx_io_country ON intlorgs(country);
          CREATE INDEX IF NOT EXISTS idx_io_city ON intlorgs(city);
          CREATE INDEX IF NOT EXISTS idx_io_founded ON intlorgs(founded);
          CREATE INDEX IF NOT EXISTS idx_io_name ON intlorgs(name);
          CREATE TABLE IF NOT EXISTS glossary_terms(id INTEGER PRIMARY KEY AUTOINCREMENT, en TEXT, kr TEXT,
            letter TEXT, creator_email TEXT, creator_name TEXT, ts TEXT);''')
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
    try:
        seed_wpsc(con)
    except Exception as e:
        print('[wpsc] seed skip:', e); con.rollback()
    try:
        seed_intlorgs(con)
    except Exception as e:
        print('[uia] seed skip:', e); con.rollback()
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

# ---------------- WPSC 게시판(편집 가능) — dbrecords(subsystem='wpsc') ----------------
WPSC_KINDS = ('trips', 'visits', 'partners', 'progress')

def _summary_to_bullets(s):
    """기존 단락 요약 → 불릿 포인트 배열(문장/구분자 기준 분리)."""
    import re
    s = (s or '').strip()
    if not s: return []
    parts = re.split(r'(?<=[.。!?])\s+|\n+|\s·\s', s)
    return [p.strip() for p in parts if p.strip()]

def _wpsc_title(kind, it):
    return (it.get('title') or it.get('org_kr') or it.get('period') or '(제목 없음)')

def seed_wpsc(con):
    """WPSC 게시판 데이터를 dbrecords(subsystem='wpsc')로 1회 시드(수퍼관리자 편집 가능화)."""
    import wpscdata, json as _json
    n = con.execute("SELECT COUNT(*) FROM dbrecords WHERE subsystem='wpsc'").fetchone()[0]
    if n > 0: return
    if IS_PG:
        ins = "INSERT INTO dbrecords(subsystem,kind,slug,title,data,updated) VALUES(?,?,?,?,?,?) ON CONFLICT (subsystem,slug) DO NOTHING"
    else:
        ins = "INSERT OR IGNORE INTO dbrecords(subsystem,kind,slug,title,data,updated) VALUES(?,?,?,?,?,?)"
    cnt = 0
    for kind in WPSC_KINDS:
        for i, it in enumerate(wpscdata.WPSC.get(kind, [])):
            d = dict(it); d['bullets'] = _summary_to_bullets(it.get('summary')); d['order'] = i
            con.execute(ins, ('wpsc', kind, f'wpsc-{kind}-{i:03d}', _wpsc_title(kind, it),
                              _json.dumps(d, ensure_ascii=False), now()))
            cnt += 1
    print(f'[wpsc] {cnt} board records seeded')

def seed_intlorgs(con):
    """UIA 국제기구 디렉터리(uia_orgs.json)를 전용 인덱스 테이블 `intlorgs`로 시드.
    설립연도(founded)는 정수로 파싱(연도 범위 질의용). 파일 건수가 DB와 다르면 전체 교체."""
    import json as _json, re as _re
    p = os.path.join(HERE, 'uia_orgs.json')
    if not os.path.exists(p): return
    # 구버전(dbrecords kind='intlorg') 정리 — 전용 테이블로 이전
    try: con.execute("DELETE FROM dbrecords WHERE subsystem='wpsc' AND kind='intlorg'")
    except Exception: pass
    orgs = _json.load(open(p, encoding='utf-8'))
    n = con.execute("SELECT COUNT(*) FROM intlorgs").fetchone()[0]
    if n == len(orgs): return   # 이미 최신
    con.execute("DELETE FROM intlorgs")
    def yr(s):
        m = _re.match(r'\s*(\d{3,4})', str(s or ''))
        return int(m.group(1)) if m else None
    rows = [(o.get('uiaid') or f'n{i}', o.get('name') or '', o.get('acronym') or '',
             yr(o.get('founded')), o.get('city') or '', o.get('country') or '')
            for i, o in enumerate(orgs)]
    if IS_PG:
        import psycopg2.extras
        psycopg2.extras.execute_values(con.conn.cursor(),
            "INSERT INTO intlorgs(uiaid,name,acronym,founded,city,country) VALUES %s ON CONFLICT (uiaid) DO NOTHING",
            rows, page_size=1000)
    else:
        con.conn.executemany(
            "INSERT OR IGNORE INTO intlorgs(uiaid,name,acronym,founded,city,country) VALUES(?,?,?,?,?,?)", rows)
    print(f'[uia] reseeded {len(rows)} intlorgs into table (was {n})')

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
    # 한영 용어 사전: 권한(역할) 있는 모든 사용자 열람·메모 가능
    if ch == GLOSSARY_CH: return True
    # 관리자급은 전체 열람, 집필자·감수자는 '배정된 장'만 열람
    if u['role'] in ADMIN_ROLES: return True
    return ch in assigned_chapters(u['email'])

def can_edit(u, ch):
    # 한영 용어 사전: 편집(수정)은 관리자만
    if ch == GLOSSARY_CH: return u['role'] in ADMIN_ROLES
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
def books_hub():
    # 영문단행본 허브: 두 단행본 중 권한 있는 책을 선택해 입장
    u = current()
    if not u: return redirect('/?sys=book')
    if not (can_access_system(u, 'book') or can_access_system(u, 'globalbook') or can_access_system(u, 'smartcity')):
        return redirect('/?denied=book')
    return render_template('books_hub.html')

@app.route('/book/growing')
def book_growing():
    u = current()
    if not u: return redirect('/?sys=book')
    if not can_access_system(u, 'book'): return redirect('/book?denied=growing')
    return render_template('index.html', book_key='growing')   # 「성장하는 도시를 위한 도시계획」

@app.route('/book/global')
def book_global():
    u = current()
    if not u: return redirect('/?sys=book')
    if not can_access_system(u, 'globalbook'): return redirect('/book?denied=global')
    return render_template('index.html', book_key='global')    # 「Planning the Global City with AI」

@app.route('/book/smart')
@app.route('/smartcity')
def book_smart():
    u = current()
    if not u: return redirect('/?sys=book')
    if not can_access_system(u, 'smartcity'): return redirect('/book?denied=smart')
    return render_template('index.html', book_key='smart')     # 「AI 시대의 스마트도시 계획과 국제협력」

@app.route('/globalbook')
@app.route('/global-book')
def globalbook_redirect():
    return redirect('/book/global')   # 구 경로 호환

@app.route('/wpsc')
def wpsc_page():
    u = current()
    if not u: return redirect('/?sys=wpsc')
    if not can_access_system(u, 'wpsc'): return redirect('/?denied=wpsc')
    return render_template('wpsc.html')   # 게시판 SPA(국외출장·연구원내원·글로벌협력기관)

@app.route('/wpsc/itinerary')
def wpsc_itinerary():
    u = current()
    if not u: return redirect('/?sys=wpsc')
    if not can_access_system(u, 'wpsc'): return redirect('/?denied=wpsc')
    return send_file(os.path.join(HERE, 'wpsc_itinerary.html'))   # 기존 WPSC 출장 일정 페이지

@app.route('/wpsc/analysis')
def wpsc_analysis():
    u = current()
    if not u: return redirect('/?sys=wpsc')
    if not can_access_system(u, 'wpsc'): return redirect('/?denied=wpsc')
    return send_file(os.path.join(HERE, 'wpsc_analysis.html'))   # WPSC 일정 분석(.md 렌더)

# ---------------- WPSC 출장결과보고서 (편집/사진/다운로드) — dbrecords(subsystem='wpsc', kind='report') ----------------
WPSC_REPORT_SLUG = 'wpsc-report-main'
def default_wpsc_report():
    return {
        "title": "해외출장보고서 — 제6회 세계도시계획대학총회(WPSC 2026, 핀란드 헬싱키) 결과 보고",
        "meta": {"부서": "글로벌연구협력센터", "작성일": "2026. 7. 9.", "작성자": "최준영 선임연구위원"},
        "sections": [
            {"h": "1. 출장개요", "body":
             "<ul><li><b>출장자</b>: 최준영 선임연구위원(서울연구원 글로벌연구협력센터)</li>"
             "<li><b>출장지</b>: 핀란드 헬싱키·에스포 (개인 동선: 탐페레·탈린 병행)</li>"
             "<li><b>출장기간</b>: 2026. 6. 27.(토) ~ 7. 5.(일) / 7박 9일</li>"
             "<li><b>출장목적</b>: ① 논문 발표 — 보행 중심 생활권 내 인구구조 변화 대응 최적 편의시설 배치(선형계획 기반) "
             "② 도시계획 데이터사이언스 동향 파악(15분도시·보행생활권·접근성·AI/빅데이터) "
             "③ 국제 연구협력 — GPEAN 회원단체와 생활권 지원모듈 협력방안 논의 및 네트워크 구축</li>"
             "<li><b>항공·숙소</b>: 핀에어 AY42/AY41 · 스칸딕 그랜드 센트럴 헬싱키(6박)</li></ul>"
             "<p><b>[출장일정]</b></p>"
             "<table><tr><th>일자</th><th>지역</th><th>주요 활동</th></tr>"
             "<tr><td>6/27(토)</td><td>인천→헬싱키</td><td>이동 (핀에어 AY42)</td></tr>"
             "<tr><td>6/28(일)</td><td>에스포·헬싱키</td><td>도시계획 현장조사(타피올라·야트카사리)</td></tr>"
             "<tr><td>6/29(월)</td><td>에스포(알토대)</td><td>WPSC 등록·개막식·기조강연·세션·리셉션</td></tr>"
             "<tr><td>6/30(화)</td><td>에스포(알토대)</td><td>★ 논문 구두발표(Track 1, 16:00) · 세션</td></tr>"
             "<tr><td>7/1(수)</td><td>헬싱키(헬싱키대)</td><td>기조강연·모바일 워크숍·VR 워크숍</td></tr>"
             "<tr><td>7/2(목)</td><td>에스포(알토대)</td><td>세션·GPEAN 협력 컨택·작별 리셉션</td></tr>"
             "<tr><td>7/3(금)</td><td>탈린(개인)</td><td>구시가·도시재생 현장답사</td></tr>"
             "<tr><td>7/4~5</td><td>헬싱키→인천</td><td>이동 (핀에어 AY41)</td></tr></table>"},
            {"h": "2. 출장내용 (일자별)", "body":
             "<p><b>1) 6/28(일) 도시계획 현장조사</b></p><ul>"
             "<li><b>타피올라(Tapiola, 에스포)</b>: 1950년대 계획된 보행 중심 전원도시. 혼합용도·보행네트워크·근린생활시설 배치 등 15분 도시 개념의 선행 사례로서 공간구성 원칙 및 시설 배치 전략을 현장 조사. <i>시사점</i> — 보행 중심 혼합용도·근린 배치를 서울시 생활권계획 시설배치 전략에 적용.</li>"
             "<li><b>야트카사리(Jätkäsaari, 헬싱키)</b>: 항만 폐쇄 후 혼합용도 지구로 전환 중인 도시재생 사업지. 트램·자전거도로·보행축 중심 생활권 공간구성 및 녹지 네트워크 조사. <i>시사점</i> — 항만·유휴부지 재생을 통한 직주근접 생활권 조성.</li></ul>"
             "<p><b>2) 6/29~30(월·화) WPSC 본회의 — 알토대(오타니에미)</b></p><ul>"
             "<li>개막식 및 개막 기조강연(Anacláudia Rossbach, UN-Habitat 사무총장) 참석, 에스포시 주관 리셉션 네트워킹.</li>"
             "<li>15분 도시·보행 생활권·근린 접근성 및 AI/빅데이터 기반 계획지원체계 관련 병렬세션·라운드테이블 참석, 연구동향·공간분석 기술 자료 수집.</li></ul>"
             "<p><b>3) 6/30(화) ★ 논문 발표</b></p><ul>"
             "<li>제목: <i>Balancing Efficiency and Equity in Walkable Living Areas through Optimized Amenity Placement Amidst Demographic Change</i> (Track 1: Accessibility and Mobility, 제출ID 1385, 16:00–17:30 구두발표).</li>"
             "<li>선형계획 기반 최적화 모델(효율–형평 균형)의 방법론적 엄밀성과 실무 적용성에 대한 국제적 검증 및 해외 전문가 피드백 수렴.</li></ul>"
             "<p><b>4) 7/1(수) 헬싱키대학교</b></p><ul>"
             "<li>환영사·기조강연 참석, 학회 주관 모바일 워크숍(헬싱키 도시계획 현장 탐방) 참가, UrbanISE VR 워크숍(헬싱키대 본관 Studium 1) 참관.</li></ul>"
             "<p><b>5) 7/2(목) 알토대 — 협력 네트워킹</b></p><ul>"
             "<li>기조강연(Stefano Moroni)·세션 참석. GPEAN 회원단체 인사 접촉 — ANPUR(브라질) 회장 José R. Vargas de Faria, ALEUP(중남미) Beatriz Rave·Juan Demerutis, KPA 국제협력위원장 이관옥 교수(NUS)와 생활권 지원모듈 협력방안 논의.</li>"
             "<li>저녁 헬싱키 시청(City Hall) 작별 리셉션 참석.</li></ul>"
             "<p><b>6) 7/3(금) 탈린(에스토니아) — 개인 현장답사</b></p><ul>"
             "<li>구시가(UNESCO 세계유산)·텔리스키비(Telliskivi) 산업유산 도시재생 사례 답사(헬싱키↔탈린 페리).</li></ul>"},
            {"h": "3. 주요 성과", "body":
             "<ul><li><b>연구성과 국제 검증</b>: 보행 생활권 편의시설 최적배치(선형계획·효율/형평) 모델을 국제 학술무대에 발표, 방법론 피드백 확보.</li>"
             "<li><b>연구동향 수집</b>: 15분 도시·동적 접근성(N-Minute City)·2SFCA·AI/빅데이터 기반 계획지원 최신 사례 조사.</li>"
             "<li><b>국제 협력 네트워크</b>: GPEAN 회원단체(중남미 ANPUR·ALEUP, 아프리카 AAPS 접촉 의향)와 빅데이터·AI 도시계획 협력 기반 마련, 이관옥 교수(KPA 국제협력위원장) 연계.</li></ul>"},
            {"h": "4. 연구과제 적용방안 및 향후계획", "body":
             "<ul><li>생활권계획 수립지원시스템 고도화 — 동적 접근성·AI 기반 시설입지 최적화 방법 보강.</li>"
             "<li>타피올라·야트카사리 등 선진사례를 서울시 생활권계획 시설배치·도시재생에 적용 검토.</li>"
             "<li>KPA 빅데이터연구위원회 ↔ GPEAN(AAPS·AESOP·APSA) 협력 후속 — 공동 특별세션·교육모듈·MOU 추진.</li></ul>"},
            {"h": "5. 사진 / 첨부", "body":
             "<p style='color:#6E7C8C'>아래 ‘사진 추가’ 버튼으로 현장사진을 첨부하세요. (편집 권한자만)</p>"},
        ],
    }

@app.get('/api/wpsc/report')
def api_wpsc_report():
    u = current()
    if not u: return jsonify(error='로그인이 필요합니다.'), 401
    if not can_access_system(u, 'wpsc'): return jsonify(error='접근 권한이 없습니다.'), 403
    import json as _json
    row = db().execute("SELECT data,updated FROM dbrecords WHERE subsystem='wpsc' AND slug=?", (WPSC_REPORT_SLUG,)).fetchone()
    if row:
        try: data = _json.loads(row['data'])
        except Exception: data = default_wpsc_report()
        updated = row['updated']
    else:
        data = default_wpsc_report(); updated = None
    return jsonify(report=data, updated=updated, canEdit=(u['role'] == 'superadmin'))

@app.post('/api/wpsc/report')
@super_required
def api_wpsc_report_save():
    import json as _json
    j = request.get_json(force=True) or {}
    rep = j.get('report') or {}
    body = _json.dumps(rep, ensure_ascii=False)
    con = db()
    ex = con.execute("SELECT id FROM dbrecords WHERE subsystem='wpsc' AND slug=?", (WPSC_REPORT_SLUG,)).fetchone()
    if ex:
        con.execute("UPDATE dbrecords SET kind='report',title=?,data=?,updated=? WHERE id=?",
                    ('WPSC 출장결과보고서', body, now(), ex['id']))
    else:
        con.insert("INSERT INTO dbrecords(subsystem,kind,slug,title,data,updated) VALUES(?,?,?,?,?,?)",
                   ('wpsc', 'report', WPSC_REPORT_SLUG, 'WPSC 출장결과보고서', body, now()))
    con.commit()
    return jsonify(ok=True, updated=now())

@app.get('/api/wpsc')
def api_wpsc():
    u = current()
    if not u: return jsonify(error='로그인이 필요합니다.'), 401
    if not can_access_system(u, 'wpsc'): return jsonify(error='접근 권한이 없습니다.'), 403
    import wpscdata, json as _json
    rows = db().execute("SELECT id,kind,slug,data FROM dbrecords WHERE subsystem='wpsc'").fetchall()
    out = {k: [] for k in WPSC_KINDS}
    for r in rows:
        try: d = _json.loads(r['data'])
        except Exception: d = {}
        d['id'] = r['id']; d['slug'] = r['slug']
        if r['kind'] in out: out[r['kind']].append(d)
    for k in WPSC_KINDS:
        out[k].sort(key=lambda x: x.get('order', 0))
    return jsonify(data=out, categories=wpscdata.CATEGORIES, canEdit=(u['role'] == 'superadmin'))

@app.post('/api/wpsc/item')
@super_required
def wpsc_add():
    import json as _json
    j = request.get_json(force=True) or {}
    kind = j.get('kind'); it = dict(j.get('item') or {})
    if kind not in WPSC_KINDS: return jsonify(error='잘못된 분류입니다.'), 400
    con = db(); maxo = 0
    for r in con.execute("SELECT data FROM dbrecords WHERE subsystem='wpsc' AND kind=?", (kind,)).fetchall():
        try: maxo = max(maxo, _json.loads(r['data']).get('order', 0))
        except Exception: pass
    it.setdefault('order', maxo + 1)
    slug = f'wpsc-{kind}-{int(time.time() * 1000)}'
    rid = con.insert('INSERT INTO dbrecords(subsystem,kind,slug,title,data,updated) VALUES(?,?,?,?,?,?)',
                     ('wpsc', kind, slug, _wpsc_title(kind, it), _json.dumps(it, ensure_ascii=False), now()))
    con.commit()
    return jsonify(ok=True, id=rid, slug=slug)

@app.put('/api/wpsc/item/<int:rid>')
@super_required
def wpsc_edit(rid):
    import json as _json
    j = request.get_json(force=True) or {}
    it = dict(j.get('item') or {}); con = db()
    row = con.execute("SELECT kind FROM dbrecords WHERE id=? AND subsystem='wpsc'", (rid,)).fetchone()
    if not row: return jsonify(error='항목을 찾을 수 없습니다.'), 404
    kind = j.get('kind') or row['kind']
    if kind not in WPSC_KINDS: return jsonify(error='잘못된 분류입니다.'), 400
    con.execute("UPDATE dbrecords SET kind=?,title=?,data=?,updated=? WHERE id=? AND subsystem='wpsc'",
                (kind, _wpsc_title(kind, it), _json.dumps(it, ensure_ascii=False), now(), rid))
    con.commit()
    return jsonify(ok=True)

@app.delete('/api/wpsc/item/<int:rid>')
@super_required
def wpsc_del(rid):
    con = db()
    con.execute("DELETE FROM dbrecords WHERE id=? AND subsystem='wpsc'", (rid,))
    con.commit()
    return jsonify(ok=True)

_IO_FACETS = None   # 패싯 캐시(워커별, 시드 후 1회 계산)

@app.get('/api/wpsc/intlorgs/facets')
@login_required
def api_intlorgs_facets():
    """국가(건수)·상위 도시·설립연도 범위 — 필터 드롭다운용(캐시)."""
    u = current()
    if not can_access_system(u, 'wpsc'): return jsonify(error='접근 권한이 없습니다.'), 403
    global _IO_FACETS
    if _IO_FACETS is None:
        con = db()
        countries = [{'v': r[0], 'n': r[1]} for r in con.execute(
            "SELECT country, COUNT(*) c FROM intlorgs WHERE country<>'' GROUP BY country ORDER BY c DESC").fetchall()]
        cities = [r[0] for r in con.execute(
            "SELECT city FROM intlorgs WHERE city<>'' GROUP BY city ORDER BY COUNT(*) DESC LIMIT 500").fetchall()]
        yr = con.execute("SELECT MIN(founded), MAX(founded) FROM intlorgs WHERE founded IS NOT NULL").fetchone()
        total = con.execute("SELECT COUNT(*) FROM intlorgs").fetchone()[0]
        _IO_FACETS = {'countries': countries, 'cities': cities,
                      'yearMin': yr[0], 'yearMax': yr[1], 'total': total}
    return jsonify(_IO_FACETS)

@app.get('/api/wpsc/intlorgs')
@login_required
def api_intlorgs():
    """국제기구 필터·검색(이름·약어·국가·도시·설립연도) + 페이지네이션. 인덱스 SQL로 무지연."""
    u = current()
    if not can_access_system(u, 'wpsc'): return jsonify(error='접근 권한이 없습니다.'), 403
    a = request.args
    def _int(k):
        try: return int(a.get(k))
        except (TypeError, ValueError): return None
    q = (a.get('q') or '').strip().lower()
    country = (a.get('country') or '').strip()
    city = (a.get('city') or '').strip().lower()
    yfrom, yto = _int('yfrom'), _int('yto')
    page = max(0, _int('page') or 0); PAGE = 50
    sort = a.get('sort')
    order = {'founded': 'founded DESC NULLS LAST, name', 'founded_asc': 'founded ASC NULLS LAST, name'}.get(sort, 'name') \
        if IS_PG else {'founded': 'founded IS NULL, founded DESC, name', 'founded_asc': 'founded IS NULL, founded ASC, name'}.get(sort, 'name')
    where, params = [], []
    if q:
        where.append('(LOWER(name) LIKE ? OR LOWER(acronym) LIKE ?)')
        like = '%' + q.replace('%', '').replace('_', '') + '%'; params += [like, like]
    if country:
        where.append('country=?'); params.append(country)
    if city:
        where.append('LOWER(city) LIKE ?'); params.append('%' + city.replace('%', '').replace('_', '') + '%')
    if yfrom is not None:
        where.append('founded>=?'); params.append(yfrom)
    if yto is not None:
        where.append('founded<=?'); params.append(yto)
    wsql = (' WHERE ' + ' AND '.join(where)) if where else ''
    con = db()
    total = con.execute('SELECT COUNT(*) FROM intlorgs' + wsql, params).fetchone()[0]
    rows = con.execute(f'SELECT uiaid,name,acronym,founded,city,country FROM intlorgs{wsql} ORDER BY {order} LIMIT ? OFFSET ?',
                       params + [PAGE, page * PAGE]).fetchall()
    orgs = [{'uiaid': r[0], 'name': r[1], 'acronym': r[2], 'founded': r[3], 'city': r[4], 'country': r[5]} for r in rows]
    return jsonify(orgs=orgs, total=total, page=page, pageSize=PAGE, hasMore=(page + 1) * PAGE < total)

@app.route('/worldcities')
@app.route('/world-cities')
def worldcities_page():
    u = current()
    if not u: return redirect('/?sys=worldcities')
    if not can_access_system(u, 'worldcities'): return redirect('/?denied=worldcities')
    return render_template('worldcities.html')

@app.route('/worldcities/doc/<slug>')
def worldcities_doc(slug):
    """글로벌 연구 디렉토리 문서 전문(HTML) 서빙 — worldcities 접근권한 게이트."""
    u = current()
    if not u: return redirect('/?sys=worldcities')
    if not can_access_system(u, 'worldcities'): return redirect('/?denied=worldcities')
    doc = next((d for d in WC_DOCS if d['slug'] == slug), None)
    if not doc: abort(404)
    return send_file(os.path.join(HERE, 'docs', doc['docFile']))

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

# 글로벌 연구 디렉토리(kind='document') — 풀텍스트 HTML 보고서는 docs/ 에서 서빙.
# dbrecords에 저장하지 않아 KB prune의 영향을 받지 않음(항상 노출).
WC_DOCS = [
    {'slug': 'io-seoul-cabei-korea-office', 'kind': 'document',
     'title': 'CABEI 한국사무소 개설 과정·현황과 다자금융기구 서울 유치 정책과제 (개정)',
     'category': 'research', 'program': '국제기구 서울 유치 활성화 연구',
     'summary': '중미경제통합은행(CABEI) 한국사무소 사례를 중심으로, 서울시 금융조례 기반 지원효과·유치 영향요인과 함께 다자금융기구 추가 유치를 위한 중앙정부·서울시 제도개선, 서울글로벌센터·여의도 IFC 이원거점 유치모델과 체크리스트를 정리한 개정 보고서.',
     'date': '2026-06-18', 'tags': ['국제기구 서울유치', 'CABEI', '다자금융기구', '다자개발은행', '금융조례', '유치전략', '여의도 IFC', '서울글로벌센터'],
     'docFile': 'cabei-korea-office.html', 'docUrl': '/worldcities/doc/io-seoul-cabei-korea-office',
     'body': '국제기구 서울유치 활성화 전략 기초연구의 사례 보고서(개정판). CABEI 한국사무소 개설 과정·현황과 서울시 금융조례 기반 지원효과를 분석하고, 향후 다자금융기구 유치를 위한 **중앙정부 제도개선**(법적 지위·Host Office Agreement·재정지원·비자정주·조달연계), **서울시 조례·운영 개선**(지원대상 확장·국제기구형 성과기준·Host City Concierge), **서울글로벌센터·여의도 IFC 이원거점 유치모델**과 단계별 체크리스트·추진 로드맵을 제시한다. 상단의 **📄 전문 보기** 버튼으로 전체 보고서를 확인하세요.'},
    {'slug': 'io-seoul-attraction-interviews', 'kind': 'document',
     'title': '국제기구 서울 유치 활성화 전략 기초연구 — 인터뷰 조사 중간보고서',
     'category': 'research', 'program': '국제기구 서울 유치 활성화 연구',
     'summary': '서울 소재 국제기구 대상 대면 인터뷰 5건의 중간분석과, 본 조사의 핵심 산출물인 개선 설문(질문지), 신규 유치 시사점·후보기관 발굴, 후속조치 제안을 담은 중간보고서.',
     'date': '2026-06', 'tags': ['국제기구 서울유치', '인터뷰 조사', '유치전략', '설문 개선', '서울연구원'],
     'docFile': 'io-seoul-attraction-interviews.html', 'docUrl': '/worldcities/doc/io-seoul-attraction-interviews',
     'body': '국제기구 서울유치 활성화 전략 기초연구의 인터뷰 조사 중간보고서. 대면 인터뷰 5건 중간분석, 개선 설문지(핵심 산출물), 미인터뷰 기관 실행계획, 신규 유치 시사점·후보기관 발굴, 후속조치 제안으로 구성. 상단의 **📄 전문 보기** 버튼으로 전체 보고서를 확인하세요.'},
    {'slug': 'oda-kcn-bogota-calle72', 'kind': 'document', 'category': 'oda',
     'title': 'KIND K-City Network — 보고타 Calle 72 스마트시티 계획 (RENOBO)',
     'program': 'ODA · K-City Network 공모',
     'summary': '국토교통부·KIND의 「K-City Network 글로벌 협력 프로그램」(스마트시티 계획수립형) 공모 사업. 콜롬비아 보고타 Calle 72 일대(RENOBO 도시재생 대상지)의 스마트시티 계획수립을 서울연구원·플랜웍스가 제안하며, 산출물로 사업요청서(PCP)를 작성·제출한다.',
     'agency': '국토교통부 · KIND (K-City Network)', 'performer': '서울연구원 · 플랜웍스',
     'site': '콜롬비아 보고타 Calle 72 (RENOBO / SAZP)', 'projectType': '스마트시티 계획수립 공모 (PCP)',
     'status': '진행 (2025)', 'date': '2025-11',
     'timeline': '2025.8 제안서 작성방향 협의 → 2025.10 서울–보고타 회의 → 2025.11 제출용 PCP 작업·Lessons learnt',
     'keyDocuments': ['KCN Colombia Proposal — Project Preparation (Planworks)', 'KIND Pilot project', 'Calls-for-Projects 2025 K-City Network — Calle 72 SAZP', 'PCP — RENOBO pilot project AE Calle 72'],
     'body': '## 사업 개요\n국토교통부와 KIND가 운영하는 **K-City Network 글로벌 협력 프로그램(스마트시티 계획수립형)** 공모에 제출한 사업이다. 콜롬비아 **보고타 Calle 72** 일대(RENOBO 주도 도시재생 대상지)를 대상으로 스마트시티 계획을 수립하며, 서울연구원과 플랜웍스가 수행한다.\n\n## 추진 경과\n2025년 8월 서울연구원–플랜웍스 제안서 작성방향 협의, 10월 서울–보고타 회의, 11월 제출용 사업요청서(PCP) 작업과 Lessons learnt 정리로 진행되었다.\n\n## 산출물\n사업요청서(PCP), 파일럿 프로젝트 정의서 등.'},
    {'slug': 'oda-haegunhyup-bogota-montevideo', 'kind': 'document', 'category': 'oda',
     'title': '해건협 국토교통ODA — 콜롬비아 보고타 스마트 도시재생 (몬테비데오 SAZP)',
     'program': 'ODA · 국토교통부 해외건설협회',
     'summary': '해외건설협회(해건협) 국토교통ODA 신규사업 공모에 제출(2024.9 완료)한 사업. 콜롬비아 보고타 몬테비데오(Montevideo) 전략지역조닝계획(SAZP)을 중심으로 한 스마트 도시재생을 제안하며, 신규사업 제안서·사업개요서·사전타당성조사(Pre-FS)·영문 PCP·수원기관 LOI·예산내역 등을 제출하였다.',
     'agency': '해외건설협회 · 국토교통 ODA', 'site': '콜롬비아 보고타 Montevideo (SAZP 전략지역조닝계획)',
     'projectType': '스마트 도시재생 신규사업 제안 (제출 완료)', 'status': '제출 완료 (2024.9)', 'date': '2024-09',
     'timeline': '2024.9 신규사업 제안서·국문 사업개요서·사전타당성조사(Pre-FS)·영문 PCP·수원기관 LOI·예산 산출 내역서 제출',
     'keyDocuments': ['신규사업 제안서(양식1)', '국문 사업개요서(양식2)', '사전타당성조사 보고서(양식3, Pre-FS)', '관계기관 영문 사업요청서(PCP)', '수원기관 사업요청 공문(LOI)', '예산 산출 내역서', '수원국 사업 대상지역 지도'],
     'body': '## 사업 개요\n해외건설협회(해건협)가 주관하는 **국토교통 ODA 신규사업** 공모에 제출(2024년 9월 완료)한 사업이다. 콜롬비아 **보고타 몬테비데오(Montevideo)** 전략지역조닝계획(SAZP, Strategic Area Zoning Plan)을 중심으로 한 스마트 도시재생을 제안하였다.\n\n## 제출 서류\n신규사업 제안서(양식1), 국문 사업개요서(양식2), 사전타당성조사 보고서(양식3·Pre-FS), 관계기관 영문 사업요청서(PCP), 수원기관 사업요청 공문(LOI), 예산 산출 내역서, 대상지역 지도.'},
]

# 토론(kind='discussion') — 세미나 발표자료 요약 + 종합토론 내용. WC_DOCS와 동일하게 코드에 상주.
WC_DISCUSSIONS = [
    {'slug': 'disc-2026-kpa-ai-pres1-kimseungnam', 'kind': 'discussion',
     'discType': '주제발표 1',
     'title': '[발표 1] AI 시대의 도시공간 변화 예측과 대응 — 김승남',
     'event': '2026 국토교통기술대전 학술세미나 「AI와 도시계획·설계의 미래: 기회와 도전」',
     'session': '주제발표', 'date': '2026-06-25', 'venue': '코엑스 컨퍼런스룸 E4 (3F)',
     'host': '대한국토·도시계획학회 4차산업혁명위원회 · KAIA',
     'presenter': '김승남', 'affiliation': '중앙대학교 교수',
     'summary': 'AI가 도시공간 구조와 미시적 도시공간을 어떻게 바꾸는지(대상으로서의 AI)를 기술발전사·집중분산 논쟁·가로공간 재구성·분절적 도시화의 틀로 조망하고, 시나리오 대응 계획·공간유형별 도시공간정책·열린(가역적) 설계라는 대응 방향을 제시한 발표.',
     'keyPoints': [
        'AI는 도시를 분석하는 도구를 넘어 도시 안에서 스스로 판단·실행하는 행위자로 전환(Smart Urbanism → AI Urbanism, Cugurullo et al. 2024).',
        'AI의 도시 효율 향상은 더 크고 고밀한 도시를 가능케 하지만, 고용·통근 변화는 도심 집중을 완화 — 집중 vs 분산 논쟁이 재점화됨.',
        'Physical AI(자율주행차·배송로봇·드론·UAM)가 도로·도로변·보도·옥상 등 물리적 공간을 두고 기존 이용주체와 경쟁 → 가로공간 재구성(street reallocation) 필요.',
        'AI는 분절적 도시화(splintering urbanism)와 디지털 격차를 심화 — 국가·도시·개인 간 양극화와 알고리즘적 redlining 우려.',
        '대응: ①단일 예측형이 아닌 시나리오 대응 계획 ②기술정책이 아니라 공간유형별 도시공간정책 ③닫힌 설계에서 가역적·가변적인 열린 설계로.',
     ],
     'tags': ['AI urbanism', '도시공간구조', '가로공간 재구성', 'splintering urbanism', '시나리오 계획', '자율주행', '도시공간정책'],
     'relatedPresentations': ['disc-2026-kpa-ai-pres2-eomsunyong', 'disc-2026-kpa-ai-panel-choijunyoung'],
     'sources': [
        '발표자료: 김승남, 「AI 시대의 도시공간 변화 예측과 대응」, 2026 국토교통기술대전 학술세미나 (2026.6.25)',
        '김승남(2024), "AI 시대, 도시계획가의 미래와 역할 변화", 월간 국토 510호: 17-24',
        'Cugurullo et al.(2024), The rise of AI urbanism in post-smart cities, Urban Studies 61(6): 1168-1182',
        'Speck, J.(2018), Walkable City Rules',
     ],
     'body': '## 발표 개요\n중앙대학교 김승남 교수는 **AI가 도시공간을 어떻게 바꾸는가(대상으로서의 AI)**를 다섯 갈래로 조망한다.\n\n## 1. 기술 발전과 도시공간 진화\n엘리베이터·철근콘크리트가 마천루를, 자동차·고속도로가 모터리제이션과 도시 확산(urban sprawl)을 낳았듯, AI·자율주행·드론·UAM·VR/AR이 도시형태와 삶을 다시 바꾼다. 근린주구이론(Perry 1929 → DPZ 1998 → Farr 2008·2018)의 변천처럼 도시설계 패러다임도 기술에 맞춰 진화해 왔다.\n\n## 2. AI 기술의 본질\nBig data+AI(분석·예측), Generative AI(콘텐츠 생성·의사결정 지원), Physical AI(자동화·로보틱스), AI Agent(자율·협력 실행)로 정리된다. AI는 도시 운영의 정시성·정확도·효율을 높이는 동시에 고용시장 재구조화·일자리 감소·디지털 격차를 야기한다.\n\n## 3. 도시공간구조 변화\n- AI에 의한 효율 향상은 집적의 순이익을 키워 **더 크고 고밀한 도시**를 가능케 함.\n- 동시에 AI가 노동을 대체하며 사무실 수요 감소·원격근무 확대·다핵화·생활권 자족성 강화로 **도심 집중을 완화**.\n- 교통수단 발달은 **집중–분산 논쟁**을 재점화(Driverless sprawl vs. Ratti의 도심 정주성 향상).\n- Winner-takes-all 특성은 **분절적 도시화**와 주거지 분화를 심화.\n\n## 4. 미시적 도시공간 변화\n자율주행차·배송로봇·PM·드론·UAM이 도로·보도·자전거도로·옥상·정류장에서 기존 이용주체와 **공간을 두고 경쟁**한다. 도로변(curbside) 재배분, 주차공간의 용도전환, 옥상의 진입·이착륙 공간화, AI 추천에 의한 **장소성·상권의 선별적 집중**이 일어난다.\n\n## 5. 어떻게 대응할 것인가\n- **시나리오 대응 계획**: 단일 미래 예측 대신 복수 시나리오별 대응안 마련(Speck의 "Law가 아니라 Lane으로").\n- **공간정책으로 대응**: AI의 순영향(집중/분산) 방향은 예측 불가하나 영향받을 공간 범주는 예측 가능 → 도심·교외·혁신지구·주거·교통·데이터 인프라 등 **공간유형별 정책** 필요.\n- **열린 설계**: 비가역적 설계에서 벗어나 가역성·가변성을 핵심 가치로(예: Sidewalk Labs의 dynamic curb).'},

    {'slug': 'disc-2026-kpa-ai-pres2-eomsunyong', 'kind': 'discussion',
     'discType': '주제발표 2',
     'title': '[발표 2] 빅데이터 분석을 위한 AI의 활용 방안 — 엄선용',
     'event': '2026 국토교통기술대전 학술세미나 「AI와 도시계획·설계의 미래: 기회와 도전」',
     'session': '주제발표', 'date': '2026-06-25', 'venue': '코엑스 컨퍼런스룸 E4 (3F)',
     'host': '대한국토·도시계획학회 4차산업혁명위원회 · KAIA',
     'presenter': '엄선용', 'affiliation': '한양대학교 도시대학원 교수',
     'summary': 'AI를 도시분석에 어떻게 쓸 것인가(도구로서의 AI)를 ①기존 도시분석의 활용 장벽 완화와 ②새로운 분석 패러다임의 확장이라는 두 축으로 정리하고, X-minute city·전국 대중교통 접근성(MAI)·보행생활권 알고리즘·가로경관 LLM 평가·재해 도로 판독·시민 페르소나 등 실증 사례로 보여준 발표.',
     'keyPoints': [
        'AI 활용의 두 축: ①기술적으로 가능했으나 장벽·비용이 높던 분석의 활용 장벽 완화 ②AI 이전에는 불가능했던 분석 패러다임의 확장.',
        '코딩 특화 AI 어시스턴트로 논문+서울시 원본데이터만 입력해 X-minute city, 전국 500m 격자 대중교통 접근성(MAI)을 재현 — 진입장벽이 급격히 낮아짐.',
        '멀티모달 LLM으로 거리이미지 기반 가로경관(보행 안전·편안·즐거움) 평가, 재해 도로상태 자동 판독 등 비정형·멀티모달 자료까지 분석 확장.',
        '시민 페르소나(Nemotron-Personas-Korea)는 실제 시민참여를 대체하는 것이 아니라 정책 대상자 유형·쟁점을 사전 탐색하는 보조 도구.',
        'AI가 낮추는 것은 도시분석의 진입장벽이지 공공적 판단의 책임이 아님 — 계획가는 "답을 내는 사람"에서 "질문하고 결과를 검증·설명하는 사람"으로 이동.',
     ],
     'tags': ['도시 빅데이터', 'X-minute city', '대중교통 접근성', 'MAI', '멀티모달 LLM', '가로경관 평가', '생활권', '시민 페르소나', 'PSS'],
     'relatedPresentations': ['disc-2026-kpa-ai-pres1-kimseungnam', 'disc-2026-kpa-ai-panel-choijunyoung'],
     'sources': [
        '발표자료: 엄선용, 「빅데이터 분석을 위한 AI의 활용 방안」, 2026 국토교통기술대전 학술세미나 (2026.6.25)',
        'Kang, M. & Eom, S.(2026), Multi-activity accessibility by public transit, Applied Geography 191, 104004',
        'Yoo, M., Cho, G.-H. & Kim, D.(2026), Explaining walkability with a zero-shot multimodal LLM, Sustainable Cities and Society 144, 107431',
        'Batty, M.(2013), Big data, smart cities and city planning, Dialogues in Human Geography 3(3)',
     ],
     'body': '## 발표 개요\n한양대 엄선용 교수는 **AI를 도시분석에 어떻게 쓸 것인가(도구로서의 AI)**를 두 축으로 정리한다. AI의 가치는 도시를 대신 판단하는 데 있지 않고, 도시현상을 더 잘 설명·발견·이해·일반화하는 데 있다.\n\n## 첫 번째 역할 — 기존 도시분석의 활용 장벽 완화\n도시계획은 이미 데이터·모델의 학문이었으나 방법론을 실무에서 호출하는 장벽이 높았다(Vonk et al. 2005의 implementation gap). 코딩 특화 AI 어시스턴트의 등장으로 누구나 분석이 가능해진다.\n- **X-minute city**: 논문과 서울시 원본데이터(미정제)만 입력해 방법론 재현.\n- **전국 대중교통 접근성**: 500m 격자에서 시간표 기반 대중교통과 생활시설 운영시간을 결합, 목적지 도달(Purpose-specific)을 넘어 **다중활동 접근성(MAI)**을 측정. 핵심 쟁점은 "도달 후 활동 결합"보다 "처음부터 도달 가능한가"이며, 대중교통 접근성의 지역 불평등이 자동차보다 뚜렷.\n- **보행생활권 구축 알고리즘**: 시설 접근성+통신사 데이터로 생활권을 자동 생성하고, 실무자가 직접 조작하며 재배치 대안을 탐색·비교(단계형 분석·검토 플랫폼).\n\n## 두 번째 역할 — 새로운 분석 패러다임의 확장\n과거에는 다루기 어려웠던 자료·질문까지 분석 대상으로 확장한다.\n- **가로경관 LLM 평가**: 서울 거리이미지 1,000장에 zero-shot 멀티모달 LLM을 적용해 보행 안전·편안·즐거움을 평가, 전문가 평가와의 일치도 검증(반복평가 신뢰도 0.90+). 단, 장소 맥락·심미 판단에는 전문가 검토 필요.\n- **재해 도로상태 판독**: 반지도학습으로 도로 손상 유형·통행가능성을 자동 판독, 재난 직후 신속 대응 지원.\n- **시민 페르소나(Nemotron-Personas-Korea)**: 실제 시민참여를 대체하지 않고 쟁점·반응을 사전 탐색하는 보조 도구.\n\n## 결론 — AI 시대의 도시계획가\nAI가 낮추는 것은 **진입장벽**이지 **공공적 판단의 책임**이 아니다. 오히려 어떤 데이터를 넣고 어떤 모형을 택하며 결과를 어떻게 이해할지 결정하는 **검증·설명 책임**은 더 커진다. 계획가는 "답을 내는 사람"·"기술을 적용하는 사람"에서 **"질문하는 사람"·"결과를 검증하고 설명하는 사람"**으로 이동한다.'},

    {'slug': 'disc-2026-kpa-ai-panel-choijunyoung', 'kind': 'discussion',
     'discType': '종합토론',
     'title': '[종합토론] 글로벌 도시·국제협력 관점의 토론 — 최준영',
     'event': '2026 국토교통기술대전 학술세미나 「AI와 도시계획·설계의 미래: 기회와 도전」',
     'session': '종합토론', 'date': '2026-06-25', 'venue': '코엑스 컨퍼런스룸 E4 (3F)',
     'host': '대한국토·도시계획학회 4차산업혁명위원회 · KAIA',
     'discussant': '최준영', 'affiliation': '서울연구원 글로벌연구협력센터장',
     'moderator': '최창규 (한양대학교 교수, 학회 학술부회장)',
     'summary': '서울연구원 글로벌연구협력센터장 최준영이 두 주제발표를 글로벌 도시 경쟁력·국제협력·서울 정책의 관점에서 종합토론한 내용. AI 도시격차의 도시외교 의제화, 공간정책 대응, 시민·자치구 거버넌스로의 분석 장벽 확장, 검증·설명 책임의 제도화, 한국 실증의 글로벌 표준·ODA 연결 등을 제언.',
     'discussionPoints': [
        'AI 도시격차(AI urban divide)는 도시 내부를 넘어 도시 간·국가 간 경쟁력 격차 — WPSC·MeTTA 등 도시외교 채널의 공동 의제로.',
        '"기술정책이 아니라 공간정책으로 대응"은 서울에도 적용 — 데이터센터 입지·전력·주민수용성을 공간계획 단계에서 선제 대응.',
        '분석 장벽 완화는 자치구·시민이 직접 대안을 탐색하는 참여형 거버넌스로 확장 가능 — 단, 공공 데이터·표준 방법론·검증 체계 동반 필요.',
        '알고리즘 등록·편향점검·인간감독을 제도화해 서울이 AI 거버넌스 국제 선도사례를 만들 수 있음.',
        '한국의 도시 빅데이터·AI 분석 실증을 재현 가능한 방법론·오픈데이터·플랫폼으로 패키징해 글로벌 표준화·ODA(K-City Network 등)로 연결.',
        '"시나리오 대응"·"열린 설계"는 도시외교·국제협력 전략에도 유효 — 가역적·유연한 의제 설계.',
     ],
     'tags': ['종합토론', '글로벌 도시', '도시외교', '국제협력', 'AI 거버넌스', 'AI 도시격차', '서울 정책', 'ODA', 'WPSC', '생활권'],
     'relatedPresentations': ['disc-2026-kpa-ai-pres1-kimseungnam', 'disc-2026-kpa-ai-pres2-eomsunyong'],
     'sources': [
        '2026 국토교통기술대전 학술세미나 「AI와 도시계획·설계의 미래: 기회와 도전」, 대한국토·도시계획학회 4차산업혁명위원회·KAIA, 코엑스 E4 (2026.6.25)',
        '종합토론 좌장 최창규(한양대) / 토론 최준영(서울연구원)·권용석(경북연구원)·송재민(서울대)·안상훈(동명기술공단)',
     ],
     'body': '## 종합토론 — 글로벌 도시·국제협력의 관점에서\n서울연구원 글로벌연구협력센터장으로서 두 발표를 **글로벌 도시 경쟁력과 국제협력**의 관점에서 토론한다. 두 발표는 상호 보완적이다. 김승남 교수는 *AI가 도시공간을 어떻게 바꾸는가(대상으로서의 AI)*를, 엄선용 교수는 *AI를 도시분석에 어떻게 쓰는가(도구로서의 AI)*를 다룬다. 두 발표가 공통으로 도달하는 결론은 **"AI는 계획가를 대체하지 않으며, 공공적 판단과 검증의 책임은 오히려 커진다"**는 것이다. 이 지점에서 여섯 가지 논점을 제기한다.\n\n### 1. AI 도시격차는 곧 도시외교의 의제다\n김승남 교수가 지적한 **분절적 도시화(splintering urbanism)**와 **Winner-takes-all**은 도시 내부만의 문제가 아니라 **도시 간·국가 간 격차**의 문제다. AI 인프라(데이터센터·연산·인재)를 갖춘 선도도시와 그렇지 못한 도시 사이의 서비스 격차는 21세기 도시 경쟁력의 핵심 변수가 된다. 서울 같은 선도도시는 이를 자국 내 문제로만 볼 것이 아니라, **세계대도시협의체(WPSC)·광역계획기관 글로벌 네트워크(MeTTA)** 등 도시외교 채널을 통해 "AI 격차 완화"를 공동 의제로 끌어올릴 책임이 있다.\n\n### 2. \'기술정책이 아니라 공간정책\'은 서울에도 그대로 적용된다\n김승남 교수의 *"AI의 영향은 기술정책이 아니라 도시공간 정책으로 대응해야 한다"*는 제언에 전적으로 동의한다. 서울도 공간 유형별(도심·혁신지구·생활권·모빌리티·데이터 인프라) 대응 전략이 필요하다. 특히 **데이터센터 입지·전력·폐열·물 사용·주민 수용성**은 이미 서울의 현안이며, AI 도시 전환이 가시화될수록 입지 갈등은 심화된다. 사후 대응이 아니라 **공간계획 단계에서 선제적으로 다루는 제도**가 시급하다.\n\n### 3. 분석 장벽의 완화는 \'시민·자치구 거버넌스\'로 확장될 수 있다\n엄선용 교수가 보여준 **X-minute city·전국 대중교통 접근성(MAI)·보행생활권 구축 알고리즘**은 서울연구원이 추진해 온 생활권·15분도시 논의와 직접 맞닿아 있다. AI로 분석의 진입장벽이 낮아진 만큼, 전문가의 전유물이던 도시분석을 **자치구 공무원·시민이 직접 대안을 탐색·비교하는 참여형 거버넌스**로 확장할 수 있다. 다만 "누구나 분석할 수 있다"가 "누구의 분석이든 타당하다"는 뜻은 아니므로, 공공 데이터·표준 방법론·검증 체계를 함께 제공하는 플랫폼 설계가 관건이다.\n\n### 4. 검증·설명 책임의 제도화 — 서울이 선도사례를 만들 수 있다\n두 발표 모두 **알고리즘 감사·편향 점검·인간 감독·설명 책임**을 강조했다. 이는 선언으로 끝낼 문제가 아니라 제도로 정착시켜야 한다. 서울은 **도시외교 조례**와 데이터 거버넌스 체계를 기반으로, 공공의사결정에 활용되는 *알고리즘의 등록·편향점검·인간감독*을 제도화하는 국제 선도사례를 만들 수 있다. 이는 곧 서울의 글로벌 도시 브랜드이자 협력 자산이 된다.\n\n### 5. 한국의 실증을 \'글로벌 표준·ODA\'로 연결하자\n엄선용 교수의 가로경관 LLM 평가·재해 도로 판독, 김승남 교수의 가로공간 재구성 모델은 **글로벌 도시 간 비교·벤치마킹**과 **국제개발협력(ODA)**에 직접 활용할 수 있다. K-City Network(보고타 Calle 72 등) 사업이 보여주듯, 한국이 축적한 도시 빅데이터·AI 분석 방법론은 개발도상 도시의 계획 역량을 끌어올리는 강력한 협력 수단이다. 국내 실증에 머물지 말고 **재현 가능한 방법론·오픈 데이터·플랫폼**으로 패키징해 글로벌 표준화·수출로 연결할 것을 제안한다.\n\n### 6. \'시나리오 대응\'과 \'열린 설계\'는 국제협력 전략에도 유효하다\n김승남 교수의 **단일 예측형 계획 → 시나리오 대응 계획**, **닫힌 설계 → 열린 설계** 제언은 공간계획을 넘어 도시외교·국제협력 전략에도 적용된다. AI가 바꿀 도시의 미래가 불확실한 만큼, 협력 의제와 제도 역시 단일 시나리오에 고정하기보다 **가역적·유연한** 형태로 설계해야 한다.\n\n## 제언(질문)\n- 한국형 **AI urbanism의 거버넌스 모델**은 무엇이어야 하는가 — 효율과 형평, 자동화와 자율성 사이에서?\n- **시민 페르소나(Nemotron-Personas-Korea 등)**가 실제 시민참여를 *보완*하되 *대체*하지 않도록 하는 원칙은 어떻게 세울 것인가?\n- 도시 빅데이터·AI 분석의 성과를 **국제 비교·ODA 협력**으로 확장하기 위한 공공 플랫폼·표준은 누가 주도할 것인가?'},
]

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
    if subsystem == 'worldcities':
        out.extend(copy.deepcopy(d) for d in WC_DOCS)
        out.extend(copy.deepcopy(d) for d in WC_DISCUSSIONS)
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

@app.get('/graph')
@login_required
def graph_page():
    return render_template('graph.html')

@app.get('/api/graph')
@login_required
def api_graph():
    """접근 가능한 연구 DB(worldcities·urbanrobotics)의 노드+엣지(slug 교차참조) 지식그래프."""
    u = current()
    subs = [s for s in ('worldcities', 'urbanrobotics') if can_access_system(u, s)]
    recs = []
    for s in subs:
        recs += _load_records(s)
    # 노드: slug → {id,label,kind,subsystem}
    bysub = {}
    for s in subs:
        for r in _load_records(s):
            bysub[r['slug']] = s
    nodes, slugset = [], set()
    for r in recs:
        slugset.add(r['slug'])
        nodes.append({'id': r['slug'], 'label': r['title'], 'kind': r['kind'],
                      'subsystem': bysub.get(r['slug'], '')})
    # 엣지: 각 레코드의 필드값 중 다른 노드 slug 와 일치하는 것
    SKIP = {'id', 'slug', 'title', 'kind', 'updated', 'body'}
    edges, seen = [], set()
    for r in recs:
        for k, v in r.items():
            if k in SKIP: continue
            vals = v if isinstance(v, list) else ([v] if isinstance(v, str) else [])
            for item in vals:
                if isinstance(item, str) and item in slugset and item != r['slug']:
                    key = tuple(sorted((r['slug'], item)))
                    if key in seen: continue
                    seen.add(key)
                    edges.append({'from': r['slug'], 'to': item, 'label': k})
    return jsonify(nodes=nodes, edges=edges, subsystems=subs)

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
        usys = [s for s in (u0.get('systems') or '').split(',') if s]
        if system == 'book':   # 단행본 허브: 세 책 중 하나라도 권한이 있으면 입장
            ok = r['role'] == 'superadmin' or 'book' in usys or 'globalbook' in usys or 'smartcity' in usys
        else:
            ok = r['role'] == 'superadmin' or system in usys
        if not ok:
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
    bkey = request.args.get('book') or 'growing'
    need = {'global': 'globalbook', 'smart': 'smartcity'}.get(bkey, 'book')   # 책별 접근 권한 분리
    if not can_access_system(u, need):
        return jsonify(error='이 단행본에 접근할 권한이 없습니다.'), 403
    bk = book_by_key(bkey)                                  # 'growing'(기본) | 'global' | 'smart'
    ov = load_overrides(); orders = load_order()
    chs = []
    for c in bk['chapters']:
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
    return jsonify({'chapters': chs, 'meta': bk['meta']})

@app.post('/api/order')
@login_required
def set_order():
    u = current(); j = request.get_json(force=True)
    ch = int(j.get('chapter', -1)); seq = [int(x) for x in j.get('order', [])]
    if not can_edit(u, ch): return jsonify(error='이 장을 편집할 권한이 없습니다.'), 403
    chap = find_chapter(ch)
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
    chap = find_chapter(ch)
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
    chap = find_chapter(ch)
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

# ---------- 한영 용어 사전 (가상 장 GLOSSARY_CH, 메모=comments·수정=overrides 재사용) ----------
GLOSS_ADDED_OFFSET = 100000   # 사용자 추가 용어 id = OFFSET + DB row id (기본 660건 id와 충돌 방지)

def _gloss_letter(en, kr):
    for ch in (en or kr or ''):
        if ch.isascii() and ch.isalpha():
            return ch.upper()
    return '#'

def _load_added_terms():
    return [dict(r) for r in db().execute(
        'SELECT id,en,kr,letter,creator_name FROM glossary_terms ORDER BY id').fetchall()]

def _find_term(tid):
    """기본 용어(GLOSSARY) 또는 사용자 추가 용어를 통합 조회. {id,en,kr} 또는 None."""
    if tid >= GLOSS_ADDED_OFFSET:
        r = db().execute('SELECT en,kr FROM glossary_terms WHERE id=?',
                         (tid - GLOSS_ADDED_OFFSET,)).fetchone()
        return {'id': tid, 'en': r['en'], 'kr': r['kr']} if r else None
    return next((t for t in GLOSSARY if t['id'] == tid), None)

@app.get('/api/glossary')
@login_required
def glossary_get():
    u = current()
    ov = load_overrides()
    out = []
    def apply_ov(tid, en, kr):
        e = ov.get((GLOSSARY_CH, tid))
        if e:
            try:
                d = json.loads(e); return d.get('en', en), d.get('kr', kr), True
            except Exception:
                pass
        return en, kr, False
    for t in GLOSSARY:
        en, kr, edited = apply_ov(t['id'], t['en'], t['kr'])
        out.append({'id': t['id'], 'letter': t['letter'], 'en': en, 'kr': kr,
                    'edited': edited, 'added': False})
    for r in _load_added_terms():
        tid = GLOSS_ADDED_OFFSET + r['id']
        en, kr, edited = apply_ov(tid, r['en'], r['kr'])
        out.append({'id': tid, 'letter': r['letter'] or _gloss_letter(en, kr), 'en': en, 'kr': kr,
                    'edited': edited, 'added': True, 'by': r['creator_name']})
    return jsonify(terms=out, canEdit=can_edit(u, GLOSSARY_CH), canAdd=True, chapter=GLOSSARY_CH)

@app.post('/api/glossary/add')
@login_required
def glossary_add():
    """새 용어 추가 — 모든 사용자 가능."""
    u = current()
    j = request.get_json(force=True) or {}
    en = (j.get('en') or '').strip(); kr = (j.get('kr') or '').strip()
    if not en and not kr:
        return jsonify(error='영문·국문 중 하나 이상을 입력하세요.'), 400
    letter = _gloss_letter(en, kr)
    con = db()
    nid = con.insert('INSERT INTO glossary_terms(en,kr,letter,creator_email,creator_name,ts) VALUES(?,?,?,?,?,?)',
                     (en, kr, letter, u['email'], u['name'], now()))
    con.commit()
    return jsonify(ok=True, id=GLOSS_ADDED_OFFSET + nid, en=en, kr=kr, letter=letter,
                   added=True, by=u['name'])

@app.delete('/api/glossary/<int:tid>')
@login_required
def glossary_delete(tid):
    """용어 삭제 — 모든 사용자 가능(사용자 추가 용어에 한함, 기본 660건은 보호)."""
    if tid < GLOSS_ADDED_OFFSET:
        return jsonify(error='기본 용어집 항목은 삭제할 수 없습니다.'), 400
    con = db()
    row = con.execute('SELECT id FROM glossary_terms WHERE id=?', (tid - GLOSS_ADDED_OFFSET,)).fetchone()
    if not row:
        return jsonify(error='대상 용어를 찾을 수 없습니다.'), 404
    con.execute('DELETE FROM glossary_terms WHERE id=?', (tid - GLOSS_ADDED_OFFSET,))
    con.execute('DELETE FROM comments WHERE chapter=? AND block=?', (GLOSSARY_CH, f'b{GLOSSARY_CH}_{tid}'))
    con.execute('DELETE FROM overrides WHERE chapter=? AND blk=?', (GLOSSARY_CH, tid))
    con.commit()
    return jsonify(ok=True)

@app.post('/api/glossary/edit')
@login_required
def glossary_edit():
    u = current()
    if not can_edit(u, GLOSSARY_CH):
        return jsonify(error='용어 사전 수정은 관리자만 가능합니다.'), 403
    j = request.get_json(force=True) or {}
    try:
        tid = int(j.get('id', -1))
    except (TypeError, ValueError):
        return jsonify(error='잘못된 요청입니다.'), 400
    term = _find_term(tid)
    if not term:
        return jsonify(error='대상 용어를 찾을 수 없습니다.'), 404
    en = (j.get('en') or '').strip(); kr = (j.get('kr') or '').strip()
    if not en and not kr:
        return jsonify(error='영문·국문 중 하나 이상을 입력하세요.'), 400
    oldd = {'en': term['en'], 'kr': term['kr']}
    cur = load_overrides().get((GLOSSARY_CH, tid))
    if cur:
        try: oldd = json.loads(cur)
        except Exception: pass
    newd = {'en': en, 'kr': kr}
    if newd == oldd:
        return jsonify(ok=True, unchanged=True, en=en, kr=kr)
    con = db()
    _set_override(con, GLOSSARY_CH, tid, json.dumps(newd, ensure_ascii=False), u['email'])
    con.execute('INSERT INTO editlog(chapter,blk,oldv,newv,editor,name,role,ts) VALUES(?,?,?,?,?,?,?,?)',
                (GLOSSARY_CH, tid, f"{oldd.get('en','')} / {oldd.get('kr','')}",
                 f"{en} / {kr}", u['email'], u['name'], u['role'], now()))
    con.commit()
    return jsonify(ok=True, en=en, kr=kr)

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
    chap = find_chapter(ch)
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
    chap = find_chapter(ch)
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
    label = {c['order']: c['label'] for c in all_chapters()}
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
    chapters = [{'order': c['order'], 'label': c['label'], 'titleKR': c['titleKR'],
                 'book': ('smart' if c['order'] >= 2000 else 'global' if c['order'] >= 1000 else 'growing')} for c in all_chapters()]
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
