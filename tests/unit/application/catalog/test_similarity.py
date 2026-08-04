"""Testes para concilium.application.catalog.similarity (ADR-179)."""

from __future__ import annotations

import pytest

from concilium.application.catalog.similarity import (
    _categoria_sim,
    _desc_sim,
    _price_sim,
    _price_sim_direto,
    _price_sim_encargos,
    _tokens_de_conteudo,
    _weighted_dice,
    build_idf,
    find_candidate_duplicates,
    insumo_similarity,
)

# ── _tokens_de_conteudo ───────────────────────────────────────────────────────


class TestTokensDeConteudo:
    def test_remove_acentos_e_minusculiza(self):
        assert _tokens_de_conteudo("Operário") == frozenset({"operario"})

    def test_remove_stopwords(self):
        assert _tokens_de_conteudo("Operador de Trator de Esteiras") == frozenset({"operador", "trator", "esteiras"})

    def test_remove_parenteses_e_virgulas(self):
        tokens = _tokens_de_conteudo("Operador de Escavadeira (Sábado, 12×36)")
        assert tokens == frozenset({"operador", "escavadeira", "sabado"})

    def test_remove_turno_e_digitos_de_escala(self):
        """Regressão real: "Diurno"/"Noturno" + dígitos de escala ("12×36") são
        metadado de turno, não da função/equipamento — inflavam desc_sim entre
        equipamentos DIFERENTES (Motoniveladora x Escavadeira) que só compartilham
        o boilerplate de turno."""
        diurno = _tokens_de_conteudo("Operador de Motoniveladora (Diurno, 12×36)")
        noturno = _tokens_de_conteudo("Operador de Escavadeira (Noturno, 12×36)")
        assert diurno == frozenset({"operador", "motoniveladora"})
        assert noturno == frozenset({"operador", "escavadeira"})

    def test_string_vazia(self):
        assert _tokens_de_conteudo("") == frozenset()

    def test_none(self):
        assert _tokens_de_conteudo(None) == frozenset()


# ── _weighted_dice / build_idf ────────────────────────────────────────────────


class TestWeightedDice:
    def test_conjuntos_identicos_sem_idf(self):
        assert _weighted_dice(frozenset({"a", "b"}), frozenset({"a", "b"}), None) == 1.0

    def test_conjuntos_disjuntos_sem_idf(self):
        assert _weighted_dice(frozenset({"a"}), frozenset({"b"}), None) == 0.0

    def test_ambos_vazios(self):
        assert _weighted_dice(frozenset(), frozenset(), None) == 1.0

    def test_um_vazio(self):
        assert _weighted_dice(frozenset({"a"}), frozenset(), None) == 0.0

    def test_overlap_parcial_sem_idf_equivale_a_dice_nao_ponderado(self):
        # {a,b,c} vs {a,b,d}, sem idf (peso 1.0 pra tudo): 2*2/(3+3) = 0.667
        assert _weighted_dice(frozenset({"a", "b", "c"}), frozenset({"a", "b", "d"}), None) == pytest.approx(
            2 / 3, abs=1e-6
        )

    def test_token_ausente_do_idf_cai_para_peso_1(self):
        idf = {"a": 5.0}  # "b" não está no corpus usado para construir o idf
        # a∩b = {} (disjuntos), token ausente não afeta esse caso, mas cobre o fallback
        assert _weighted_dice(frozenset({"a"}), frozenset({"b"}), idf) == 0.0

    def test_idf_favorece_token_raro_sobre_token_comum(self):
        # "operador" é comum (peso baixo), "valetadeira"/"escavadeira" são raros (peso alto)
        idf = {"operador": 1.0, "valetadeira": 5.0, "escavadeira": 5.0}
        # Compartilham só "operador" (comum) — score baixo
        baixo = _weighted_dice(frozenset({"operador", "valetadeira"}), frozenset({"operador", "escavadeira"}), idf)
        # Compartilham "operador" E o termo raro — score alto
        alto = _weighted_dice(frozenset({"operador", "valetadeira"}), frozenset({"operador", "valetadeira"}), idf)
        assert baixo < alto
        assert alto == 1.0


class TestBuildIdf:
    def test_lista_vazia(self):
        assert build_idf([]) == {}

    def test_token_em_toda_descricao_tem_peso_minimo(self):
        idf = build_idf(["Operador de Escavadeira", "Operador de Motoniveladora"])
        assert idf["operador"] == pytest.approx(1.0, abs=1e-9)  # df=N → ln(1)+1=1.0

    def test_token_raro_pesa_mais_que_token_comum(self):
        idf = build_idf(["Operador de Escavadeira", "Operador de Motoniveladora", "Pedreiro"])
        assert idf["escavadeira"] > idf["operador"]

    def test_e_deterministico(self):
        descs = ["Operador de Escavadeira", "Pedreiro", "Ajudante"]
        assert build_idf(descs) == build_idf(descs)


# ── _desc_sim ─────────────────────────────────────────────────────────────────


class TestDescSim:
    def test_descricoes_identicas(self):
        assert _desc_sim({"descricao": "Sala Técnica"}, {"descricao": "Sala Técnica"}) == 1.0

    def test_descricoes_totalmente_diferentes(self):
        assert _desc_sim({"descricao": "Pedreiro"}, {"descricao": "Carpinteiro"}) == 0.0

    def test_papeis_similares_mas_distintos_tem_overlap_parcial(self):
        # "Operador de Trator de Esteiras" vs "Operador de Trator de Pneus"
        sim = _desc_sim(
            {"descricao": "Operador de Trator de Esteiras"},
            {"descricao": "Operador de Trator de Pneus"},
        )
        assert 0.5 < sim < 0.8  # parecido (mesma família), mas não é a mesma função


# ── _price_sim_direto / _price_sim_encargos ──────────────────────────────────


class TestPriceSimDireto:
    def test_precos_iguais(self):
        assert _price_sim_direto(100.0, 100.0) == 1.0

    def test_precos_dentro_da_tolerancia(self):
        # 5% de diferença, tolerância é 15%
        assert _price_sim_direto(100.0, 105.0) > 0.5

    def test_precos_muito_diferentes(self):
        assert _price_sim_direto(100.0, 500.0) == 0.0

    def test_preco_zero_nao_comparavel(self):
        assert _price_sim_direto(0.0, 100.0) == 0.0


class TestPriceSimEncargos:
    def test_razao_fora_da_faixa_de_alpha(self):
        # razão 5x — muito além de ALPHA_MAX_ENCARGOS (2.5)
        assert _price_sim_encargos(100.0, 500.0) == 0.0

    def test_razao_proxima_do_alpha_tipico(self):
        # 1830.51 * 1.777 ≈ 3254 — razão próxima do α típico CLT
        assert _price_sim_encargos(1830.51, 3253.62) > 0.9

    def test_razao_2x_dentro_da_faixa_mas_nao_no_centro(self):
        # Sala Técnica real: 12000 vs 24720 (razão 2.06, α típico é 1.777)
        sim = _price_sim_encargos(12_000.0, 24_720.0)
        assert 0.7 < sim < 0.95


# ── _categoria_sim ────────────────────────────────────────────────────────────


class TestCategoriaSim:
    def test_categorias_iguais(self):
        assert _categoria_sim({"categoria": "TERRAPLENAGEM"}, {"categoria": "TERRAPLENAGEM"}) == 1.0

    def test_categorias_diferentes(self):
        assert _categoria_sim({"categoria": "TERRAPLENAGEM"}, {"categoria": "MINERACAO"}) == 0.0

    def test_categoria_ausente_e_neutro(self):
        assert _categoria_sim({}, {"categoria": "TERRAPLENAGEM"}) == 0.5


# ── insumo_similarity — casos reais do catálogo mendeslobo ───────────────────


class TestInsumoSimilarity:
    def test_equipamentos_diferentes_com_mesmo_turno_boilerplate_nao_e_duplicata(self):
        """Regressão de bug real achado ao validar antes de aplicar no catálogo:
        SV-P0043-D (Motoniveladora) e SV-P0040-D (Escavadeira) — equipamentos
        DIFERENTES — pontuavam duplicata_provavel (score=0,825) só por
        compartilharem "(Diurno, 12×36)"; teria fundido dois cargos distintos."""
        motonivel = {
            "codigo": "SV-P0043-D",
            "tipo": "MAO_OBRA",
            "descricao": "Operador de Motoniveladora (Diurno, 12×36)",
            "preco_unitario": 27.0759,
        }
        escav = {
            "codigo": "SV-P0040-D",
            "tipo": "MAO_OBRA",
            "descricao": "Operador de Escavadeira (Diurno, 12×36)",
            "preco_unitario": 27.0759,
        }
        result = insumo_similarity(motonivel, escav)
        assert result.classificacao != "duplicata_provavel"

    def test_unidade_h_nao_usa_hipotese_de_encargos(self):
        """Regressão de bug real: unidade="h" já é taxa all-in por convenção (AGIS/SV)
        — não existe "hora sem encargos" nesse catálogo pra hipótese de α resgatar.
        AGIS-FN-MOTOR-BASC (R$38,10/h, terceirizado) x SV-P0032-D (R$18,48/h,
        tabela interna por turno) caem na faixa de α [1,0-2,5] por coincidência de
        razão (2,06x) — não é a mesma pessoa em duas bases, são fontes de preço
        distintas. Com unidade="h" em ambos, a hipótese de encargos não deve
        entrar (só a tolerância direta, que aqui reprova por estarem longe)."""
        agis = {
            "codigo": "AGIS-FN-MOTOR-BASC",
            "tipo": "MAO_OBRA",
            "descricao": "Motorista de Caminhão Basculante",
            "preco_unitario": 38.1,
            "unidade": "h",
        }
        sv = {
            "codigo": "SV-P0032-D",
            "tipo": "MAO_OBRA",
            "descricao": "Motorista de Caminhão Basculante (Diurno, 12×36)",
            "preco_unitario": 18.4792,
            "unidade": "h",
        }
        result = insumo_similarity(agis, sv)
        assert result.classificacao != "duplicata_provavel"

    def test_sala_tecnica_p0058_vs_mo_sala_tec(self):
        """Caso real que escapou do dedup exato: mesma função, preços diferentes
        por tratamento de encargos (AGIS embutido vs. CLT-normalizado ADR-009)."""
        p0058 = {
            "codigo": "P0058",
            "tipo": "MAO_OBRA",
            "descricao": "Sala Técnica",
            "preco_unitario": 24_720.0,
            "unidade": "mês",
        }
        mo_sala_tec = {
            "codigo": "MO-SALA-TEC",
            "tipo": "MAO_OBRA",
            "descricao": "Sala Técnica",
            "preco_unitario": 12_000.0,
            "unidade": "mes",
            "categoria": "DIVERSOS",
        }
        result = insumo_similarity(p0058, mo_sala_tec)
        assert result.classificacao in ("duplicata_provavel", "revisar")
        assert result.desc_sim == 1.0

    def test_papeis_diferentes_mesma_faixa_salarial_nao_e_duplicata_provavel(self):
        """AGIS-FN-OPER-ESCAV e AGIS-FN-OPER-TRAT-EST compartilham a mesma taxa
        horária flat (42.7) por serem do mesmo tier de operador — descrição deve
        dominar e impedir classificação como duplicata de alta confiança."""
        escav = {
            "codigo": "AGIS-FN-OPER-ESCAV",
            "tipo": "MAO_OBRA",
            "descricao": "Operador de Escavadeira",
            "preco_unitario": 42.7,
            "unidade": "h",
        }
        trat_est = {
            "codigo": "AGIS-FN-OPER-TRAT-EST",
            "tipo": "MAO_OBRA",
            "descricao": "Operador de Trator de Esteiras",
            "preco_unitario": 42.7,
            "unidade": "h",
        }
        result = insumo_similarity(escav, trat_est)
        assert result.classificacao != "duplicata_provavel"

    def test_referencia_externa_declarada_e_duplicata_direta(self):
        canonico = {"codigo": "MO-ENG-CIVIL", "tipo": "MAO_OBRA", "descricao": "x", "preco_unitario": 1.0}
        p_code = {
            "codigo": "P0024",
            "tipo": "MAO_OBRA",
            "descricao": "y",
            "preco_unitario": 999.0,
            "codigo_referencia_externa": "",
        }
        canonico["codigo_referencia_externa"] = "P0024"
        result = insumo_similarity(canonico, p_code)
        assert result.classificacao == "duplicata_provavel"
        assert result.score == 1.0

    def test_itens_totalmente_nao_relacionados(self):
        a = {"codigo": "MO-1", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 3000.0, "unidade": "mes"}
        b = {
            "codigo": "MO-2",
            "tipo": "MAO_OBRA",
            "descricao": "Engenheiro Florestal",
            "preco_unitario": 9000.0,
            "unidade": "mes",
        }
        result = insumo_similarity(a, b)
        assert result.classificacao is None

    def test_to_dict_tem_todas_as_chaves(self):
        a = {"codigo": "MO-1", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 3000.0}
        b = {"codigo": "MO-2", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 3000.0}
        d = insumo_similarity(a, b).to_dict()
        assert set(d.keys()) == {"codigo_a", "codigo_b", "score", "desc_sim", "price_sim", "categoria_sim", "classificacao", "detalhe"}


# ── find_candidate_duplicates ─────────────────────────────────────────────────


class TestFindCandidateDuplicates:
    def test_bloqueia_por_tipo_nao_compara_mao_obra_com_equipamento(self):
        insumos = [
            {"codigo": "MO-1", "tipo": "MAO_OBRA", "descricao": "Escavadeira", "preco_unitario": 100.0},
            {"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "descricao": "Escavadeira", "preco_unitario": 100.0},
        ]
        assert find_candidate_duplicates(insumos) == []

    def test_encontra_duplicata_dentro_do_bloco(self):
        insumos = [
            {"codigo": "MO-1", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 3000.0},
            {"codigo": "MO-2", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 3000.0},
        ]
        result = find_candidate_duplicates(insumos)
        assert len(result) == 1
        assert {result[0].codigo_a, result[0].codigo_b} == {"MO-1", "MO-2"}

    def test_ordenado_por_score_decrescente(self):
        insumos = [
            {"codigo": "MO-1", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 3000.0},
            {"codigo": "MO-2", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 3000.0},
            {"codigo": "MO-3", "tipo": "MAO_OBRA", "descricao": "Pedreiro Líder", "preco_unitario": 3200.0},
        ]
        result = find_candidate_duplicates(insumos)
        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_lista_vazia(self):
        assert find_candidate_duplicates([]) == []

    def test_idf_do_corpus_evita_falso_positivo_por_palavra_generica(self):
        """Regressão de achado real: sem IDF, 'Encarregado de Frente' (R$7.500) e
        'Encarregado de Obras' (R$3.737,80) eram classificados como similares só
        por compartilharem a palavra genérica 'Encarregado' + razão de preço
        (2,006x) caindo por coincidência na faixa de α. Com IDF calculado sobre um
        corpus onde 'encarregado' aparece em várias funções distintas, o peso dessa
        palavra cai e o par não passa de 'duplicata_provavel'."""
        insumos = [
            {"codigo": "A", "tipo": "MAO_OBRA", "descricao": "Encarregado de Frente", "preco_unitario": 7500.0},
            {"codigo": "B", "tipo": "MAO_OBRA", "descricao": "Encarregado de Obras", "preco_unitario": 3737.8},
            {"codigo": "C", "tipo": "MAO_OBRA", "descricao": "Encarregado de Drenagem", "preco_unitario": 10000.0},
            {"codigo": "D", "tipo": "MAO_OBRA", "descricao": "Encarregado de Terraplenagem", "preco_unitario": 4485.36},
            {"codigo": "E", "tipo": "MAO_OBRA", "descricao": "Encarregado Geral", "preco_unitario": 9000.0},
        ]
        result = find_candidate_duplicates(insumos)
        par_ab = [r for r in result if {r.codigo_a, r.codigo_b} == {"A", "B"}]
        assert not par_ab or par_ab[0].classificacao != "duplicata_provavel"
