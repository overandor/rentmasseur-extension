"""Stage 1 — Evidence ingestion.

Preserve raw bytes before interpretation. Record source, timestamp,
tenant, media type, acquisition method, access boundary, and content hash.

The original evidence must remain available even when later stages
produce a cleaner representation.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class Evidence:
    """A single piece of preserved evidence."""
    id: str
    source: str
    timestamp: str
    tenant: str
    media_type: str
    acquisition_method: str
    access_boundary: str
    content_hash: str
    raw_bytes: bytes = b""
    metadata: dict = field(default_factory=dict)
    size: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "timestamp": self.timestamp,
            "tenant": self.tenant,
            "media_type": self.media_type,
            "acquisition_method": self.acquisition_method,
            "access_boundary": self.access_boundary,
            "content_hash": self.content_hash,
            "size": self.size,
            "metadata": self.metadata,
        }


class EvidenceStore:
    """SQLite-backed evidence store. Raw bytes preserved on disk."""

    def __init__(self, db_path: Path | str = "artifacts/acr/evidence.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.blob_dir = self.db_path.parent / "evidence_blobs"
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                tenant TEXT NOT NULL,
                media_type TEXT NOT NULL,
                acquisition_method TEXT NOT NULL,
                access_boundary TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                blob_path TEXT NOT NULL,
                size INTEGER NOT NULL,
                metadata TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_evidence_hash ON evidence(content_hash);
            CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source);
            CREATE INDEX IF NOT EXISTS idx_evidence_ts ON evidence(timestamp);
        """)
        conn.commit()
        conn.close()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def ingest(
        self,
        source: str,
        data: bytes | str,
        media_type: str = "text/plain",
        tenant: str = "default",
        acquisition_method: str = "direct",
        access_boundary: str = "local",
        metadata: Optional[dict] = None,
    ) -> Evidence:
        """Ingest raw evidence and return the Evidence record."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        content_hash = self._sha256(data)
        ts = self._now_iso()
        ev_id = f"ev_{content_hash[:16]}_{int(time.time())}"

        blob_path = self.blob_dir / f"{ev_id}.bin"
        blob_path.write_bytes(data)

        ev = Evidence(
            id=ev_id,
            source=source,
            timestamp=ts,
            tenant=tenant,
            media_type=media_type,
            acquisition_method=acquisition_method,
            access_boundary=access_boundary,
            content_hash=content_hash,
            raw_bytes=data,
            size=len(data),
            metadata=metadata or {},
        )

        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """INSERT OR REPLACE INTO evidence
               (id, source, timestamp, tenant, media_type, acquisition_method,
                access_boundary, content_hash, blob_path, size, metadata)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (ev_id, source, ts, tenant, media_type, acquisition_method,
             access_boundary, content_hash, str(blob_path), len(data),
             json.dumps(metadata or {})),
        )
        conn.commit()
        conn.close()
        return ev

    def get(self, ev_id: str) -> Optional[Evidence]:
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute("SELECT * FROM evidence WHERE id = ?", (ev_id,)).fetchone()
        conn.close()
        if not row:
            return None
        blob_path = Path(row[8])
        raw = blob_path.read_bytes() if blob_path.exists() else b""
        return Evidence(
            id=row[0], source=row[1], timestamp=row[2], tenant=row[3],
            media_type=row[4], acquisition_method=row[5], access_boundary=row[6],
            content_hash=row[7], raw_bytes=raw, size=row[9],
            metadata=json.loads(row[10]) if row[10] else {},
        )

    def by_hash(self, content_hash: str) -> list[Evidence]:
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("SELECT id FROM evidence WHERE content_hash = ?", (content_hash,)).fetchall()
        conn.close()
        return [self.get(r[0]) for r in rows if self.get(r[0])]

    def recent(self, limit: int = 20) -> list[dict]:
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute(
            "SELECT id, source, timestamp, media_type, content_hash, size FROM evidence ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [{"id": r[0], "source": r[1], "timestamp": r[2], "media_type": r[3],
                 "content_hash": r[4], "size": r[5]} for r in rows]
