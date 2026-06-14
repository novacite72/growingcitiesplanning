# growingcitiesplanning.org — 시스템 구축·관리 가이드 (인계 문서)

> 목적: 새 대화창에서도 이 플랫폼 구축을 **이어서** 진행하기 위한 자세한 컨텍스트.
> 새 창에서 이 파일을 첨부하면 전체 구조·배포·운영을 바로 파악할 수 있다.
> 운영자: 서울연구원 최준영 박사(junyoung.choi@si.re.kr). 마지막 갱신: 2026-06-14, 버전 **v0.27**.

---

## 0. 한눈에 보기

서울연구원 최준영 박사의 **개인 글로벌 도시연구 플랫폼**. 하나의 도메인 아래 4개 서브시스템 + 부가 페이지.

```
이용자 → Cloudflare(DNS·TLS) → Render(Flask/gunicorn) → Neon(PostgreSQL)
포털(/) ─┬─ 🌐 세계도시 연구 DB        /worldcities   (open)
         ├─ 🤖 도시로봇·HRI 연구 DB     /urbanrobotics (open)
         ├─ 🤝 세계대도시협력(게시판)    /wpsc          (superadmin) + /wpsc/itinerary
         └─ 📘 영문단행본 감수 SPA       /book          (역할기반)
부가:  /architecture(+/about) 공개  ·  /graph 지식그래프(login)
지식기반(로컬): Zotero→Obsidian(vault)→kb_build→kb_publish(Import API)→Neon  / kb_extract(무키 LLM 추출)
```

---

## 1. 저장소·인프라·자격증명

| 항목 | 값 |
|---|---|
| 앱 저장소(GitHub) | `novacite72/growingcitiesplanning` (Flask 앱) |
| 지식기반 저장소(GitHub, 비공개) | `novacite72/growingcities-kb` (Obsidian vault + 파이프라인) |
| 호스팅 | **Render** 무료 웹서비스, 서비스ID `srv-d8kht6f7f7vs73drsocg`, `https://growing-cities-book.onrender.com` |
| DB | **Neon PostgreSQL** (host `ep-polished-heart-aodsncr5-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb`) |
| 도메인 | **growingcitiesplanning.org** (+www), Cloudflare DNS only(회색), apex/www CNAME→onrender |
| 로컬 앱 경로 | `/Users/jychoi/seoul_urban_book_app` |
| 로컬 KB 경로 | `/Users/jychoi/growingcities-kb` |
| 수퍼관리자 | `junyoung.choi@si.re.kr` / pw·토큰·DATABASE_URL은 **auto-memory(MEMORY → project_growing_cities_book.md)** 와 `~/growingcities-kb/.kb.env`(gitignore) 에 저장됨 |

> ⚠️ **비밀(GitHub PAT, Neon 비밀번호, 수퍼관리자 pw)** 은 이 문서에 적지 않는다. 새 대화창에는
> 프로젝트 메모리가 자동 로드되어 이미 포함되어 있고, KB 발행용은 `~/growingcities-kb/.kb.env` 에 있다.
> git push 시 토큰은 URL에 1회만 사용하고 **즉시 `git remote set-url origin <토큰없는 URL>` 로 제거**한다.

---

## 2. 배포 워크플로 (표준 절차)

코드 수정 → 커밋 → push → Render 자동 재배포(~75초) → curl 검증.

```bash
cd ~/seoul_urban_book_app
git add -A && git commit -m "feat: vX.YZ ..."   # 끝에 Co-Authored-By: Claude ...
git push https://novacite72:<PAT>@github.com/novacite72/growingcitiesplanning.git main:main
# 배포 대기(정적 app.js의 버전 마커로 폴링)
for i in $(seq 1 40); do curl -s https://growingcitiesplanning.org/static/app.js | grep -q "vX.YZ" && break; sleep 15; done
```

- **버전 올릴 때**: `static/app.js` 의 `CHANGELOG` 배열 맨 앞에 새 항목 추가(날짜·항목). 도움말 게시판에 표시됨.
- **검증**: curl로 라우트 status·API JSON 확인. 로그인은
  `curl -s -c /tmp/sa.txt -X POST .../api/login -d '{"email":"junyoung.choi@si.re.kr","password":"<pw>"}'`.
- **PDF/한글**: 셸 heredoc에서 한글 깨지면 `export PYTHONIOENCODING=utf-8 LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8`.

### 로컬 개발/미리보기
- 로컬 실행: `PUBLIC=0 PORT=8000 python3 app.py` (백그라운드 nohup). 종료: `lsof -ti:8000 | xargs kill`.
- **Preview 도구 주의**: `preview_start`는 **루트 `~/.claude/launch.json`** 을 읽는다(앱폴더의 것 아님). 미리보기로 Flask를 띄우려면 루트 launch.json에 `{"name":"book-flask","runtimeExecutable":"python3","runtimeArgs":["/Users/jychoi/seoul_urban_book_app/app.py"],"port":8000}` 항목을 임시 추가하고, 끝나면 제거(원복). 포트 8000 충돌 시 먼저 kill.
- 미리보기 로그인: `preview_eval` 로 `fetch('/api/login',{...})` 후 `location.href='/worldcities'` 등.

---

## 3. 앱 저장소 파일 맵 (`~/seoul_urban_book_app`)

| 파일 | 역할 |
|---|---|
| `app.py` | Flask 본체. DB 추상화(SQLite/PG 자동), 라우트·API·권한·init_db·시드. |
| `dbseed.py` | 연구 DB 초기 시드(`RECORDS`). dbrecords 비었을 때만 1회 적재. |
| `dbgen.py` | 생성기 3종(hri-study-design·observation-codebook·experiment-protocol) → Markdown. |
| `wpscdata.py` | WPSC 게시판 데이터(`WPSC` dict: trips/visits/partners/progress, `CATEGORIES`). |
| `extract.py` | 단행본 docx→data.json 추출(strip_cover·fignum_shift). 단행본 원고 갱신용. |
| `templates/portal.html` | 포털 첫화면(UN-Habitat풍, 4서브시스템 카드, 로그인 모달, 아키텍처 배너). |
| `templates/index.html` + `static/app.js` + `static/style.css` | 단행본 감수 SPA. |
| `templates/worldcities.html` | 세계도시 DB SPA(vanilla JS). |
| `templates/urbanrobotics.html` | 도시로봇·HRI DB SPA(+생성기 폼3). |
| `templates/wpsc.html` | WPSC 게시판 SPA(3구분 탭+진행상황 타임라인). |
| `templates/architecture.html` | 공개 아키텍처 페이지. |
| `templates/graph.html` | 지식그래프(vis-network CDN). |
| `wpsc_itinerary.html` | 기존 WPSC 출장 일정(367KB, send_file). `/wpsc/itinerary`. |
| `static/img/` | 단행본 이미지 169장. |
| `requirements.txt` | Flask·Werkzeug·gunicorn·psycopg2-binary·Pillow. |
| `render.yaml`·`runtime.txt`(py3.11) | Render 배포 설정. |

### app.py 핵심 구조
- **DB 래퍼**: `?`→`%s` 변환, DictCursor, `insert()` RETURNING. `IS_PG = bool(DATABASE_URL)`.
- **테이블**: users·comments·assignments·overrides·editlog·chorder·images·**dbrecords**(연구DB). init_db가 PG/SQLite 양쪽 생성·마이그레이션·시드.
- `dbrecords(id, subsystem, kind, slug, title, data=JSON TEXT, updated, UNIQUE(subsystem,slug))`.
- **역할/시스템**: `ROLES={superadmin,admin,author,reviewer}`, `ADMIN_ROLES=('admin','superadmin')`,
  `SYSTEMS={worldcities,urbanrobotics,wpsc,book}`, `DB_SUBSYSTEMS={worldcities,urbanrobotics}`.
  `users.systems`(콤마구분). `can_access_system(u,sys)`(superadmin=True). `super_required` 데코레이터.
- **주요 API**: `/api/login`(system 선택 가능)·`/api/me`(isSuper·systems)·`/api/systems`·
  `/api/db/<sys>`·`/api/db/<sys>/<slug>`(교차참조 index)·`/api/generate/<tool>`·
  `/api/admin/import`(super, slug upsert, prune)·`/api/admin/export`(super)·`/api/wpsc`·`/api/graph`.
- **렌더 주의**: 템플릿은 `render_template`(Jinja2)이라 JS에서 `{{ }}`·`{% %}` 금지(JS는 `${...}` 사용). `Response`는 flask 최상위 import.

---

## 4. 서브시스템별 상세

### 4-1. 세계도시 연구 DB (`worldcities`, teal `#0a6e8c`, 🌐)
- kind: `city·case·policy·topic`. 현재 city 23 / case 5 / policy 4 / topic 20.
- 검색·유형/지역 필터·카드그리드·상세(한국어 라벨)·교차참조 칩(xref-chip)·`?slug=` 딥링크·**서술형 위키 본문(body)** 렌더.
- 2026-06-14 스마트도시론(2025/2026·UD캠프) 강의로 신규 도시13·토픽10 추가.

### 4-2. 도시로봇·HRI 연구 DB (`urbanrobotics`, purple `#6d4bb6`, 🤖)
- kind: `robottype·robotcase·hri·studydesign·observation·experiment·instrument·policyissue`.
- **연구 산출물 생성기 3종**(연구설계·관찰 코딩북·실험 프로토콜) + Markdown 복사/다운로드.
- 서울 항목은 최준영 실제 연구(성수동 ADR 보행자 관찰·전문가 AHP·perceived safety, 한-캐 서울-토론토 ADR 공동연구)와 연결. 참고문헌 4건(Choi2026·Macrorie2021·Saaty1980·Weinberg2023).

### 4-3. 세계대도시협력 WPSC (`wpsc`, teal `#138f8f`, 🤝) — **게시판**
- `/wpsc` = 게시판 SPA(3구분 탭 **국외출장/연구원내원/글로벌협력기관** + 진행상황 타임라인), 데이터 `wpscdata.py`, API `/api/wpsc`.
- 국외출장 카드 `wpsc=true` → "📅 WPSC 출장 일정 보기" → `/wpsc/itinerary`(기존 일정 페이지).
- 수퍼관리자 전용(can_access_system wpsc=superadmin). 내용=대외협력 폴더 정리.

### 4-4. 영문단행본 (`book`, han `#1d6fb8`, 📘)
- 18장 본문·그림·메모(스레드)·감수·직접편집(그림 교체 포함). 역할별 권한·장(章) 배정.
- 단행본 원고 갱신: 로컬 `python3 extract.py` → git push → Render 재배포.

### 4-5. 공개 아키텍처 (`/architecture`,`/about`) — 로그인 불필요
- 4서브시스템 구조도·로컬 우선 KB 파이프라인·기술스택·권한모델·지식그래프 링크. 포털 상단/배너에서 진입.

### 4-6. 지식그래프 (`/graph`, login_required)
- `/api/graph`: 접근 가능한 worldcities·urbanrobotics 노드 + 필드값이 다른 노드 slug면 엣지(SKIP id/slug/title/kind/updated/body). 노드 클릭→`/worldcities|urbanrobotics?slug=`.
- vis-network CDN 9.1.9. teal=worldcities, purple=urbanrobotics. 현재 94노드/123엣지.

### 통일된 네비게이션 (v0.27)
- **전 시스템 동일 드롭다운** `.sysswitch`/`#sysSwitch`/`#ssBtn`/`#ssMenu` (5링크 + 🕸 지식그래프), **수퍼관리자만 표시**. book은 헤더 드롭다운(style.css `.ss*` --han), wpsc/graph는 네이티브.
- **무재로그인**: 수퍼관리자는 세션 유지로 모든 서브시스템 재로그인 없이 이동. 포털은 `/api/me`로 로그인 감지→접근권한 보유 시 로그인모달 없이 '바로 입장'.

---

## 5. 지식기반 파이프라인 (`~/growingcities-kb`)

**로컬 우선**: Obsidian에서 작성 → 빌드 → 발행. 노트 1개 = dbrecords 1개. `[[wikilink]]`/slug = 엣지.

| 파일 | 역할 |
|---|---|
| `vault/<subsystem>/<kind>/<slug>.md` | 노트(YAML frontmatter + 서술형 본문). |
| `kb_bootstrap.py` | dbseed.RECORDS(또는 live export)→ vault 노트 1회 생성. slug값은 `[[ ]]`로 감싸 그래프링크화. |
| `kb_build.py` | vault→`build/records.json`. data의 `[[slug]]`→slug 정규화, 본문 `[[ ]]` 보존, slug중복·본문링크 검사, `zotero/references.bib` citekey→서지 확장. `_`폴더(예 `_literature`) 제외. |
| `kb_publish.py` | records.json→login 후 `/api/admin/import`. `--prune`(삭제동기화)·`--local`. `.kb.env`에서 KB_EMAIL/KB_PASSWORD/KB_BASE. |
| `kb_extract.py` | **무키 LLM 추출**(아래 §5b). |
| `zotero/references.bib` | Better BibTeX 내보내기 자리. citekey를 노트 `sources`에 적으면 빌드시 서지 확장. 표준문헌(TAM·UTAUT·Godspeed) + 사용자연구 + 한-캐 ADR 문헌. |
| `.obsidian/` | Vault 설정 + Citations 플러그인(v0.4.5) 사전구성(BibLaTeX, path=zotero/references.bib). |
| `.kb.env`(gitignore) | KB_BASE/KB_EMAIL/KB_PASSWORD. |

**일상 루프**: Obsidian 작성 → `python3 kb_build.py` → `python3 kb_publish.py` → `git push`.

### 5b. kb_extract.py — 키 없이 지식그래프 추출
링크·논문·기사 → (개체–관계–개체) 트리플 추출 → 기존 slug 정규화 → `relatedExtracted` 보강.

| provider | 방식 | 키 |
|---|---|---|
| `claude`(기본) | Claude Code 헤드리스 `claude -p`(구독 사용) | **불필요** |
| `ollama` | 로컬 모델(오프라인). `ollama pull llama3.1` | **불필요** |
| `api` | Anthropic API(`ANTHROPIC_API_KEY`) | 필요 |

```bash
python3 kb_extract.py --url <URL>            # 검토만(무키)
python3 kb_extract.py --file paper.pdf --apply   # relatedExtracted 안전병합 + stub
# 반영 후: python3 kb_build.py && python3 kb_publish.py
```
- 노드 인덱스(slug)·온톨로지를 LLM에 주고 `{entities, triples}` 추출. `--apply`는 기존 구조화 필드 불변, `relatedExtracted`(슬러그 목록)에만 병합 → 사이트가 교차참조 칩으로 렌더.
- ⚠️ 이 추출용 `claude`/`ollama` CLI는 **사용자 Mac 환경에서** 동작(작업 샌드박스엔 미설치). Claude Code 데스크톱 로그인 시 `claude -p` 무키 경로 작동.

### Zotero·Obsidian (설치·연동 완료)
- 둘 다 `/Applications`에 설치(Obsidian 1.12.7, Zotero 9.0.4). Better BibTeX 9.0.28 설치·활성화. Obsidian Citations 플러그인 v0.4.5 설치·활성화·설정 확인.
- Zotero 라이브러리 비어 있어 BBT 자동내보내기는 보류(켜면 curated references.bib 덮어씀). 사용자가 실제 문헌 추가 후 Export(Keep updated)로 연결.
- 컴퓨터 제어 메모: 세션 시작 후 설치된 앱은 request_access 리졸버가 못 찾음 → `lsregister -f`+`open`으로 인식. 브라우저=read tier(클릭불가). 화면기록 권한은 켠 뒤 Claude 앱 재시작 필요.

---

## 6. 데이터 모델 요약

- **연구 DB(worldcities·urbanrobotics)** = `dbrecords` 1테이블. data=JSON. 필드는 camelCase. 배열/스칼라 값이 다른 노드 slug면 교차참조(엣지).
  - cross-ref 필드 예: city.relatedRobotCases·case.relatedRobotCases·studydesign.relatedCases·robotcase.relatedStudyDesigns·sources(citekey 또는 서지문자열)·`relatedExtracted`(추출).
- **WPSC** = `wpscdata.WPSC` 파이썬 dict(코드 시드, 정적). 변경은 wpscdata.py 수정→배포.
- **단행본** = extract.py 산출 data.json + overrides/editlog/comments/images.

---

## 7. 버전 이력(CHANGELOG, app.js)

- v0.27 WPSC 게시판·통일 네비·지식그래프·세계도시 확장(스마트도시론)·무키 추출
- v0.26 서브시스템 간 이동(수퍼관리자 무재로그인)
- v0.25 공개 아키텍처 페이지 + 한-캐 ADR 연구 발행
- v0.24 로컬 우선 지식기반(Import/Export API + 서술형 위키 본문)
- v0.23 두 연구 DB(세계도시·도시로봇) 신설(dbrecords)
- v0.22 단행본 그림 업로드·교체
- v0.2x 통합 포털·역할위계(superadmin)·개인 플랫폼 브랜딩
- v0.1x 본문 편집·되돌리기·블록이동·도움말 게시판

---

## 8. 검증 패턴(반복)
1. 로컬: `python3 -c "import app"` + curl 라우트/ API.
2. 미리보기: launch.json 임시 추가 → preview_start → eval 로그인 → screenshot/eval 검증 → 원복.
3. 배포: push → app.js 버전 마커 폴링 → 라이브 curl(상태·JSON·게이트) → 필요시 Neon 테스트데이터 정리.
4. KB: round-trip(vault→build) 카운트 일치, 발행 멱등(updated N, inserted/deleted 0).

---

## 9. 주의사항(gotchas)
- macOS NFC/NFD 파일명 → `unicodedata.normalize('NFC', ...)`.
- Render 무료 = **ephemeral fs**(재배포 시 업로드 파일 소실) → 사용자 데이터·이미지는 Neon에 저장(images 테이블 base64).
- Render 무료 15분 슬립(첫 접속 ~50s). 상시가동 원하면 UptimeRobot 핑 또는 Starter$7.
- `render_template` 템플릿의 JS에서 `{{`/`}}`/`{%`/`%}` 금지.
- git push 토큰은 1회 사용 후 `git remote set-url origin <토큰없는>` 으로 제거(.git/config 노출 방지).
- PDF 텍스트는 PyPDF2/pdfminer(설치 시), pptx=python-pptx, xlsx=openpyxl. **hwp/hwpx는 일반 추출 불가**(스킵 또는 hwpx-converter 스킬).
- 한글 출력 깨짐 → PYTHONIOENCODING=utf-8.

---

## 10. 미완·향후 작업
- [ ] **벡터(의미)검색**: 보류 중. 각 dbrecords에 임베딩(Voyage AI 권장 또는 로컬모델) → `/api/db/<sys>/search` 코사인. kb_build에 `data.embedding` 생성 자리만 남김. Render 무료(512MB)엔 로컬모델 무거워 Voyage API가 현실적(웹 의미검색 시), 또는 Obsidian 로컬 위주.
- [ ] kb_extract 실사용: 사용자 Mac에서 `claude -p`(무키) 또는 ollama로 링크/논문 추출 → relatedExtracted 보강 → 그래프 확장.
- [ ] Zotero 실제 문헌 채우고 BBT 자동 export 연결.
- [ ] (선택) WPSC 게시판을 dbrecords/관리UI로 전환(현재 wpscdata.py 정적).
- [ ] (선택) 단행본 18장 콘텐츠 보강·영문 최종본.

---

## 11. 새 창에서 이어가기 — 빠른 시작
1. 이 파일을 첨부(또는 프로젝트 메모리 자동 로드 확인).
2. 작업 디렉토리: 앱=`~/seoul_urban_book_app`, KB=`~/growingcities-kb`.
3. 변경→커밋→push(토큰은 메모리에)→버전 폴링→라이브 검증의 **배포 워크플로(§2)** 준수.
4. 새 기능은 해당 SPA(템플릿) + app.py 라우트/API + CHANGELOG(app.js) 갱신 + 검증.
5. 데이터(연구DB)는 KB vault 노트로 작성→`kb_build`→`kb_publish`(또는 직접 `/api/admin/import`).
6. 끝에 프로젝트 메모리(`project_growing_cities_book.md`)에 변경 요약 추가.
