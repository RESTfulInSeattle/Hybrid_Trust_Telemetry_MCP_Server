"""Dynamic Data Loss Prevention (DLP) and payload sanitization engine.

Enforces context-aware redaction at the MCP server layer to protect:
- Payment Card Industry data (PCI-DSS PANs validated via Luhn algorithm)
- Healthcare & Personal Identifiable Information (HIPAA / PII, SSNs, Patient IDs)
- Secrets and credentials (OAuth tokens, JWTs, AWS keys, private keys, database URLs)
- Internal network topography (RFC 1918 private IPv4 addresses)
- Proprietary algorithmic symbols and trade secrets
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from threading import Lock

from telemetry_mcp_server.config import settings

# ---------------------------------------------------------------------------
# Regex Patterns for Sensitive Data Detection
# ---------------------------------------------------------------------------

# Candidate PAN (13 to 19 digits, optional dashes or spaces)
_PAN_CANDIDATE_REGEX = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{1,7}\b|\b\d{13,19}\b")
_CVV_REGEX = re.compile(r"(?i)\b(cvv|cvc|cid)\s*[:=]\s*\d{3,4}\b")

# HIPAA & PII Patterns
_SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PATIENT_ID_REGEX = re.compile(
    r"(?i)\b(patient[_-]?id|mrn|medical[_-]?record(?:[_-]?number)?)\s*[:=]\s*([a-zA-Z0-9_-]+)"
)
_EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b")
_PHONE_REGEX = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")

# Secrets & Credentials
_BEARER_REGEX = re.compile(r"(?i)Bearer\s+[A-Za-z0-9_\-\.]{20,}")
_JWT_REGEX = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_AWS_KEY_REGEX = re.compile(r"\b(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}\b")
_PRIVATE_KEY_REGEX = re.compile(
    r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"
)
_DATABASE_URL_REGEX = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s:]+:[^\s@]+@[^\s]+\b"
)
_GENERIC_SECRET_REGEX = re.compile(
    r"(?i)\b(api[_-]?key|secret|password|passwd|auth[_-]?token)\s*[:=]\s*['\"]?([^\s'\"<>,;]{8,})['\"]?"
)

# RFC 1918 Private IPv4 Addresses
_RFC1918_IP_REGEX = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3})\b"
)

# Proprietary Trade Secrets & Algorithmic Markers
_PROPRIETARY_SYMBOLS_REGEX = re.compile(
    r"(?i)\b(order_book_ring_buffer|lock_free_sequence_barrier|alpha_weight_vector|"
    r"proprietary_pricing_model|matching_engine_core_algo)\b"
)
_PROPRIETARY_WEIGHTS_REGEX = re.compile(r"(?i)\bformula_weights\s*:\s*\[[^\]]+\]")


def is_luhn_valid(number: str) -> bool:
    """Validate a card number string using the Luhn checksum algorithm.

    Args:
        number: Potential PAN string (digits with optional formatting).

    Returns:
        True if the number passes the Luhn checksum, False otherwise.
    """
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for idx, d in enumerate(reverse_digits):
        if idx % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


@dataclass
class DLPAuditMetrics:
    """Thread-safe cumulative metrics of DLP redactions performed."""

    pci_dss: int = 0
    pii_hipaa: int = 0
    credentials: int = 0
    network_topology: int = 0
    trade_secrets: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record(self, category: str, count: int = 1) -> None:
        """Record one or more redaction events for a category."""
        with self._lock:
            if category == "pci_dss":
                self.pci_dss += count
            elif category == "pii_hipaa":
                self.pii_hipaa += count
            elif category == "credentials":
                self.credentials += count
            elif category == "network_topology":
                self.network_topology += count
            elif category == "trade_secrets":
                self.trade_secrets += count

    def to_dict(self) -> dict[str, int]:
        """Return metrics as a dictionary."""
        with self._lock:
            return {
                "pci_dss": self.pci_dss,
                "pii_hipaa": self.pii_hipaa,
                "credentials": self.credentials,
                "network_topology": self.network_topology,
                "trade_secrets": self.trade_secrets,
                "total_redactions": (
                    self.pci_dss
                    + self.pii_hipaa
                    + self.credentials
                    + self.network_topology
                    + self.trade_secrets
                ),
            }

    def reset(self) -> None:
        """Reset all metrics to zero (useful in testing)."""
        with self._lock:
            self.pci_dss = 0
            self.pii_hipaa = 0
            self.credentials = 0
            self.network_topology = 0
            self.trade_secrets = 0


# Global metrics accumulator
audit_metrics = DLPAuditMetrics()


@dataclass(frozen=True)
class DLPResult:
    """Result of DLP redaction processing."""

    text: str
    redacted_count: int
    categories: dict[str, int]


class DLPScrubber:
    """High-throughput regex and pattern scrubber for telemetry payloads."""

    def __init__(self, metrics: DLPAuditMetrics | None = None) -> None:
        self.metrics = metrics or audit_metrics

    def _scrub_pans(self, text: str) -> tuple[str, int]:
        """Scrub Luhn-valid PANs, preserving only last 4 digits."""
        redactions = 0

        def replace_pan(match: re.Match[str]) -> str:
            nonlocal redactions
            raw_val = match.group(0)
            digits_only = re.sub(r"\D", "", raw_val)
            if is_luhn_valid(digits_only):
                redactions += 1
                last4 = digits_only[-4:]
                return f"[CARD_REDACTED_*{last4}]"
            return raw_val

        scrubbed = _PAN_CANDIDATE_REGEX.sub(replace_pan, text)

        # Also scrub CVVs
        def replace_cvv(match: re.Match[str]) -> str:
            nonlocal redactions
            redactions += 1
            key = match.group(1)
            return f"{key}: [CVV_REDACTED]"

        scrubbed = _CVV_REGEX.sub(replace_cvv, scrubbed)
        return scrubbed, redactions

    def _scrub_hipaa_pii(self, text: str) -> tuple[str, int]:
        """Scrub SSNs, patient identifiers, emails, and phone numbers."""
        redactions = 0

        # SSNs
        ssn_matches = len(_SSN_REGEX.findall(text))
        if ssn_matches > 0:
            redactions += ssn_matches
            text = _SSN_REGEX.sub("[SSN_REDACTED]", text)

        # Patient IDs
        def replace_patient(match: re.Match[str]) -> str:
            nonlocal redactions
            redactions += 1
            return f"{match.group(1)}: [PATIENT_ID_REDACTED]"

        text = _PATIENT_ID_REGEX.sub(replace_patient, text)

        # Emails
        email_matches = len(_EMAIL_REGEX.findall(text))
        if email_matches > 0:
            redactions += email_matches
            text = _EMAIL_REGEX.sub("[EMAIL_REDACTED]", text)

        # Phone numbers
        phone_matches = len(_PHONE_REGEX.findall(text))
        if phone_matches > 0:
            redactions += phone_matches
            text = _PHONE_REGEX.sub("[PHONE_REDACTED]", text)

        return text, redactions

    def _scrub_credentials(self, text: str) -> tuple[str, int]:
        """Scrub Bearer tokens, JWTs, AWS access keys, private keys, and DB URLs."""
        redactions = 0

        # Private Keys
        pk_matches = len(_PRIVATE_KEY_REGEX.findall(text))
        if pk_matches > 0:
            redactions += pk_matches
            text = _PRIVATE_KEY_REGEX.sub("[PRIVATE_KEY_REDACTED]", text)

        # Bearer tokens
        bearer_matches = len(_BEARER_REGEX.findall(text))
        if bearer_matches > 0:
            redactions += bearer_matches
            text = _BEARER_REGEX.sub("Bearer [TOKEN_SCRUBBED]", text)

        # Database connection strings
        db_matches = len(_DATABASE_URL_REGEX.findall(text))
        if db_matches > 0:
            redactions += db_matches
            text = _DATABASE_URL_REGEX.sub("[DATABASE_URL_REDACTED]", text)

        # JWT tokens
        jwt_matches = len(_JWT_REGEX.findall(text))
        if jwt_matches > 0:
            redactions += jwt_matches
            text = _JWT_REGEX.sub("[JWT_REDACTED]", text)

        # AWS keys
        aws_matches = len(_AWS_KEY_REGEX.findall(text))
        if aws_matches > 0:
            redactions += aws_matches
            text = _AWS_KEY_REGEX.sub("[AWS_KEY_REDACTED]", text)

        # Generic secrets (api_key=..., password=...)
        def replace_generic(match: re.Match[str]) -> str:
            nonlocal redactions
            redactions += 1
            return f"{match.group(1)}: [SECRET_REDACTED]"

        text = _GENERIC_SECRET_REGEX.sub(replace_generic, text)

        return text, redactions

    def _scrub_network_topology(self, text: str) -> tuple[str, int]:
        """Scrub RFC 1918 private IPv4 addresses."""
        matches = len(_RFC1918_IP_REGEX.findall(text))
        if matches > 0:
            text = _RFC1918_IP_REGEX.sub("[INTERNAL_IP_REDACTED]", text)
        return text, matches

    def _scrub_trade_secrets(self, text: str) -> tuple[str, int]:
        """Scrub proprietary algorithmic symbols and mathematical weight vectors."""
        redactions = 0

        # Formula weights
        weight_matches = len(_PROPRIETARY_WEIGHTS_REGEX.findall(text))
        if weight_matches > 0:
            redactions += weight_matches
            text = _PROPRIETARY_WEIGHTS_REGEX.sub(
                "formula_weights: [PROPRIETARY_WEIGHTS_REDACTED]", text
            )

        # Proprietary algorithm markers
        symbol_matches = len(_PROPRIETARY_SYMBOLS_REGEX.findall(text))
        if symbol_matches > 0:
            redactions += symbol_matches
            text = _PROPRIETARY_SYMBOLS_REGEX.sub("[PROPRIETARY_ALGO_REDACTED]", text)

        return text, redactions

    def scrub(self, payload: str, mode: str | None = None) -> DLPResult:
        """Process a text payload and apply dynamic redactions according to security mode.

        Args:
            payload: Input text (log lines, JSON response, or exception trace).
            mode: Security mode override ('STRICT_LOCAL', 'REDACTED_CLOUD', 'AUDIT_ONLY').
                Defaults to configured settings.security_mode.

        Returns:
            DLPResult containing the sanitized text and redaction metadata.
        """
        active_mode = (mode or settings.security_mode).upper()
        if not settings.dlp_enabled or not payload:
            return DLPResult(text=payload, redacted_count=0, categories={})

        categories: dict[str, int] = {
            "pci_dss": 0,
            "pii_hipaa": 0,
            "credentials": 0,
            "network_topology": 0,
            "trade_secrets": 0,
        }

        # Step 1: Execute all scrubber passes
        t, c_pans = self._scrub_pans(payload)
        categories["pci_dss"] = c_pans

        t, c_hipaa = self._scrub_hipaa_pii(t)
        categories["pii_hipaa"] = c_hipaa

        t, c_cred = self._scrub_credentials(t)
        categories["credentials"] = c_cred

        t, c_net = self._scrub_network_topology(t)
        categories["network_topology"] = c_net

        t, c_secrets = self._scrub_trade_secrets(t)
        categories["trade_secrets"] = c_secrets

        total_redacted = sum(categories.values())

        # Step 2: Record metrics regardless of mode
        if total_redacted > 0:
            for cat, count in categories.items():
                if count > 0:
                    self.metrics.record(cat, count)

        # Step 3: Handle mode-specific return payload
        if active_mode == "STRICT_LOCAL":
            # Permitted over trusted local boundary: return original raw text
            return DLPResult(
                text=payload,
                redacted_count=total_redacted,
                categories=categories,
            )
        elif active_mode == "AUDIT_ONLY":
            # Shadow evaluation: return original raw text, metrics recorded
            return DLPResult(
                text=payload,
                redacted_count=total_redacted,
                categories=categories,
            )
        else:
            # REDACTED_CLOUD (and any untrusted mode): enforce zero-leak sanitized text
            return DLPResult(
                text=t,
                redacted_count=total_redacted,
                categories=categories,
            )


# Default shared scrubber instance
dlp_scrubber = DLPScrubber()


def sanitize_payload(
    payload: str,
    mode: str | None = None,
) -> str:
    """Convenience helper to sanitize a text payload through the default scrubber.

    Args:
        payload: Input text.
        mode: Optional security mode override.

    Returns:
        Sanitized text payload.
    """
    result = dlp_scrubber.scrub(payload=payload, mode=mode)
    return result.text
