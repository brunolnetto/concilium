"""Validadores de compatibilidade entre CPU e insumos."""

from typing import Any

from concilium.domain.models.canonical import ValidacaoItem
from concilium.domain.validations.catalog_refs import REF_EQUIPAMENTOS, REF_FUNCOES, REF_MATERIAIS, ids_faltantes

CATEGORIA_TIPO_MAPA: dict[str, list[str]] = {
    "EQUIPAMENTO": ["EQUIPAMENTO"],
    "MAO_OBRA": ["MAO_OBRA"],
    "MATERIAL": ["MATERIAL"],
    "DIESEL": ["MATERIAL"],
    "COMBUSTIVEL": ["COMBUSTIVEL", "MATERIAL"],
    "TERCEIRIZADO": ["TERCEIRIZADO"],
    "ADESTRAMENTO": ["SERVICO", "MAO_OBRA"],
}

CARACTERES_PROIBIDOS = ["Ã§", "Ã£", "â‰¥", "â‰¤", "â†’"]
RANGE_SENSATO_POR_UNIDADE: dict[str, tuple[float, float]] = {
    "mes": (0.001, 1.0),
    "mês": (0.001, 1.0),  # Variante acentuada
    "h": (0.0001, 100.0),
    "litro": (0.001, 1000.0),
    "l": (0.001, 1000.0),
    "kg": (0.001, 10000.0),
    "m": (0.001, 100.0),
    "m2": (0.001, 1000.0),
    "m²": (0.001, 1000.0),  # Variante com símbolo
    "m3": (0.001, 100.0),
    "m³": (0.001, 100.0),  # Variante com símbolo
    "ton": (0.0001, 1000.0),
    "t": (0.0001, 1000.0),
    "saco": (0.001, 100.0),
    "unidade": (0.001, 100.0),
    "un": (0.001, 100.0),  # Forma abreviada de unidade
}

RANGE_OBRIGATORIO_POR_UNIDADE: dict[str, tuple[float, float]] = {
    **RANGE_SENSATO_POR_UNIDADE,
    "mes": (1e-7, 12.0),
    "mês": (1e-7, 12.0),  # Variante acentuada com range estendido
}


class ValidadorCPUInsumo:
    """Orquestra validações VAL-CPU-INS-* para uma CPU."""

    CATEGORIAS_PERMITIDAS = {
        "TERRAPLENAGEM",
        "DRENAGEM",
        "OBRAS_ARTE",
        "DIVERSOS",
        "PAVIMENTACAO",
        "SINALIZACAO",
        "CANTEIRO",
        "MEIO_AMBIENTE",
        "DESMATAMENTO",
        "SANEAMENTO",
        "FERROVIA",
        "INFRAESTRUTURA",
        "MINERACAO",
    }
    UNIDADES_NORM_MAP = {
        "M2": "m2",
        "M²": "m2",
        "m²": "m2",
        "M3": "m3",
        "M³": "m3",
        "m³": "m3",
        "UN": "un",
        "Un": "un",
        "UNID": "un",
        "unid": "un",
        "UNIDADE": "unidade",
        "Unidade": "unidade",
        "H": "h",
        "HORA": "h",
        "MES": "mes",
        "MÊS": "mes",
        "mês": "mes",
        "Mês": "mes",
        "KG": "kg",
        "TON": "t",
        "T": "t",
    }

    def __init__(self, repo: Any):
        self.repo = repo

    def validar_insumo_existe(self, composicao_item: dict[str, Any]) -> ValidacaoItem:
        insumo_id = composicao_item.get("insumo_id")
        if not self.repo.insumo_existe(insumo_id):
            return ValidacaoItem(
                codigo="VAL-CPU-INS-01",
                status="ERRO",
                mensagem=f"Insumo '{insumo_id}' não encontrado no catálogo",
            )
        return ValidacaoItem(codigo="VAL-CPU-INS-01", status="OK")

    def validar_tipo_compativel(
        self,
        composicao_item: dict[str, Any],
        insumo: dict[str, Any],
    ) -> ValidacaoItem:
        categoria = composicao_item.get("categoria_custo")
        tipos_esperados = CATEGORIA_TIPO_MAPA.get(categoria, [])  # type: ignore[arg-type]
        if insumo.get("tipo") not in tipos_esperados:
            return ValidacaoItem(
                codigo="VAL-CPU-INS-02",
                status="ERRO",
                mensagem=(f"Tipo insumo '{insumo.get('tipo')}' incompatível com categoria_custo '{categoria}'"),
            )
        return ValidacaoItem(codigo="VAL-CPU-INS-02", status="OK")

    def validar_coeficiente_positivo(self, composicao_item: dict[str, Any]) -> ValidacaoItem:
        coeficiente = composicao_item.get("coeficiente")
        if coeficiente is None or coeficiente <= 0:
            return ValidacaoItem(
                codigo="VAL-CPU-INS-03",
                status="ERRO",
                mensagem=f"Coeficiente deve ser > 0, recebido: {coeficiente}",
            )
        return ValidacaoItem(codigo="VAL-CPU-INS-03", status="OK")

    def validar_coeficiente_sensato(
        self,
        composicao_item: dict[str, Any],
        insumo: dict[str, Any],
    ) -> ValidacaoItem:
        unidade = str(insumo.get("unidade", "")).strip().lower()
        coeficiente = composicao_item.get("coeficiente")
        if unidade not in RANGE_SENSATO_POR_UNIDADE or coeficiente is None:
            return ValidacaoItem(codigo="VAL-CPU-INS-04", status="OK")

        minimo, maximo = RANGE_SENSATO_POR_UNIDADE[unidade]
        if not (minimo <= coeficiente <= maximo):
            return ValidacaoItem(
                codigo="VAL-CPU-INS-04",
                status="AVISO",
                mensagem=(
                    f"Coeficiente {coeficiente} está fora do intervalo sensato "
                    f"[{minimo}, {maximo}] para unidade '{unidade}'"
                ),
            )
        return ValidacaoItem(codigo="VAL-CPU-INS-04", status="OK")

    def validar_unidade_compativel(
        self,
        composicao_item: dict[str, Any],
        insumo: dict[str, Any],
    ) -> ValidacaoItem:
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        unidade_insumo_raw = str(insumo.get("unidade", "")).strip()
        unidade_composicao_raw = str(composicao_item.get("unidade", unidade_insumo_raw)).strip()

        # Normalizar unidades para formas canônicas (m² → m2, mês → mes, etc.)
        unidade_insumo = self.UNIDADES_NORM_MAP.get(unidade_insumo_raw, unidade_insumo_raw.lower())
        unidade_composicao = self.UNIDADES_NORM_MAP.get(unidade_composicao_raw, unidade_composicao_raw.lower())

        coeficiente_raw = composicao_item.get("coeficiente")
        coeficiente: int | float | None = coeficiente_raw if isinstance(coeficiente_raw, int | float) else None

        if unidade_composicao != unidade_insumo:
            if not ConversorUnidades.sao_compativeis(unidade_composicao, unidade_insumo):
                return ValidacaoItem(
                    codigo="VAL-CPU-INS-05",
                    status="ERRO",
                    mensagem=f"Incompatibilidade dimensional: não é possível converter '{unidade_composicao}' para '{unidade_insumo}'",  # noqa: E501
                )
            if coeficiente is None:
                coeficiente_val = None
            else:
                try:
                    coeficiente_val = ConversorUnidades.converter(coeficiente, unidade_composicao, unidade_insumo)
                except Exception:
                    coeficiente_val = coeficiente
        else:
            coeficiente_val = coeficiente

        if unidade_insumo not in RANGE_OBRIGATORIO_POR_UNIDADE:
            return ValidacaoItem(
                codigo="VAL-CPU-INS-05",
                status="ERRO",
                mensagem=f"Unidade '{unidade_insumo_raw}' (normalizada: '{unidade_insumo}') "
                f"do insumo não é reconhecida no mapa de ranges",
            )

        if coeficiente_val is None:
            return ValidacaoItem(
                codigo="VAL-CPU-INS-05",
                status="ERRO",
                mensagem="Coeficiente ausente para validação de unidade",
            )

        minimo, maximo = RANGE_OBRIGATORIO_POR_UNIDADE[unidade_insumo]
        if not (minimo <= coeficiente_val <= maximo):
            return ValidacaoItem(
                codigo="VAL-CPU-INS-05",
                status="ERRO",
                mensagem=(
                    f"Coeficiente {coeficiente_val} (base '{unidade_insumo}') é incompatível com a unidade "
                    f"do catálogo [{minimo}, {maximo}]"
                ),
            )
        return ValidacaoItem(codigo="VAL-CPU-INS-05", status="OK")

    def _obter_equipe(self, cpu: dict[str, Any]) -> dict[str, Any]:
        equipe = None
        pid = cpu.get("producao_id_ref")
        if pid:
            ficha = self.repo.obter_producao(pid)
            if ficha:
                equipe = ficha.get("composicao_padrao_equipe")
        return equipe or {}

    def validar_funcoes_existem(self, cpu: dict[str, Any]) -> ValidacaoItem:
        equipe = self._obter_equipe(cpu)
        erros = ids_faltantes(equipe, REF_FUNCOES, self.repo.funcao_existe)

        if erros:
            return ValidacaoItem(
                codigo="VAL-CPU-INS-06",
                status="ERRO",
                mensagem=(f"Funções não encontradas no catálogo: {', '.join(sorted(set(erros)))}"),
            )
        return ValidacaoItem(codigo="VAL-CPU-INS-06", status="OK")

    def validar_equipamentos_existem(self, cpu: dict[str, Any]) -> ValidacaoItem:
        equipe = self._obter_equipe(cpu)
        erros = ids_faltantes(equipe, REF_EQUIPAMENTOS, self.repo.equipamento_existe)

        if erros:
            return ValidacaoItem(
                codigo="VAL-CPU-INS-07",
                status="ERRO",
                mensagem=(f"Equipamentos não encontrados no catálogo: {', '.join(sorted(set(erros)))}"),
            )
        return ValidacaoItem(codigo="VAL-CPU-INS-07", status="OK")

    def validar_materiais_existem(self, cpu: dict[str, Any]) -> ValidacaoItem:
        """VAL-CPU-INS-08: composicao_padrao_equipe.materiais[].insumo_id (ADR-030 D2,
        consumo) deve existir no catálogo. Simétrico a VAL-PROD-GERACAO-01
        (materiais_gerados, ADR-139) — antes deste registro, o lado consumido não
        tinha checagem em nenhum dos dois validadores de referência do catálogo.
        """
        equipe = self._obter_equipe(cpu)
        erros = ids_faltantes(equipe, REF_MATERIAIS, self.repo.insumo_existe)

        if erros:
            return ValidacaoItem(
                codigo="VAL-CPU-INS-08",
                status="ERRO",
                mensagem=(f"Materiais não encontrados no catálogo: {', '.join(sorted(set(erros)))}"),
            )
        return ValidacaoItem(codigo="VAL-CPU-INS-08", status="OK")

    def validar_materiais_gerados(self, cpu: dict[str, Any]) -> ValidacaoItem:
        """VAL-PROD-GERACAO-01 (ADR-139 D3): cada `Producao.materiais_gerados[].insumo_id`
        deve referenciar insumo existente com `origem_material == "GERACAO_INTERNA"`.
        """
        pid = cpu.get("producao_id_ref")
        ficha = self.repo.obter_producao(pid) if pid else None
        materiais_gerados = (ficha or {}).get("materiais_gerados") or []

        erros: list[str] = []
        for mg in materiais_gerados:
            insumo_id = mg.get("insumo_id")
            if not self.repo.insumo_existe(insumo_id):
                erros.append(f"'{insumo_id}' não encontrado no catálogo")
                continue
            insumo = self.repo.obter_insumo(insumo_id) or {}
            origem = insumo.get("origem_material")
            if origem != "GERACAO_INTERNA":
                erros.append(
                    f"'{insumo_id}' tem origem_material={origem!r}, esperado 'GERACAO_INTERNA' "
                    "(classifique o insumo antes de declará-lo como material gerado)"
                )

        if erros:
            return ValidacaoItem(
                codigo="VAL-PROD-GERACAO-01",
                status="ERRO",
                mensagem=f"materiais_gerados inválidos: {'; '.join(erros)}",
            )
        return ValidacaoItem(codigo="VAL-PROD-GERACAO-01", status="OK")

    def validar_producao_existe(self, cpu: dict[str, Any]) -> ValidacaoItem:
        pid = cpu.get("producao_id_ref")
        if pid and not self.repo.producao_existe(pid):
            return ValidacaoItem(
                codigo="VAL-CPU-STR-03",
                status="ERRO",
                mensagem=f"Ficha de produção '{pid}' não encontrada no repositório de produtividades",
            )
        if not pid:
            return ValidacaoItem(
                codigo="VAL-CPU-STR-03",
                status="ERRO",
                mensagem="CPU sem producao_id_ref",
            )
        return ValidacaoItem(codigo="VAL-CPU-STR-03", status="OK")

    def validar_encoding(self, entidade: dict[str, Any]) -> ValidacaoItem:
        textos = [str(v) for v in entidade.values() if isinstance(v, str)]
        for t in textos:
            for prob in CARACTERES_PROIBIDOS:
                if prob in t:
                    return ValidacaoItem(
                        codigo="VAL-CAT-ENC-01",
                        status="AVISO",
                        mensagem=f"Detectado possível corrupção de encoding (Mojibake): '{prob}' em '{t[:30]}...'",
                    )
        return ValidacaoItem(codigo="VAL-CAT-ENC-01", status="OK")

    def validar_vigencia(self, insumo: dict[str, Any]) -> ValidacaoItem:
        data = insumo.get("data_referencia_preco")
        if not data:
            return ValidacaoItem(
                codigo="VAL-INS-VIG-01",
                status="AVISO",
                mensagem="Insumo sem data de referência de preço definida",
            )
        if "2025" not in str(data):
            return ValidacaoItem(
                codigo="VAL-INS-VIG-02",
                status="AVISO",
                mensagem=f"Data de referência defasada: {data}. Recomenda-se atualização para 2025.",
            )
        return ValidacaoItem(codigo="VAL-INS-VIG-01", status="OK")

    def validar_unidade_normalizada(self, entidade: dict[str, Any]) -> ValidacaoItem:
        unidade = str(entidade.get("unidade", "")).strip()
        if not unidade:
            return ValidacaoItem(codigo="VAL-CAT-UNIT-01", status="ERRO", mensagem="Unidade ausente")

        unidade_norm = self.UNIDADES_NORM_MAP.get(unidade.upper(), unidade.lower())
        if unidade != unidade_norm:
            return ValidacaoItem(
                codigo="VAL-CAT-UNIT-01",
                status="AVISO",
                mensagem=f"Unidade '{unidade}' não normalizada. Recomendado: '{unidade_norm}'",
            )
        return ValidacaoItem(codigo="VAL-CAT-UNIT-01", status="OK")

    def validar_categoria_permitida(self, entidade: dict[str, Any]) -> ValidacaoItem:
        categoria = str(entidade.get("categoria", "")).upper()
        if not categoria:
            return ValidacaoItem(codigo="VAL-CAT-CAT-01", status="AVISO", mensagem="Categoria não definida")

        if categoria not in self.CATEGORIAS_PERMITIDAS:
            return ValidacaoItem(
                codigo="VAL-CAT-CAT-01",
                status="ERRO",
                mensagem=f"Categoria inválida: '{categoria}'. Permitidas: {sorted(self.CATEGORIAS_PERMITIDAS)}",
            )
        return ValidacaoItem(codigo="VAL-CAT-CAT-01", status="OK")

    def validar_valores_auditaveis(self, entidade: dict[str, Any]) -> list[ValidacaoItem]:
        erros = []
        if entidade.get("tipo"):  # É um insumo
            preco = entidade.get("preco_unitario")
            # ADR-139 D1: material de geração interna tem preço 0.0 por convenção
            # (custo já capturado na CPU produtora) — não é dado faltante.
            geracao_interna = entidade.get("origem_material") == "GERACAO_INTERNA"
            if (preco is None or preco <= 0) and not geracao_interna:
                erros.append(
                    ValidacaoItem(
                        codigo="VAL-INS-VAL-01",
                        status="ERRO",
                        mensagem=f"Insumo '{entidade.get('codigo')}' com preço nulo ou zerado",
                    )
                )
        if "composicao_itens" in entidade:  # É uma CPU
            prod_ref = entidade.get("producao_id_ref")
            if not prod_ref:
                erros.append(
                    ValidacaoItem(
                        codigo="VAL-CPU-VAL-01",
                        status="ERRO",
                        mensagem=f"CPU '{entidade.get('codigo')}' sem producao_id_ref",
                    )
                )

            if any(k in entidade for k in ["producao_horaria", "producao_id", "equipe", "atributos_categoria"]):
                erros.append(
                    ValidacaoItem(
                        codigo="VAL-CPU-VAL-LEGACY",
                        status="AVISO",
                        mensagem=(
                            f"CPU '{entidade.get('codigo')}' contém campos legados "
                            "(producao_horaria/producao_id/equipe/atributos_categoria)."
                        ),
                    )
                )

        return erros if erros else [ValidacaoItem(codigo="VAL-CAT-VAL-01", status="OK")]

    def validar_cpu_integridade(self, cpu: dict[str, Any]) -> list[ValidacaoItem]:
        resultados = []
        codigo = cpu.get("codigo", "S/C")

        if not cpu.get("unidade"):
            resultados.append(
                ValidacaoItem(
                    codigo="VAL-CPU-STR-01", status="ERRO", mensagem=f"CPU '{codigo}' sem unidade de medida definida"
                )
            )

        if not cpu.get("producao_id_ref"):
            resultados.append(
                ValidacaoItem(
                    codigo="VAL-CPU-STR-02",
                    status="ERRO",
                    mensagem=f"CPU '{codigo}' sem referência de produtividade (producao_id_ref)",
                )
            )

        if any(k in cpu for k in ["producao_horaria", "producao_id", "equipe", "atributos_categoria"]):
            resultados.append(
                ValidacaoItem(
                    codigo="VAL-CPU-STR-03",
                    status="AVISO",
                    mensagem=(
                        f"CPU '{codigo}' contém campos legados "
                        "(producao_horaria/producao_id/equipe/atributos_categoria)."
                    ),
                )
            )

        if not resultados:
            resultados.append(ValidacaoItem(codigo="VAL-CPU-STR-01", status="OK"))

        return resultados

    def validar_cpu_completa(self, cpu: dict[str, Any]) -> list[ValidacaoItem]:
        resultados: list[ValidacaoItem] = []

        # 1. Integridade Estrutural
        resultados.extend(self.validar_cpu_integridade(cpu))

        for composicao_item in cpu.get("composicao_itens", []):
            resultado_01 = self.validar_insumo_existe(composicao_item)
            resultados.append(resultado_01)
            if resultado_01.status == "ERRO":
                continue

            insumo = self.repo.obter_insumo(composicao_item["insumo_id"])
            if insumo is None:
                continue

            resultados.append(self.validar_tipo_compativel(composicao_item, insumo))
            resultados.append(self.validar_coeficiente_positivo(composicao_item))
            resultados.append(self.validar_coeficiente_sensato(composicao_item, insumo))
            resultados.append(self.validar_unidade_compativel(composicao_item, insumo))

        resultados.append(self.validar_funcoes_existem(cpu))
        resultados.append(self.validar_equipamentos_existem(cpu))
        resultados.append(self.validar_materiais_existem(cpu))
        resultados.append(self.validar_materiais_gerados(cpu))
        resultados.append(self.validar_producao_existe(cpu))
        resultados.append(self.validar_encoding(cpu))
        resultados.append(self.validar_unidade_normalizada(cpu))
        resultados.append(self.validar_categoria_permitida(cpu))
        resultados.extend(self.validar_valores_auditaveis(cpu))
        return resultados
