"""Runtime do Concilium: carrega config (jurisdição, perfil, catálogo, referência),
registra snapshots, dispatchei skills."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from concilium.models.canonical import CanonicalModel, ValidacaoItem
from concilium.skills import SKILLS
from concilium.skills.escopo import SkillResult
from concilium.storage.project import ProjectStore


class RuntimeError(Exception):
    """Erro de orquestração do pipeline."""


class Runtime:
    """Camada de orquestração: composição de stores + dispatch de skills."""

    def __init__(self, config_root: Path):
        """config_root é o diretório que contém jurisdicoes/, perfis/, catalogo/, referencias/."""
        self.config_root = config_root

    def load_jurisdicao(self, codigo: str) -> dict[str, Any]:
        path = self.config_root / "jurisdicoes" / f"{codigo}.json"
        if not path.exists():
            raise RuntimeError(f"Jurisdição '{codigo}' não encontrada em {path}")
        return json.loads(path.read_text())

    def load_perfil(self, perfil_id: str) -> dict[str, Any]:
        path = self.config_root / "perfis" / f"{perfil_id}.json"
        if not path.exists():
            raise RuntimeError(f"Perfil '{perfil_id}' não encontrado em {path}")
        return json.loads(path.read_text())

    def load_referencia(self, ref_id: str) -> dict[str, Any]:
        path = self.config_root / "referencias" / f"{ref_id}.json"
        if not path.exists():
            raise RuntimeError(f"Referência '{ref_id}' não encontrada em {path}")
        return json.loads(path.read_text())

    def load_catalogo(self) -> dict[str, Any]:
        """Catálogo agregado: insumos + cpus + templates."""
        cat_dir = self.config_root / "catalogo"
        catalogo: dict[str, Any] = {}
        for fname, key in [
            ("insumos.json", "insumos"),
            ("cpus.json", "cpus"),
            ("templates-obra.json", "templates"),
        ]:
            path = cat_dir / fname
            if path.exists():
                data = json.loads(path.read_text())
                # Suporta tanto {"insumos": [...]} quanto array direto
                if key in data:
                    catalogo[key] = data[key]
                elif isinstance(data, list):
                    catalogo[key] = data
                else:
                    catalogo[key] = data.get(key, [])
        return catalogo

    def create_snapshots(self, project: ProjectStore) -> dict[str, str]:
        """Lê todas as camadas atuais e cria snapshots por hash. Retorna {kind: hash}."""
        snaps = project.snapshots
        meta = project.meta
        result: dict[str, str] = {}

        # Jurisdição
        jurisd = self.load_jurisdicao(meta["jurisdicao_id"])
        result["jurisdicao"] = snaps.store("jurisdicao", jurisd)

        # Perfil
        perfil = self.load_perfil(meta["perfil_construtora_id"])
        result["perfil"] = snaps.store("perfil", perfil)

        # Catálogo
        catalogo = self.load_catalogo()
        result["catalogo"] = snaps.store("catalogo", catalogo)

        return result

    def run_skill(
        self,
        skill_id: str,
        project: ProjectStore,
        version: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> SkillResult:
        """Despacha skill, registra invocação no log."""
        if skill_id not in SKILLS:
            raise RuntimeError(f"Skill desconhecida: '{skill_id}'. Disponíveis: {list(SKILLS)}")

        skill_fn = SKILLS[skill_id]
        v = version or project.current_version()
        if v is None:
            raise RuntimeError("Nenhuma versão ativa. Execute 'concilium version new' primeiro.")

        canonical_in = project.load_canonical(v)
        meta = project.meta
        perfil = self.load_perfil(meta["perfil_construtora_id"]) if False else self.load_perfil(meta["perfil_construtora_id"])
        catalogo = self.load_catalogo()
        inputs = inputs or {}

        # Dispatch específico por skill (cada uma tem assinatura própria)
        ts_inicio = datetime.now(UTC)

        # Injetar percentual_encargos da jurisdição se skill consome
        if skill_id in ("03-equipes-diretas",) and "percentual_encargos" not in inputs:
            jurisd = self.load_jurisdicao(meta["jurisdicao_id"])
            motor = jurisd.get("motor_encargos_sociais", {})
            enc_horista = motor.get("percentual_total")
            enc_mensalista = motor.get("percentual_mensalista")
            if enc_horista is not None:
                inputs["percentual_encargos"] = enc_horista
            if enc_mensalista is not None:
                inputs["percentual_encargos_mensalista"] = enc_mensalista

        try:
            if skill_id == "00-escopo":
                snap_ids = self.create_snapshots(project)
                inputs.setdefault("snapshot_catalogo_id", snap_ids["catalogo"])
                inputs.setdefault("snapshot_perfil_id", snap_ids["perfil"])
                inputs.setdefault("perfil_id", meta["perfil_construtora_id"])
                inputs.setdefault("jurisdicao_id", meta["jurisdicao_id"])
                result = skill_fn(canonical_in, inputs, catalogo)
            elif skill_id == "01-praticabilidade":
                result = skill_fn(canonical_in, inputs, perfil)
            elif skill_id == "02-cronograma":
                result = skill_fn(canonical_in, inputs, catalogo)
            elif skill_id == "03-equipes-diretas":
                result = skill_fn(canonical_in, inputs, catalogo, perfil)
            elif skill_id == "04-planejamento-bdi":
                result = skill_fn(canonical_in, inputs, catalogo, perfil)
            elif skill_id == "05-indiretos":
                result = skill_fn(canonical_in, inputs, perfil)
            elif skill_id == "06-consolidar-resultado":
                result = skill_fn(canonical_in, inputs, perfil)
            else:
                result = skill_fn(canonical_in, inputs)
        except Exception as e:
            project.log_invocation(
                v,
                {
                    "ts": ts_inicio.isoformat(),
                    "skill": skill_id,
                    "status": "ERRO",
                    "erro": str(e),
                },
            )
            raise

        ts_fim = datetime.now(UTC)
        # Persiste canônico sempre (mesmo com erros — engenheiro precisa ver o resultado)
        # Exceção: skill 00 com ERRO não deve sobrescrever canônico existente
        should_save = not (skill_id == "00-escopo" and result.has_errors)
        if should_save:
            project.save_canonical(result.canonical, v)

        # Log de invocação
        project.log_invocation(
            v,
            {
                "ts": ts_inicio.isoformat(),
                "skill": skill_id,
                "status": "ERRO" if result.has_errors else "OK",
                "duration_ms": int((ts_fim - ts_inicio).total_seconds() * 1000),
                "validacoes": [{"codigo": v.codigo, "status": v.status} for v in result.validacoes],
            },
        )
        return result
