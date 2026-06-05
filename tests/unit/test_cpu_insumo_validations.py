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
