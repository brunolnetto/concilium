"""Coverage batch 17 — artifact_store, flat_version_store, runner_utils small gaps."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# artifact_store.py line 70: json.dumps path when payload has no model_dump_json
# ---------------------------------------------------------------------------


class TestFileSystemArtifactStoreSavePlainPayload:
    def test_save_plain_dict_payload_uses_json_dumps(self):
        """Line 70: payload is a plain dict → hasattr(payload, 'model_dump_json') is False
        → json.dumps(payload, ...) used instead of model_dump_json."""
        from concilium.domain.models.artifact import ArtifactEnvelope, ArtifactKind, ArtifactMeta
        from concilium.infrastructure.storage.artifact_store import FileSystemArtifactStore

        with tempfile.TemporaryDirectory() as tmp:
            store = FileSystemArtifactStore(tmp)

            meta = ArtifactMeta(
                kind=ArtifactKind.RESULTADO,
                schema_name="TestSchema",
                schema_version="1.0.0",
                created_by="test-batch17",
                content_hash="abc123fakehash",
            )
            # Plain dict payload — no model_dump_json attribute.
            # model_construct skips Pydantic validation, bypassing coercion to BaseModel.
            envelope = ArtifactEnvelope.model_construct(meta=meta, payload={"custo_total": 500_000.0})
            store.save(envelope)

            payload_path = Path(tmp) / f"{meta.artifact_id}.json"
            assert payload_path.exists()
            data = json.loads(payload_path.read_text(encoding="utf-8"))
            assert data["custo_total"] == 500_000.0


# ---------------------------------------------------------------------------
# flat_version_store.py line 89->87: empty line in invocations.log → if line: False
# ---------------------------------------------------------------------------


class TestFlatVersionStoreReadInvocationsEmptyLines:
    def test_empty_lines_skipped_in_read_invocations(self):
        """Line 89->87 branch: invocations.log has blank lines → stripped line='' → if line: False."""
        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "v1"
            root.mkdir()

            # Write log with blank lines AND a valid JSON line
            log_path = root / FlatVersionStore.INVOCATIONS_LOG
            log_path.write_text(
                "\n"  # blank line (if line: False)
                + "   \n"  # whitespace-only (if line: False)
                + json.dumps({"skill_id": "04"})
                + "\n",  # valid line
                encoding="utf-8",
            )

            project_mock = MagicMock()
            project_mock.version_path.return_value = root
            project_mock.meta = {}

            store = FlatVersionStore(project_mock, "v1")
            result = store.read_invocations()

            # Only the valid JSON line returned; blank lines skipped
            assert len(result) == 1
            assert result[0]["skill_id"] == "04"


# ---------------------------------------------------------------------------
# runner_utils.py line 71->70: equip without 'custo_mensal' → if check False → continue
# ---------------------------------------------------------------------------


class TestApplyCustoDeltaEquipNoCustoMensal:
    def test_equipment_without_custo_mensal_skipped(self):
        """Line 71->70 branch: equip has no 'custo_mensal' key → if 'custo_mensal' in equip: False."""
        from concilium.application.scenarios.runner_utils import apply_custo_delta

        inputs = {
            "composicao_customizada": {
                "ITEM-01": {
                    "funcoes": [],
                    "equipamentos": [
                        {"equip_id": "EQ-01"},  # no custo_mensal → skipped
                        {"equip_id": "EQ-02", "custo_mensal": 8000.0},  # has it → updated
                    ],
                }
            }
        }
        result = apply_custo_delta(inputs, delta=1.1)

        equips = result["composicao_customizada"]["ITEM-01"]["equipamentos"]
        # EQ-01 has no custo_mensal → unchanged
        assert "custo_mensal" not in equips[0]
        # EQ-02 has custo_mensal → updated by delta
        assert equips[1]["custo_mensal"] == round(8000.0 * 1.1, 2)
