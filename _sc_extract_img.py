#!/usr/bin/env python3
# 스마트도시 단행본용 실제 이미지 추출 v2: 주차 폴더 재귀 탐색 → PPTX 미디어 + 단독 이미지
import os, zipfile, io, json, shutil, glob, unicodedata
from PIL import Image
def nfc(s): return unicodedata.normalize('NFC', s)

BASE = "/Users/jychoi/Library/CloudStorage/OneDrive-개인/교육_평가_자문/01. 교육강의"
L251 = f"{BASE}/2025년/2025년 1학기 스마트도시론"
L252 = f"{BASE}/2025년/2025년 2학기 스마트도시론2"
L261 = f"{BASE}/2026년/2026년1학기_스마트도시론1"
UDC  = f"{BASE}/2026년/2026년 ud 캠프 _ 도시설계와 피지컬ai/피지컬ai와 도시설계"
SUWON = "/Users/jychoi/suwon_15min_analysis/figures"
OUT = "/Users/jychoi/seoul_urban_book_app/static/img/sc"

def folders(root, *prefixes):
    if not os.path.isdir(root): return []
    pref=[nfc(p.rstrip('*')) for p in prefixes]
    out=[]
    for name in os.listdir(root):
        fn=nfc(name)
        if any(fn.startswith(pp) for pp in pref):
            full=os.path.join(root,name)
            if os.path.isdir(full): out.append(full)
    return out

def pptx_in(dirs):
    out=[]
    for d in dirs:
        for r,_,fs in os.walk(d):
            for fn in fs:
                if fn.lower().endswith('.pptx') and not fn.startswith('~$'):
                    out.append(os.path.join(r,fn))
    return out

def files_glob(*pats):
    out=[]
    for p in pats: out += glob.glob(p)
    return [f for f in out if os.path.isfile(f)]

def find_files(root, substr, exts=('.png','.jpg','.jpeg')):
    sub=nfc(substr); out=[]
    if not os.path.isdir(root): return out
    for r,_,fs in os.walk(root):
        for fn in fs:
            n=nfc(fn)
            if sub in n and n.lower().endswith(exts): out.append(os.path.join(r,fn))
    return out

# chapter -> (folder dirs for pptx, standalone files, cap, priority pptx substr)
CH = {
 1:  (folders(L261,"1주차*","2주차*"), [], 5, None),
 2:  (folders(L252,"2주차*","3주차*"), files_glob(f"{SUWON}/map1_pop.png",f"{SUWON}/map2_acc_base.png",f"{SUWON}/map3_gain.png",f"{SUWON}/chart_bca_equity.png",f"{SUWON}/flow.png"), 5, None),
 3:  (folders(L252,"4주차*"), [], 5, None),
 4:  ([UDC], files_glob(f"{UDC}/포스터.png"), 8, "Cesium"),
 5:  (folders(L252,"7주차*"), [], 6, None),
 6:  (folders(L252,"6주차*")+folders(L261,"7주차*"), [], 6, None),
 7:  (folders(L252,"15주차*"), [], 6, None),
 8:  (folders(L261,"9주차*"), [], 6, None),
 9:  (folders(L252,"9주차*","14주차*","10주차*"), [], 6, "조직도"),
 10: (folders(L261,"10주차*","11주차*"), find_files(L261,"presentación"), 8, None),
 11: (folders(L261,"12주차*","13주차*"), [], 8, None),
 12: (folders(L252,"12주차*"), [], 6, None),
 13: (folders(L252,"13주차*"), files_glob(f"{UDC}/20260220_173509.jpg",f"{UDC}/20260220_173515.jpg",f"{UDC}/20260220_173528.jpg"), 8, None),
 14: (folders(L252,"14주차*"), [], 6, None),
}

def save_img(data, dst):
    try:
        im = Image.open(io.BytesIO(data))
        if im.mode in ('RGBA','P','LA','CMYK'): im = im.convert('RGB')
        w,h = im.size
        if min(w,h) < 130: return False
        if max(w,h) > 1600:
            r = 1600/max(w,h); im = im.resize((int(w*r),int(h*r)))
        im.save(dst,'JPEG',quality=82); return True
    except Exception:
        return False

if os.path.isdir(OUT): shutil.rmtree(OUT)
os.makedirs(OUT, exist_ok=True)
manifest={}

for ch,(dirs, sfiles, cap, prio) in CH.items():
    d=os.path.join(OUT,str(ch)); os.makedirs(d,exist_ok=True)
    n=0; items=[]
    for fp in sfiles:
        if n>=cap: break
        try: data=open(fp,'rb').read()
        except: continue
        dst=os.path.join(d,f"{n+1:02d}.jpg")
        if save_img(data,dst): n+=1; items.append({'src':f"img/sc/{ch}/{n:02d}.jpg",'from':os.path.basename(fp)})
    decks=pptx_in(dirs)
    if prio: decks.sort(key=lambda p: (nfc(prio) not in nfc(os.path.basename(p)), -os.path.getsize(p)))
    else:    decks.sort(key=lambda p: -os.path.getsize(p))
    decks=decks[:3]
    media=[]
    for px in decks:
        try: z=zipfile.ZipFile(px)
        except: continue
        ms=[m for m in z.namelist() if m.startswith('ppt/media/') and m.lower().rsplit('.',1)[-1] in ('png','jpg','jpeg')]
        ms.sort(key=lambda m:(int(''.join(c for c in os.path.basename(m) if c.isdigit()) or 0)))
        for m in ms:
            try: data=z.read(m)
            except: continue
            if len(data)<12000: continue
            media.append((os.path.basename(px),m,data))
    seen=set(); media.sort(key=lambda t:-len(t[2]))
    for src,m,data in media:
        if n>=cap: break
        k=len(data)//500
        if k in seen: continue
        seen.add(k)
        dst=os.path.join(d,f"{n+1:02d}.jpg")
        if save_img(data,dst): n+=1; items.append({'src':f"img/sc/{ch}/{n:02d}.jpg",'from':f"{src}:{os.path.basename(m)}"})
    manifest[ch]=items
    print(f"ch{ch}: {n}장  (decks {len(decks)})")

json.dump(manifest,open(os.path.join(OUT,'_manifest.json'),'w'),ensure_ascii=False,indent=1)
print("TOTAL:",sum(len(v) for v in manifest.values()))
