# -*- coding: utf-8 -*-
"""연구 산출물 템플릿 생성기 (Urban Robotics & HRI).

초기 구현은 입력값 기반 템플릿 채움(mock). 동일한 함수 시그니처를 유지하므로
추후 LLM/RAG API로 교체 가능. 모든 함수는 입력 dict를 받아 Markdown 문자열을 반환.
"""

ROBOT_LABEL = {
    'autonomous_delivery_robot': '자율주행 배송로봇 (Autonomous Delivery Robot)',
    'care_robot': '돌봄로봇 (Care Robot)',
}
STUDY_LABEL = {
    'field_observation': '현장 관찰조사 (Field Observation)',
    'video_coding': '영상 코딩 (Video Coding)',
    'field_experiment': '현장 실험 (Field Experiment)',
    'lab_experiment': '실험실 실험 (Lab Experiment)',
    'survey': '설문조사 (Survey)',
    'interview': '심층면접 (Interview)',
    'mixed_methods': '혼합방법 (Mixed Methods)',
}


def _li(items, fallback='(작성 필요)'):
    items = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not items:
        return f'- {fallback}\n'
    return ''.join(f'- {x}\n' for x in items)


def _csv(items):
    return ', '.join([str(x).strip() for x in (items or []) if str(x).strip()]) or '(미지정)'


def gen_hri_study_design(inp):
    rt = inp.get('robotType', 'autonomous_delivery_robot')
    st = inp.get('studyType', 'field_observation')
    constructs = inp.get('hriConstructs', [])
    users = inp.get('targetUsers', [])
    site = inp.get('siteContext', [])
    city = inp.get('targetCity', '')
    rl = ROBOT_LABEL.get(rt, rt)
    sl = STUDY_LABEL.get(st, st)
    ctitle = f'{rl} {sl} 연구설계'
    rqs = [f'{rl} 이용 맥락에서 {c}은(는) 어떻게 형성·변화하는가?' for c in constructs] or \
          [f'{rl}에 대한 이용자 수용성과 지각된 안전은 어떻게 형성되는가?']
    iv = (['로봇 행동 유형(양보/속도/신호 eHMI 유무)', '근접 거리(proxemics)'] if st in ('field_experiment', 'lab_experiment')
          else ['로봇 행동 유형(관찰된 양보/속도)', '보행 환경(보도 폭·혼잡도)'])
    dv = constructs or ['지각된 안전(perceived safety)', '수용성(acceptance)', '신뢰(trust)']
    md = f"""# {ctitle}

> 자동 생성된 연구설계 초안 — 검토·보완 후 사용하세요. (대상도시: {city or '미지정'})

## 1. 제목
{ctitle}{(' — ' + city) if city else ''}

## 2. 연구 배경
{rl}의 도시 내 확산에 따라 {_csv(users)} 등 이용자·보행자와의 상호작용에서
{_csv(constructs)} 등이 핵심 쟁점으로 부상하고 있다. 본 연구는 {sl} 방법으로 이를 실증한다.

## 3. 연구 질문
{_li(rqs)}
## 4. 가설
{_li([f'H1. {rl}의 친사회적 행동(양보·감속)은 {(dv[0] if dv else "지각된 안전")}을(를) 높일 것이다.', 'H2. 근접 거리/혼잡도는 상호작용 결과를 조절할 것이다.'])}
## 5. 참여자 / 관찰 대상
{_li(users, '보행자 · 이용자 · 운영자')}
## 6. 현장 · 맥락
{_li(site, '보도 · 캠퍼스 · 상업지구 등')}
## 7. 변수
**독립변수(IV)**
{_li(iv)}**종속변수(DV)**
{_li(dv)}**통제변수**
{_li(['시간대', '날씨', '보행 밀도', '연령대'])}
## 8. 시나리오
{_li(['정상 주행 중 보행자 조우', '교차 상황(좁은 보도)', '정지·양보 상황', '돌발(아동·자전거) 상황'])}
## 9. 자료수집 방법
{_li(['행동 관찰 및 영상 기록(개인정보 비식별)', '현장 노트', '간이 설문/인터셉트 인터뷰'] if st in ('field_observation', 'video_coding')
     else ['사전·사후 설문', '행동 측정', '심층면접'])}
## 10. 연구 도구
{_li(['관찰 코딩시트', f'{_csv(constructs)} 측정 설문문항', '인터뷰 가이드'])}
## 11. 윤리 점검
{_li(['IRB 승인', '공공장소 영상촬영 고지·비식별', '취약계층(아동·고령자) 보호', '데이터 보관·파기 계획'])}
## 12. 분석 계획
{_li(['관찰자 간 신뢰도(Cohen κ) 산출', '기술통계 및 군집/교차분석', '구조모형 또는 회귀로 DV 예측'] )}
## 13. 정책적 시사점
{_li(['보도 운행 가이드라인', '지각된 안전 제고를 위한 eHMI·속도 기준', '수용성 제고 커뮤니케이션'])}
## 14. 관련 위키 페이지
{_li([f'세계도시 DB: {city}' if city else '세계도시 DB: 대상도시 프로파일', '도시로봇 DB: 관련 사례·HRI 구성개념'])}
"""
    return md


def gen_observation_codebook(inp):
    rt = inp.get('robotType', 'autonomous_delivery_robot')
    setting = inp.get('observationSetting', 'sidewalk')
    rl = ROBOT_LABEL.get(rt, rt)
    md = f"""# 관찰 코딩북 (Observation Codebook)

> 1차 대상: {rl} · 현장 {setting} 관찰

## A. 맥락 변수 (Context)
{_li(['일시/시간대', '장소·보도 폭', '보행 밀도(저/중/고)', '날씨', '주변 소음'])}
## B. 로봇 행동 변수 (Robot Behavior)
{_li(['이동 속도(정지/저속/주행)', '양보 여부', '경로 변경', '정지/대기', '신호(eHMI: 라이트·소리) 유무'])}
## C. 인간 행동 변수 (Human Behavior)
{_li(['회피 여부·방향', '속도 변화(감속/정지)', '주시(시선)·촬영', '접촉·간섭', '동반자와 상호작용'])}
## D. 상호작용 유형 (Interaction Types)
{_li(['단순 통과(무상호작용)', '상호 양보', '경합(누가 먼저)', '근접 회피', '정지 대치'])}
## E. 충돌·안전 사건 (Conflict & Safety)
{_li(['급정지', '경로 봉쇄', '근접(<0.5m) 통과', '접촉', '넘어짐/회피 실패'])}
## F. 결과 변수 (Outcome)
{_li(['상호작용 성공/실패', '지각된 위험(관찰 추정)', '소요 시간', '재발 빈도'])}
## G. 현장 노트 템플릿 (Field Notes)
```
[사건ID] ____  [시각] __:__  [위치] ______
[로봇행동] __________  [인간행동] __________
[상호작용유형] ______  [안전사건] ______
[비고/특이사항] ____________________________
```
## H. 코딩 규칙 (Coding Rules)
{_li(['하나의 조우(encounter) = 1 관찰단위', '동시 다발 사건은 주된 1건으로 코딩', '판단 불가시 9=불명 처리', '관찰자 2인 독립 코딩 후 신뢰도(κ) 산출·합의'])}
"""
    return md


def gen_experiment_protocol(inp):
    rt = inp.get('robotType', 'care_robot')
    rl = ROBOT_LABEL.get(rt, rt)
    constructs = inp.get('hriConstructs', []) or ['신뢰(trust)', '수용성(acceptance)', '지각된 안전']
    users = inp.get('targetUsers', [])
    md = f"""# 실험 프로토콜 (Experiment Protocol)

> 대상: {rl}

## 1. 연구 배경
{rl}의 상호작용 설계 요소가 {_csv(constructs)}에 미치는 영향을 통제된 조건에서 검증한다.

## 2. 연구 질문
{_li([f'{rl}의 설계 조건은 {c}에 어떤 영향을 주는가?' for c in constructs])}
## 3. 가설
{_li([f'H1. 실험조건(친사회적/중립)은 {constructs[0]}에 유의한 차이를 만든다.', 'H2. 효과는 이용자 특성(연령 등)에 의해 조절된다.'])}
## 4. 참여자 기준
{_li(users, '대상 이용자(예: 65세 이상 고령자) · 표본크기 검정력 분석으로 산정')}
## 5. 실험 조건
{_li(['조건 A: 친사회적 행동(양보·발화·표정)', '조건 B: 중립/기능적 행동', '(필요시) 조건 C: Wizard-of-Oz 원격조종'])}
## 6. 시나리오
{_li(['도입·안내', '과업 수행(배송 수령/돌봄 상호작용)', '돌발 상황 대응', '종료·회상'])}
## 7. 변수
**독립변수**
{_li(['로봇 상호작용 설계 조건'])}**종속변수**
{_li(constructs)}**통제변수**
{_li(['연령', '사전 로봇 경험', '과업 난이도'])}
## 8. 측정 도구
{_li(['표준화 설문(신뢰·수용성·지각된 안전 척도)', '행동 측정(과업 완수·근접거리)', '생리지표(선택)'])}
## 9. 설문 문항
{_li([f'{c} 관련 5점 리커트 문항 세트' for c in constructs])}
## 10. 면접 질문
{_li(['로봇에 대한 전반적 인상', '불안/불편했던 순간', '개선 요구', '재이용 의향'])}
## 11. 윤리 고려
{_li(['IRB 승인', '고지된 동의', '고령자·취약계층 보호', '중단권 보장', '데이터 비식별·파기'])}
## 12. 분석 계획
{_li(['집단 간 비교(t-test/ANOVA)', '조절효과(회귀/PROCESS)', '정성자료 주제분석'])}
"""
    return md
