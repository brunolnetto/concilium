"""Mixin de inputs: normalização de defaults e construção de kwargs por skill."""

from __future__ import annotations

from typing import Any


class InputsMixin:
    """Mixin com _apply_runtime_defaults e _build_skill_kwargs."""

    def _apply_runtime_defaults(
        self, skill_id: str, project: Any, contexto: Any, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        normalized = dict(inputs)
        if skill_id == "01-escopo-e-eap":
            snap_ids = self.create_snapshots(project)  # type: ignore[attr-defined]
            normalized.setdefault("snapshot_catalogo_id", snap_ids["catalogo"])
            normalized.setdefault("snapshot_perfil_id", snap_ids["perfil"])
            normalized.setdefault("contexto_id", contexto.id)

            p_meta = project.meta
            normalized.setdefault("nome", p_meta.get("nome"))
            normalized.setdefault("tipo_obra", p_meta.get("tipo_obra", "terraplenagem"))
            normalized.setdefault("localizacao", p_meta.get("localizacao", "Não Definido"))
            normalized.setdefault("data_inicio", p_meta.get("data_inicio"))
            normalized.setdefault("data_termino", p_meta.get("data_termino"))
            normalized.setdefault("data_base_orcamento", p_meta.get("data_base_orcamento"))

            if "coordenadas" not in normalized and "coordenadas" in p_meta:
                normalized["coordenadas"] = p_meta["coordenadas"]
            else:
                normalized.setdefault(
                    "coordenadas",
                    {"lat": p_meta.get("coordenadas_lat", 0.0), "lng": p_meta.get("coordenadas_lng", 0.0)},
                )

            if "regime_trabalho" not in normalized:
                normalized["regime_trabalho"] = {
                    "dias_semana": p_meta.get("dias_semana", 6),
                    "horas_dia": p_meta.get("horas_dia", 8),
                }

        if skill_id in ("03-equipes-diretas", "05-equipes-e-alocacao") and "percentual_encargos" not in normalized:
            jurisd = self.load_jurisdicao(contexto.jurisdicao_id)  # type: ignore[attr-defined]
            motor = jurisd.get("motor_encargos_sociais", {})
            # Preferência: campos específicos (ADR-097 F4) > percentual_total (retrocompat)
            horista = motor.get("percentual_horista") or motor.get("percentual_total")
            mensalista = motor.get("percentual_mensalista")
            if horista is not None:
                normalized["percentual_encargos"] = horista
            if mensalista is not None:
                normalized["percentual_encargos_mensalista"] = mensalista
            if motor.get("percentual_pj") is not None:
                normalized["percentual_encargos_pj"] = motor["percentual_pj"]

        if skill_id == "04-cronograma" and "calendario_operacional" not in normalized:
            proj_id = str(getattr(project, "id", "") or "")
            normalized["calendario_operacional"] = self.load_calendario_operacional(  # type: ignore[attr-defined]
                contexto.jurisdicao_id,
                proj_id or None,
            )

        if skill_id == "09-relatorio-e-artefatos":
            try:
                deliv_cfg = project.read_json("deliverables_config.json", {})
                outputs = deliv_cfg.get("outputs", {}) if isinstance(deliv_cfg, dict) else {}
                normalized.setdefault(
                    "gerar_excel",
                    bool(outputs.get("resultado_xlsx", outputs.get("cronograma_xlsx", True))),
                )
                normalized.setdefault("gerar_modelo_vivo", bool(outputs.get("modelo_vivo_xlsx", False)))
            except Exception:
                pass

        return normalized

    def _build_skill_kwargs(
        self,
        contract: Any,
        *,
        canonical_in: Any,
        inputs: dict[str, Any],
        catalogo: dict[str, Any],
        perfil: dict[str, Any],
        contexto: Any,
        project: Any,
        version: str,
    ) -> dict[str, Any]:
        providers: dict[str, Any] = {
            "canonical_in": canonical_in,
            "inputs": inputs,
            "catalogo": catalogo,
            "perfil": perfil,
            "contexto": contexto,
            "project": project,
            "version": version,
            "runtime": self,
        }
        kwargs: dict[str, Any] = {}
        for param in contract.signature:
            if param in providers:
                kwargs[param] = providers[param]
        return kwargs
