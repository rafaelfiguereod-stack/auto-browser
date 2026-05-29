from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .induce import SkillCandidate

logger = logging.getLogger(__name__)


class SkillStagingRegistry:
    def __init__(self, staging_root: str | Path):
        self.staging_root = Path(staging_root)

    def list_candidates(self) -> list[dict[str, Any]]:
        if not self.staging_root.exists():
            return []
        candidates: list[dict[str, Any]] = []
        for path in sorted(self.staging_root.glob("*/candidate.json")):
            try:
                candidates.append(SkillCandidate.model_validate_json(path.read_text(encoding="utf-8")).model_dump())
            except Exception as exc:
                logger.debug("skipping unreadable staged skill candidate %s: %s", path, exc)
                continue
        return candidates

    def get_candidate(self, skill_id: str) -> SkillCandidate:
        path = self._candidate_path(skill_id)
        if not path.exists():
            raise KeyError(skill_id)
        return SkillCandidate.model_validate_json(path.read_text(encoding="utf-8"))

    def candidate_dir(self, skill_id: str) -> Path:
        path = self._candidate_path(skill_id).parent
        if not path.exists():
            raise KeyError(skill_id)
        return path

    def _candidate_path(self, skill_id: str) -> Path:
        staging_root = self.staging_root.resolve()
        path = (self.staging_root / skill_id / "candidate.json").resolve()
        try:
            path.relative_to(staging_root)
        except ValueError as exc:
            raise KeyError(skill_id) from exc
        return path


def mesh_identity_signer(identity) -> Any:
    from app.mesh.models import PeerRecord
    from app.mesh.transport import make_envelope, verify_envelope

    def sign(payload: dict[str, Any]) -> dict[str, Any]:
        envelope = make_envelope(identity, payload, recipient_node_id="")
        peer = PeerRecord(node_id=identity.node_id, pubkey_b64=identity.pubkey_b64)
        verified_payload = verify_envelope(envelope, peer, expected_recipient_node_id="")
        if verified_payload != payload:
            raise RuntimeError("mesh skill candidate envelope verification round-trip failed")
        return envelope.model_dump(mode="json")

    return sign
