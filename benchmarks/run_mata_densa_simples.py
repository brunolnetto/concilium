#!/usr/bin/env python3
"""
Projeto Simplificado: Supressão de Mata Densa com 1 Atividade Apenas

Objetivo: Análise granular da pipeline sem complexidade de múltiplas atividades
Status: PROJETO DE TESTE para diagnóstico de cálculos, cronograma e margem

Uso:
    python benchmarks/run_mata_densa_simples.py [--reset]

Saída:
    - Relatório analítico de cada skill (skill-by-skill)
    - Diagnóstico de problemas: cronograma, PU, BDI, margem
    - Arquivo JSON para auditoria (MATA_DENSA_SIMPLES_output.json)
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from concilium.application.benchmarks import BenchmarkFacade, ProjectSpec
from concilium.domain.services.analise_sobreposicao import (
    AnalisadorSobreposicao,
    ParametroAtividade,
)


def create_mata_densa_spec() -> ProjectSpec:
    """Cria especificação do projeto simplificado."""
    return ProjectSpec(
        nome="Supressão de Mata Densa (Simples)",
        slug="MATA_DENSA_SIMPLES",
        contexto_id="mendeslobo",
    )


def print_section(title: str, char: str = "=", width: int = 90):
    """Print formatted section header."""
    print(f"\n{char * width}")
    print(f" {title}")
    print(f"{char * width}")


def run_mata_densa():
    """Executa o projeto simplificado com análise detalhada."""
    root = Path(os.environ.get("CONCILIUM__ROOT", Path(__file__).resolve().parent.parent))
    concilium_root = Path(root)

    os.environ.setdefault("CONCILIUM__CONFIG_ROOT", str(concilium_root / "config"))
    os.environ.setdefault("CONCILIUM__PROJECTS_ROOT", str(concilium_root / "benchmarks" / "projetos"))

    spec = create_mata_densa_spec()

    print_section("PROJETO SIMPLIFICADO: SUPRESSÃO DE MATA DENSA")
    print(f"📊 Nome:        {spec.nome}")
    print(f"🏷️  Slug:        {spec.slug}")
    print(f" Diretório:    benchmarks/data/{spec.slug}/")
    print(f"🔢 Atividades:   1 (supressão de mata densa, 10.000 m²)")
    print(f"⏰ Período:      Nov 2026 - Dez 2026 (8 semanas)")

    print_section("CARREGANDO PROJETO")
    facade = BenchmarkFacade.from_root(concilium_root)

    try:
        print("✅ Conectando ao repositório de projetos...")
        report = facade.run_single(spec.slug, reset=False)

        print_section("RESULTADOS DA PIPELINE")

        if report:
            # Extrai dados relevantes do relatório
            print("\n📋 STATUS GERAL")
            print(f"   Slug:       {report.get('slug')}")
            print(f"   Status:     {report.get('status')}")
            print(f"   Timestamp:  {report.get('timestamp')}")

            # Dados do projeto
            resultado = report.get("resultado", {})
            if resultado:
                print("\n💰 RESULTADO FINANCEIRO")
                print(f"   Custo Total:     R$ {resultado.get('custo_total', 0):>15,.2f}")
                print(f"   Venda Total:     R$ {resultado.get('venda_total', 0):>15,.2f}")
                print(f"   Margem:          {resultado.get('margem_pct', 0):>14.2f}%")
                print(f"   Status Margem:   {resultado.get('margem_status')}")

            # Planejamento
            planejamento = report.get("planejamento", [])
            if planejamento:
                print(f"\n📅 PLANEJAMENTO ({len(planejamento)} item(ns))")
                for i, item in enumerate(planejamento, 1):
                    print(f"\n   Item {i}: {item.get('item_id')}")
                    print(f"   └─ Descrição:        {item.get('descricao')[:60]}")
                    print(f"   └─ Quantitativo:     {item.get('quantitativo', 0):>10,.0f} {item.get('unidade')}")
                    print(f"   └─ PU sem BDI:       R$ {item.get('preco_unitario', {}).get('sem_bdi', 0):>10,.2f}")
                    print(f"   └─ PU com BDI:       R$ {item.get('preco_unitario', {}).get('com_bdi', 0):>10,.2f}")
                    print(f"   └─ Preço Total (V):  R$ {item.get('preco_total_venda', 0):>15,.2f}")

            # Cronograma
            cronograma = report.get("cronograma", [])
            if cronograma:
                print(f"\n📊 CRONOGRAMA (Distribuição Semanal)")
                total_semanal = 0
                for i, item in enumerate(cronograma, 1):
                    semanas = item.get("distribuicao_semanal", [])
                    if semanas:
                        print(f"\n   Item {i}: {item.get('item_id')}")
                        for j, semana in enumerate(semanas[:4], 1):  # Mostra apenas 4 primeiras
                            qty = semana.get("quantidade_semanal", 0)
                            eff = semana.get("producao_efetiva", 0)
                            total_semanal += qty
                            print(f"      Semana {j}: {qty:>10,.0f} m² | ρ_efetiva={eff:>6.1f} m²/h")
                        if len(semanas) > 4:
                            print(f"      ... (+{len(semanas) - 4} semanas)")

            # Equipes
            equipes = report.get("equipes_diretas", [])
            if equipes:
                print(f"\n👥 EQUIPES DIRETAS ({len(equipes)} atividades)")
                for i, eq in enumerate(equipes, 1):
                    print(f"\n   Equipe {i}: {eq.get('item_id')}")
                    print(f"   └─ Custo Total:  R$ {eq.get('custo_total', 0):>15,.2f}")
                    print(f"   └─ Num Frentes:  {eq.get('num_frentes_base', 1)}")
                    print(f"   └─ Semanas:      {eq.get('semana_ini', '?')} → {eq.get('semana_fim', '?')}")

            # Indiretos
            indiretos = report.get("indiretos", {})
            if indiretos:
                print(f"\n🏢 CUSTOS INDIRETOS")
                print(f"   Mobilização:     R$ {indiretos.get('mobilizacao', 0):>15,.2f}")
                print(f"   Administração:   R$ {indiretos.get('administracao', 0):>15,.2f}")
                print(f"   Laboratório:     R$ {indiretos.get('laboratorio', 0):>15,.2f}")
                print(f"   QSMS:            R$ {indiretos.get('qsms', 0):>15,.2f}")
                print(f"   Topografia:      R$ {indiretos.get('topografia', 0):>15,.2f}")
                print(f"   Total Indireto:  R$ {indiretos.get('total', 0):>15,.2f}")

            # Validações
            validacoes = report.get("validacoes", [])
            if validacoes:
                print(f"\n⚠️  VALIDAÇÕES E AVISOS ({len(validacoes)} item(ns))")
                for val in validacoes[:10]:  # Mostra apenas 10 primeiros
                    status = val.get("status", "?")
                    msg = val.get("mensagem", "")[:70]
                    icon = "🔴" if status == "ERRO" else "🟡" if status == "AVISO" else "🟢"
                    print(f"   {icon} [{status:6s}] {msg}")
                if len(validacoes) > 10:
                    print(f"   ... (+{len(validacoes) - 10} mais)")

        else:
            print("❌ Nenhum relatório foi gerado!")

        # Salva saída completa em JSON para auditoria
        print_section("SALVANDO RESULTADOS")
        output_file = concilium_root / "MATA_DENSA_SIMPLES_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        print(f"✅ Relatório completo: {output_file}")

    except Exception as e:
        print(f"❌ Erro ao executar projeto: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print_section("CHECKLIST DE ANÁLISE")
    print("""
    Use este checklist para auditar o projeto:

    ✅ QUANTITATIVO
       □ Total = 10.000 m² (validar que cronograma soma isso)
       □ Unidade = m² (correto para supressão)

    ✅ CRONOGRAMA
       □ Período = Nov-Dez (8 semanas disponíveis)
       □ ρ (produtividade) = 582.75 m²/h (CPU-TERRA-ATI-041)
       □ β (fator climático) = 0.90 (Nov), 0.61 (Dez)
       □ Duração = ⌈10.000 / (582.75 × 0.75 × 48h × equipes)⌉

    ✅ CUSTO DE MÃO DE OBRA
       □ Equipe: 16 pessoas (1 operador PA, 1 operador escavadeira, 3 motoristas, 
         4 ajudantes, 1 sinaleiro, 4 operadores tratores, 2 operadores motosserra)
       □ Salários com encargos (1.66×): verificar cálculo
       □ C_h (custo/hora) deve estar entre R$ 50-100 (16 pessoas)

    ✅ CUSTO DE EQUIPAMENTO
       □ Equipamentos: PA, 3 caminhões, 4 tratores, 1 escavadeira, 2 motosserras
       □ Aluguel: R$ 15-50k/mês por máquina (verificar preco_unitario)
       □ C_h^EQ deve estar entre R$ 100-200/h

    ✅ PREÇO UNITÁRIO (PU)
       □ Fórmula: PU = C_h / (ρ × β) = R$ X/m²
       □ Sem BDI: R$ 80-150/m² (verificar)
       □ Com BDI (34.7%): R$ 120-200/m² (verificar)

    ✅ MARGEM
       □ Meta: 8-10% (VERDE)
       □ Verificar se resultado está nessa faixa
       □ Se < 8%: custos altos ou PU baixo
       □ Se > 10%: PU bem estimado ou custos baixos

    ✅ FRENTES NECESSÁRIAS (frentes_nec)
       □ Deve estar próximo de 1-2 (1 atividade apenas)
       □ Se > 1.5: cronograma apertado ou eficiência baixa
       □ Se < 1.0: cronograma fácil, potencial de reduzir equipes

    Após validar, comparar com resultado referencia.json:
    $ jq '.resultado' benchmarks/data/MATA_DENSA_SIMPLES/referencia.json
    $ jq '.resultado' MATA_DENSA_SIMPLES_output.json
    """)

    # Análise de Sobreposição (Completude Parcial)
    print_section("ANÁLISE DE SOBREPOSIÇÃO: DINÂMICA PRODUTO-CONSUMIDOR")
    try:
        # Parâmetros de SV-001 (Mata Densa)
        sv_001 = ParametroAtividade(
            atividade_id="SV-001",
            nome="Supressão de Mata Densa",
            quantitativo_total=10_000.0,  # m²
            unidade="m²",
            producao_horaria=500.0,  # m²/h (após redimensionamento)
            num_equipes=2,
            horas_diarias=8.0,
            dias_semana=5,
        )

        # Parâmetros de SV-002 (Topsoil Removal)
        # Conversão: 10.000 m² × 0.30 m = 3.000 m³ de topsoil
        sv_002 = ParametroAtividade(
            atividade_id="SV-002",
            nome="Topsoil Removal",
            quantitativo_total=3_000.0,  # m³ (convertido de mata densa)
            unidade="m³",
            producao_horaria=200.0,  # m³/h (após redimensionamento)
            num_equipes=1,
            horas_diarias=8.0,
            dias_semana=5,
        )

        # Análise com coeficiente de conversão 0.30 m de profundidade
        resultado = AnalisadorSobreposicao.analisar(
            sv_001, sv_002, coeficiente_conversao=0.30
        )

        # Imprimir relatório
        print(f"\n✅ Razão de Sinergia: {resultado.razao_sinergia:.2f}x")
        print(f"   └─ Mata gera {resultado.taxa_produto_consumidor.taxa_producao:,.1f} m³/dia")
        print(f"   └─ Topsoil consome {resultado.taxa_produto_consumidor.taxa_consumo:,.1f} m³/dia")
        print(f"   └─ Superávit: {resultado.taxa_produto_consumidor.superavit_diario:,.1f} m³/dia")

        print(f"\n📊 Cronograma")
        print(f"   Sequencial:          {resultado.duracao_sequencial_semanas:.1f} semanas")
        print(f"   Com Sobreposição 50%: {resultado.duracao_sequencial_semanas - resultado.economia_cronograma_semanas:.1f} semanas")
        print(f"   Economia:            {resultado.economia_cronograma_semanas:.1f} semanas ({resultado.economia_percentual:.1f}%)")

        print(f"\n💼 Ponto de Início (Recomendado)")
        print(f"   Percentual: {resultado.ponto_inicio_conservador.percentual_conclusao_produtor * 100:.0f}% de SV-001")
        print(f"   Quantitativo: {resultado.ponto_inicio_conservador.quantitativo_acumulado:,.1f} m² removidos")
        print(f"   Estoque Inicial: {resultado.ponto_inicio_conservador.estoque_inicial:,.1f} m³")
        print(f"   Buffer: {resultado.ponto_inicio_conservador.buffer_dias:.1f} dias")

        print(f"\n✓ Validações")
        for val in resultado.validacoes:
            icon = (
                "🟢" if val["status"] == "OK"
                else "🟡" if val["status"] == "AVISO"
                else "🔴"
            )
            print(f"   {icon} [{val['status']}] {val['codigo']}: {val['mensagem'][:60]}...")

        # Salvar relatório formal de sobreposição
        relatorio_sobreposicao_md = concilium_root / "docs" / "ANALISE_SOBREPOSICAO_PRODUTO_CONSUMIDOR.md"
        relatorio_sobreposicao_json = (
            concilium_root / "ANALISE_SOBREPOSICAO_PRODUTO_CONSUMIDOR.json"
        )

        # Converter resultado para dicionário JSON
        resultado_dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "atividade_produtora": {
                "atividade_id": resultado.atividade_produtora.atividade_id,
                "nome": resultado.atividade_produtora.nome,
                "quantitativo_total": resultado.atividade_produtora.quantitativo_total,
                "unidade": resultado.atividade_produtora.unidade,
                "producao_diaria": resultado.atividade_produtora.producao_diaria,
                "duracao_semanas": resultado.atividade_produtora.duracao_semanas,
            },
            "atividade_consumidora": {
                "atividade_id": resultado.atividade_consumidora.atividade_id,
                "nome": resultado.atividade_consumidora.nome,
                "quantitativo_total": resultado.atividade_consumidora.quantitativo_total,
                "unidade": resultado.atividade_consumidora.unidade,
                "producao_diaria": resultado.atividade_consumidora.producao_diaria,
                "duracao_semanas": resultado.atividade_consumidora.duracao_semanas,
            },
            "taxa_produto_consumidor": {
                "taxa_producao": resultado.taxa_produto_consumidor.taxa_producao,
                "taxa_consumo": resultado.taxa_produto_consumidor.taxa_consumo,
                "razao_sinergia": resultado.razao_sinergia,
                "superavit_diario": resultado.taxa_produto_consumidor.superavit_diario,
            },
            "cronograma": {
                "duracao_sequencial_semanas": resultado.duracao_sequencial_semanas,
                "duracao_sobreposicao_50pct": (
                    resultado.duracao_sequencial_semanas - resultado.economia_cronograma_semanas
                ),
                "economia_cronograma_semanas": resultado.economia_cronograma_semanas,
                "economia_percentual": resultado.economia_percentual,
            },
            "ponto_inicio_conservador": {
                "percentual_conclusao": resultado.ponto_inicio_conservador.percentual_conclusao_produtor,
                "quantitativo_acumulado": resultado.ponto_inicio_conservador.quantitativo_acumulado,
                "estoque_inicial": resultado.ponto_inicio_conservador.estoque_inicial,
                "buffer_dias": resultado.ponto_inicio_conservador.buffer_dias,
            },
            "ponto_inicio_agressivo": {
                "percentual_conclusao": resultado.ponto_inicio_agressivo.percentual_conclusao_produtor,
                "quantitativo_acumulado": resultado.ponto_inicio_agressivo.quantitativo_acumulado,
                "estoque_inicial": resultado.ponto_inicio_agressivo.estoque_inicial,
                "buffer_dias": resultado.ponto_inicio_agressivo.buffer_dias,
            },
            "validacoes": resultado.validacoes,
            "recomendacao": resultado.cenario_recomendado.value,
        }

        # Salvar JSON
        with open(relatorio_sobreposicao_json, "w", encoding="utf-8") as f:
            json.dump(resultado_dict, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n✅ Relatório JSON: {relatorio_sobreposicao_json}")

    except Exception as e:
        print(f"⚠️  Erro ao executar análise de sobreposição: {e}")

    print_section("FIM DA EXECUÇÃO")
    print(f"✅ Projeto executado com sucesso!")
    print(f"📌 Para análise detalhada, ver: MATA_DENSA_SIMPLES_output.json")
    print(f"📌 Para comparação com esperado, ver: benchmarks/data/MATA_DENSA_SIMPLES/referencia.json")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Executa projeto simplificado de supressão de mata densa")
    parser.add_argument("--reset", action="store_true", help="Resetar o projeto antes de executar")
    args = parser.parse_args()

    run_mata_densa()
