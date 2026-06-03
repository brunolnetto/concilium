"""Testes — ResolutionDecisionStore: persist, load, query."""

import json

from concilium.application.resolution.models import ResolutionDecision
from concilium.application.resolution.storage import ResolutionDecisionStore
from concilium.application.semantic.intent import Dimension, ExtractionConfidence, SemanticIntent


def _make_intent(scope_item_id: str = "item-01", activity_type: str = "cut_fill") -> SemanticIntent:
    return SemanticIntent(
        raw_text="Texto de teste",
        scope_item_id=scope_item_id,
        domain="earthwork",
        activity_type=activity_type,
        unit="m3",
        dimensions=[Dimension(name="dmt", value=2000.0, unit="m")],
        extraction_confidence=ExtractionConfidence(domain=0.9, activity_type=0.9, unit=0.99, dimensions=0.85),
    )


def _make_decision(scope_item_id: str = "item-01", cpu_id: str = "ESCO-CARGA-1CAT-DMT2000") -> ResolutionDecision:
    return ResolutionDecision(
        scope_item_id=scope_item_id,
        selected_cpu_id=cpu_id,
        candidate_set=[],
        eliminated_set=[],
        scoring_config_version="1.0.0",
        confidence="HIGH",
        explanations=[],
        decision_source="AUTO",
        intent_snapshot=_make_intent(scope_item_id),
    )


# ── Testes ────────────────────────────────────────────────────────────────────


class TestResolutionDecisionStore:
    def test_persist_cria_arquivo_jsonl(self, tmp_path):
        """persist() deve criar o arquivo se não existir."""
        store_file = tmp_path / "decisions.jsonl"
        store = ResolutionDecisionStore(store_file)

        decision = _make_decision()
        store.persist(decision)

        assert store_file.exists()
        lines = store_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["selected_cpu_id"] == "ESCO-CARGA-1CAT-DMT2000"

    def test_persist_append_only(self, tmp_path):
        """Múltiplos persist() devem adicionar linhas, nunca sobrescrever."""
        store = ResolutionDecisionStore(tmp_path / "d.jsonl")
        store.persist(_make_decision("item-01"))
        store.persist(_make_decision("item-02"))
        store.persist(_make_decision("item-03"))

        all_decisions = store.load_all()
        assert len(all_decisions) == 3

    def test_load_for_scope_item(self, tmp_path):
        """load_for_scope_item deve filtrar por scope_item_id."""
        store = ResolutionDecisionStore(tmp_path / "d.jsonl")
        store.persist(_make_decision("escopo-A"))
        store.persist(_make_decision("escopo-B"))
        store.persist(_make_decision("escopo-A"))  # segundo para escopo-A

        results = store.load_for_scope_item("escopo-A")
        assert len(results) == 2
        assert all(d.scope_item_id == "escopo-A" for d in results)

    def test_load_arquivo_inexistente_retorna_vazio(self, tmp_path):
        """Store vazio deve retornar lista vazia sem erros."""
        store = ResolutionDecisionStore(tmp_path / "nao_existe.jsonl")
        assert store.load_all() == []
        assert store.load_for_scope_item("qualquer") == []

    def test_count_correto(self, tmp_path):
        """count() deve refletir o número de entradas persistidas."""
        store = ResolutionDecisionStore(tmp_path / "c.jsonl")
        assert store.count() == 0
        store.persist(_make_decision("i1"))
        store.persist(_make_decision("i2"))
        assert store.count() == 2

    def test_load_recent_for_activity_type(self, tmp_path):
        """load_recent_for_activity_type deve retornar apenas decisões do tipo."""
        store = ResolutionDecisionStore(tmp_path / "r.jsonl")

        # 3 decisões cut_fill, 1 embankment_compaction
        for i in range(3):
            intent = _make_intent(scope_item_id=f"item-{i}", activity_type="cut_fill")
            decision = ResolutionDecision(
                scope_item_id=f"item-{i}",
                selected_cpu_id="ESCO-CARGA-1CAT-DMT2000",
                candidate_set=[],
                eliminated_set=[],
                scoring_config_version="1.0.0",
                confidence="HIGH",
                explanations=[],
                decision_source="AUTO",
                intent_snapshot=intent,
            )
            store.persist(decision)

        intent_emb = _make_intent("item-emb", activity_type="embankment_compaction")
        dec_emb = ResolutionDecision(
            scope_item_id="item-emb",
            selected_cpu_id="COMPACT-ATERRO-100PN",
            candidate_set=[],
            eliminated_set=[],
            scoring_config_version="1.0.0",
            confidence="MEDIUM",
            explanations=[],
            decision_source="AUTO",
            intent_snapshot=intent_emb,
        )
        store.persist(dec_emb)

        cut_fill_results = store.load_recent_for_activity_type("cut_fill")
        assert len(cut_fill_results) == 3
        assert all(d.intent_snapshot.activity_type == "cut_fill" for d in cut_fill_results)
