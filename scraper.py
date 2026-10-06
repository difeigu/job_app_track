"""
Fetches a job posting URL and extracts as much structured information as
possible: first via embedded schema.org JobPosting JSON-LD (used by most
ATS platforms — Greenhouse, Lever, Workday, SmartRecruiters, LinkedIn,
Indeed, etc.), falling back to Open Graph / meta tags, and finally to
URL-pattern heuristics (e.g. greenhouse.io/{company}/... or lever.co/{company}/...).
"""
import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

TITLE_SUFFIX_SPLIT = re.compile(r"\s*[|\-–—]\s*")

KNOWN_SOURCES = {
    "linkedin.com": "LinkedIn",
    "indeed.com": "Indeed",
    "glassdoor.com": "Glassdoor",
    "greenhouse.io": "Greenhouse",
    "job-boards.greenhouse.io": "Greenhouse",
    "boards.greenhouse.io": "Greenhouse",
    "lever.co": "Lever",
    "jobs.lever.co": "Lever",
    "myworkdayjobs.com": "Workday",
    "smartrecruiters.com": "SmartRecruiters",
    "workable.com": "Workable",
    "bamboohr.com": "BambooHR",
    "ashbyhq.com": "Ashby",
    "wellfound.com": "Wellfound",
    "ziprecruiter.com": "ZipRecruiter",
    "monster.com": "Monster",
}

REMOTE_PATTERN = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b|\btelecommute\b", re.I)
HYBRID_PATTERN = re.compile(r"\bhybrid\b", re.I)
ONSITE_PATTERN = re.compile(r"\bon[\s-]?site\b|\bin[\s-]?office\b|\bin[\s-]?person\b", re.I)

EMPLOYMENT_TYPE_PATTERNS = [
    (re.compile(r"\bintern(ship)?\b", re.I), "Internship"),
    (re.compile(r"\bpart[\s-]?time\b", re.I), "Part-time"),
    (re.compile(r"\bcontract(or)?\b|\bfreelance\b|\btemporary\b|\btemp\b", re.I), "Contract"),
    (re.compile(r"\bfull[\s-]?time\b", re.I), "Full-time"),
]

SALARY_PATTERN = re.compile(
    r"[$£€]\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s?(k)?"
    r"\s?(?:-|to|–|—)\s?"
    r"[$£€]?\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s?(k)?",
    re.I,
)
SINGLE_MONEY_PATTERN = re.compile(r"[$£€]\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s?(k)?", re.I)
HOUR_PERIOD_PATTERN = re.compile(r"\b(?:hour|hr|hourly)\b", re.I)
YEAR_PERIOD_PATTERN = re.compile(r"\b(?:year|yr|annum|annual(?:ly)?)\b", re.I)
MONTH_PERIOD_PATTERN = re.compile(r"\b(?:month|mo|monthly)\b", re.I)


def _period_from_text(text):
    if not text:
        return None
    if HOUR_PERIOD_PATTERN.search(text):
        return "Hour"
    if MONTH_PERIOD_PATTERN.search(text):
        return "Month"
    if YEAR_PERIOD_PATTERN.search(text):
        return "Year"
    return None


def _parse_money(text):
    match = SINGLE_MONEY_PATTERN.search(text or "")
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    if match.group(2):
        value *= 1000
    return value


def _friendly_source(domain):
    for key, label in KNOWN_SOURCES.items():
        if domain == key or domain.endswith("." + key):
            return label
    return domain


def _infer_work_mode(text):
    if not text:
        return None
    if REMOTE_PATTERN.search(text):
        return "Remote"
    if HYBRID_PATTERN.search(text):
        return "Hybrid"
    if ONSITE_PATTERN.search(text):
        return "Onsite"
    return None


def _infer_employment_type(text):
    if not text:
        return None
    for pattern, label in EMPLOYMENT_TYPE_PATTERNS:
        if pattern.search(text):
            return label
    return None


def _infer_salary(text):
    if not text:
        return {}
    match = SALARY_PATTERN.search(text)
    if not match:
        return {}
    try:
        low = float(match.group(1).replace(",", ""))
        high = float(match.group(3).replace(",", ""))
    except ValueError:
        return {}
    if match.group(2):
        low *= 1000
    if match.group(4):
        high *= 1000
    if low > high:
        low, high = high, low
    # Prefer an explicit unit near the match (e.g. "$23/hour"); fall back to
    # a magnitude guess only when no unit is stated anywhere in the text.
    window = text[max(0, match.start() - 20): match.end() + 20]
    period = _period_from_text(window) or _period_from_text(text)
    if not period:
        period = "Hour" if low < 500 else ("Year" if low > 1000 else "Month")
    return {"salary_min": low, "salary_max": high, "salary_period": period}


COMPANY_DOMAIN_HINTS = {
    "lifeattiktok.com": "TikTok",
    "metacareers.com": "Meta",
    "amazon.jobs": "Amazon",
    "careers.google.com": "Google",
}

LEGAL_ENTITY_PREFIX = re.compile(r"^\d+\s+")

ATS_COMPANY_PATTERNS = [
    (re.compile(r"greenhouse\.io/([^/]+)"), 1),
    (re.compile(r"boards\.greenhouse\.io/([^/]+)"), 1),
    (re.compile(r"jobs\.lever\.co/([^/]+)"), 1),
    (re.compile(r"([^.]+)\.workable\.com"), 1),
    (re.compile(r"smartrecruiters\.com/([^/]+)"), 1),
    (re.compile(r"([^.]+)\.bamboohr\.com"), 1),
    (re.compile(r"([^.]+)\.applytojob\.com"), 1),
    (re.compile(r"myworkdayjobs\.com/[^/]+/([^/]+)"), 1),
]


def _clean_text(value, limit=None):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    text = re.sub(r"<[^>]+>", " ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if limit:
        text = text[:limit]
    return text


def _find_jobposting(node):
    """Recursively search parsed JSON-LD for a schema.org JobPosting object."""
    if isinstance(node, dict):
        types = node.get("@type")
        if types:
            type_list = types if isinstance(types, list) else [types]
            if any(str(t).lower() == "jobposting" for t in type_list):
                return node
        graph = node.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                found = _find_jobposting(item)
                if found:
                    return found
        for value in node.values():
            found = _find_jobposting(value)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_jobposting(item)
            if found:
                return found
    return None


def _extract_jsonld(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        job = _find_jobposting(data)
        if job:
            return job
    return None


def _find_key(node, key):
    """Recursively search parsed JSON for the first dict value under `key`."""
    if isinstance(node, dict):
        if key in node and isinstance(node[key], dict):
            return node[key]
        for value in node.values():
            found = _find_key(value, key)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_key(item, key)
            if found:
                return found
    return None


def _extract_meta_careers_job(soup):
    """metacareers.com doesn't expose JobPosting JSON-LD or OG tags — the real
    data lives in a React hydration blob keyed 'xcp_requisition_job_description'."""
    for script in soup.find_all("script", type="application/json"):
        raw = script.string or script.get_text()
        if not raw or "xcp_requisition_job_description" not in raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        job = _find_key(data, "xcp_requisition_job_description")
        if job:
            return job
    return None


def _address_part_text(value):
    """Fields like addressCountry can be a plain string or a schema.org
    Country/AdministrativeArea object ({"@type": "Country", "name": "US"})."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return _address_part_text(value.get("name"))
    return None


def _location_from_jobposting(job):
    locations = job.get("jobLocation")
    if not locations:
        return None
    if isinstance(locations, dict):
        locations = [locations]
    parts = []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        addr = loc.get("address")
        if isinstance(addr, dict):
            bits = [
                _address_part_text(addr.get("addressLocality")),
                _address_part_text(addr.get("addressRegion")),
                _address_part_text(addr.get("addressCountry")),
            ]
            bits = [b for b in bits if b]
            # Some feeds duplicate the country inside the region string too
            # (e.g. region="MA,US", country="US") — flatten and dedupe tokens.
            tokens = []
            for bit in bits:
                for token in bit.split(","):
                    token = token.strip()
                    if token and token not in tokens:
                        tokens.append(token)
            if tokens:
                parts.append(", ".join(tokens))
        elif isinstance(addr, str):
            parts.append(addr)
    return "; ".join(dict.fromkeys(parts)) if parts else None


def _work_mode_from_jobposting(job):
    location_type = job.get("jobLocationType")
    if location_type and "telecommute" in str(location_type).lower():
        return "Remote"
    if job.get("applicantLocationRequirements"):
        return "Remote"
    return None


def _salary_from_jobposting(job):
    salary = job.get("baseSalary")
    if not isinstance(salary, dict):
        return {}
    currency = salary.get("currency")
    value = salary.get("value")
    result = {"salary_currency": currency}
    if isinstance(value, dict):
        result["salary_min"] = value.get("minValue") or value.get("value")
        result["salary_max"] = value.get("maxValue") or value.get("value")
        unit = value.get("unitText")
        result["salary_period"] = unit.title() if isinstance(unit, str) else None
    elif isinstance(value, (int, float)):
        result["salary_min"] = value
        result["salary_max"] = value
    return {k: v for k, v in result.items() if v is not None}


def _company_from_jobposting(job):
    org = job.get("hiringOrganization")
    name, logo = None, None
    if isinstance(org, dict):
        name = _clean_text(org.get("name"))
        logo_val = org.get("logo")
        if isinstance(logo_val, str):
            logo = logo_val
        elif isinstance(logo_val, dict):
            logo = logo_val.get("url")
    elif isinstance(org, str):
        name = org
    if name:
        # Workday and similar ATSes often prefix the name with an internal
        # legal-entity code, e.g. "2100 NVIDIA USA".
        name = LEGAL_ENTITY_PREFIX.sub("", name).strip() or name
    return name, logo


def _company_from_domain_hint(domain):
    for suffix, company in COMPANY_DOMAIN_HINTS.items():
        if domain == suffix or domain.endswith("." + suffix):
            return company
    return None


def _company_from_url(url):
    for pattern, group in ATS_COMPANY_PATTERNS:
        match = pattern.search(url)
        if match:
            slug = match.group(group)
            return slug.replace("-", " ").replace("_", " ").title()
    return None


def _meta(soup, *names):
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _fallback_title(soup, url):
    og_title = _meta(soup, "og:title", "twitter:title")
    if og_title:
        return _clean_text(og_title, 300)
    if soup.title and soup.title.string:
        parts = TITLE_SUFFIX_SPLIT.split(soup.title.string.strip())
        return _clean_text(parts[0], 300) if parts else _clean_text(soup.title.string, 300)
    return None


def scrape_job(url):
    """
    Returns a dict of extracted fields plus scrape_status ('ok' | 'partial' | 'failed')
    and scrape_message explaining what happened.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    result = {
        "url": url,
        "source": domain,
        "title": None,
        "company": None,
        "company_logo": None,
        "location": None,
        "work_mode": None,
        "employment_type": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_period": None,
        "description": None,
        "date_posted": None,
        "deadline": None,
        "scrape_status": "failed",
        "scrape_message": "",
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        result["title"] = _company_from_url(url) and f"Position at {_company_from_url(url)}"
        result["company"] = _company_from_url(url)
        result["scrape_status"] = "failed"
        result["scrape_message"] = f"Could not fetch the page ({exc.__class__.__name__}). Fill details manually."
        return result

    soup = BeautifulSoup(resp.text, "lxml")
    job = _extract_jsonld(soup)

    found_fields = []

    if job:
        try:
            title = _clean_text(job.get("title"), 300)
            if title:
                result["title"] = title
                found_fields.append("title")

            company, logo = _company_from_jobposting(job)
            if company:
                result["company"] = company
                found_fields.append("company")
            if logo:
                result["company_logo"] = logo

            location = _location_from_jobposting(job)
            if location:
                result["location"] = location
                found_fields.append("location")

            work_mode = _work_mode_from_jobposting(job)
            if work_mode:
                result["work_mode"] = work_mode

            employment_type = job.get("employmentType")
            if employment_type:
                if isinstance(employment_type, list):
                    employment_type = employment_type[0]
                employment_type = _address_part_text(employment_type) or str(employment_type)
                result["employment_type"] = employment_type.replace("_", " ").title()

            result.update(_salary_from_jobposting(job))

            description = _clean_text(job.get("description"), 8000)
            if description:
                result["description"] = description
                found_fields.append("description")

            date_posted = _address_part_text(job.get("datePosted")) or job.get("datePosted")
            if date_posted:
                result["date_posted"] = str(date_posted)[:10]

            valid_through = _address_part_text(job.get("validThrough")) or job.get("validThrough")
            if valid_through:
                result["deadline"] = str(valid_through)[:10]
        except (TypeError, AttributeError, KeyError):
            # Some sites emit non-standard/malformed JobPosting JSON-LD.
            # Fall through to the meta-tag/heuristic extraction below rather
            # than failing the whole request.
            pass

    if not result["title"] and "metacareers.com" in domain:
        try:
            meta_job = _extract_meta_careers_job(soup)
            if meta_job:
                title = _clean_text(meta_job.get("title"), 300)
                if title:
                    result["title"] = title
                    found_fields.append("title")

                locations = meta_job.get("locations")
                if isinstance(locations, list) and locations:
                    result["location"] = "; ".join(str(l) for l in locations)
                    found_fields.append("location")

                departments = meta_job.get("departments")
                if isinstance(departments, list) and departments:
                    result["tags"] = ", ".join(str(d) for d in departments)

                raw_description = meta_job.get("description")
                if isinstance(raw_description, str):
                    try:
                        inner = json.loads(raw_description)
                        raw_description = inner.get("__html", raw_description)
                    except (json.JSONDecodeError, TypeError):
                        pass
                    description = _clean_text(raw_description, 8000)
                    if description:
                        result["description"] = description
                        found_fields.append("description")

                comp = meta_job.get("public_compensation")
                if isinstance(comp, list) and comp:
                    min_text = comp[0].get("compensation_amount_minimum", "") or ""
                    max_text = comp[0].get("compensation_amount_maximum", "") or ""
                    low = _parse_money(min_text)
                    high = _parse_money(max_text)
                    if low is not None and high is not None:
                        result["salary_min"] = low
                        result["salary_max"] = high
                        result["salary_period"] = _period_from_text(min_text + " " + max_text)
                        found_fields.append("salary")
        except (TypeError, AttributeError, KeyError):
            pass

    if not result["title"]:
        fallback_title = _fallback_title(soup, url)
        if fallback_title:
            result["title"] = fallback_title
            found_fields.append("title (page title)")

    if not result["company"]:
        og_site = _meta(soup, "og:site_name")
        company = og_site or _company_from_domain_hint(domain) or _company_from_url(url)
        if company:
            result["company"] = company
            found_fields.append("company")

    if not result["company_logo"]:
        og_image = _meta(soup, "og:image", "twitter:image")
        if og_image:
            result["company_logo"] = og_image

    if not result["description"]:
        meta_desc = _meta(soup, "og:description", "description")
        if meta_desc:
            result["description"] = _clean_text(meta_desc, 2000)
            found_fields.append("description (summary only)")

    # Infer anything still missing from the combined text, so the app never
    # needs the user to type it in manually.
    combined_text = " ".join(filter(None, [result["title"], result["location"], result["description"]]))

    if not result["work_mode"]:
        inferred = _infer_work_mode(combined_text)
        if inferred:
            result["work_mode"] = inferred
            found_fields.append("work mode (inferred)")

    if not result["employment_type"]:
        inferred = _infer_employment_type(combined_text)
        if inferred:
            result["employment_type"] = inferred
            found_fields.append("employment type (inferred)")

    if not result["salary_min"]:
        inferred = _infer_salary(combined_text)
        if inferred:
            result.update(inferred)
            found_fields.append("salary (inferred)")

    result["source"] = _friendly_source(domain)

    if result["title"] and result["company"]:
        result["scrape_status"] = "ok"
        result["scrape_message"] = "Extracted: " + ", ".join(found_fields)
    elif result["title"] or result["company"]:
        result["scrape_status"] = "partial"
        result["scrape_message"] = (
            "Only partial data could be found on this page ("
            + ", ".join(found_fields)
            + "). This site may require login or JavaScript — fill in the rest manually."
        )
    else:
        result["scrape_status"] = "partial"
        result["scrape_message"] = (
            "Page fetched but no structured job data was found. "
            "This site may block automated access — fill in the details manually."
        )

    return result
