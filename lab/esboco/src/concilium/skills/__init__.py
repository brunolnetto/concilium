"""Skills do pipeline Concilium. Cada skill é função pura: canônico_in -> canônico_out."""

from concilium.skills.consolidar import run_consolidar_resultado
from concilium.skills.cronograma import run_cronograma
from concilium.skills.equipes_diretas import run_equipes_diretas
from concilium.skills.escopo import run_escopo
from concilium.skills.indiretos import run_indiretos
from concilium.skills.planejamento_bdi import run_planejamento_bdi
from concilium.skills.praticabilidade import run_praticabilidade

SKILLS = {
    "00-escopo": run_escopo,
    "01-praticabilidade": run_praticabilidade,
    "02-cronograma": run_cronograma,
    "03-equipes-diretas": run_equipes_diretas,
    "04-planejamento-bdi": run_planejamento_bdi,
    "05-indiretos": run_indiretos,
    "06-consolidar-resultado": run_consolidar_resultado,
}

__all__ = [
    "SKILLS",
    "run_consolidar_resultado",
    "run_cronograma",
    "run_equipes_diretas",
    "run_escopo",
    "run_indiretos",
    "run_planejamento_bdi",
    "run_praticabilidade",
]
