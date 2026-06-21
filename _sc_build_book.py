#!/usr/bin/env python3
# 정제 마크다운(clean/) + 추출 이미지(static/img/sc/) → smartcity_data.json
# 본문 표시 텍스트의 둥근 괄호 ( ) 전면 제거(참고문헌 서지 제외)
import os, re, json

CLEAN = "/Users/jychoi/Desktop/스마트도시_국제협력_단행본/clean"
MANI  = "/Users/jychoi/seoul_urban_book_app/static/img/sc/_manifest.json"
OUT   = "/Users/jychoi/seoul_urban_book_app/smartcity_data.json"
manifest = json.load(open(MANI, encoding='utf-8'))

# (파일, label, part, partname, 이미지 매핑 챕터번호)
ORDER = [
 ("00_서장.md","서장",0,"서장",None),
 ("01.md","1장",1,"제1편 이론편 — 스마트도시 계획의 원리와 기술","1"),
 ("02.md","2장",1,"제1편 이론편 — 스마트도시 계획의 원리와 기술","2"),
 ("03.md","3장",1,"제1편 이론편 — 스마트도시 계획의 원리와 기술","3"),
 ("04.md","4장",1,"제1편 이론편 — 스마트도시 계획의 원리와 기술","4"),
 ("05.md","5장",1,"제1편 이론편 — 스마트도시 계획의 원리와 기술","5"),
 ("06.md","6장",1,"제1편 이론편 — 스마트도시 계획의 원리와 기술","6"),
 ("07.md","7장",1,"제1편 이론편 — 스마트도시 계획의 원리와 기술","7"),
 ("08.md","8장",2,"제2편 실제편 — 스마트도시 국제개발협력의 전략과 사례","8"),
 ("09.md","9장",2,"제2편 실제편 — 스마트도시 국제개발협력의 전략과 사례","9"),
 ("10.md","10장",2,"제2편 실제편 — 스마트도시 국제개발협력의 전략과 사례","10"),
 ("11.md","11장",2,"제2편 실제편 — 스마트도시 국제개발협력의 전략과 사례","11"),
 ("12.md","12장",2,"제2편 실제편 — 스마트도시 국제개발협력의 전략과 사례","12"),
 ("13.md","13장",2,"제2편 실제편 — 스마트도시 국제개발협력의 전략과 사례","13"),
 ("14.md","14장",2,"제2편 실제편 — 스마트도시 국제개발협력의 전략과 사례","14"),
 ("15_맺음말.md","맺음말",3,"맺음말",None),
]

def strip_parens(s):
    # 둥근 괄호와 내용 제거(중첩 대비 반복) + 잔여 공백 정리
    prev=None
    while prev!=s:
        prev=s; s=re.sub(r"\([^()]*\)","",s)
    s=re.sub(r"\s{2,}"," ",s)
    s=re.sub(r"\s+([,.·])",r"\1",s)
    return s.strip()

def debold(s):
    return s.replace("**","").strip()

FIG_HDR = re.compile(r"^###\s*그림")
REF_HDR = re.compile(r"^###\s*참고문헌")
def parse(md):
    lines = md.split("\n")
    title = ""
    body=[]      # 본문 블록(참고문헌 앞)
    refs=[]      # 참고문헌 ref 텍스트
    figcaps=[]   # 그림 제안 캡션
    mode="body"
    for ln in lines:
        t=ln.rstrip()
        if not t.strip():
            continue
        if t.startswith("## ") and not t.startswith("###"):
            title=t[3:].strip(); continue
        if FIG_HDR.match(t):
            mode="fig"; continue
        if REF_HDR.match(t):
            mode="ref"; body.append({"t":"h","level":1,"kr":"참고문헌","en":"References","kind":"refs"}); continue
        if mode=="fig":
            if t.startswith("- "):
                cap=t[2:]
                cap=re.sub(r"^〔그림[^〕]*〕\s*","",cap)   # 라벨 제거
                cap=strip_parens(debold(cap)).strip(" -—")
                if cap: figcaps.append(cap)
            continue
        if mode=="ref":
            if t.startswith("- "):
                refs.append(strip_parens(debold(t[2:])).strip())
            elif t.startswith("#"):
                mode="body"  # 참고문헌 뒤 다른 섹션이면 본문 복귀
            continue
        # 본문
        if t.startswith("#### ") or t.startswith("### "):
            lvl = 2 if t.startswith("####") else 1
            txt = t.lstrip("#").strip()
            txt = strip_parens(debold(txt))
            body.append({"t":"h","level":lvl,"kr":txt,"en":"","kind":"sub"})
        elif t.startswith("> "):
            body.append({"t":"p","text":strip_parens(debold(t[2:]))})
        elif t.startswith("- "):
            body.append({"t":"p","text":"· "+strip_parens(debold(t[2:]))})
        else:
            body.append({"t":"p","text":strip_parens(debold(t))})
    return title, body, refs, figcaps

books=[]
for i,(fn,label,part,partname,imgkey) in enumerate(ORDER):
    md=open(os.path.join(CLEAN,fn),encoding='utf-8').read()
    title, body, refs, figcaps = parse(md)
    # titleKR에서 중복되는 장 라벨 접두 제거(예 "10장 중남미..." → "중남미...", "서장 — ..." → "...")
    title = re.sub(r"^(서장|맺음말)\s*[—-]\s*","",title)
    title = re.sub(r"^\d+장\s+","",title)
    # 참고문헌 ref 블록을 본문 끝 'refs' 헤딩 뒤에 추가
    content=[]
    refhead_idx=None
    for b in body:
        content.append(b)
    # ref 텍스트 블록 부착
    if refs:
        for r in refs: content.append({"t":"ref","text":r})

    # 이미지 삽입: 참고문헌 헤딩 이전 본문 구간에 균등 분산
    imgs = manifest.get(imgkey or "", [])
    # 캡션 매핑
    def cap_for(k):
        if k < len(figcaps): return figcaps[k]
        return f"{label} 관련 자료"
    # refs 헤딩 위치(본문 끝부분) 찾기
    ref_pos=len(content)
    for idx,b in enumerate(content):
        if b.get("t")=="h" and b.get("kind")=="refs":
            ref_pos=idx; break
    # 삽입 가능한 위치(첫 헤딩 이후 ~ ref 이전의 p/h 경계). 단순히 1..ref_pos 사이 균등.
    insert_blocks=[]
    if imgs:
        n=len(imgs)
        span=max(1,ref_pos-1)
        positions=[]
        for k in range(n):
            pos = 2 + int((k+1)*span/(n+1))
            pos=min(max(pos,1),ref_pos)
            positions.append(pos)
        # 뒤에서부터 삽입(인덱스 밀림 방지)
        for k in range(n-1,-1,-1):
            fig=imgs[k]
            blk_img={"t":"img","src":fig["src"]}
            blk_cap={"t":"cap","text":f"〔그림 {imgkey}-{k+1}〕 {cap_for(k)}"}
            content[positions[k]:positions[k]] = [blk_img, blk_cap]
    chars=sum(len(b.get("text","")+b.get("kr","")) for b in content)
    books.append({
        "order":2000+i, "label":label, "num":"", "part":part, "partname":partname,
        "titleKR":title, "titleEN":"", "content":content, "mode":"authored",
        "file":fn, "chars":chars, "images":len(imgs), "tables":0,
        "headings":[b["kr"] for b in content if b.get("t")=="h" and b.get("kind")=="sub"][:8],
        "cases":[], "caseCount":0
    })

data={"meta":{
        "publisher":"서울연구원 · 한양대학교",
        "titleKR":"AI 시대의 스마트도시 계획과 국제협력",
        "titleEN":"Smart City Planning and International Cooperation in the Age of AI"},
      "chapters":books}
json.dump(data,open(OUT,'w'),ensure_ascii=False,indent=1)
print("저장:",OUT)
print("장수:",len(books)," 총이미지:",sum(b["images"] for b in books)," 총글자:",sum(b["chars"] for b in books))
# 괄호 잔존 검사(본문/캡션, ref 제외)
leak=0
for b in books:
    for blk in b["content"]:
        if blk.get("t") in ("p","cap","ref") and "(" in blk.get("text",""):
            leak+=1
        if blk.get("t")=="h" and "(" in blk.get("kr",""):
            leak+=1
print("전체 블록 괄호 잔존(참고문헌 포함):",leak)
