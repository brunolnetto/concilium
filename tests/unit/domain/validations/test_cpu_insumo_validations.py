from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo
from concilium.infrastructure.repositories.insumo import RepositorioInsumo


def test_repositorio_insumo_existe():
    catalogo = {"insumos": [{"codigo": "ESCAV-HID", "tipo": "EQUIPAMENTO"}]}
    repo = RepositorioInsumo(catalogo)

    assert repo.insumo_existe("ESCAV-HID")
    assert repo.obter_insumo("ESCAV-HID")["tipo"] == "EQUIPAMENTO"
    assert repo.funcao_existe("ESCAV-HID") is False
    assert repo.equipamento_existe("ESCAV-HID") is True


def test_validar_insumo_existe_retorna_erro():
    repo = RepositorioInsumo({"insumos": []})
    validator = ValidadorCPUInsumo(repo)
    resultado = validator.validar_insumo_existe(
        {"insumo_id": "NAO-EXISTE", "coeficiente": 0.5, "categoria_custo": "MATERIAL"}
    )

    assert resultado.codigo == "VAL-CPU-INS-01"
    assert resultado.status == "ERRO"
    assert "não encontrado" in resultado.mensagem


def test_validar_tipo_compativel_retorna_erro_para_tipo_incompativel():
    catalogo = {"insumos": [{"codigo": "ESCAV-HID", "tipo": "EQUIPAMENTO", "unidade": "h"}]}
    repo = RepositorioInsumo(catalogo)
    validator = ValidadorCPUInsumo(repo)
    insumo = repo.obter_insumo("ESCAV-HID")

    resultado = validator.validar_tipo_compativel(
        {"insumo_id": "ESCAV-HID", "coeficiente": 1.0, "categoria_custo": "MAO_OBRA"},
        insumo,
    )

    assert resultado.codigo == "VAL-CPU-INS-02"
    assert resultado.status == "ERRO"


def test_validar_coeficiente_positivo_retorna_erro_para_zero_e_negativo():
    catalogo = {"insumos": [{"codigo": "AJUDANTE", "tipo": "MAO_OBRA", "unidade": "mes"}]}
    repo = RepositorioInsumo(catalogo)
    validator = ValidadorCPUInsumo(repo)

    resultado_zero = validator.validar_coeficiente_positivo(
        {"insumo_id": "AJUDANTE", "coeficiente": 0.0, "categoria_custo": "MAO_OBRA"}
    )
    resultado_negativo = validator.validar_coeficiente_positivo(
        {"insumo_id": "AJUDANTE", "coeficiente": -1.0, "categoria_custo": "MAO_OBRA"}
    )

    assert resultado_zero.status == "ERRO"
    assert resultado_negativo.status == "ERRO"


def test_validar_unidade_compativel_detecta_unidade_desconhecida():
    catalogo = {"insumos": [{"codigo": "STRANGE", "tipo": "MATERIAL", "unidade": "xpto"}]}
    repo = RepositorioInsumo(catalogo)
    validator = ValidadorCPUInsumo(repo)
    insumo = repo.obter_insumo("STRANGE")

    resultado = validator.validar_unidade_compativel(
        {"insumo_id": "STRANGE", "coeficiente": 1.0, "categoria_custo": "MATERIAL"},
        insumo,
    )

    assert resultado.codigo == "VAL-CPU-INS-05"
    assert resultado.status == "ERRO"


def test_validar_cpu_completa_retorna_7_validacoes_incluindo_funcoes_e_equipamentos():
    catalogo = {
        "insumos": [
            {"codigo": "AJUDANTE", "tipo": "MAO_OBRA", "unidade": "mes"},
            {"codigo": "ESCOAV", "tipo": "EQUIPAMENTO", "unidade": "h"},
        ]
    }
    repo = RepositorioInsumo(catalogo)
    validator = ValidadorCPUInsumo(repo)
    cpu = {
        "codigo": "TEST-CPU",
        "composicao_itens": [
            {"insumo_id": "AJUDANTE", "coeficiente": 0.5, "categoria_custo": "MAO_OBRA"},
            {"insumo_id": "NAO-EXISTE", "coeficiente": 0.1, "categoria_custo": "MATERIAL"},
        ],
        "composicao_padrao_equipe": {
            "funcoes": [{"funcao_id": "OPER-ESCAV", "num_pessoas": 1}],
            "equipamentos": [{"equip_id": "ESCAV-HID-38T", "num_unidades": 1}],
        },
    }

    resultados = validator.validar_cpu_completa(cpu)
    codigos = [resultado.codigo for resultado in resultados]

    assert "VAL-CPU-INS-01" in codigos
    assert "VAL-CPU-INS-02" in codigos
    assert "VAL-CPU-INS-03" in codigos
    assert "VAL-CPU-INS-04" in codigos
    assert "VAL-CPU-INS-05" in codigos
    assert "VAL-CPU-INS-06" in codigos
    assert "VAL-CPU-INS-07" in codigos


def test_validar_cpu_integridade_reporta_item_malformado_em_composicao_itens():
    """Regressão: composicao_itens com uma string solta (não {insumo_id, ...}) —
    dado de catálogo/overlay resolvido sem validação de schema pode conter isso
    após um merge/rascunho incompleto. Deve ser reportado (VAL-CPU-STR-04), não
    causar AttributeError('str' object has no attribute 'get') em skill-05."""
    repo = RepositorioInsumo({"insumos": []})
    validator = ValidadorCPUInsumo(repo)
    cpu = {
        "codigo": "TEST-CPU-MALFORMADO",
        "unidade": "m3",
        "producao_id_ref": "PROD-X",
        "composicao_itens": [
            {"insumo_id": "AJUDANTE", "coeficiente": 0.5, "categoria_custo": "MAO_OBRA"},
            "DIESEL-S10",  # malformado: string em vez de dict
        ],
    }

    resultados = validator.validar_cpu_integridade(cpu)
    str04 = [r for r in resultados if r.codigo == "VAL-CPU-STR-04"]

    assert len(str04) == 1
    assert str04[0].status == "ERRO"
    assert "DIESEL-S10" in str04[0].mensagem


def test_validar_cpu_completa_nao_trava_com_item_malformado_em_composicao_itens():
    """Regressão: validar_cpu_completa não deve propagar AttributeError quando
    composicao_itens tem um elemento string solto — só reporta via VAL-CPU-STR-04
    (validar_cpu_integridade) e ignora o item malformado no loop de VAL-CPU-INS-*."""
    repo = RepositorioInsumo({"insumos": [{"codigo": "AJUDANTE", "tipo": "MAO_OBRA", "unidade": "mes"}]})
    validator = ValidadorCPUInsumo(repo)
    cpu = {
        "codigo": "TEST-CPU-MALFORMADO",
        "unidade": "m3",
        "producao_id_ref": "PROD-X",
        "composicao_itens": [
            {"insumo_id": "AJUDANTE", "coeficiente": 0.5, "categoria_custo": "MAO_OBRA"},
            "DIESEL-S10",
        ],
    }

    resultados = validator.validar_cpu_completa(cpu)  # não deve levantar AttributeError

    assert any(r.codigo == "VAL-CPU-STR-04" for r in resultados)





# ══ validations/cpu_insumo.py ════════════════════════════════════════════════


class TestCpuInsumoValidacoes:
    def _make_validator(self, insumos_list=None):
        from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {"insumos": insumos_list or []}
        repo = RepositorioInsumo(catalogo)
        return ValidadorCPUInsumo(repo)

    def test_validar_coeficiente_sensato_unidade_desconhecida_ok(self):
        """Unidade not in RANGE_SENSATO → OK (line 88)."""
        validator = self._make_validator()
        comp_item = {"insumo_id": "X", "coeficiente": 99999}
        insumo = {"unidade": "unidade_estranha"}
        result = validator.validar_coeficiente_sensato(comp_item, insumo)
        assert result.status == "OK"

    def test_validar_coeficiente_sensato_fora_range_aviso(self):
        """Coeficiente outside range → AVISO (lines 92-99)."""
        from concilium.domain.validations.cpu_insumo import RANGE_SENSATO_POR_UNIDADE

        validator = self._make_validator()
        unit = next(iter(RANGE_SENSATO_POR_UNIDADE))
        _minimo, maximo = RANGE_SENSATO_POR_UNIDADE[unit]
        comp_item = {"insumo_id": "X", "coeficiente": maximo * 1000}
        insumo = {"unidade": unit}
        result = validator.validar_coeficiente_sensato(comp_item, insumo)
        assert result.status == "AVISO"
        assert result.codigo == "VAL-CPU-INS-04"

    def test_validar_unidade_compativel_coeficiente_none(self):
        """coeficiente is None → ERRO (lines 116-120)."""
        from concilium.domain.validations.cpu_insumo import RANGE_OBRIGATORIO_POR_UNIDADE

        validator = self._make_validator()
        unit = next(iter(RANGE_OBRIGATORIO_POR_UNIDADE))
        comp_item = {"insumo_id": "X", "coeficiente": None}
        insumo = {"unidade": unit}
        result = validator.validar_unidade_compativel(comp_item, insumo)
        assert result.status == "ERRO"
        assert result.codigo == "VAL-CPU-INS-05"

    def test_validar_unidade_compativel_coeficiente_fora_range(self):
        """Coeficiente outside mandatory range → ERRO (lines 123-129)."""
        from concilium.domain.validations.cpu_insumo import RANGE_OBRIGATORIO_POR_UNIDADE

        validator = self._make_validator()
        unit = next(iter(RANGE_OBRIGATORIO_POR_UNIDADE))
        _minimo, maximo = RANGE_OBRIGATORIO_POR_UNIDADE[unit]
        comp_item = {"insumo_id": "X", "coeficiente": maximo * 999999}
        insumo = {"unidade": unit}
        result = validator.validar_unidade_compativel(comp_item, insumo)
        assert result.status == "ERRO"
        assert result.codigo == "VAL-CPU-INS-05"

    def test_validar_cpu_completa_insumo_none_skip(self):
        """When insumo is found in repo index but obter_insumo returns None → continue (line 179)."""
        from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {"insumos": [{"codigo": "X", "tipo": "MAO_OBRA", "unidade": "h"}]}
        repo = RepositorioInsumo(catalogo)
        # Monkey-patch obter_insumo to return None even though the item exists
        repo.obter_insumo = lambda codigo: None  # type: ignore[method-assign]
        validator = ValidadorCPUInsumo(repo)
        cpu = {
            "composicao_itens": [{"insumo_id": "X", "coeficiente": 1.0, "categoria_custo": "MAO_OBRA"}],
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
        }
        results = validator.validar_cpu_completa(cpu)
        # VAL-CPU-INS-01 OK (item exists via insumo_existe), then None → continue
        assert any(r.codigo == "VAL-CPU-INS-01" and r.status == "OK" for r in results)


def test_validar_materiais_existem_retorna_erro_para_material_nao_encontrado():
    catalogo = {
        "insumos": [],
        "producoes": [
            {
                "id": "PROD-01",
                "composicao_padrao_equipe": {
                    "materiais": [{"insumo_id": "CIMENTO-NAO-EXISTE", "coeficiente": 1.0}],
                },
            }
        ],
    }
    repo = RepositorioInsumo(catalogo)
    validator = ValidadorCPUInsumo(repo)
    cpu = {"producao_id_ref": "PROD-01"}

    resultado = validator.validar_materiais_existem(cpu)

    assert resultado.codigo == "VAL-CPU-INS-08"
    assert resultado.status == "ERRO"
    assert "CIMENTO-NAO-EXISTE" in resultado.mensagem



