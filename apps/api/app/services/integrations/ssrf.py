# Purpose: SSRF-safe validation of outbound integration endpoints.
# Responsibilities: enforce https (outside development), a per-organization domain allowlist, and
#   reject loopback / link-local / private / cloud-metadata / reserved destinations by resolving DNS
#   and checking every resolved address. Used before saving an integration and again immediately
#   before each delivery (revalidate). Redirects are disabled by the transport, not followed here.
# Dependencies: settings, stdlib socket/ipaddress.
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from app.config.settings import Settings

# Cloud metadata + reserved endpoints that must never be reachable.
_METADATA_HOSTS = frozenset(
    {"169.254.169.254", "fd00:ec2::254", "metadata.google.internal", "metadata"}
)


class SsrfError(Exception):
    """Raised when an endpoint fails SSRF validation. Message is safe (no secrets)."""


def _blocked_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_private: bool
) -> bool:
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    if isinstance(ip, ipaddress.IPv4Address) and str(ip).startswith("169.254."):
        return True  # link-local incl. cloud metadata
    if ip.is_private and not allow_private:
        return True
    return False


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as error:
        raise SsrfError("endpoint host could not be resolved") from error
    return sorted({str(info[4][0]) for info in infos})


def validate_endpoint(url: str, settings: Settings) -> str:
    """Validate an endpoint URL for SSRF safety; return the normalized host. Raises SsrfError.

    - scheme must be https (http allowed only in development)
    - no embedded credentials in the URL
    - host must be in the organization allowlist (when configured)
    - the host must not be a metadata endpoint
    - every DNS-resolved address must be public (unless private networks are explicitly allowed)
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("https", "http"):
        raise SsrfError("endpoint scheme must be https")
    if scheme == "http" and not settings.is_development:
        raise SsrfError("endpoint must use https outside development")
    if parts.username or parts.password:
        raise SsrfError("endpoint must not embed credentials")
    host = parts.hostname
    if not host:
        raise SsrfError("endpoint host is required")
    host = host.lower()
    if host in _METADATA_HOSTS:
        raise SsrfError("endpoint targets a metadata service")

    allowed = [d.lower() for d in settings.security_export_allowed_domains]
    if allowed and not any(host == d or host.endswith("." + d) for d in allowed):
        raise SsrfError("endpoint host is not in the allowlist")

    allow_private = settings.security_export_allow_private_networks and settings.is_development
    # If the host is a literal IP, check it directly; otherwise resolve and check all addresses.
    candidates: list[str]
    try:
        ipaddress.ip_address(host)
        candidates = [host]
    except ValueError:
        candidates = _resolve(host)
    for raw in candidates:
        if raw in _METADATA_HOSTS:
            raise SsrfError("endpoint resolves to a metadata service")
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if _blocked_ip(ip, allow_private):
            raise SsrfError("endpoint resolves to a blocked (private/loopback/reserved) address")
    return host
