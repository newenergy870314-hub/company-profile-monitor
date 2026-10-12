#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""기업·기관 조직도 + 주요인사 프로필 포털 FINAL V1.

- 32개 기업·기관 마스터
- 공식 홈페이지 우선 수집
- 산업통상부 공식 조직도 구조를 최대한 반영
- 조직도 내 인물 클릭 시 프로필 모달 표시
- root/index.html 자동 생성 (GitHub Pages main/root)
- snapshot 비교 및 변경이력 저장
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
TODAY = NOW.strftime("%Y.%m.%d")
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "company_profile_data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
SITE_DIR = BASE_DIR / "company_profile_site"
SITE_DATA_DIR = SITE_DIR / "data"
CHANGE_LOG = DATA_DIR / "change_log.json"
for p in (DATA_DIR, SNAPSHOT_DIR, SITE_DIR, SITE_DATA_DIR):
    p.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/155 Safari/537.36"}
REQUEST_TIMEOUT = 25
REQUEST_SLEEP = 0.4


@dataclass
class Person:
    id: str
    name: str
    title: str
    name_en: str = ""
    birth: str = ""
    image_url: str = ""
    profile_url: str = ""
    education: list[str] = field(default_factory=list)
    career: list[str] = field(default_factory=list)
    remarks: list[str] = field(default_factory=list)


@dataclass
class OrgNode:
    id: str
    name: str
    leader: str = ""
    person_id: str = ""
    parent: str = ""
    level: int = 0
    highlight: bool = False


@dataclass
class Target:
    key: str
    category: str
    name_ko: str
    name_en: str
    country: str
    official_url: str = ""
    organization_url: str = ""
    leadership_url: str = ""
    org_unit_selector: str = ""
    org_name_selector: str = ""
    org_leader_selector: str = ""
    person_card_selector: str = ""
    person_name_selector: str = ""
    person_title_selector: str = ""
    person_image_selector: str = "img"
    person_detail_link_selector: str = "a"


TARGETS = [
    Target("holtec","SMR 개발사","홀텍 인터내셔널","Holtec International","미국"),
    Target("fortum","에너지 기업","포툼","Fortum","핀란드"),
    Target("khnp","에너지 기업","한수원","Korea Hydro & Nuclear Power (KHNP)","한국"),
    Target("kepco","에너지 기업","한국전력","Korea Electric Power Corporation (KEPCO)","한국"),
    Target("kaeri","연구기관","한국원자력연구원","Korea Atomic Energy Research Institute (KAERI)","한국"),
    Target("motir","정부기관","산업통상부","Ministry of Trade, Industry and Resources","한국",
           "https://www.motir.go.kr/","https://www.motir.go.kr/kor/26/headquarters",
           "https://www.motir.go.kr/kor/contents/70"),
    Target("mcee","정부기관","기후에너지환경부","Ministry of Climate, Energy and Environment","한국"),
    Target("msit","정부기관","과학기술정보통신부","Ministry of Science and ICT","한국"),
    Target("westinghouse","에너지 기업","웨스팅하우스","Westinghouse","미국"),
    Target("terrapower","SMR 개발사","테라파워","TerraPower","미국"),
    Target("xenergy","SMR 개발사","엑스에너지","X-energy","미국"),
    Target("blueenergy","에너지 기업","블루에너지","Blue Energy","미국"),
    Target("fermiamerica","에너지 기업","퍼미 아메리카","Fermi America","미국"),
    Target("enec","에너지 기업","UAE 원자력공사","ENEC (Emirates Nuclear Energy Company)","UAE"),
    Target("entergy","에너지 기업","엔터지 서비스","Entergy Services","미국"),
    Target("fanco","SMR 개발사","퍼스트 아메리칸 뉴클리어","FANCO (First American Nuclear Co.)","미국"),
    Target("thorizon","SMR 개발사","토리존","Thorizon","네덜란드"),
    Target("duke","에너지 기업","듀크에너지","Duke Energy","미국"),
    Target("pseg","에너지 기업","PSEG","PSEG","미국"),
    Target("genenergija","에너지 기업","젠 에너지","GEN Energija","슬로베니아"),
    Target("whitingturner","건설 및 엔지니어링 기업","Whiting-Turner","Whiting-Turner","미국"),
    Target("pcl","건설 및 엔지니어링 기업","PCL Construction","PCL Construction","캐나다"),
    Target("bartonmalow","건설 및 엔지니어링 기업","Barton Malow","Barton Malow","미국"),
    Target("clayco","건설 및 엔지니어링 기업","Clayco","Clayco","미국"),
    Target("alberici","건설 및 엔지니어링 기업","Alberici","Alberici","미국"),
    Target("brandsafway","건설 및 엔지니어링 기업","BrandSafway","BrandSafway","미국"),
    Target("cbi","건설 및 엔지니어링 기업","CB&I","CB&I","미국"),
    Target("dayzimmermann","건설 및 엔지니어링 기업","Day & Zimmermann","Day & Zimmermann","미국"),
    Target("dpr","건설 및 엔지니어링 기업","DPR Construction","DPR Construction","미국"),
    Target("evans","건설 및 엔지니어링 기업","Evans General Contractors","Evans General Contractors","미국"),
    Target("walbridge","건설 및 엔지니어링 기업","Walbridge","Walbridge","미국"),
    Target("zachry","건설 및 엔지니어링 기업","Zachry Group","Zachry Group","미국"),
]

# 산업통상부 공식 조직안내 구조를 기반으로 한 계층 fallback.
MOTIR_ORG = [
    OrgNode("minister","장관실","김정관","kim_jungkwan","",0,True),
    OrgNode("advisor","장관정책보좌관","","","minister",1),
    OrgNode("spokesperson","대변인","","","minister",1),
    OrgNode("audit","감사관","","","minister",1),
    OrgNode("vice","차관","문신학","moon_shinhak","minister",1,True),
    OrgNode("planning","기획조정실","","","vice",2),
    OrgNode("industry","산업정책실","","","vice",2),
    OrgNode("growth","산업성장실","","","vice",2),
    OrgNode("security","산업자원안보실","양기욱","yang_kiuk","vice",2,True),
    OrgNode("trade_head","통상교섭본부장","여한구","yeo_hankoo","minister",1,True),
    OrgNode("trade_policy","통상정책국","","","trade_head",2),
    OrgNode("trade_coop","통상협력국","","","trade_head",2),
    OrgNode("trade_neg","통상교섭실","","","trade_head",2),
    OrgNode("investment","무역투자실","강감찬","kang_gamchan","trade_head",2,True),
    OrgNode("nuclear","원전전략기획관","김창희","kim_changhee","investment",3,True),
    OrgNode("nuclear_export","원전수출진흥과","","","nuclear",4,True),
    OrgNode("nuclear_coop","원전수출협력과","","","nuclear",4,True),
]

MOTIR_PEOPLE = [
    Person("kim_jungkwan","김정관","산업통상부 장관","Kim, Jung-kwan","1968년생",
           profile_url="https://www.motir.go.kr/kor/contents/70",
           education=["광주제일고등학교 졸업","서울대학교 경제학과 학사","미국 미주리대학교 경제학 박사"],
           career=["산업통상부 장관","두산에너빌리티 사장","두산에너빌리티 부사장·마케팅부문장(CMO)","두산경영연구원 대표이사","제36회 행정고시"],
           remarks=["전력수요 대응과 원전 역할 관련 주요 발언","원전 수출 경쟁력 및 해외시장 관련 주요 발언"]),
    Person("moon_shinhak","문신학","산업통상부 1차관","Moon, Shin-hak","1967년생",
           education=["조선대학교부속고등학교 졸업","서울대학교 경제학과 학사"],
           career=["산업통상부 1차관","산업통상자원부 대변인","산업통상자원부 장관정책보좌관","산업통상자원부 원전산업정책관","제38회 행정고시"],
           remarks=["산업·통상 정책과 성장 관련 주요 발언","기후·에너지 정책과 산업정책 연계 관련 주요 발언"]),
    Person("yeo_hankoo","여한구","통상교섭본부장","Yeo, Han-koo","1969년생",
           education=["서울대학교 경영학과 학사","서울대학교 행정대학원 행정학 석사","미국 하버드대학교 케네디스쿨 행정학 석사","미국 하버드대학교 경영대학원 경영학 석사"],
           career=["산업통상부 통상교섭본부장","미국 피터슨국제경제연구소 선임연구위원","서울대학교 경영대학 초빙교수","산업통상자원부 통상교섭본부장"],
           remarks=["글로벌 통상환경과 개방·협력 관련 주요 발언"]),
    Person("yang_kiuk","양기욱","산업자원안보실장","Yang Ki-Uk","1972년생",
           education=["서울대학교 경제학과 학사","미국 델라웨어대학교 에너지·환경정책학 석사"],
           career=["산업통상부 산업자원안보실장","산업통상자원부 원전전략기획관","산업통상자원부 FTA정책관","국무조정실 산업·과학·중기정책관"],
           remarks=["에너지·산업 안보와 원전 생태계 강화 관련 주요 발언","원전 해체 및 고준위 방폐물 정책 관련 주요 발언"]),
    Person("kang_gamchan","강감찬","무역투자실장","Kang, Gam-Chan","1973년생",
           education=["서울대학교 경제학과 졸업","미국 카네기멜론대 정보학 석사"],
           career=["산업통상부 무역투자실장","산업통상자원부 산업정책관","산업통상자원부 무역안보정책관","산업통상자원부 전략산업정책과장"],
           remarks=["원전·SMR의 탄소감축 기여와 에너지 안보 관련 주요 발언","원전 산업의 수출 전략적 가치 관련 주요 발언"]),
    Person("kim_changhee","김창희","원전전략기획관","Kim Chang-hee","1971년생",
           education=["고려대학교 경영학과 학사"],
           career=["산업통상부 원전전략기획관","KOTRA 외국인투자지원센터 국장","산업통상자원부 소재부품장비총괄과장","산업통상자원부 기술안보과장"],
           remarks=["원전 수출 및 산업정책 관련 주요 업무"]),
]


def clean_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def esc(v) -> str:
    return html.escape(str(v or ""))


def absolute_url(base: str, value: str | None) -> str:
    return urljoin(base, value or "") if value else ""


def fetch_soup(url: str):
    if not requests or not BeautifulSoup:
        raise RuntimeError("requests와 beautifulsoup4가 필요합니다.")
    time.sleep(REQUEST_SLEEP)
    r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def payload_hash(v) -> str:
    raw = json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def snapshot_path(key: str) -> Path:
    return SNAPSHOT_DIR / f"{key}.json"


def collect_motir(target: Target) -> dict:
    """산업통상부 공식 홈페이지 확인 + 공식 구조 fallback."""
    org = [asdict(x) for x in MOTIR_ORG]
    people = [asdict(x) for x in MOTIR_PEOPLE]
    errors = []

    try:
        soup = fetch_soup(target.organization_url)
        page_text = clean_text(soup.get_text(" ", strip=True))
        for node in org:
            node["source_verified"] = node["name"] in page_text
    except Exception as e:
        errors.append(f"조직도 확인 실패: {e}")

    try:
        soup = fetch_soup(target.leadership_url)
        txt = clean_text(soup.get_text(" ", strip=True))
        if "김정관" in txt:
            for p in people:
                if p["id"] == "kim_jungkwan":
                    p["source_verified"] = True
                    # 이름 주변 이미지 best-effort
                    text_node = soup.find(string=re.compile("김정관"))
                    cur = text_node.parent if text_node else None
                    for _ in range(6):
                        if not cur:
                            break
                        img = cur.find("img")
                        if img:
                            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                            if src:
                                p["image_url"] = absolute_url(target.leadership_url, src)
                                break
                        cur = cur.parent
    except Exception as e:
        errors.append(f"장관 프로필 확인 실패: {e}")

    return {
        "key": target.key, "category": target.category, "name_ko": target.name_ko,
        "name_en": target.name_en, "country": target.country,
        "official_url": target.official_url, "organization_url": target.organization_url,
        "leadership_url": target.leadership_url,
        "updated_at": NOW.isoformat(timespec="seconds"),
        "status": "OK" if not errors else "PARTIAL",
        "source": "산업통상부 공식 홈페이지",
        "organization": org, "people": people, "errors": errors,
    }


def configured(t: Target) -> bool:
    return bool((t.organization_url and t.org_unit_selector) or (t.leadership_url and t.person_card_selector))


def collect_generic(t: Target) -> dict:
    if not configured(t):
        return {
            "key": t.key, "category": t.category, "name_ko": t.name_ko, "name_en": t.name_en,
            "country": t.country, "official_url": t.official_url,
            "organization_url": t.organization_url, "leadership_url": t.leadership_url,
            "updated_at": NOW.isoformat(timespec="seconds"), "status": "PENDING",
            "source": "", "organization": [], "people": [], "errors": [],
        }

    org, people, errors = [], [], []
    if t.organization_url and t.org_unit_selector:
        try:
            soup = fetch_soup(t.organization_url)
            for i, block in enumerate(soup.select(t.org_unit_selector), 1):
                nn = block.select_one(t.org_name_selector) if t.org_name_selector else block
                ln = block.select_one(t.org_leader_selector) if t.org_leader_selector else None
                name = clean_text(nn.get_text(" ", strip=True)) if nn else ""
                leader = clean_text(ln.get_text(" ", strip=True)) if ln else ""
                if name:
                    org.append({"id":f"org_{i}","name":name,"leader":leader,"person_id":"","parent":"","level":0,
                                "highlight":bool(re.search(r"nuclear|energy|smr|원전|원자력|에너지",name,re.I))})
        except Exception as e:
            errors.append(f"조직 수집 실패: {e}")

    if t.leadership_url and t.person_card_selector:
        try:
            soup = fetch_soup(t.leadership_url)
            for i, card in enumerate(soup.select(t.person_card_selector), 1):
                nn = card.select_one(t.person_name_selector) if t.person_name_selector else None
                tn = card.select_one(t.person_title_selector) if t.person_title_selector else None
                name = clean_text(nn.get_text(" ", strip=True)) if nn else ""
                title = clean_text(tn.get_text(" ", strip=True)) if tn else ""
                if not name:
                    continue
                img_url = ""
                img = card.select_one(t.person_image_selector) if t.person_image_selector else None
                if img:
                    img_url = absolute_url(t.leadership_url, img.get("src") or img.get("data-src"))
                profile_url = ""
                a = card.select_one(t.person_detail_link_selector) if t.person_detail_link_selector else None
                if a and a.get("href"):
                    profile_url = absolute_url(t.leadership_url, a.get("href"))
                people.append({"id":f"person_{i}","name":name,"title":title,"name_en":"","birth":"",
                               "image_url":img_url,"profile_url":profile_url,"education":[],"career":[],"remarks":[]})
        except Exception as e:
            errors.append(f"주요인사 수집 실패: {e}")

    return {
        "key": t.key, "category": t.category, "name_ko": t.name_ko, "name_en": t.name_en,
        "country": t.country, "official_url": t.official_url,
        "organization_url": t.organization_url, "leadership_url": t.leadership_url,
        "updated_at": NOW.isoformat(timespec="seconds"),
        "status": "OK" if not errors else "PARTIAL", "source": "공식 홈페이지",
        "organization": org, "people": people, "errors": errors,
    }


def collect_target(t: Target) -> dict:
    return collect_motir(t) if t.key == "motir" else collect_generic(t)


def detect_changes(old: Optional[dict], new: dict) -> list[dict]:
    if old is None:
        return [{"type":"INITIAL","text":"최초 데이터 등록"}]
    changes = []
    if payload_hash(old.get("organization", [])) != payload_hash(new.get("organization", [])):
        changes.append({"type":"ORG_CHANGED","text":"조직도 변경 감지"})
    oldp = {p.get("id") or p.get("name"):p for p in old.get("people", [])}
    newp = {p.get("id") or p.get("name"):p for p in new.get("people", [])}
    for k in sorted(set(newp) - set(oldp)):
        changes.append({"type":"PERSON_ADDED","text":f"신규 주요인사: {newp[k].get('name','')}"})
    for k in sorted(set(oldp) - set(newp)):
        changes.append({"type":"PERSON_REMOVED","text":f"주요인사 제외/변경 가능성: {oldp[k].get('name','')}"})
    for k in sorted(set(oldp) & set(newp)):
        for field, label in (("title","직책"),("education","학력"),("career","경력"),("remarks","주요발언/활동")):
            if oldp[k].get(field) != newp[k].get(field):
                changes.append({"type":"PERSON_CHANGED","text":f"{newp[k].get('name','')} {label} 변경"})
    return changes


def append_change_log(company: dict, changes: list[dict]):
    if not changes:
        return
    log = load_json(CHANGE_LOG) or []
    log.append({"checked_at":NOW.isoformat(timespec="seconds"),"key":company["key"],"company":company["name_ko"],"changes":changes})
    save_json(CHANGE_LOG, log[-1000:])


def person_map(data: dict) -> dict[str,dict]:
    return {p.get("id",""):p for p in data.get("people",[]) if p.get("id")}


def render_org_tree(data: dict) -> str:
    nodes = data.get("organization", [])
    if not nodes:
        return '<div class="empty">조직도 연결 준비중</div>'
    by_parent = {}
    for n in nodes:
        by_parent.setdefault(n.get("parent",""), []).append(n)
    people = person_map(data)

    def rec(parent: str) -> str:
        children = by_parent.get(parent, [])
        if not children:
            return ""
        out = ['<div class="org-level">']
        for n in children:
            pid = n.get("person_id","")
            clickable = bool(pid and pid in people)
            cls = "org-node" + (" hot" if n.get("highlight") else "") + (" clickable" if clickable else "")
            onclick = f' onclick="openProfile(\'{esc(data["key"])}\',\'{esc(pid)}\')"' if clickable else ""
            hint = '<div class="click-hint">프로필 보기</div>' if clickable else ""
            out.append(
                f'<div class="org-branch"><button type="button" class="{cls}"{onclick}>'
                f'<div class="org-name">{esc(n.get("name"))}</div>'
                f'<div class="org-leader">{esc(n.get("leader"))}</div>{hint}</button>'
                f'{rec(n.get("id",""))}</div>'
            )
        out.append('</div>')
        return ''.join(out)
    return rec("") or '<div class="empty">조직도 데이터를 표시할 수 없습니다.</div>'


def js_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def render_company(data: dict, changes: list[dict]) -> str:
    status_label = {"OK":"공식 홈페이지 연결됨","PARTIAL":"일부 수집","PENDING":"연결 준비중","ERROR":"수집 오류"}.get(data.get("status"), data.get("status",""))
    change_box = ""
    if changes:
        change_box = '<div class="change-box"><strong>최근 변경 감지</strong><ul>' + ''.join(f'<li>{esc(x.get("text"))}</li>' for x in changes[:8]) + '</ul></div>'
    return f'''
<section class="company-view" data-company="{esc(data['key'])}">
  <div class="company-summary">
    <div><div class="eyebrow">{esc(data['category'])} · {esc(data['country'])}</div><h1>{esc(data['name_ko'])}</h1><div class="en">{esc(data['name_en'])}</div></div>
    <div class="status">{esc(status_label)}</div>
  </div>
  <section class="paper">
    <div class="paper-head"><div class="paper-title">{esc(data['name_ko'])} 조직도</div><div class="date">{TODAY}</div></div>
    <div class="guide">조직도 내 <b>인물명이 있는 직위</b>를 클릭하면 별도 이동 없이 프로필이 바로 표시됩니다.</div>
    <div class="org-scroll"><div class="org-canvas">{render_org_tree(data)}</div></div>
    {change_box}
    <div class="source"><div><b>출처</b> {esc(data.get('source')) or '-'}</div><div><b>공식 홈페이지</b> {esc(data.get('official_url')) or '-'}</div><div><b>조직도</b> {esc(data.get('organization_url')) or '-'}</div><div><b>Leadership</b> {esc(data.get('leadership_url')) or '-'}</div><div><b>업데이트</b> {esc(data.get('updated_at'))}</div></div>
  </section>
</section>'''


def build_site(all_data: list[dict], changes_map: dict[str,list[dict]]):
    for d in all_data:
        save_json(SITE_DATA_DIR / f"{d['key']}.json", d)
    categories = []
    for d in all_data:
        if d["category"] not in categories:
            categories.append(d["category"])
    nav = []
    for cat in categories:
        nav.append(f'<div class="nav-cat">{esc(cat)}</div>')
        for d in [x for x in all_data if x["category"] == cat]:
            dot = "●" if d["status"] in ("OK","PARTIAL") else "○"
            nav.append(f'<button class="company-btn" data-key="{esc(d["key"])}"><span>{dot}</span>{esc(d["name_ko"])}</button>')
    views = ''.join(render_company(d, changes_map.get(d["key"], [])) for d in all_data)
    profiles = {d["key"]:person_map(d) for d in all_data}
    first = all_data[0]["key"] if all_data else ""

    page = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>기업·기관 조직도 및 주요인사 프로필</title>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;padding:0}}body{{font-family:"Malgun Gothic","Apple SD Gothic Neo",Arial,sans-serif;background:#eef2f6;color:#15191f}}
.topbar{{height:58px;background:#0b2545;color:#fff;display:flex;align-items:center;justify-content:space-between;padding:0 20px;position:sticky;top:0;z-index:30}}.topbar b{{font-size:18px}}
.layout{{display:grid;grid-template-columns:270px 1fr;min-height:calc(100vh - 58px)}}.sidebar{{background:#102c50;color:#fff;height:calc(100vh - 58px);position:sticky;top:58px;overflow:auto;padding:14px 10px}}
.nav-cat{{font-size:11px;color:#99afc8;font-weight:900;margin:18px 8px 6px}}.company-btn{{display:block;width:100%;border:0;background:transparent;color:#fff;text-align:left;padding:9px 10px;border-radius:7px;cursor:pointer}}.company-btn:hover,.company-btn.active{{background:#24496f}}.company-btn span{{display:inline-block;width:18px;color:#ffd500}}
.main{{padding:22px}}.company-view{{display:none;max-width:1120px;margin:0 auto}}.company-view.active{{display:block}}.company-summary{{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:14px}}.company-summary h1{{margin:4px 0 2px;font-size:28px}}.eyebrow{{font-size:12px;color:#687583;font-weight:800}}.en{{font-size:13px;color:#687583}}.status{{background:#dceaf8;color:#174d82;border-radius:999px;padding:7px 11px;font-size:12px;font-weight:900}}
.paper{{background:#fff;border-radius:12px;padding:22px;box-shadow:0 2px 14px rgba(0,0,0,.06)}}.paper-head{{display:flex;justify-content:space-between;border-bottom:2px solid #989fa7;padding-bottom:9px;margin-bottom:14px}}.paper-title{{font-size:21px;font-weight:900}}.date{{font-size:13px;color:#555}}.guide{{background:#f4f7fa;border-left:4px solid #1b548a;padding:10px 12px;font-size:12px;margin-bottom:15px}}
.org-scroll{{overflow:auto;padding:4px 0 16px}}.org-canvas{{min-width:980px}}.org-level{{display:flex;justify-content:center;gap:14px;align-items:flex-start;margin:12px 0}}.org-branch{{display:flex;flex-direction:column;align-items:center;min-width:130px}}.org-branch>.org-level{{border-top:2px solid #cbd2d9;padding-top:12px}}.org-node{{min-width:130px;max-width:175px;border:1px solid #cbd2d9;background:#f5f7f9;border-radius:7px;padding:10px 8px;text-align:center;color:#15191f}}.org-node.hot{{background:#fff2aa;border:2px dashed #d74343}}.org-node.clickable{{cursor:pointer}}.org-node.clickable:hover{{background:#eaf4fd;border-color:#76a8d3}}.org-name{{font-size:12px;font-weight:800}}.org-leader{{font-size:14px;font-weight:900;color:#174d82;margin-top:4px}}.click-hint{{font-size:9px;color:#7d8995;margin-top:4px}}.empty{{padding:60px 20px;border:1px dashed #aeb7c1;text-align:center;color:#7d8791}}
.change-box{{margin-top:16px;background:#fff7d6;border:1px solid #e4cb66;padding:12px}}.change-box ul{{margin:7px 0 0;padding-left:20px}}.source{{margin-top:18px;font-size:11px;color:#67717c;line-height:1.65;word-break:break-all}}
.modal-bg{{position:fixed;inset:0;background:rgba(7,22,39,.62);z-index:100;display:none;align-items:center;justify-content:center;padding:18px}}.modal-bg.open{{display:flex}}.modal{{width:min(900px,96vw);max-height:92vh;background:#fff;border-radius:14px;overflow:auto;box-shadow:0 18px 60px rgba(0,0,0,.3)}}.modal-head{{position:sticky;top:0;z-index:2;background:#fff;border-bottom:1px solid #d8dde3;display:flex;justify-content:space-between;align-items:center;padding:14px 18px}}.modal-head strong{{font-size:19px}}.close{{width:36px;height:36px;border:0;border-radius:50%;background:#edf1f5;font-size:22px;cursor:pointer}}
.profile{{padding:18px}}.profile-title{{font-size:27px;font-weight:900;margin:0 0 15px}}.profile-title span{{font-size:18px;margin-left:8px}}.identity{{display:grid;grid-template-columns:1fr 180px;gap:14px}}.identity-table{{display:grid;grid-template-columns:100px 1fr;border-top:1px solid #d2d6db;border-left:1px solid #d2d6db}}.identity-table>div{{border-right:1px solid #d2d6db;border-bottom:1px solid #d2d6db;padding:14px}}.label{{background:#f5f5f5;font-weight:900;text-align:center}}.photo{{width:180px;height:210px;border:1px solid #d2d6db;background:#f4f6f8;object-fit:cover;display:flex;align-items:center;justify-content:center;color:#8b949e;font-weight:800}}.row{{display:grid;grid-template-columns:100px 1fr;border-left:1px solid #d2d6db;border-right:1px solid #d2d6db;border-bottom:1px solid #d2d6db}}.row-label{{background:#f5f5f5;border-right:1px solid #d2d6db;display:flex;align-items:center;justify-content:center;font-weight:900;text-align:center;padding:12px}}.row-body{{padding:15px 18px;line-height:1.65}}.row-body ul{{margin:0;padding-left:20px}}.profile-source{{margin-top:12px;font-size:11px;color:#67717c}}
@media(max-width:850px){{.layout{{display:block}}.sidebar{{height:auto;position:relative;top:auto;display:flex;overflow-x:auto;padding:9px}}.nav-cat{{display:none}}.company-btn{{min-width:150px;white-space:nowrap}}.main{{padding:10px}}.paper{{padding:14px;border-radius:8px}}.company-summary h1{{font-size:23px}}.identity{{grid-template-columns:1fr 110px}}.photo{{width:110px;height:140px}}.identity-table{{grid-template-columns:74px 1fr}}.row{{grid-template-columns:74px 1fr}}.profile-title{{font-size:22px}}.profile-title span{{display:block;margin:4px 0 0;font-size:15px}}}}
</style></head><body>
<div class="topbar"><b>기업·기관 조직도 및 주요인사 프로필</b><span style="font-size:11px">Official-site first</span></div>
<div class="layout"><aside class="sidebar">{''.join(nav)}</aside><main class="main">{views}</main></div>
<div class="modal-bg" id="modalBg" onclick="closeByBg(event)"><div class="modal"><div class="modal-head"><strong id="modalHead">주요인사 프로필</strong><button class="close" onclick="closeProfile()">×</button></div><div class="profile" id="profileBody"></div></div></div>
<script>
const PROFILE_DATA = {js_json(profiles)};
const buttons=[...document.querySelectorAll('.company-btn')]; const views=[...document.querySelectorAll('.company-view')];
function openCompany(key){{buttons.forEach(b=>b.classList.toggle('active',b.dataset.key===key));views.forEach(v=>v.classList.toggle('active',v.dataset.company===key));localStorage.setItem('company-profile-selected',key);window.scrollTo({{top:0,behavior:'instant'}});}}
buttons.forEach(b=>b.addEventListener('click',()=>openCompany(b.dataset.key)));
function escapeHtml(s){{return String(s||'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[c]));}}
function listHtml(arr){{if(!arr||!arr.length)return '<div style="color:#89939c">확인된 정보 없음</div>';return '<ul>'+arr.map(x=>'<li>'+escapeHtml(x)+'</li>').join('')+'</ul>';}}
function openProfile(companyKey,personId){{const p=(PROFILE_DATA[companyKey]||{{}})[personId];if(!p)return;document.getElementById('modalHead').textContent=p.name+' '+p.title;const photo=p.image_url?`<img class="photo" src="${{escapeHtml(p.image_url)}}" alt="${{escapeHtml(p.name)}}">`:'<div class="photo">PHOTO</div>';const source=p.profile_url?`<a href="${{escapeHtml(p.profile_url)}}" target="_blank">공식 프로필</a>`:'공식 홈페이지/공개자료';document.getElementById('profileBody').innerHTML=`<div class="profile-title">${{escapeHtml(p.name)}} <span>${{escapeHtml(p.title)}}</span></div><div class="identity"><div class="identity-table"><div class="label">성명</div><div>${{escapeHtml(p.name)}} ${{p.name_en?'('+escapeHtml(p.name_en)+')':''}} ${{p.birth?'· '+escapeHtml(p.birth):''}}</div><div class="label">직책</div><div>${{escapeHtml(p.title)}}</div><div class="label">출처</div><div>${{source}}</div></div>${{photo}}</div><div class="row"><div class="row-label">학력</div><div class="row-body">${{listHtml(p.education)}}</div></div><div class="row"><div class="row-label">경력</div><div class="row-body">${{listHtml(p.career)}}</div></div><div class="row"><div class="row-label">주요발언<br>·최근활동</div><div class="row-body">${{listHtml(p.remarks)}}</div></div><div class="profile-source">※ 공식 홈페이지를 우선으로 하며 미공개 항목은 등록된 보완자료를 사용합니다.</div>`;document.getElementById('modalBg').classList.add('open');document.body.style.overflow='hidden';}}
function closeProfile(){{document.getElementById('modalBg').classList.remove('open');document.body.style.overflow='';}} function closeByBg(e){{if(e.target.id==='modalBg')closeProfile();}} document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeProfile();}});
const saved=localStorage.getItem('company-profile-selected');openCompany(buttons.some(b=>b.dataset.key===saved)?saved:{json.dumps(first)});
</script></body></html>'''
    (BASE_DIR / "index.html").write_text(page, encoding="utf-8")
    (SITE_DIR / "index.html").write_text(page, encoding="utf-8")


def main():
    all_data, changes_map = [], {}
    print("="*72)
    print("기업·기관 조직도 / 주요인사 프로필 포털 FINAL V1")
    print("="*72)
    for i,t in enumerate(TARGETS,1):
        print(f"[{i:02d}/{len(TARGETS)}] {t.name_ko} ... ", end="", flush=True)
        try:
            new = collect_target(t)
        except Exception as e:
            new = {"key":t.key,"category":t.category,"name_ko":t.name_ko,"name_en":t.name_en,"country":t.country,"official_url":t.official_url,"organization_url":t.organization_url,"leadership_url":t.leadership_url,"updated_at":NOW.isoformat(timespec="seconds"),"status":"ERROR","source":"","organization":[],"people":[],"errors":[str(e)]}
        old = load_json(snapshot_path(t.key))
        changes = detect_changes(old,new)
        if new["status"] in ("OK","PARTIAL"):
            save_json(snapshot_path(t.key),new)
        append_change_log(new,changes)
        all_data.append(new); changes_map[t.key]=changes
        print(f"{new['status']} / 조직 {len(new.get('organization',[]))} / 인사 {len(new.get('people',[]))}")
    build_site(all_data,changes_map)
    save_json(DATA_DIR / "company_registry.json", [asdict(x) for x in TARGETS])
    print("\n[완료]")
    print("GitHub Pages root:", BASE_DIR / "index.html")
    print("생성물 보관:", SITE_DIR / "index.html")

if __name__ == "__main__":
    main()
