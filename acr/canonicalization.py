"""Stage 2 — Multimodal canonicalization.

Normalize representation without pretending that normalization
establishes truth. Every transformation produces the raw representation,
the canonical representation, transformation history, input and output
hashes, confidence, arbitration trace, receipt version, and explicit
loss accounting.

Canonicalization precedes interpretation, but canonicalization does not
manufacture truth.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TransformationStep:
    """A single transformation applied during canonicalization."""
    name: str
    description: str
    input_hash: str
    output_hash: str
    loss: str = "none"  # none | whitespace | encoding | ocr | boilerplate | privacy


@dataclass
class CanonicalForm:
    """The output of canonicalization."""
    raw: str
    canonical: str
    raw_hash: str
    canonical_hash: str
    transformations: list[TransformationStep] = field(default_factory=list)
    confidence: float = 1.0
    arbitration_trace: list[str] = field(default_factory=list)
    receipt_version: str = "1.0"
    loss_accounting: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "raw_hash": self.raw_hash,
            "canonical_hash": self.canonical_hash,
            "transformations": [
                {"name": t.name, "description": t.description, "loss": t.loss,
                 "input_hash": t.input_hash, "output_hash": t.output_hash}
                for t in self.transformations
            ],
            "confidence": self.confidence,
            "arbitration_trace": self.arbitration_trace,
            "receipt_version": self.receipt_version,
            "loss_accounting": self.loss_accounting,
            "canonical": self.canonical,
        }


class Canonicalizer:
    """Normalize input through a governed transformation pipeline."""

    # Homoglyph ranges to normalize (Latin lookalikes)
    HOMOGLYPH_MAP = {
        "\u0430": "a",  # Cyrillic a
        "\u0435": "e",  # Cyrillic e
        "\u043e": "o",  # Cyrillic o
        "\u0440": "p",  # Cyrillic p
        "\u0441": "c",  # Cyrillic c
        "\u0445": "x",  # Cyrillic x
        "\u0443": "y",  # Cyrillic y
        "\uff21": "A",  # Fullwidth A
        "\uff22": "B",  # Fullwidth B
    }

    # Bidi control characters to strip
    BIDI_CONTROLS = {
        "\u200e", "\u200f",  # LRM, RLM
        "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",  # LRE, RLE, PDF, LRO, RLO
        "\u2066", "\u2067", "\u2068", "\u2069",  # LRI, RLI, FSI, PDI
    }

    def __init__(self, enable_privacy: bool = False):
        self.enable_privacy = enable_privacy

    def _sha256(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _step(self, name: str, desc: str, before: str, after: str, loss: str = "none") -> TransformationStep:
        return TransformationStep(
            name=name,
            description=desc,
            input_hash=self._sha256(before),
            output_hash=self._sha256(after),
            loss=loss,
        )

    def canonicalize(self, raw: str) -> CanonicalForm:
        """Apply the full canonicalization pipeline."""
        raw_hash = self._sha256(raw)
        steps: list[TransformationStep] = []
        arbitration: list[str] = []
        losses: list[str] = []

        current = raw

        # 1. Unicode normalization (NFC)
        normalized = unicodedata.normalize("NFC", current)
        if normalized != current:
            steps.append(self._step("unicode_nfc", "Unicode NFC normalization", current, normalized, "encoding"))
            losses.append("unicode_normalization: combining characters composed")
            current = normalized

        # 2. Strip bidi control characters
        stripped = "".join(c for c in current if c not in self.BIDI_CONTROLS)
        if stripped != current:
            steps.append(self._step("strip_bidi", "Remove bidirectional control characters", current, stripped, "encoding"))
            losses.append("bidi_controls_removed: invisible formatting stripped")
            current = stripped

        # 3. Homoglyph normalization
        homoglyphed = current
        for src, dst in self.HOMOGLYPH_MAP.items():
            homoglyphed = homoglyphed.replace(src, dst)
        if homoglyphed != current:
            steps.append(self._step("homoglyph_normalize", "Normalize homoglyph lookalikes", current, homoglyphed, "encoding"))
            losses.append("homoglyphs_normalized: visual lookalikes mapped to ASCII")
            arbitration.append("homoglyph: Cyrillic/fullwidth lookalikes detected and normalized")
            current = homoglyphed

        # 4. Whitespace stabilization
        ws_stabilized = re.sub(r"[ \t]+", " ", current)
        ws_stabilized = re.sub(r"\r\n?", "\n", ws_stabilized)
        ws_stabilized = re.sub(r"\n{3,}", "\n\n", ws_stabilized)
        ws_stabilized = ws_stabilized.strip()
        if ws_stabilized != current:
            steps.append(self._step("whitespace_stabilize", "Collapse runs, normalize newlines, strip edges", current, ws_stabilized, "whitespace"))
            losses.append("whitespace_normalized: multiple spaces/tabs collapsed, CRLF→LF, trailing whitespace stripped")
            current = ws_stabilized

        # 5. Boilerplate isolation (detect and mark common boilerplate)
        boilerplate_patterns = [
            (r"(?i)^(disclaimer:|note:|warning:|caution:)\s.*$", "boilerplate_disclaimer"),
            (r"(?i)^-{5,}$", "boilerplate_separator"),
            (r"(?i)^={5,}$", "boilerplate_separator"),
        ]
        boilerplate_lines = []
        for line in current.split("\n"):
            for pattern, label in boilerplate_patterns:
                if re.match(pattern, line.strip()):
                    boilerplate_lines.append(line.strip())
                    break
        if boilerplate_lines:
            arbitration.append(f"boilerplate_detected: {len(boilerplate_lines)} boilerplate lines identified (not removed, marked)")

        # 6. Privacy transformations (if enabled)
        if self.enable_privacy:
            # Redact email addresses
            redacted = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", "[EMAIL_REDACTED]", current)
            if redacted != current:
                steps.append(self._step("privacy_email_redact", "Redact email addresses", current, redacted, "privacy"))
                losses.append("email_redacted: email addresses replaced with [EMAIL_REDACTED]")
                current = redacted

            # Redact phone numbers
            redacted = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE_REDACTED]", current)
            if redacted != current:
                steps.append(self._step("privacy_phone_redact", "Redact phone numbers", current, redacted, "privacy"))
                losses.append("phone_redacted: phone numbers replaced with [PHONE_REDACTED]")
                current = redacted

        canonical_hash = self._sha256(current)

        # Confidence: reduced by each lossy transformation
        confidence = 1.0
        lossy_count = sum(1 for s in steps if s.loss != "none")
        confidence = max(0.5, 1.0 - (lossy_count * 0.05))

        return CanonicalForm(
            raw=raw,
            canonical=current,
            raw_hash=raw_hash,
            canonical_hash=canonical_hash,
            transformations=steps,
            confidence=confidence,
            arbitration_trace=arbitration,
            receipt_version="1.0",
            loss_accounting=losses,
        )
