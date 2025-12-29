from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime, timezone
import zlib
import base64
import json

class ChangeType(str, Enum):
    UI_TWEAK = "UI_TWEAK"
    CONTENT_UPDATE = "CONTENT_UPDATE"
    MAJOR_OVERHAUL = "MAJOR_OVERHAUL"
    INITIAL_BASELINE = "INITIAL_BASELINE"

@dataclass
class SimilarityMetrics:
    jaccard: float = 0.0
    levenshtein: float = 0.0
    semantic: float = 0.0
    final_score: float = 0.0

@dataclass
class WeightedFingerprint:
    hash: str
    version: str = "v2.0"
    algorithm: str = "weighted_semantic"
    content_weights: Dict[str, float] = field(default_factory=dict)
    structure_signature: str = ""

@dataclass
class ForensicSnapshot:
    timestamp: str  # ISO 8601 UTC
    change_type: ChangeType
    compressed_content: str  # Base64 encoded zlib compressed string
    
    @classmethod
    def create(cls, content: str, change_type: ChangeType = ChangeType.CONTENT_UPDATE) -> 'ForensicSnapshot':
        """Creates a snapshot by compressing the content."""
        # Compress
        compressed_data = zlib.compress(content.encode('utf-8'))
        # Encode to base64 for JSON storage
        b64_str = base64.b64encode(compressed_data).decode('ascii')
        
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            change_type=change_type,
            compressed_content=b64_str
        )
    
    def decompress(self) -> str:
        """Decompresses the stored content."""
        try:
            decoded_data = base64.b64decode(self.compressed_content)
            return zlib.decompress(decoded_data).decode('utf-8')
        except Exception as e:
            return f"[Error Decompressing Snapshot: {e}]"

@dataclass
class MonitorMetadata:
    created_at: str  # ISO 8601 UTC
    last_check: Optional[str] = None
    check_count: int = 0
    failure_count: int = 0
    circuit_breaker_state: str = "CLOSED"
    snooze_until: Optional[str] = None

@dataclass
class Monitor:
    url: str
    fingerprint: Optional[WeightedFingerprint] = None
    metadata: MonitorMetadata = field(default_factory=lambda: MonitorMetadata(created_at=datetime.now(timezone.utc).isoformat()))
    forensic_snapshots: List[ForensicSnapshot] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Monitor':
        # Defensive reconstruction
        fp_data = data.get("fingerprint")
        fp = WeightedFingerprint(**fp_data) if fp_data else None
        
        meta_data = data.get("metadata", {})
        # Ensure default metadata if missing or partial
        if not meta_data:
             meta_data = {"created_at": datetime.now(timezone.utc).isoformat()}
        meta = MonitorMetadata(**meta_data)
        
        snapshots = [ForensicSnapshot(**s) for s in data.get("forensic_snapshots", [])]
        
        return cls(
            url=data["url"],
            fingerprint=fp,
            metadata=meta,
            forensic_snapshots=snapshots
        )

@dataclass
class UserConfig:
    similarity_threshold: float = 0.85
    check_interval: int = 60
    include_diff: bool = True

@dataclass
class UserData:
    user_config: UserConfig = field(default_factory=UserConfig)
    monitors: List[Monitor] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
