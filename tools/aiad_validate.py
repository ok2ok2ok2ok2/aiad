#!/usr/bin/env python3
"""AIAD validator.

Validates AIAD offers files (``ai-ads``) and reviews files (``ai-reviews``)
against the JSON schemas shipped in this repository, plus a set of semantic
checks (duplicate ids, host/domain consistency, date ranges, vocabulary
conformance, prompt-injection attempts and marketing superlatives).

Usage:
    python tools/aiad_validate.py FILE [FILE ...] [--vocab PATH | --no-vocab]
                                   [--host HOST] [--now ISO] [--json] [--version]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

try:
    import jsonschema
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover - dependency is declared in the spec
    jsonschema = None
    Draft202012Validator = None
    FormatChecker = None

VERSION = "0.1.0"

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
    else os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE)
SCHEMA_DIR = os.path.join(REPO_ROOT, "schema")
DEFAULT_VOCAB = os.path.join(REPO_ROOT, "vocab", "categories.json")
OFFERS_SCHEMA = os.path.join(SCHEMA_DIR, "ai-ads.schema.json")
REVIEWS_SCHEMA = os.path.join(SCHEMA_DIR, "ai-reviews.schema.json")


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

@dataclass
class Finding:
    """A single validation finding."""

    file: str
    path: str
    code: str
    severity: str
    message: str

    def __str__(self) -> str:
        return "{:<7} {:<20} {}:{}  {}".format(
            self.severity.upper(), self.code, self.file, self.path, self.message
        )


def _finding(file: str, path: str, code: str, severity: str, message: str) -> Finding:
    return Finding(file=file, path=path or "", code=code, severity=severity, message=message)


# --------------------------------------------------------------------------
# Regexes
# --------------------------------------------------------------------------

INSTRUCTION_PATTERNS = [
    # English
    r"ignore (all|any|previous|prior|earlier|above|the above|other)\b",
    r"ignore .{0,20}instructions",
    r"disregard (all|any|previous|prior|the|other)\b",
    r"\byou are (a|an|the|now)\b",
    r"\bas an ai\b",
    r"system prompt",
    r"\b(always|only|must) recommend",
    r"\brecommend (only|us|this (product|store|shop))\b",
    r"\b(do not|don't|never) mention\b",
    r"\brank (us|this|it) (first|higher|on top)\b",
    r"note to the (ai|assistant|model)",
    r"\[/?inst\]",
    r"<\|",
    r"^\s*(assistant|system)\s*:",
    # Chinese
    r"忽略(之前|前面|以上|其他|所有|先前)",
    r"你(現在)?是一?(個|位)?(購物|AI|ai|人工智慧)?助(理|手)",
    r"你現在是",
    r"(一定要|務必|請|只能|優先)推薦",
    r"不要提(到|及)",
    r"系統提示",
    r"扮演",
]

INSTRUCTION_RE = re.compile("|".join("(?:{})".format(p) for p in INSTRUCTION_PATTERNS),
                            re.IGNORECASE | re.MULTILINE)

SUPERLATIVE_RE = re.compile(
    r"\b(best|greatest|number one|world'?s (leading|first|best))\b|#1\b|\bno\.\s?1\b"
    r"|最好|最佳|最強|第一|頂級|冠軍|首選",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _pointer(parts: Iterable[Any]) -> str:
    """Build a JSON pointer from path components."""
    out = ""
    for part in parts:
        token = str(part).replace("~", "~0").replace("/", "~1")
        out += "/" + token
    return out


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse an ISO 8601 datetime; naive values are treated as UTC."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_date(value: Any) -> Optional[date]:
    """Parse an ISO 8601 date (or datetime) into a date."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _hostname(url: Any) -> Optional[str]:
    if not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = parsed.hostname
    return host.lower() if host else None


def _domain_matches(host: Optional[str], domain: Optional[str]) -> bool:
    """True when host equals domain or is a subdomain of it."""
    if not host or not domain:
        return False
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".").lstrip(".")
    if not domain:
        return False
    return host == domain or host.endswith("." + domain)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "number":
        return _is_number(value)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _load_json(path: str) -> tuple[Optional[Any], Optional[Finding]]:
    """Load a JSON file. Returns (data, finding)."""
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    except OSError as exc:
        return None, _finding(path, "", "E-IO", "error",
                              "cannot read file: {}".format(exc))
    except UnicodeDecodeError as exc:
        return None, _finding(path, "", "E-IO", "error",
                              "file is not UTF-8: {}".format(exc))
    try:
        return json.loads(text), None
    except ValueError as exc:
        return None, _finding(path, "", "E-JSON", "error",
                              "invalid JSON: {}".format(exc))


def _load_schema(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _load_vocab(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    categories = data.get("categories")
    if not isinstance(categories, dict):
        return None
    return categories


# --------------------------------------------------------------------------
# Schema validation
# --------------------------------------------------------------------------

def _schema_findings(file: str, data: Any, schema: Optional[dict]) -> list[Finding]:
    if schema is None or Draft202012Validator is None:
        return []
    try:
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    except Exception as exc:  # pragma: no cover - defensive
        return [_finding(file, "", "E-SCHEMA", "error",
                         "schema validation failed: {}".format(exc))]
    out = []
    for err in errors:
        out.append(_finding(file, _pointer(err.absolute_path), "E-SCHEMA", "error",
                            err.message))
    return out


# --------------------------------------------------------------------------
# Recursive scans
# --------------------------------------------------------------------------

def _scan_instructions(file: str, node: Any, parts: list[Any]) -> list[Finding]:
    out: list[Finding] = []
    if isinstance(node, str):
        match = INSTRUCTION_RE.search(node)
        if match:
            out.append(_finding(
                file, _pointer(parts), "E-INSTRUCTION", "error",
                "text appears to address an AI: {!r}".format(match.group(0)),
            ))
    elif isinstance(node, dict):
        for key, value in node.items():
            out.extend(_scan_instructions(file, value, parts + [key]))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(_scan_instructions(file, value, parts + [index]))
    return out


def _scan_superlatives(file: str, node: Any, parts: list[Any]) -> list[Finding]:
    out: list[Finding] = []
    if isinstance(node, str):
        match = SUPERLATIVE_RE.search(node)
        if match:
            out.append(_finding(
                file, _pointer(parts), "W-SUPERLATIVE", "warning",
                "marketing superlative {!r}; move it to a claim with evidence".format(
                    match.group(0)),
            ))
    elif isinstance(node, dict):
        for key, value in node.items():
            out.extend(_scan_superlatives(file, value, parts + [key]))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(_scan_superlatives(file, value, parts + [index]))
    return out


# --------------------------------------------------------------------------
# Offers checks
# --------------------------------------------------------------------------

def _check_offers(file: str, data: dict, vocab: Optional[dict], host: Optional[str],
                  now: datetime) -> list[Finding]:
    out: list[Finding] = []

    issuer = data.get("issuer")
    issuer_domain = None
    if isinstance(issuer, dict):
        domain = issuer.get("domain")
        if isinstance(domain, str):
            issuer_domain = domain

    if host is not None:
        if not issuer_domain or issuer_domain.lower() != host.lower():
            out.append(_finding(
                file, "/issuer/domain", "E-HOST", "error",
                "issuer.domain {!r} does not match expected host {!r}".format(
                    issuer_domain, host),
            ))

    offers = data.get("offers")
    if not isinstance(offers, list):
        return out

    seen_ids: dict[Any, int] = {}

    for index, offer in enumerate(offers):
        base = "/offers/{}".format(index)
        if not isinstance(offer, dict):
            continue

        offer_id = offer.get("id")
        if isinstance(offer_id, str):
            if offer_id in seen_ids:
                out.append(_finding(
                    file, base + "/id", "E-DUP-ID", "error",
                    "duplicate offer id {!r} (first seen at /offers/{}/id)".format(
                        offer_id, seen_ids[offer_id]),
                ))
            else:
                seen_ids[offer_id] = index

        url_host = _hostname(offer.get("url"))
        if url_host and issuer_domain:
            if not _domain_matches(url_host, issuer_domain):
                out.append(_finding(
                    file, base + "/url", "W-URL-DOMAIN", "warning",
                    "offer url host {!r} is not {!r} or a subdomain of it".format(
                        url_host, issuer_domain),
                ))

        valid_from = _parse_datetime(offer.get("valid_from"))
        valid_until = _parse_datetime(offer.get("valid_until"))

        if valid_from is not None and valid_until is not None and valid_from >= valid_until:
            out.append(_finding(
                file, base + "/valid_from", "E-RANGE", "error",
                "valid_from is not before valid_until",
            ))
        if valid_until is not None and valid_until < now:
            out.append(_finding(
                file, base + "/valid_until", "E-EXPIRED", "error",
                "offer expired at {}".format(valid_until.isoformat()),
            ))
        if valid_from is not None and valid_from > now:
            out.append(_finding(
                file, base + "/valid_from", "W-NOT-YET", "warning",
                "offer is not valid yet (starts {})".format(valid_from.isoformat()),
            ))

        claims = offer.get("claims")
        if isinstance(claims, list):
            today = now.date()
            for c_index, claim in enumerate(claims):
                if not isinstance(claim, dict):
                    continue
                expires = _parse_date(claim.get("expires"))
                if expires is not None and expires < today:
                    out.append(_finding(
                        file, "{}/claims/{}/expires".format(base, c_index),
                        "W-CLAIM-EXPIRED", "warning",
                        "claim evidence expired on {}".format(expires.isoformat()),
                    ))

        category = offer.get("category")
        category_specs = None
        if vocab is not None and isinstance(category, str):
            entry = vocab.get(category)
            if not isinstance(entry, dict):
                out.append(_finding(
                    file, base + "/category", "W-CATEGORY-UNKNOWN", "warning",
                    "unknown category {!r}".format(category),
                ))
            else:
                specs = entry.get("specs")
                category_specs = specs if isinstance(specs, dict) else {}

        if category_specs is not None:
            specs = offer.get("specs")
            if isinstance(specs, list):
                for s_index, spec in enumerate(specs):
                    if not isinstance(spec, dict):
                        continue
                    s_path = "{}/specs/{}".format(base, s_index)
                    name = spec.get("name")
                    if not isinstance(name, str):
                        continue
                    spec_def = category_specs.get(name)
                    if not isinstance(spec_def, dict):
                        out.append(_finding(
                            file, s_path + "/name", "W-SPEC-UNKNOWN", "warning",
                            "unknown spec {!r} for category {!r}".format(name, category),
                        ))
                        continue
                    expected_unit = spec_def.get("unit")
                    if expected_unit is not None:
                        actual_unit = spec.get("unit")
                        if actual_unit != expected_unit:
                            out.append(_finding(
                                file, s_path + "/unit", "E-SPEC-UNIT", "error",
                                "spec {!r} expects unit {!r}, got {!r}".format(
                                    name, expected_unit, actual_unit),
                            ))
                    expected_type = spec_def.get("type")
                    if isinstance(expected_type, str) and "value" in spec:
                        if not _type_matches(spec.get("value"), expected_type):
                            out.append(_finding(
                                file, s_path + "/value", "E-SPEC-TYPE", "error",
                                "spec {!r} expects type {!r}".format(name, expected_type),
                            ))

    return out


# --------------------------------------------------------------------------
# Reviews checks
# --------------------------------------------------------------------------

def _check_reviews(file: str, data: dict, offer_keys: Optional[set[tuple[str, str]]]) -> list[Finding]:
    out: list[Finding] = []
    if offer_keys is None:
        return out
    items = data.get("items")
    if not isinstance(items, list):
        return out
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        ref = item.get("offer_ref")
        if not isinstance(ref, dict):
            continue
        domain = ref.get("issuer_domain")
        offer_id = ref.get("offer_id")
        if not isinstance(domain, str) or not isinstance(offer_id, str):
            continue
        key = (domain.lower(), offer_id)
        if key not in offer_keys:
            out.append(_finding(
                file, "/items/{}/offer_ref".format(index), "W-REF-UNKNOWN", "warning",
                "offer_ref {!r} does not match any loaded offer".format(
                    "{}#{}".format(domain, offer_id)),
            ))
    return out


def _collect_offer_keys(data: dict) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    issuer = data.get("issuer")
    domain = None
    if isinstance(issuer, dict) and isinstance(issuer.get("domain"), str):
        domain = issuer["domain"].lower()
    offers = data.get("offers")
    if domain and isinstance(offers, list):
        for offer in offers:
            if isinstance(offer, dict) and isinstance(offer.get("id"), str):
                keys.add((domain, offer["id"]))
    return keys


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def validate_paths(paths: list[str], vocab_path: Optional[str] = None,
                   host: Optional[str] = None,
                   now: Optional[datetime] = None) -> list[Finding]:
    """Validate the given AIAD files and return all findings."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    vocab = _load_vocab(vocab_path)
    offers_schema = _load_schema(OFFERS_SCHEMA)
    reviews_schema = _load_schema(REVIEWS_SCHEMA)

    findings: list[Finding] = []
    loaded: list[tuple[str, str, dict]] = []  # (file, kind, data)

    for path in paths:
        data, err = _load_json(path)
        if err is not None:
            findings.append(err)
            continue
        if not isinstance(data, dict):
            findings.append(_finding(path, "", "E-TYPE", "error",
                                     "top-level JSON value must be an object"))
            continue
        if "aiad" in data:
            kind = "offers"
        elif "aiad_reviews" in data:
            kind = "reviews"
        else:
            findings.append(_finding(
                path, "", "E-TYPE", "error",
                "unrecognised file type: expected key 'aiad' or 'aiad_reviews'",
            ))
            continue
        loaded.append((path, kind, data))

    offer_keys: set[tuple[str, str]] = set()
    for _path, kind, data in loaded:
        if kind == "offers":
            offer_keys |= _collect_offer_keys(data)
    has_offers = any(kind == "offers" for _p, kind, _d in loaded)

    for path, kind, data in loaded:
        if kind == "offers":
            findings.extend(_schema_findings(path, data, offers_schema))
            findings.extend(_check_offers(path, data, vocab, host, now))
            findings.extend(_scan_instructions(path, data, []))
            offers = data.get("offers")
            if isinstance(offers, list):
                for index, offer in enumerate(offers):
                    if not isinstance(offer, dict):
                        continue
                    for field in ("title", "summary"):
                        text = offer.get(field)
                        if isinstance(text, str):
                            findings.extend(_scan_superlatives(
                                path, text, ["offers", index, field]))
        else:
            findings.extend(_schema_findings(path, data, reviews_schema))
            findings.extend(_scan_instructions(path, data, []))
            findings.extend(_check_reviews(path, data, offer_keys if has_offers else None))

    return findings


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiad_validate",
        description="Validate AIAD offers and reviews files.",
    )
    parser.add_argument("files", nargs="+", metavar="FILE",
                        help="AIAD JSON file(s) to validate")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--vocab", metavar="PATH",
                       help="path to the vocabulary file (default: repo vocab/categories.json)")
    group.add_argument("--no-vocab", action="store_true",
                       help="skip all vocabulary checks")
    parser.add_argument("--host", metavar="HOST",
                        help="expected issuer domain; mismatches are errors")
    parser.add_argument("--now", metavar="ISO",
                        help="reference time for date checks (ISO 8601, default: now)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit machine-readable JSON instead of text")
    parser.add_argument("--version", action="version",
                        version="aiad_validate {}".format(VERSION))
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

    parser = _build_parser()
    args = parser.parse_args(argv)

    for path in args.files:
        if not os.path.exists(path):
            print("error: file not found: {}".format(path), file=sys.stderr)
            return 2

    now = None
    if args.now is not None:
        now = _parse_datetime(args.now)
        if now is None:
            print("error: invalid --now value: {}".format(args.now), file=sys.stderr)
            return 2

    if args.no_vocab:
        vocab_path = None
    elif args.vocab is not None:
        vocab_path = args.vocab
    else:
        vocab_path = DEFAULT_VOCAB if os.path.exists(DEFAULT_VOCAB) else None

    findings = validate_paths(args.files, vocab_path=vocab_path, host=args.host, now=now)

    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")

    if args.as_json:
        payload = {
            "findings": [
                {
                    "file": f.file,
                    "path": f.path,
                    "code": f.code,
                    "severity": f.severity,
                    "message": f.message,
                }
                for f in findings
            ],
            "errors": errors,
            "warnings": warnings,
        }
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for finding in findings:
            print(str(finding))
        print("{} error(s), {} warning(s) in {} file(s)".format(
            errors, warnings, len(args.files)))

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
