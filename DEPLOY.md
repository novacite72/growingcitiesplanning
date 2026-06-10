# 클라우드 배포 가이드 — Render(무료) + Neon Postgres(무료)

Mac과 무관하게 24시간 운영. 메모·계정 데이터는 Neon Postgres에 영구 보존됩니다.
코드는 이미 SQLite(로컬)/Postgres(클라우드) 자동 전환되도록 준비돼 있습니다.

## 0. 무료 계정 가입
- GitHub (github.com)
- Render (render.com)
- Neon (neon.tech)

## 1. Neon Postgres 만들기 (데이터 보존소)
1. neon.tech 로그인 → **New Project** (Region: Singapore / AWS ap-southeast 권장)
2. 생성 후 **Connection string** 복사 — 형태:
   `postgresql://USER:PASSWORD@ep-xxxx.ap-southeast-1.aws.neon.tech/dbname?sslmode=require`
   → 이 값이 곧 **DATABASE_URL** 입니다.

## 2. GitHub에 코드 올리기
이 폴더에 git 커밋은 만들어 두었습니다. GitHub에서 빈 저장소(예: `growing-cities-book`)를 만든 뒤:
```bash
cd ~/seoul_urban_book_app
git remote add origin https://github.com/<본인계정>/growing-cities-book.git
git branch -M main
git push -u origin main
```
(이미지 약 88MB 포함 → 업로드 1~2분 소요)

## 3. Render 배포
1. render.com → **New +** → **Blueprint** → 위 GitHub 저장소 선택
   - `render.yaml`을 자동 인식합니다. (수동이면 New → Web Service)
2. **환경변수(Environment)** 입력:
   - `DATABASE_URL` = (1단계 Neon 연결 문자열)
   - `ADMIN_EMAIL` = `junyoung.choi@si.re.kr`  *(선택, 미입력 시 기본값 동일)*
   - `ADMIN_PASSWORD` = `2969`  *(선택)*
   - 나머지(SECRET_KEY·PUBLIC·REG_OPEN·PYTHON_VERSION)는 render.yaml에 자동 포함
3. **Create** → 빌드·배포(수 분). 완료되면 `https://growing-cities-book.onrender.com` 접속 확인.
   - 첫 실행 시 Neon에 테이블 생성 + 계정 23개 자동 시드(관리자/집필 7/감수 15).

## 4. 도메인 연결 — growingcitiesplanning.org
1. Render → 해당 서비스 → **Settings → Custom Domains** → `growingcitiesplanning.org` 와 `www.growingcitiesplanning.org` 추가
   - Render가 알려주는 연결 대상(예: `growing-cities-book.onrender.com`) 확인
2. **Cloudflare DNS**에서 기존 *터널 CNAME을 Render로 교체*:
   - 현재: `@`(apex), `www` → (Cloudflare Tunnel)  ← 이 두 CNAME을 수정
   - 변경: `@`, `www` → `growing-cities-book.onrender.com` (CNAME, Cloudflare가 apex CNAME 평탄화 지원)
   - Proxy 상태: **DNS only(회색 구름)** 권장 → Render 인증서 사용. (주황 구름 유지 시 SSL/TLS 모드를 **Full**로)
3. 수 분 뒤 `https://growingcitiesplanning.org` 가 Render로 연결됩니다.

## 5. 기존 자체호스팅(Mac 터널) 정리
Render 전환을 확인한 뒤 Mac 쪽을 끕니다:
```bash
cd ~/seoul_urban_book_app && ./uninstall_autostart.sh && ./stop_public.sh
```
(원하면 Cloudflare 대시보드 Zero Trust → Tunnels 에서 `seoul-book` 터널도 삭제)

## 비용 / 주의
- **Render Free 0원**: 15분 미사용 시 잠들고, 첫 접속이 ~50초 지연(cold start). 항상 깨어 있게 하려면
  ① Render Starter($7/월) 업그레이드, 또는 ② UptimeRobot 등으로 5분 간격 핑.
- **Neon Free 0원**: 0.5GB — 메모/계정 보관에 충분. **재배포해도 데이터 보존**.
- 보안: 공개 도메인이므로 초기 비밀번호(123456 / 2969) 변경을 참여자에게 꼭 안내(미발간 내부 원고).

## 원고가 바뀌면
로컬에서 `pip install -r requirements-extract.txt && python3 extract.py` 로 `data.json`·`static/img/` 갱신 후
git commit & push → Render 자동 재배포.
