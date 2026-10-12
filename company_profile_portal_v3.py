#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
기업·기관 조직도 + 주요인사 프로필 자동 업데이트 웹사이트 V4

실행:
    python company_profile_portal_v3.py

생성:
    company_profile_site/index.html
    company_profile_site/data/*.json
    company_profile_data/snapshots/*.json
    company_profile_data/change_log.json

구조:
1) 회사/기관 마스터 32개 등록
2) 공식 홈페이지 / Organization / Leadership URL 및 CSS selector를 회사별 설정
3) 공개 홈페이지에서 조직/주요인사 정보 수집
4) 이전 snapshot과 비교해 인사/직책/조직 변경 감지
5) 1페이지 조직도 + 2페이지 이후 주요인사 프로필 형식의 정적 웹사이트 생성

중요:
- 회사마다 홈페이지 HTML 구조가 달라 selector는 개별 설정이 필요합니다.
- selector 미설정 대상은 웹사이트에 '연결 준비중'으로 표시됩니다.
- DEMO_DATA에는 사용자가 제공한 산업통상부 샘플의 형식/일부 인사구성을 넣어
  실행 즉시 화면을 확인할 수 있게 했습니다.
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

for p in (DATA_DIR, SNAPSHOT_DIR, SITE_DIR, SITE_DATA_DIR):
    p.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 20
REQUEST_SLEEP = 0.6


# ============================================================
# 1) 데이터 구조
# ============================================================

@dataclass
class PersonProfile:
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
    name: str
    leader: str = ""
    parent: str = ""
    highlight: bool = False


@dataclass
class CompanyTarget:
    key: str
    category: str
    name_ko: str
    name_en: str
    country: str

    official_url: str = ""
    organization_url: str = ""
    leadership_url: str = ""

    # 조직도 selector
    org_unit_selector: str = ""
    org_name_selector: str = ""
    org_leader_selector: str = ""

    # 인물 카드 selector
    person_card_selector: str = ""
    person_name_selector: str = ""
    person_title_selector: str = ""
    person_image_selector: str = "img"
    person_detail_link_selector: str = "a"

    # 상세 프로필 selector
    detail_education_selector: str = ""
    detail_career_selector: str = ""
    detail_remarks_selector: str = ""

    highlight_keywords: list[str] = field(default_factory=lambda: [
        "nuclear", "energy", "power", "smr", "reactor",
        "원전", "원자력", "에너지"
    ])


# ============================================================
# 2) 관리 대상 32개
# ============================================================

TARGETS = [
    CompanyTarget("holtec","SMR 개발사","홀텍 인터내셔널","Holtec International","미국"),
    CompanyTarget("fortum","에너지 기업","포툼","Fortum","핀란드"),
    CompanyTarget("khnp","에너지 기업","한수원","Korea Hydro & Nuclear Power (KHNP)","한국"),
    CompanyTarget("kepco","에너지 기업","한국전력","Korea Electric Power Corporation (KEPCO)","한국"),
    CompanyTarget("kaeri","연구기관","한국원자력연구원","Korea Atomic Energy Research Institute (KAERI)","한국"),
    CompanyTarget("motie","정부기관","산업통상부","Ministry of Trade, Industry and Energy","한국"),
    CompanyTarget("mcee","정부기관","기후에너지환경부","Ministry of Climate, Energy and Environment","한국"),
    CompanyTarget("msit","정부기관","과학기술정보통신부","Ministry of Science and ICT","한국"),
    CompanyTarget("westinghouse","에너지 기업","웨스팅하우스","Westinghouse","미국"),
    CompanyTarget("terrapower","SMR 개발사","테라파워","TerraPower","미국"),
    CompanyTarget("xenergy","SMR 개발사","엑스에너지","X-energy","미국"),
    CompanyTarget("blueenergy","에너지 기업","블루에너지","Blue Energy","미국"),
    CompanyTarget("fermiamerica","에너지 기업","퍼미 아메리카","Fermi America","미국"),
    CompanyTarget("enec","에너지 기업","UAE 원자력공사","ENEC (Emirates Nuclear Energy Company)","UAE"),
    CompanyTarget("entergy","에너지 기업","엔터지 서비스","Entergy Services","미국"),
    CompanyTarget("fanco","SMR 개발사","퍼스트 아메리칸 뉴클리어","FANCO (First American Nuclear Co.)","미국"),
    CompanyTarget("thorizon","SMR 개발사","토리존","Thorizon","네덜란드"),
    CompanyTarget("duke","에너지 기업","듀크에너지","Duke Energy","미국"),
    CompanyTarget("pseg","에너지 기업","PSEG","PSEG","미국"),
    CompanyTarget("genenergija","에너지 기업","젠 에너지","GEN Energija","슬로베니아"),
    CompanyTarget("whitingturner","건설 및 엔지니어링 기업","Whiting-Turner","Whiting-Turner","미국"),
    CompanyTarget("pcl","건설 및 엔지니어링 기업","PCL Construction","PCL Construction","캐나다"),
    CompanyTarget("bartonmalow","건설 및 엔지니어링 기업","Barton Malow","Barton Malow","미국"),
    CompanyTarget("clayco","건설 및 엔지니어링 기업","Clayco","Clayco","미국"),
    CompanyTarget("alberici","건설 및 엔지니어링 기업","Alberici","Alberici","미국"),
    CompanyTarget("brandsafway","건설 및 엔지니어링 기업","BrandSafway","BrandSafway","미국"),
    CompanyTarget("cbi","건설 및 엔지니어링 기업","CB&I","CB&I","미국"),
    CompanyTarget("dayzimmermann","건설 및 엔지니어링 기업","Day & Zimmermann","Day & Zimmermann","미국"),
    CompanyTarget("dpr","건설 및 엔지니어링 기업","DPR Construction","DPR Construction","미국"),
    CompanyTarget("evans","건설 및 엔지니어링 기업","Evans General Contractors","Evans General Contractors","미국"),
    CompanyTarget("walbridge","건설 및 엔지니어링 기업","Walbridge","Walbridge","미국"),
    CompanyTarget("zachry","건설 및 엔지니어링 기업","Zachry Group","Zachry Group","미국"),
]


# ============================================================
# 3) 데모 데이터
#    산업통상부 샘플 형식을 실행 즉시 확인하기 위한 예시
# ============================================================

DEMO_DATA = {
    "motie": {
        "organization": [
            {"name": "장관", "leader": "김정관", "parent": "", "highlight": True},
            {"name": "1차관", "leader": "문신학", "parent": "장관", "highlight": True},
            {"name": "산업자원안보실", "leader": "양기욱", "parent": "1차관", "highlight": True},
            {"name": "통상교섭본부", "leader": "여한구", "parent": "장관", "highlight": True},
            {"name": "무역투자실", "leader": "강감찬", "parent": "통상교섭본부", "highlight": True},
            {"name": "원전전략기획관", "leader": "김창희", "parent": "산업자원안보실", "highlight": True},
        ],
        "people": [
            {
                "name": "김정관",
                "name_en": "Kim, Jung-kwan",
                "birth": "1968년생",
                "title": "산업통상부 장관",
                "education": [
                    "광주제일고등학교 졸업",
                    "서울대학교 경제학과 학사",
                    "미국 미주리대학교 경제학 박사",
                ],
                "career": [
                    "2025.7 ~ 현재 산업통상부 장관",
                    "2025 두산에너빌리티 사장",
                    "2022 ~ 2024 두산에너빌리티 부사장, 마케팅부문장(CMO)",
                ],
                "remarks": [
                    "전력 수요 대응과 원전 필요성 관련 주요 발언",
                    "원전 수출 경쟁력 및 유럽시장 관련 발언",
                ],
            },
            {
                "name": "문신학",
                "name_en": "Moon, Shin-hak",
                "birth": "1967년생",
                "title": "산업통상부 1차관",
                "education": [
                    "광주 조선대학교부속고등학교 졸업",
                    "서울대학교 경제학과 학사",
                ],
                "career": [
                    "2025.6 ~ 현재 산업통상부 차관",
                    "산업통상자원부 대변인",
                    "산업통상자원부 장관정책보좌관",
                ],
                "remarks": [
                    "산업·통상 정책과 성장 관련 주요 발언",
                    "기후·에너지 정책과 산업정책 연계 관련 발언",
                ],
            },
            {
                "name": "여한구",
                "name_en": "Yeo, Han-koo",
                "birth": "1969년생",
                "title": "통상교섭본부장",
                "education": [
                    "서울 경동고등학교 졸업",
                    "서울대학교 경영학과 학사",
                    "서울대학교 행정대학원 행정학 석사",
                ],
                "career": [
                    "산업통상부 통상교섭본부장",
                    "미국 피터슨국제경제연구소 선임연구위원",
                    "산업통상자원부 통상교섭본부장",
                ],
                "remarks": [
                    "글로벌 경제질서와 개방·협력 관련 주요 발언",
                ],
            },
        ],
        "source": "사용자 제공 산업통상부 조직도·주요인사 프로필 샘플",
        "demo": True,
    }
}


# ============================================================
# 4) 수집 유틸
# ============================================================

def clean_text(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def node_text(node) -> str:
    return clean_text(node.get_text(" ", strip=True)) if node else ""


def absolute_url(base: str, value: str | None) -> str:
    return urljoin(base, value or "") if value else ""


def fetch_soup(url: str):
    if not requests or not BeautifulSoup:
        raise RuntimeError("requests와 beautifulsoup4가 필요합니다.")
    time.sleep(REQUEST_SLEEP)
    r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def get_text(root, selector: str) -> str:
    if not selector:
        return ""
    return node_text(root.select_one(selector))


def get_list_text(root, selector: str) -> list[str]:
    if not selector:
        return []
    return [node_text(x) for x in root.select(selector) if node_text(x)]


def config_ready(t: CompanyTarget) -> bool:
    return bool(
        (t.organization_url and t.org_unit_selector)
        or (t.leadership_url and t.person_card_selector)
    )


# ============================================================
# 5) 홈페이지 수집
# ============================================================

def collect_organization(t: CompanyTarget) -> list[dict]:
    if not (t.organization_url and t.org_unit_selector):
        return []

    soup = fetch_soup(t.organization_url)
    result = []

    for block in soup.select(t.org_unit_selector):
        name = get_text(block, t.org_name_selector) if t.org_name_selector else node_text(block)
        leader = get_text(block, t.org_leader_selector)
        if not name:
            continue

        compact = f"{name} {leader}".lower()
        highlight = any(k.lower() in compact for k in t.highlight_keywords)

        result.append({
            "name": name,
            "leader": leader,
            "parent": "",
            "highlight": highlight,
        })

    return result


def collect_person_detail(t: CompanyTarget, url: str) -> dict:
    if not url:
        return {"education": [], "career": [], "remarks": []}

    try:
        soup = fetch_soup(url)
    except Exception:
        return {"education": [], "career": [], "remarks": []}

    return {
        "education": get_list_text(soup, t.detail_education_selector),
        "career": get_list_text(soup, t.detail_career_selector),
        "remarks": get_list_text(soup, t.detail_remarks_selector),
    }


def collect_people(t: CompanyTarget) -> list[dict]:
    if not (t.leadership_url and t.person_card_selector):
        return []

    soup = fetch_soup(t.leadership_url)
    people = []

    for card in soup.select(t.person_card_selector):
        name = get_text(card, t.person_name_selector)
        title = get_text(card, t.person_title_selector)

        if not name:
            continue

        image_url = ""
        if t.person_image_selector:
            img = card.select_one(t.person_image_selector)
            if img:
                image_url = absolute_url(
                    t.leadership_url,
                    img.get("src") or img.get("data-src") or img.get("data-lazy-src"),
                )

        profile_url = ""
        if t.person_detail_link_selector:
            a = card.select_one(t.person_detail_link_selector)
            if a and a.get("href"):
                profile_url = absolute_url(t.leadership_url, a.get("href"))

        detail = collect_person_detail(t, profile_url)

        people.append({
            "name": name,
            "name_en": "",
            "birth": "",
            "title": title,
            "image_url": image_url,
            "profile_url": profile_url,
            **detail,
        })

    return people


def collect_target(t: CompanyTarget) -> dict:
    # selector 미설정인 경우 데모 데이터 우선
    if t.key in DEMO_DATA and not config_ready(t):
        data = dict(DEMO_DATA[t.key])
        return {
            "key": t.key,
            "category": t.category,
            "name_ko": t.name_ko,
            "name_en": t.name_en,
            "country": t.country,
            "official_url": t.official_url,
            "organization_url": t.organization_url,
            "leadership_url": t.leadership_url,
            "updated_at": NOW.isoformat(timespec="seconds"),
            "status": "DEMO",
            **data,
        }

    if not config_ready(t):
        return {
            "key": t.key,
            "category": t.category,
            "name_ko": t.name_ko,
            "name_en": t.name_en,
            "country": t.country,
            "official_url": t.official_url,
            "organization_url": t.organization_url,
            "leadership_url": t.leadership_url,
            "updated_at": NOW.isoformat(timespec="seconds"),
            "status": "PENDING",
            "organization": [],
            "people": [],
            "source": "",
            "demo": False,
        }

    errors = []
    organization, people = [], []

    try:
        organization = collect_organization(t)
    except Exception as e:
        errors.append(f"조직도 수집 실패: {e}")

    try:
        people = collect_people(t)
    except Exception as e:
        errors.append(f"주요인사 수집 실패: {e}")

    return {
        "key": t.key,
        "category": t.category,
        "name_ko": t.name_ko,
        "name_en": t.name_en,
        "country": t.country,
        "official_url": t.official_url,
        "organization_url": t.organization_url,
        "leadership_url": t.leadership_url,
        "updated_at": NOW.isoformat(timespec="seconds"),
        "status": "OK" if not errors else "PARTIAL",
        "errors": errors,
        "organization": organization,
        "people": people,
        "source": "공식 홈페이지",
        "demo": False,
    }


# ============================================================
# 6) 변경 감지
# ============================================================

def snapshot_file(key: str) -> Path:
    return SNAPSHOT_DIR / f"{key}.json"


def load_snapshot(key: str) -> Optional[dict]:
    p = snapshot_file(key)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_snapshot(key: str, data: dict):
    snapshot_file(key).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalized_hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def person_map(data: dict) -> dict[str, dict]:
    return {
        clean_text(p.get("name")): p
        for p in data.get("people", [])
        if clean_text(p.get("name"))
    }


def detect_changes(old: Optional[dict], new: dict) -> list[dict]:
    if old is None:
        return [{"type": "INITIAL", "text": "최초 데이터 등록"}]

    changes = []

    old_p = person_map(old)
    new_p = person_map(new)

    for name in sorted(set(new_p) - set(old_p)):
        changes.append({"type": "PERSON_ADDED", "text": f"신규 주요인사: {name}"})

    for name in sorted(set(old_p) - set(new_p)):
        changes.append({"type": "PERSON_REMOVED", "text": f"주요인사 제외/변경 가능성: {name}"})

    for name in sorted(set(old_p) & set(new_p)):
        for field, label in [
            ("title", "직책"),
            ("education", "학력"),
            ("career", "경력"),
            ("remarks", "주요발언/활동"),
        ]:
            if old_p[name].get(field) != new_p[name].get(field):
                changes.append({
                    "type": "PERSON_CHANGED",
                    "text": f"{name} {label} 변경",
                    "before": old_p[name].get(field),
                    "after": new_p[name].get(field),
                })

    if normalized_hash(old.get("organization", [])) != normalized_hash(new.get("organization", [])):
        changes.append({"type": "ORG_CHANGED", "text": "조직도 변경 감지"})

    return changes


def append_change_log(company: dict, changes: list[dict]):
    if not changes:
        return

    path = DATA_DIR / "change_log.json"
    if path.exists():
        log = json.loads(path.read_text(encoding="utf-8"))
    else:
        log = []

    log.append({
        "checked_at": NOW.isoformat(timespec="seconds"),
        "key": company["key"],
        "company": company["name_ko"],
        "changes": changes,
    })

    path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# 7) 웹사이트 렌더링
# ============================================================

def esc(v) -> str:
    return html.escape(str(v or ""))


def bullets(items: list[str]) -> str:
    if not items:
        return '<div class="muted">확인된 정보 없음</div>'
    return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>"


def render_org(data: dict) -> str:
    org = data.get("organization", [])
    if not org:
        return '<div class="empty-box">조직도 연결 준비중</div>'

    cards = []
    for x in org:
        cls = "org-card hot" if x.get("highlight") else "org-card"
        leader = f'<div class="org-leader">{esc(x.get("leader"))}</div>' if x.get("leader") else ""
        cards.append(
            f'<div class="{cls}"><div class="org-title">{esc(x.get("name"))}</div>{leader}</div>'
        )
    return "".join(cards)


def render_person(person: dict, company_name: str, company_key: str, idx: int, total: int) -> str:
    img = (
        f'<img class="photo" src="{esc(person.get("image_url"))}" alt="">'
        if person.get("image_url")
        else '<div class="photo placeholder">PHOTO</div>'
    )

    source = (
        f'<a href="{esc(person.get("profile_url"))}" target="_blank">공식 프로필</a>'
        if person.get("profile_url")
        else "공식 홈페이지/공개자료"
    )

    name_line = esc(person.get("name"))
    if person.get("name_en"):
        name_line += f' <span class="sub">({esc(person.get("name_en"))})</span>'

    birth = esc(person.get("birth"))
    if birth:
        name_line += f' <span class="sub">· {birth}</span>'

    profile_id = f"profile-{company_key}-{idx}"
    return f"""
    <section class="paper profile-page" id="{profile_id}">
      <div class="paper-head">
        <div class="company">{esc(company_name)} 주요인사 프로필</div>
        <div class="date">{TODAY}</div>
      </div>

      <div class="profile-page-label">주요인사 프로필 {idx} / {total}</div>
      <h2>{esc(person.get("name"))} <span>{esc(person.get("title"))}</span></h2>

      <div class="identity">
        <div class="identity-table">
          <div class="label">성명</div><div class="value">{name_line}</div>
          <div class="label">직책</div><div class="value">{esc(person.get("title")) or "-"}</div>
          <div class="label">출처</div><div class="value">{source}</div>
        </div>
        {img}
      </div>

      <div class="profile-row">
        <div class="row-label">학력</div>
        <div class="row-body">{bullets(person.get("education", []))}</div>
      </div>

      <div class="profile-row career">
        <div class="row-label">경력</div>
        <div class="row-body">{bullets(person.get("career", []))}</div>
      </div>

      <div class="profile-row remarks">
        <div class="row-label">주요발언<br>·최근활동</div>
        <div class="row-body">{bullets(person.get("remarks", []))}</div>
      </div>
    </section>
    """


def render_profile_index(people: list[dict], company_key: str) -> str:
    if not people:
        return ""

    buttons = []
    for i, person in enumerate(people, start=1):
        target_id = f"profile-{company_key}-{i}"
        buttons.append(
            f'<button type="button" class="profile-jump" data-target="{target_id}">'
            f'<strong>{esc(person.get("name"))}</strong>'
            f'<span>{esc(person.get("title"))}</span>'
            f'</button>'
        )

    return f"""
    <div class="profile-index">
      <div class="profile-index-head">
        <div>
          <div class="profile-index-title">주요인사 프로필</div>
          <div class="profile-index-sub">총 {len(people)}명 · 이름을 누르면 상세 프로필로 이동</div>
        </div>
        <div class="profile-count">{len(people)}명</div>
      </div>
      <div class="profile-chip-grid">{''.join(buttons)}</div>
    </div>
    """


def render_company(data: dict, changes: list[dict]) -> str:
    status = data.get("status")
    status_label = {
        "OK": "자동수집 연결됨",
        "PARTIAL": "일부 수집",
        "PENDING": "연결 준비중",
        "DEMO": "샘플 화면",
    }.get(status, status)

    change_html = ""
    if changes:
        change_html = """
        <div class="change-box">
          <strong>최근 변경 감지</strong>
          <ul>%s</ul>
        </div>
        """ % "".join(f"<li>{esc(x.get('text'))}</li>" for x in changes[:8])

    people = data.get("people", [])
    profile_index = render_profile_index(people, data["key"])
    person_html = "".join(
        render_person(p, data["name_ko"], data["key"], i, len(people))
        for i, p in enumerate(people, start=1)
    )
    if not person_html:
        person_html = """
        <section class="paper">
          <div class="empty-box big">
            주요인사 프로필 연결 준비중<br>
            <small>Leadership 페이지 URL 및 selector를 설정하면 자동 생성됩니다.</small>
          </div>
        </section>
        """

    return f"""
    <section class="company-view" data-company="{esc(data['key'])}">
      <div class="company-summary">
        <div>
          <div class="eyebrow">{esc(data['category'])} · {esc(data['country'])}</div>
          <h1>{esc(data['name_ko'])}</h1>
          <div class="en">{esc(data['name_en'])}</div>
        </div>
        <div class="status">{esc(status_label)}</div>
      </div>

      <section class="paper org-page">
        <div class="paper-head">
          <div class="company">{esc(data['name_ko'])} 조직도</div>
          <div class="date">{TODAY}</div>
        </div>

        <h2>{esc(data['name_ko'])} 조직도</h2>
        <div class="org-grid">{render_org(data)}</div>
        {profile_index}
        {change_html}

        <div class="source">
          <div><b>Source</b> {esc(data.get('source')) or '-'}</div>
          <div><b>Organization</b> {esc(data.get('organization_url')) or '-'}</div>
          <div><b>Leadership</b> {esc(data.get('leadership_url')) or '-'}</div>
          <div><b>Updated</b> {esc(data.get('updated_at'))}</div>
        </div>
      </section>

      {person_html}
    </section>
    """


def build_site(all_data: list[dict], changes_map: dict[str, list[dict]]):
    # 개별 json
    for d in all_data:
        (SITE_DATA_DIR / f"{d['key']}.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    categories = []
    for d in all_data:
        if d["category"] not in categories:
            categories.append(d["category"])

    nav = []
    for cat in categories:
        nav.append(f'<div class="nav-cat">{esc(cat)}</div>')
        for d in [x for x in all_data if x["category"] == cat]:
            badge = "●" if d["status"] in ("OK", "DEMO", "PARTIAL") else "○"
            nav.append(
                f'<button class="company-btn" data-key="{esc(d["key"])}">'
                f'<span>{badge}</span>{esc(d["name_ko"])}</button>'
            )

    views = "".join(
        render_company(d, changes_map.get(d["key"], []))
        for d in all_data
    )

    first_key = all_data[0]["key"] if all_data else ""

    page = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>기업·기관 조직도 및 주요인사 프로필</title>
<style>
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;font-family:"Malgun Gothic","Apple SD Gothic Neo",Arial,sans-serif;background:#eef2f6;color:#15191f}}
.topbar{{height:58px;background:#0b2545;color:#fff;display:flex;align-items:center;justify-content:space-between;padding:0 22px;position:sticky;top:0;z-index:20}}
.topbar b{{font-size:18px}}
.topbar button{{border:0;background:#ffd500;padding:9px 14px;border-radius:7px;font-weight:800;cursor:pointer}}
.layout{{display:grid;grid-template-columns:270px 1fr;min-height:calc(100vh - 58px)}}
.sidebar{{background:#102c50;color:#fff;padding:16px 12px;height:calc(100vh - 58px);position:sticky;top:58px;overflow:auto}}
.nav-cat{{font-size:12px;color:#9fb3cc;font-weight:800;margin:18px 8px 7px}}
.company-btn{{width:100%;border:0;background:transparent;color:#fff;text-align:left;padding:9px 10px;border-radius:7px;cursor:pointer;font-size:13px}}
.company-btn:hover,.company-btn.active{{background:#24496f}}
.company-btn span{{display:inline-block;width:18px;color:#ffd500}}
.main{{padding:22px}}
.company-view{{display:none;max-width:1080px;margin:0 auto}}
.company-view.active{{display:block}}
.company-summary{{display:flex;align-items:flex-end;justify-content:space-between;margin:0 auto 14px;max-width:210mm}}
.company-summary h1{{margin:3px 0 2px;font-size:27px}}
.company-summary .en{{color:#66717e}}
.eyebrow{{font-size:12px;color:#6f7a86;font-weight:700}}
.status{{background:#dbe9f8;color:#174d82;padding:7px 10px;border-radius:999px;font-size:12px;font-weight:800}}
.paper{{width:210mm;min-height:297mm;background:#fff;margin:0 auto 18px;padding:15mm 14mm;box-shadow:0 2px 14px rgba(0,0,0,.07)}}
.paper-head{{display:flex;justify-content:space-between;border-bottom:2px solid #9fa5ac;padding-bottom:8px;margin-bottom:18px}}
.paper-head .company{{font-size:20px;font-weight:900}}
.paper-head .date{{font-size:14px;color:#555}}
.paper h2{{font-size:28px;margin:10px 0 20px}}
.paper h2 span{{font-size:20px}}
.org-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.org-card{{background:#eef1f4;border:1px solid #cbd2d8;min-height:78px;padding:12px}}
.org-card.hot{{background:#f2e7a8;border:2px dashed #df3c3c}}
.org-title{{font-weight:900}}
.org-leader{{margin-top:8px;color:#185293;font-weight:800}}
.profile-index{{margin-top:28px;padding-top:20px;border-top:2px solid #d8dde3}}
.profile-index-head{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:12px}}
.profile-index-title{{font-size:20px;font-weight:900}}
.profile-index-sub{{font-size:12px;color:#697480;margin-top:4px}}
.profile-count{{background:#173e6c;color:#fff;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:800}}
.profile-chip-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}}
.profile-jump{{border:1px solid #cfd6de;background:#f8fafc;border-radius:7px;padding:11px 12px;text-align:left;cursor:pointer;display:flex;flex-direction:column;gap:4px}}
.profile-jump:hover{{background:#eef5fc;border-color:#8fb4d8}}
.profile-jump strong{{color:#174d82;font-size:14px}}
.profile-jump span{{color:#505c68;font-size:12px}}
.profile-page{{scroll-margin-top:76px}}
.profile-page-label{{display:inline-block;margin-bottom:3px;padding:5px 8px;background:#eaf2fa;color:#174d82;border-radius:5px;font-size:11px;font-weight:800}}
.identity{{display:grid;grid-template-columns:1fr 185px;gap:14px}}
.identity-table{{display:grid;grid-template-columns:105px 1fr;border-top:1px solid #d2d6db;border-left:1px solid #d2d6db}}
.identity-table>div{{border-right:1px solid #d2d6db;border-bottom:1px solid #d2d6db;padding:16px}}
.label{{background:#f5f5f5;font-weight:900;text-align:center}}
.value{{display:flex;align-items:center}}
.sub{{font-weight:400;color:#555;font-size:13px}}
.photo{{width:185px;height:220px;object-fit:cover;border:1px solid #ddd}}
.placeholder{{display:flex;align-items:center;justify-content:center;color:#aaa;background:#fafafa;font-weight:800}}
.profile-row{{display:grid;grid-template-columns:105px 1fr;border-left:1px solid #d2d6db;border-right:1px solid #d2d6db;border-bottom:1px solid #d2d6db;min-height:130px}}
.profile-row.career{{min-height:300px}}
.profile-row.remarks{{min-height:180px}}
.row-label{{background:#f5f5f5;border-right:1px solid #d2d6db;font-weight:900;display:flex;align-items:center;justify-content:center;text-align:center;padding:10px}}
.row-body{{padding:16px 18px;line-height:1.7}}
.row-body ul{{margin:0;padding-left:20px}}
.source{{margin-top:20px;color:#666;font-size:11px;line-height:1.7;word-break:break-all}}
.change-box{{margin-top:18px;background:#fff7d1;border:1px solid #e6cf64;padding:12px}}
.change-box ul{{margin:7px 0 0;padding-left:20px}}
.empty-box{{border:1px dashed #aab3bc;padding:35px;text-align:center;color:#7b8793}}
.empty-box.big{{margin-top:40px;padding:90px 20px;font-size:20px}}
.muted{{color:#9099a3}}
@media(max-width:900px){{
  .layout{{display:block}}
  .sidebar{{position:relative;top:auto;height:auto;display:flex;overflow-x:auto;padding:10px}}
  .nav-cat{{display:none}}
  .company-btn{{min-width:150px}}
  .main{{padding:10px}}
  .paper{{width:100%;min-height:0;padding:18px}}
  .org-grid{{grid-template-columns:1fr 1fr}}
  .profile-chip-grid{{grid-template-columns:1fr 1fr}}
  .identity{{grid-template-columns:1fr 120px}}
  .photo{{width:120px;height:150px}}
}}
@media print{{
  .topbar,.sidebar,.company-summary{{display:none!important}}
  .layout{{display:block}}
  .main{{padding:0}}
  .company-view{{display:none!important}}
  .company-view.active{{display:block!important}}
  .paper{{width:auto;min-height:0;margin:0;box-shadow:none;page-break-after:always}}
  .paper:last-child{{page-break-after:auto}}
}}
</style>
</head>
<body>
<div class="topbar">
  <b>기업·기관 조직도 및 주요인사 프로필</b>
  <button onclick="window.print()">PDF / 인쇄</button>
</div>
<div class="layout">
  <aside class="sidebar">
    {''.join(nav)}
  </aside>
  <main class="main">
    {views}
  </main>
</div>
<script>
const buttons=[...document.querySelectorAll('.company-btn')];
const views=[...document.querySelectorAll('.company-view')];

function openCompany(key){{
  buttons.forEach(b=>b.classList.toggle('active',b.dataset.key===key));
  views.forEach(v=>v.classList.toggle('active',v.dataset.company===key));
  localStorage.setItem('profile-company',key);
  window.scrollTo({{top:0,behavior:'instant'}});
}}
buttons.forEach(b=>b.addEventListener('click',()=>openCompany(b.dataset.key)));

document.addEventListener('click',(e)=>{{
  const btn=e.target.closest('.profile-jump');
  if(!btn) return;
  const target=document.getElementById(btn.dataset.target);
  if(!target) return;
  target.scrollIntoView({{behavior:'smooth',block:'start'}});
}});

const saved=localStorage.getItem('profile-company');
const valid=buttons.some(b=>b.dataset.key===saved);
openCompany(valid?saved:{json.dumps(first_key)});
</script>
</body>
</html>"""

    (SITE_DIR / "index.html").write_text(page, encoding="utf-8")
    (BASE_DIR / "index.html").write_text(page, encoding="utf-8")


# ============================================================
# 8) 실행
# ============================================================

def main():
    all_data = []
    changes_map = {}

    print("=" * 72)
    print("기업·기관 조직도 / 주요인사 프로필 자동 업데이트")
    print("=" * 72)

    for idx, target in enumerate(TARGETS, 1):
        print(f"[{idx:02d}/{len(TARGETS)}] {target.name_ko} ... ", end="", flush=True)

        try:
            new_data = collect_target(target)
        except Exception as e:
            new_data = {
                "key": target.key,
                "category": target.category,
                "name_ko": target.name_ko,
                "name_en": target.name_en,
                "country": target.country,
                "official_url": target.official_url,
                "organization_url": target.organization_url,
                "leadership_url": target.leadership_url,
                "updated_at": NOW.isoformat(timespec="seconds"),
                "status": "ERROR",
                "errors": [str(e)],
                "organization": [],
                "people": [],
                "source": "",
                "demo": False,
            }

        old_data = load_snapshot(target.key)
        changes = detect_changes(old_data, new_data)

        # PENDING 상태는 빈 데이터로 기존 실제 snapshot을 덮지 않도록 보호
        if new_data["status"] != "PENDING":
            save_snapshot(target.key, new_data)

        append_change_log(new_data, changes)

        all_data.append(new_data)
        changes_map[target.key] = changes

        print(f"{new_data['status']} / 인사 {len(new_data.get('people', []))}명")

    build_site(all_data, changes_map)

    registry_path = DATA_DIR / "company_registry.json"
    registry_path.write_text(
        json.dumps([asdict(x) for x in TARGETS], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("[완료]")
    print("웹사이트 :", SITE_DIR / "index.html")
    print("Pages 루트:", BASE_DIR / "index.html")
    print("마스터 DB:", registry_path)
    print("Snapshot :", SNAPSHOT_DIR)
    print("변경이력 :", DATA_DIR / "change_log.json")
    print()
    print("※ 실제 자동수집을 시작하려면 TARGETS의 각 회사에")
    print("   organization_url / leadership_url / CSS selector를 설정하세요.")


if __name__ == "__main__":
    main()
