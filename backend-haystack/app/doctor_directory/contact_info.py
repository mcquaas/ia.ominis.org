"""Extract phones and emails from JSON-LD blobs and HTML (shared across scrapers)."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

_LD_PHONE_KEYS = frozenset({"telephone", "faxNumber"})
_LD_EMAIL_KEYS = frozenset({"email"})

# Reasonable email pattern; exclude obvious non-contact tokens
_EMAIL_RE = re.compile(
    r"(?<![\w.-])([a-zA-Z0-9](?:[a-zA-Z0-9._-]*[a-zA-Z0-9])?@[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,})(?![\w.-])"
)

_PHONE_PATTERNS = [
    re.compile(r"\+52\s*\(?\d{2,3}\)?\s*[\d\s]{8,25}(?:\s*Ext\.?\s*\d+)?", re.I),
    re.compile(r"\(\+52\)\s*[\d\s\(\)]{10,30}", re.I),
]


def _is_noise_phone(value: str) -> bool:
    digits = re.sub(r"\D+", "", value or "")
    return digits.endswith("5593315610")


def _is_noise_email(value: str) -> bool:
    low = (value or "").strip().lower()
    return any(
        x in low
        for x in (
            "example.com",
            "domain.com",
            "sentry.io",
            "w3.org",
            "schema.org",
            "info@topdoctors.mx",
            "nombre@example.com",
        )
    )


def _norm_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        t = v.strip()
        return [t] if t else []
    if isinstance(v, (list, tuple)):
        out: list[str] = []
        for x in v:
            out.extend(_norm_str_list(x))
        return out
    return [str(v).strip()] if str(v).strip() else []


def walk_schema_org_contact(obj: Any, phones: list[str], emails: list[str]) -> None:
    """Collect telephone / faxNumber / email from nested JSON-LD dicts."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if k in _LD_PHONE_KEYS or kl in ("telephone", "faxnumber"):
                for s in _norm_str_list(v):
                    if s and not _is_noise_phone(s) and s not in phones:
                        phones.append(s)
            elif k in _LD_EMAIL_KEYS or kl == "email":
                for s in _norm_str_list(v):
                    low = s.lower()
                    if "@" in s and not low.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")) and not _is_noise_email(s):
                        if s not in emails:
                            emails.append(s)
            else:
                walk_schema_org_contact(v, phones, emails)
    elif isinstance(obj, list):
        for item in obj:
            walk_schema_org_contact(item, phones, emails)


def extract_contacts_from_json_ld(raw: Any) -> tuple[list[str], list[str]]:
    """Phones and emails from a stored JSON-LD object (Physician node or similar)."""
    phones: list[str] = []
    emails: list[str] = []
    if raw is None:
        return [], []
    walk_schema_org_contact(raw, phones, emails)
    return phones, emails


def extract_all_ld_graph_items_from_html(html: str) -> list[dict[str, Any]]:
    """Every object from application/ld+json script tags (@graph or single node)."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            for item in data["@graph"]:
                if isinstance(item, dict):
                    out.append(item)
        elif isinstance(data, dict) and data.get("@type"):
            out.append(data)
    return out


def extract_phones_from_html_regex(html: str) -> list[str]:
    """Mexico-focused phone patterns from raw HTML (same idea as legacy scraper)."""
    seen: set[str] = set()
    phones: list[str] = []
    for pat in _PHONE_PATTERNS:
        for m in pat.finditer(html):
            raw = re.sub(r"\s+", " ", m.group(0)).strip()
            if len(raw) < 12 or raw in seen:
                continue
            if _is_noise_phone(raw):
                continue
            seen.add(raw)
            phones.append(raw)
    return phones[:12]


def extract_emails_from_html(html: str) -> list[str]:
    """mailto: hrefs + visible email-like strings."""
    seen: set[str] = set()
    out: list[str] = []
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?", 1)[0].strip()
            if addr and "@" in addr and addr not in seen:
                seen.add(addr)
                out.append(addr)
    for m in _EMAIL_RE.finditer(html):
        e = m.group(1).strip()
        low = e.lower()
        if low in seen:
            continue
        if _is_noise_email(e) or any(x in low for x in ("@2x", "@3x")):
            continue
        seen.add(low)
        out.append(e)
    return out[:12]


def merge_unique_strings(*lists: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for s in lst or []:
            t = str(s).strip()
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
    return out


def build_phones_emails_for_row(
    *,
    html: str,
    physician_ld: dict[str, Any] | None,
    graph_items: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Merge phones/emails from: full JSON-LD graph (clinics, orgs), Physician node,
    regex on HTML, and mailto in HTML.
    """
    phones: list[str] = []
    emails: list[str] = []

    for item in graph_items or []:
        p, e = extract_contacts_from_json_ld(item)
        phones.extend(p)
        emails.extend(e)

    if physician_ld:
        p, e = extract_contacts_from_json_ld(physician_ld)
        phones.extend(p)
        emails.extend(e)

    phones.extend(extract_phones_from_html_regex(html))
    emails.extend(extract_emails_from_html(html))

    phones = merge_unique_strings(phones)
    emails = merge_unique_strings(emails)
    return phones, emails


def enriched_contact_lists_for_export(
    phones_json: list[str] | None,
    emails_json: list[str] | None,
    raw_json_ld: Any,
) -> tuple[list[str], list[str]]:
    """
    Dedupe phones/emails from DB columns + anything still present in raw_json_ld
    (for rows ingested before graph/email extraction).
    """
    from_ld_p, from_ld_e = extract_contacts_from_json_ld(raw_json_ld)
    phones = merge_unique_strings(phones_json, from_ld_p)
    emails = merge_unique_strings(emails_json, from_ld_e)
    return phones, emails


def enriched_contacts_for_export(
    phones_json: list[str] | None,
    emails_json: list[str] | None,
    raw_json_ld: Any,
) -> tuple[str, str]:
    phones, emails = enriched_contact_lists_for_export(phones_json, emails_json, raw_json_ld)
    return "; ".join(phones), "; ".join(emails)
