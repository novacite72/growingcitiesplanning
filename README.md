# 성장하는 도시를 위한 도시계획 — 원고 검수 웹서비스

서울연구원 글로벌 연구협력센터 단행본(18장)의 본문·그림·사례를 열람하고,
이메일 로그인 기반으로 **관리자·집필자·감수자**가 원고에 메모(검토 의견)를 남기는 웹 서비스.

## 구성
- `extract.py` — 원문 docx 18개에서 제목·소제목·본문·이미지·사례를 추출 → `data.json` + `static/img/`
- `app.py` — Flask 백엔드(이메일 로그인, 역할, 메모, 사용자 관리). DB는 SQLite(`book.db`)
- `templates/index.html`, `static/app.js`, `static/style.css` — 프론트엔드 SPA

## 로컬 실행
```bash
pip install -r requirements.txt
python3 extract.py          # 최초 1회(원고 갱신 시 재실행)
python3 app.py              # http://localhost:8000
```
최초 실행 시 관리자 계정이 자동 생성됩니다(콘솔에 출력).
기본값: `admin@seoul.re.kr` / `seoul1234`  → 로그인 후 비밀번호 변경 권장.
환경변수 `ADMIN_EMAIL`, `ADMIN_PASSWORD`로 변경 가능.

## 🌐 운영 중인 고정 주소
- **https://growingcitiesplanning.org** (= www 동일) — Cloudflare named tunnel + Universal SSL
- 구성: gunicorn(:8000, PUBLIC=1) ← cloudflared named tunnel(`cloudflared.yml`, 터널 `seoul-book`)
- **부팅 자동시작 등록됨**(launchd): `re.si.seoulbook.app`(앱) + `re.si.seoulbook.tunnel`(터널)
  - 수동 실행: `./serve_named.sh` · 자동시작 재설치/해제: `./install_autostart.sh` / `./uninstall_autostart.sh`
- ⚠️ **Mac이 켜져 있고 잠들지 않아야** 접속됩니다(셀프호스팅). 24시간 운영하려면 시스템 설정에서 잠자기 해제(또는 `caffeinate -s`) 권장. Mac 독립 운영이 필요하면 클라우드 배포로 이전.

### 임시 공개(도메인 불필요)
```bash
./serve_public.sh      # 임시 HTTPS URL (https://xxxx.trycloudflare.com, 재실행 시 변경)
./stop_public.sh
```
- 별도 서버·도메인·포트포워딩 없이 즉시 외부 공개 URL이 생성됩니다(무료 Cloudflare quick tunnel, `bin/cloudflared`).
- 앱은 터널 뒤에서 동작하도록 `ProxyFix`로 스킴/호스트/IP를 인식하고, `PUBLIC=1`일 때 **Secure 쿠키(HTTPS 전용)** 를 사용합니다.
- **주의(임시 URL)**: quick tunnel URL은 실행할 때마다 바뀌고, 프로세스가 종료되면 끊깁니다.
  고정 주소가 필요하면 ① Cloudflare 계정으로 *named tunnel*(`cloudflared tunnel create` + DNS 연결),
  또는 ② 서울연구원/클라우드 서버에 배포(`gunicorn` + nginx + 도메인)하세요.

### 일반 서버 배포
```bash
PUBLIC=1 gunicorn -w 2 --threads 8 -b 0.0.0.0:8000 app:app   # nginx 등 HTTPS 리버스 프록시 뒤
```
- 정적 이미지(약 88MB)는 `static/img/`에서 서빙. `secret.key`·`book.db`는 외부 노출 금지.

## 공개 시 보안 점검 (중요)
- 원고는 **미발간 내부 자료**입니다. 공개 URL은 추측이 어렵지만 누구나 접속하면 로그인 화면이 보입니다.
- **초기 비밀번호(123456 / 2969)를 반드시 변경**하도록 안내하세요(우상단 메뉴 → 비밀번호 변경).
- 로그인 무차별 시도 방지: IP당 5분 내 8회 실패 시 차단(내장).
- 감수자 자가가입을 막으려면 `REG_OPEN=0` 환경변수로 실행(관리자 발급만 허용).

## 계정 / 로그인
- **관리자**: 이메일 `junyoung.choi@si.re.kr` / 비밀번호 `2969` (별명 "관리자"). env `ADMIN_EMAIL`,`ADMIN_PASSWORD`로 변경 가능.
- **집필자·감수자**: 배정표 기준 계정이 자동 생성됩니다. **로그인 ID = 본인 이름**, 초기 비밀번호 `123456` → 로그인 후 비밀번호 변경 권장.
- **자가 가입**: 새 감수자는 로그인 화면 "계정 만들기"로 직접 등록(이메일·이름·비밀번호·역할).
- 메모에는 **로그인 계정의 이름**이 표시됩니다.
- 계정 시드는 `book.db`가 없을 때 1회 수행됩니다. 명단을 바꾸려면 `app.py`의 `AUTHORS`/`REVIEWERS` 수정 후 `book.db` 삭제→재시작.

## 역할과 메모 권한
- **관리자(admin)**: 모든 메모 열람, 사용자 관리(추가·역할변경·삭제)
- **집필자(author)**: 모든 메모 열람, 해결 표시
- **감수자(reviewer)**: 본인이 작성한 메모만 열람
- 메모 작성: 세 역할 모두 가능 / 메모 확인(전체): 관리자·집필자

## 이미지 배치
`extract.py`는 문서 전체(표·텍스트박스 내부 포함)를 순서대로 순회해 본문 사이에
그림·사진과 캡션을 원위치에 배치합니다. 단, 17·18장(서식적용본)은 원본에 그림이
본문 삽입되지 않고 관계로만 남아 있어 장 끝의 "그림·사진" 섹션에 모읍니다.
