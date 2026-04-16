#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pytest fixtures com dados mock para todos os testes das 4 layers de skills AGIS.

Nenhum arquivo .xlsm é necessário: os fixtures simulam os dados reais
da planilha de planejamento para avaliar a lógica de cálculo.
"""

import sys
import importlib.util
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Importação dinâmica dos skill modules (nomes com hífen não permitem import)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SKILLS_PATH = ROOT / "skills"
sys.path.insert(0, str(ROOT))


def _load_skill(folder: str):
    skill_file = SKILLS_PATH / folder / "skill.py"
    spec = importlib.util.spec_from_file_location(
        f"skill_{folder.replace('-', '_')}", skill_file
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def skill_modules():
    return {
        "base": _load_skill("1-base-data"),
        "operational": _load_skill("2-operational-calc"),
        "planning": _load_skill("3-execution-planning"),
        "financial": _load_skill("4-financial-validation"),
    }


# ---------------------------------------------------------------------------
# Dados mock — MÃO DE OBRA
# ---------------------------------------------------------------------------
MOCK_MAO_DE_OBRA = pd.DataFrame(
    {
        "Função": [
            "Operador de Escavadeira",
            "Motorista de Basculante",
            "Encarregado",
            "Auxiliar de Produção",
        ],
        "Salário": [6_300.00, 4_800.00, 5_500.00, 2_800.00],
        "Unidade": ["mês", "mês", "mês", "mês"],
    }
)

# ---------------------------------------------------------------------------
# Dados mock — EQUIPAMENTOS
# ---------------------------------------------------------------------------
MOCK_EQUIPAMENTOS = pd.DataFrame(
    {
        "Equipamento": [
            "Escavadeira Hidráulica",
            "Caminhão Basculante",
            "Motoniveladora",
            "Compactador",
        ],
        "Valor Mensal": [15_000.00, 8_500.00, 12_000.00, 4_000.00],
        "Unidade": ["mês", "mês", "mês", "mês"],
    }
)

# ---------------------------------------------------------------------------
# Dados mock — BDI
# ---------------------------------------------------------------------------
MOCK_BDI = pd.DataFrame(
    {
        "Tipo Custo": ["Material", "Diesel", "Mão de Obra", "Equipamento"],
        "% BDI": [25.0, 20.0, 15.0, 12.0],
    }
)

# ---------------------------------------------------------------------------
# Dados mock — PRODUÇÕES
# ---------------------------------------------------------------------------
MOCK_PRODUCOES = pd.DataFrame(
    {
        "Atividade": [
            "ESCAVAÇÃO, CARGA, TRANSPORTE",
            "ATERRO COMPACTADO",
            "REVESTIMENTO ASFÁLTICO",
        ],
        "Unidade": ["M3", "M3", "M2"],
        "Produção Horária": [120.0, 80.0, 500.0],
    }
)

# ---------------------------------------------------------------------------
# Dados mock — PRATICABILIDADE (% produtivo por mês)
# ---------------------------------------------------------------------------
MOCK_PRATICABILIDADE = pd.DataFrame(
    {
        "Mês": [
            "JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
            "JUL", "AGO", "SET", "OUT", "NOV", "DEZ",
        ],
        "% Produtivo": [
            0.70, 0.72, 0.80, 0.88, 0.92, 0.95,
            0.96, 0.95, 0.88, 0.82, 0.75, 0.68,
        ],
    }
)

# ---------------------------------------------------------------------------
# Dados mock — CPU (composição unitária de serviços)
# ---------------------------------------------------------------------------
MOCK_CPU = pd.DataFrame(
    {
        "Código": ["CPU001", "CPU002", "CPU003"],
        "Serviço": [
            "ESCAVAÇÃO, CARGA, TRANSPORTE (M3)",
            "ATERRO COMPACTADO (M3)",
            "REVESTIMENTO ASFÁLTICO (M2)",
        ],
        "Unidade": ["M3", "M3", "M2"],
        "Custo Unit. s/ BDI": [18.50, 12.30, 45.00],
    }
)

# ---------------------------------------------------------------------------
# Dados mock — ENCARGOS
# ---------------------------------------------------------------------------
MOCK_ENCARGOS = pd.DataFrame(
    {
        "Item": ["Provisão", "Encargos Sociais", "Admin"],
        "Descrição": [
            "FGTS, férias, 13° salário",
            "INSS, SESI, SENAI...",
            "Administrativo",
        ],
        "% Encargo": [31.0, 30.0, 5.0],
    }
)

# ---------------------------------------------------------------------------
# Fixture — instâncias dos skills com dados mock injetados
# ---------------------------------------------------------------------------

@pytest.fixture
def base_skill(skill_modules, tmp_path):
    """BaseDataSkill instanciado com path fictício (mock não usa disco)."""
    cls = skill_modules["base"].BaseDataSkill
    # Cria arquivo vazio para contornar _validate_path() do skill
    mock_path = tmp_path / "mock.xlsm"
    mock_path.touch()
    instance = cls(spreadsheet_path=str(mock_path))
    # Injeta dados mock no cache interno (evita leitura de disco)
    instance._cache = {
        "MÃO DE OBRA": MOCK_MAO_DE_OBRA,
        "EQUIPAMENTOS": MOCK_EQUIPAMENTOS,
        "BDI": MOCK_BDI,
        "PRODUÇÕES": MOCK_PRODUCOES,
        "PRATICABILIDADE": MOCK_PRATICABILIDADE,
        "CPU": MOCK_CPU,
        "ENCARGOS": MOCK_ENCARGOS,
    }
    return instance


@pytest.fixture
def operational_skill(skill_modules, base_skill, tmp_path):
    cls = skill_modules["operational"].OperationalCalcSkill
    instance = cls(
        spreadsheet_path=str(tmp_path / "mock.xlsm"),
        base_skill=base_skill,
    )
    return instance


@pytest.fixture
def planning_skill(skill_modules, operational_skill, tmp_path):
    cls = skill_modules["planning"].ExecutionPlanningSkill
    instance = cls(
        spreadsheet_path=str(tmp_path / "mock.xlsm"),
        operational_skill=operational_skill,
    )
    return instance


@pytest.fixture
def financial_skill(skill_modules, planning_skill, tmp_path):
    cls = skill_modules["financial"].FinancialValidationSkill
    instance = cls(
        spreadsheet_path=str(tmp_path / "mock.xlsm"),
        execution_skill=planning_skill,
    )
    return instance


# ---------------------------------------------------------------------------
# Constantes reutilizáveis nos testes
# ---------------------------------------------------------------------------

ENCARGOS_RATE = 1.66  # 31% + 30% + 5% = 66%

CREW_ESCAVACAO = {
    "activity": "ESCAVAÇÃO, CARGA, TRANSPORTE",
    "labor": [
        {"function": "Operador de Escavadeira", "qty": 1, "salary": 6_300.00},
    ],
    "equipment": [
        {"name": "Escavadeira Hidráulica", "qty": 1, "monthly_value": 15_000.00},
    ],
    "duration_months": 3,
}

# Custos manuais esperados para CREW_ESCAVACAO (1 equipe, 3 meses)
# Salário c/ encargos: 6.300 × 1.66 = 10.458 /mês
# Equipamento:         15.000 /mês
# Total mensal:        25.458
# Total 3 meses:       76.374
EXPECTED_ESCAVACAO_MONTHLY = 25_458.00
EXPECTED_ESCAVACAO_TOTAL = 76_374.00
ENCARGOS_TOLERANCE = 0.01  # 1% de tolerância nos cálculos

# Cenário financeiro padrão para testes de viabilidade
FINANCEIRO_VIABLE = {
    "revenue": 1_000_000.00,
    "total_cost": 910_000.00,
    "margin_pct": 0.09,
}

FINANCEIRO_UNDERPRICED = {
    "revenue": 1_000_000.00,
    "total_cost": 940_000.00,
    "margin_pct": 0.06,
}

FINANCEIRO_OVERPRICED = {
    "revenue": 1_000_000.00,
    "total_cost": 860_000.00,
    "margin_pct": 0.14,
}
