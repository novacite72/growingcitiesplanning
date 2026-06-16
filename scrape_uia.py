# -*- coding: utf-8 -*-
"""UIA Yearbook(international organizations) 전량 수집 — 동시성·중단/재개.
출력: ./_uia_full.json (uiaid dedup) · 진행: ./_uia_done.json (완료 페이지 집합, 앱 폴더라 영속).
재실행하면 미완료 페이지만 처리. (gitignore: _uia_*)"""
import urllib.request, urllib.parse, re, html, time, json, os
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '_uia_full.json')
DONE = os.path.join(HERE, '_uia_done.json')
MAXPAGE = 3199
WORKERS = 6

def fetch(page):
    q = urllib.parse.urlencode({'page': page})
    req = urllib.request.Request('https://uia.org/ybio?' + q, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')

def parse(h):
    tb = re.search(r'<tbody>(.*?)</tbody>', h, re.S)
    if not tb:
        return []
    out = []
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', tb.group(1), re.S):
        c = dict(re.findall(r'views-field-([a-z0-9-]+)[^"]*"[^>]*>(.*?)</td>', r, re.S))
        g = lambda k: html.unescape(re.sub('<[^>]+>', '', c.get(k, ''))).strip()
        nm = g('name-en')
        if not nm:
            continue
        out.append({'name': nm, 'acronym': g('abbr-en'), 'founded': g('birthyear'),
                    'city': g('addcity-1-en'), 'country': g('addpays-1-en'),
                    'type1': g('type1'), 'type2': g('type2'), 'uiaid': g('arevid')})
    return out

def getpage(page):
    for _ in range(4):
        try:
            return page, parse(fetch(page))
        except Exception:
            time.sleep(1.5)
    return page, None

seen, done = {}, set()
if os.path.exists(OUT):
    for o in json.load(open(OUT, encoding='utf-8')):
        seen[o.get('uiaid') or o['name']] = o
if os.path.exists(DONE):
    done = set(json.load(open(DONE)))
todo = [p for p in range(MAXPAGE) if p not in done]
print(f'resume: {len(done)} done, {len(todo)} to go, {len(seen)} unique', flush=True)

def save():
    json.dump(list(seen.values()), open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(sorted(done), open(DONE, 'w'))

processed = 0
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = {ex.submit(getpage, p): p for p in todo}
    for fut in as_completed(futs):
        page, rows = fut.result()
        if rows is None:
            print(f'page {page} FAILED', flush=True); continue
        for o in rows:
            seen[o.get('uiaid') or o['name']] = o
        done.add(page); processed += 1
        if processed % 100 == 0:
            save(); print(f'{processed}/{len(todo)} · unique {len(seen)}', flush=True)
save()
print(f'DONE · {len(done)} pages · unique {len(seen)}', flush=True)
