from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .config import Settings


URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?)]}"


@dataclass(frozen=True)
class UrlValidationResult:
    url: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(TRAILING_PUNCTUATION)
        if url not in urls:
            urls.append(url)
    return urls


def domain_matches(hostname: str, configured_domain: str) -> bool:
    hostname = hostname.lower().rstrip(".")
    configured_domain = configured_domain.lower().lstrip(".").rstrip(".")
    return hostname == configured_domain or hostname.endswith(f".{configured_domain}")


def is_private_hostname(hostname: str) -> bool:
    host = hostname.lower().strip("[]").rstrip(".")

    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return True

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False

    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def validate_url(url: str, settings: Settings) -> UrlValidationResult:
    parsed = urlparse(url)

    if parsed.scheme.lower() not in {"http", "https"}:
        return UrlValidationResult(url, "Only http and https links are supported.")

    if not parsed.hostname:
        return UrlValidationResult(url, "That link does not contain a valid host name.")

    hostname = parsed.hostname.lower().rstrip(".")

    if not settings.allow_private_urls and is_private_hostname(hostname):
        return UrlValidationResult(url, "Private, local, and loopback URLs are blocked.")

    if settings.allowed_domains and not any(domain_matches(hostname, domain) for domain in settings.allowed_domains):
        allowed = ", ".join(settings.allowed_domains)
        return UrlValidationResult(url, f"This bot only accepts links from: {allowed}")

    if any(domain_matches(hostname, domain) for domain in settings.blocked_domains):
        return UrlValidationResult(url, "Links from this domain are blocked.")

    return UrlValidationResult(url)

