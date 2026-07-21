"""Freeze public source pages into a private, versioned Owner Gold corpus."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import cast
from urllib.parse import urljoin, urlparse

import httpx2 as httpx
from srbg_api.intelligence_v2.owner_gold_preparation import (
    FrozenCorpusCase,
    _validate_corpus,
)

try:
    from scripts.select_intelligence_v2_owner_gold_corpus import canonicalize_url
except ModuleNotFoundError:  # Direct ``python scripts/...py`` execution.
    from select_intelligence_v2_owner_gold_corpus import canonicalize_url

_ROOT = Path(__file__).resolve().parents[1]
_USER_AGENT = "SRBG-OwnerGold-EvidenceFreeze/1.0 (+private research; contact owner)"
_SPACE = re.compile(r"\s+")
_BLOCK_TAGS = {"h1", "h2", "h3", "p", "li", "blockquote", "td"}
_IGNORED_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "form",
    "nav",
    "header",
    "footer",
    "aside",
}
_BOILERPLATE = (
    "版权所有",
    "网站地图",
    "联系我们",
    "推荐阅读",
    "相关阅读",
    "打印本页",
    "关闭窗口",
    "浏览器版本",
    "ICP备",
    "公网安备",
)
_ENGINEERING_FACT_TERMS = (
    "通车",
    "投运",
    "投入运营",
    "贯通",
    "竣工",
    "开工",
    "施工",
    "改扩建",
    "工程",
    "部署",
    "安装",
    "监测",
    "报警",
    "整改",
    "处罚",
    "事故",
    "数字化",
)
_INDUSTRY_MILESTONE_TERMS = (
    "通车",
    "投运",
    "投入运营",
    "贯通",
    "竣工",
    "开工",
    "完成施工",
    "主体完工",
    "重大节点",
)
_OBJECT_EVIDENCE_TERMS = {
    "HIGHWAY": ("公路", "高速"),
    "RAILWAY": ("铁路", "轨道交通"),
    "BRIDGE": ("桥梁", "大桥", "桥涵"),
    "TUNNEL": ("隧道", "隧洞"),
    "BUILDING": ("房屋建筑", "建筑施工", "建筑工程", "站房", "航站楼"),
    "MINING": ("矿山", "煤矿", "矿井"),
    "MUNICIPAL": ("市政", "城市管网", "城镇燃气", "地下管网"),
    "WATER_CONSERVANCY": ("水利", "水库", "水务", "水电站"),
    "PORT_WATERWAY": ("港口", "码头", "航道", "水运"),
    "AIRPORT": ("机场", "跑道", "航站楼"),
    "ENERGY": ("能源", "电力", "电网", "电站", "光伏", "风电", "供热", "燃气"),
}
_PRIMARY_TYPE_EVIDENCE_TERMS = {
    "DIGITAL_TRANSFORMATION": ("数字", "智能", "信息化", "BIM", "机器人", "无人"),
    "SAFETY_INTELLIGENCE": ("安全", "事故", "隐患", "处罚", "整改", "监管", "标准", "规范"),
}


class _BodyBlockParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._active_tag: str | None = None
        self._text: list[str] = []
        self._anchor_depth = 0
        self._anchor_characters = 0
        self._title_depth = 0
        self._title_text: list[str] = []
        self.blocks: list[tuple[str, str, int]] = []

    @property
    def title(self) -> str:
        return _SPACE.sub(" ", " ".join(self._title_text)).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lowered = tag.lower()
        if lowered in _IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if lowered == "title":
            self._title_depth += 1
        if lowered == "a":
            self._anchor_depth += 1
        if lowered in _BLOCK_TAGS and self._active_tag is None:
            self._active_tag = lowered
            self._text = []
            self._anchor_characters = 0

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in _IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if lowered == "title" and self._title_depth:
            self._title_depth -= 1
        if lowered == "a" and self._anchor_depth:
            self._anchor_depth -= 1
        if lowered == self._active_tag:
            text = _SPACE.sub(" ", " ".join(self._text)).strip()
            self.blocks.append((lowered, text, self._anchor_characters))
            self._active_tag = None
            self._text = []
            self._anchor_characters = 0

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._title_depth:
            self._title_text.append(data)
        if self._active_tag is not None:
            self._text.append(data)
            if self._anchor_depth:
                self._anchor_characters += len(_SPACE.sub("", data))


def _outside_repository(path: Path) -> None:
    if path.resolve().is_relative_to(_ROOT):
        raise ValueError("PRIVATE_OWNER_GOLD_PATH_MUST_BE_OUTSIDE_REPOSITORY")


def _public_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("SOURCE_URL_MUST_BE_PUBLIC_HTTPS")
    for result in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(result[4][0])
        if not address.is_global:
            raise ValueError("SOURCE_URL_RESOLVES_TO_NON_PUBLIC_ADDRESS")


def _fetch(url: str) -> tuple[bytes, str, str]:
    current = url
    with httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        for _hop in range(4):
            _public_https(current)
            response = client.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("SOURCE_REDIRECT_WITHOUT_LOCATION")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0]
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise ValueError(f"SOURCE_MIME_NOT_SUPPORTED:{content_type}")
            return response.content, current, content_type
    raise ValueError("SOURCE_REDIRECT_LIMIT_EXCEEDED")


def _decode_html(raw: bytes) -> str:
    head = raw[:4096].decode("ascii", errors="ignore")
    declared = re.search(r"charset\s*=\s*['\"]?([a-zA-Z0-9_-]+)", head, re.I)
    encodings = [declared.group(1)] if declared else []
    encodings.extend(["utf-8", "gb18030"])
    for encoding in dict.fromkeys(encodings):
        try:
            return raw.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _normalize_html(raw: bytes) -> tuple[str, str, tuple[str, ...]]:
    parser = _BodyBlockParser()
    parser.feed(_decode_html(raw))
    parser.close()
    parsed_blocks = parser.blocks
    blocks: list[str] = []
    locators: list[str] = []
    total = 0
    for index, (tag, text, anchor_characters) in enumerate(parsed_blocks, 1):
        visible_characters = len(_SPACE.sub("", text))
        if (
            len(text) < 12
            or text in blocks
            or any(term in text for term in _BOILERPLATE)
            or (visible_characters and anchor_characters / visible_characters > 0.45)
        ):
            continue
        encoded = text.encode("utf-8")
        block_hash = sha256(encoded).hexdigest()
        blocks.append(text)
        locators.append(f"html:{tag}:{index}:sha256:{block_hash}")
        total += len(text)
        if total >= 8_000:
            break
    normalized = "\n\n".join(blocks).strip()
    h1 = next((text for tag, text, _anchors in parsed_blocks if tag == "h1" and text), "")
    title = _SPACE.sub(" ", unescape(h1 or parser.title)).strip()
    if not title or len(normalized) < 40 or not locators:
        raise ValueError("SOURCE_CONTENT_INSUFFICIENT")
    return title[:500], normalized, tuple(locators)


def validate_frozen_content(
    candidate: dict[str, object], *, title: str, normalized_content: str
) -> None:
    """Apply preregistered central-fact gates without consulting Owner labels."""

    combined = f"{title}\n{normalized_content}"
    primary_type = candidate.get("sampling_primary_type")
    negative_family = candidate.get("negative_family")
    central_fact_kind = candidate.get("central_fact_kind")
    if candidate.get("sampling_stratum") == "POSITIVE":
        primary_terms = _PRIMARY_TYPE_EVIDENCE_TERMS.get(str(primary_type))
        if primary_terms is not None and not any(term in combined for term in primary_terms):
            raise ValueError(f"POSITIVE_PRIMARY_TYPE_NOT_EVIDENCED:{primary_type}")
        for engineering_object in candidate.get("engineering_objects", []):
            terms = _OBJECT_EVIDENCE_TERMS.get(str(engineering_object), ())
            if not terms or not any(term in combined for term in terms):
                raise ValueError(
                    f"POSITIVE_ENGINEERING_OBJECT_NOT_EVIDENCED:{engineering_object}"
                )
        if "TUNNEL_GAS_MONITORING" in candidate.get("specialty_facets", []) and not (
            any(term in combined for term in ("瓦斯", "有毒有害气体", "有害气体"))
            and any(term in combined for term in ("监测", "检测", "报警"))
        ):
            raise ValueError("POSITIVE_TUNNEL_GAS_NOT_EVIDENCED")
        if "CONSTRUCTION_MACHINERY" in candidate.get("equipment_domains", []) and not (
            "施工" in combined
            and any(term in combined for term in ("机械", "设备", "机器人", "台车"))
        ):
            raise ValueError("POSITIVE_CONSTRUCTION_MACHINERY_NOT_EVIDENCED")
    if primary_type == "INDUSTRY_UPDATE" and not any(
        term in combined for term in _INDUSTRY_MILESTONE_TERMS
    ):
        raise ValueError("INDUSTRY_UPDATE_MILESTONE_NOT_EVIDENCED")
    if negative_family == "PROCESS_ONLY_NOTICE" and any(
        term in combined for term in _ENGINEERING_FACT_TERMS
    ):
        raise ValueError("PROCESS_ONLY_NOTICE_CONTAINS_ENGINEERING_FACT")
    if negative_family == "PURE_MEDICAL_HEALTH" and any(
        term in combined for term in ("工程", "施工", "改扩建", "新院区", "建筑", "竣工", "开工")
    ):
        raise ValueError("PURE_MEDICAL_CASE_CONTAINS_ENGINEERING_FACT")
    if central_fact_kind == "PURE_MEDICAL_HEALTH" and not any(
        term in combined for term in ("诊疗", "药品", "用药", "健康", "疾病", "临床")
    ):
        raise ValueError("PURE_MEDICAL_CENTRAL_FACT_NOT_EVIDENCED")
    if (
        candidate.get("sampling_stratum") == "POSITIVE"
        and "通知" in title
        and not any(
            term in combined
            for term in (
                "必须",
                "标准",
                "事故",
                "整改",
                "处罚",
                "施工",
                "部署",
                "监测",
                "数字化",
            )
        )
    ):
        raise ValueError("SUBSTANTIVE_NOTICE_FACT_NOT_EVIDENCED")


def _validate_frozen_plan_design(plan: dict[str, object]) -> None:
    raw_cases = plan.get("cases")
    if not isinstance(raw_cases, list) or not all(isinstance(value, dict) for value in raw_cases):
        raise ValueError("OWNER_GOLD_SELECTION_PLAN_INVALID")
    cases = cast(list[dict[str, object]], raw_cases)
    positives = [value for value in cases if value.get("sampling_stratum") == "POSITIVE"]
    boundaries = [value for value in cases if value.get("sampling_stratum") == "BOUNDARY"]
    negatives = [value for value in cases if value.get("sampling_stratum") == "NEGATIVE"]
    if (len(positives), len(boundaries), len(negatives)) != (20, 0, 20):
        raise ValueError("OWNER_GOLD_SELECTION_PLAN_DISTRIBUTION_INVALID")
    positive_types = Counter(value.get("sampling_primary_type") for value in positives)
    if positive_types != {
        "DIGITAL_TRANSFORMATION": 7,
        "SAFETY_INTELLIGENCE": 7,
        "INDUSTRY_UPDATE": 6,
    }:
        raise ValueError("OWNER_GOLD_SELECTION_PLAN_PRIMARY_TYPE_INVALID")
    covered_objects = {
        str(obj) for value in positives for obj in value.get("engineering_objects", [])
    }
    if covered_objects != {
        "HIGHWAY",
        "RAILWAY",
        "BRIDGE",
        "TUNNEL",
        "BUILDING",
        "MINING",
        "MUNICIPAL",
        "WATER_CONSERVANCY",
        "PORT_WATERWAY",
        "AIRPORT",
        "ENERGY",
    }:
        raise ValueError("OWNER_GOLD_SELECTION_PLAN_OBJECT_COVERAGE_INVALID")
    if not any(
        "TUNNEL_GAS_MONITORING" in value.get("specialty_facets", [])
        and "TUNNEL" in value.get("engineering_objects", [])
        and bool({"HIGHWAY", "RAILWAY"} & set(value.get("engineering_objects", [])))
        for value in positives
    ):
        raise ValueError("OWNER_GOLD_SELECTION_PLAN_TUNNEL_GAS_INVALID")
    if (
        sum("CONSTRUCTION_MACHINERY" in value.get("equipment_domains", []) for value in positives)
        < 2
    ):
        raise ValueError("OWNER_GOLD_SELECTION_PLAN_EQUIPMENT_INVALID")
    negative_counts = Counter(value.get("negative_family") for value in negatives)
    if set(negative_counts.values()) != {4} or len(negative_counts) != 5:
        raise ValueError("OWNER_GOLD_SELECTION_PLAN_NEGATIVE_QUOTA_INVALID")


def freeze(plan_path: Path, output_root: Path) -> list[FrozenCorpusCase]:
    _outside_repository(output_root)
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes.decode("utf-8"))
    if plan.get("corpus_version") in {
        "owner-gold-2026-07-20.2",
        "owner-gold-2026-07-20.3",
        "owner-gold-2026-07-20.4",
        "owner-gold-2026-07-20.5",
    }:
        _validate_frozen_plan_design(plan)
    raw_root = output_root / "raw"
    corpus_root = output_root / "corpus"
    manifest_path = corpus_root / "corpus-manifest.json"
    if manifest_path.exists():
        raise ValueError("OWNER_GOLD_CORPUS_ALREADY_FROZEN")
    cases: list[FrozenCorpusCase] = []
    fetch_receipts: list[dict[str, object]] = []
    design_receipts: list[dict[str, object]] = []
    failures: list[str] = []
    excluded_case_ids = {str(value) for value in plan.get("excluded_case_ids", [])}
    excluded_urls = {
        canonicalize_url(str(value)) for value in plan.get("excluded_canonical_urls", [])
    }
    excluded_content_hashes = {str(value) for value in plan.get("excluded_content_sha256", [])}
    if any(str(item.get("case_id")) in excluded_case_ids for item in plan["cases"]):
        raise ValueError("OWNER_GOLD_PRIOR_CASE_ID_REUSED")
    selected_urls: set[str] = set()
    selected_content_hashes: set[str] = set()
    for item in plan["cases"]:
        raw: bytes | None = None
        final_url = ""
        content_type = ""
        title = ""
        normalized = ""
        locators: tuple[str, ...] = ()
        selected_candidate: dict[str, object] | None = None
        selected_candidate_index = 0
        candidate_failures: list[str] = []
        candidate_chain = item.get("candidate_chain")
        if not isinstance(candidate_chain, list):
            candidate_chain = [{"canonical_url": item["url"]}]
        for candidate_index, candidate_value in enumerate(candidate_chain, 1):
            if not isinstance(candidate_value, dict):
                candidate_failures.append(f"{candidate_index}:CANDIDATE_INVALID")
                continue
            candidate = cast(dict[str, object], candidate_value)
            requested_url = str(candidate.get("canonical_url") or candidate.get("url") or "")
            try:
                fetched_raw, fetched_final_url, fetched_content_type = _fetch(requested_url)
                fetched_title, fetched_normalized, fetched_locators = _normalize_html(fetched_raw)
                content_hash = sha256(fetched_normalized.encode("utf-8")).hexdigest()
                canonical_final_url = canonicalize_url(fetched_final_url)
                if canonical_final_url in excluded_urls:
                    raise ValueError("OWNER_GOLD_PRIOR_CANONICAL_URL_REUSED")
                if content_hash in excluded_content_hashes:
                    raise ValueError("OWNER_GOLD_PRIOR_CONTENT_HASH_REUSED")
                if canonical_final_url in selected_urls:
                    raise ValueError("OWNER_GOLD_FINAL_CANONICAL_URL_DUPLICATE")
                if content_hash in selected_content_hashes:
                    raise ValueError("OWNER_GOLD_FINAL_CONTENT_HASH_DUPLICATE")
                validate_frozen_content(
                    {**item, **candidate},
                    title=fetched_title,
                    normalized_content=fetched_normalized,
                )
            except (ValueError, httpx.HTTPError) as error:
                candidate_failures.append(f"{candidate_index}:{error}")
                continue
            raw = fetched_raw
            final_url = canonical_final_url
            content_type = fetched_content_type
            title = fetched_title
            normalized = fetched_normalized
            locators = fetched_locators
            selected_candidate = candidate
            selected_candidate_index = candidate_index
            break
        if raw is None or selected_candidate is None:
            failures.append(
                f"{item['case_id']}:NO_ELIGIBLE_CANDIDATE:{'|'.join(candidate_failures)}"
            )
            continue
        retrieved_at = datetime.now(UTC)
        case_id = str(item["case_id"])
        raw_path = raw_root / f"{case_id}.html"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw)
        case = FrozenCorpusCase(
            case_id=case_id,
            corpus_version=str(plan["corpus_version"]),
            sampling_stratum=item["sampling_stratum"],
            sampling_primary_type=item["sampling_primary_type"],
            title=title,
            source_url=final_url,
            rights_basis="PUBLIC_OFFICIAL_PAGE_PRIVATE_RESEARCH_NO_REDISTRIBUTION",
            retrieved_at=retrieved_at,
            raw_object_path=str(raw_path.resolve()),
            raw_object_sha256=sha256(raw).hexdigest(),
            normalized_content=normalized,
            content_sha256=sha256(normalized.encode("utf-8")).hexdigest(),
            evidence_locators=locators,
        )
        selected_urls.add(final_url)
        selected_content_hashes.add(case.content_sha256)
        cases.append(case)
        fetch_receipts.append(
            {
                "case_id": case_id,
                "selection_slot": item.get("selection_slot"),
                "candidate_id": selected_candidate.get("candidate_id"),
                "candidate_index": selected_candidate_index,
                "requested_url": selected_candidate.get("canonical_url")
                or selected_candidate.get("url"),
                "final_url": final_url,
                "canonical_url_sha256": sha256(final_url.encode("utf-8")).hexdigest(),
                "content_type": content_type,
                "retrieved_at": retrieved_at.isoformat(),
                "raw_object_sha256": case.raw_object_sha256,
                "content_sha256": case.content_sha256,
                "prior_candidate_failures": candidate_failures,
            }
        )
        design_receipts.append(
            {
                "case_id": case_id,
                "selection_slot": item.get("selection_slot"),
                "sampling_stratum": item["sampling_stratum"],
                "sampling_primary_type": item["sampling_primary_type"],
                "boundary_family": item.get("boundary_family"),
                "negative_family": item.get("negative_family"),
                "central_fact_kind": item.get("central_fact_kind"),
                "engineering_objects": item.get("engineering_objects", []),
                "specialty_facets": item.get("specialty_facets", []),
                "equipment_domains": item.get("equipment_domains", []),
            }
        )
    if failures:
        raise ValueError("OWNER_GOLD_SOURCE_FETCH_FAILED:" + ",".join(failures))
    _validate_corpus(cases, corpus_version=str(plan["corpus_version"]))
    corpus_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "intelligence-v2-owner-gold-corpus-1.1.0",
        "corpus_version": plan["corpus_version"],
        "rule_version": plan["rule_version"],
        "model_id": plan["model_id"],
        "model_profile_version": plan["model_profile_version"],
        "prompt_version": plan["prompt_version"],
        "model_schema_version": plan["model_schema_version"],
        "owner_gold_schema_version": plan["owner_gold_schema_version"],
        "selection_plan_sha256": sha256(plan_bytes).hexdigest(),
        "candidate_frame_sha256": plan.get("candidate_frame_sha256"),
        "prior_corpus_manifest_sha256": plan.get("prior_corpus_manifest_sha256"),
        "frozen_at": datetime.now(UTC).isoformat(),
        "rights_notice": "Private research only; do not commit or redistribute source bodies.",
        "cases": [asdict(case) for case in cases],
        "case_design": design_receipts,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str, sort_keys=True)
    manifest_path.write_text(rendered + "\n", encoding="utf-8")
    (corpus_root / "fetch-receipts.json").write_text(
        json.dumps(fetch_receipts, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return cases


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    cases = freeze(args.plan, args.output_root)
    print(f"OWNER_GOLD_CORPUS_FROZEN:{len(cases)}:{args.output_root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
