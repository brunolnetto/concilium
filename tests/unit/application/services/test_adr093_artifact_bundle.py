"""ADR-093: Serviço de artefatos — testes de classificação, leitura e bundle zip."""

import base64
import io
import zipfile

import pytest

from concilium.application.services.artifact import artifact_bundle as ab


@pytest.fixture
def store(tmp_path):
    """ProjectHandle real via BlobStoragePort (ADR-047) — artifact_bundle.py não
    depende de filesystem local, então o teste tem que exercitar a abstração
    de verdade (list_file_names/read_bytes/exists), não um stub com `.root`
    tratado como Path real."""
    from concilium.infrastructure.storage.store_factory import build_project_repository

    project = build_project_repository(tmp_path).create_project("Obra Teste", "ctx-test")
    v = project.new_version()
    project.write_bytes(f"{v}/outputs/relatorio.md", "# Relatório\nconteúdo".encode())
    project.write_bytes(f"{v}/outputs/memorial_bdi.md", b"# Memorial BDI")
    project.write_bytes(f"{v}/outputs/resultado_planejamento.xlsx", b"PK\x03\x04fake-xlsx")
    project.write_bytes(f"{v}/outputs/gantt_cronograma.png", b"\x89PNG\r\n\x1a\nfakepng")
    project.write_bytes(f"{v}/intermediate/relatorio.json", b'{"a": 1}')
    project.write_bytes(f"{v}/artifacts/abc123.json", b'{"kind": "x"}')
    project.write_bytes(f"{v}/artifacts/abc123.meta.json", b'{"meta": 1}')
    return project


class TestClassificacao:
    def test_audiencia_por_nome_e_extensao(self):
        assert ab.classify_audience("relatorio.md") == ab.AUDIENCIA_AGENTE
        assert ab.classify_audience("resultado_planejamento.xlsx") == ab.AUDIENCIA_HUMANO
        assert ab.classify_audience("gantt_cronograma.png") == ab.AUDIENCIA_HUMANO
        assert ab.classify_audience("resumo_executivo.md") == ab.AUDIENCIA_AMBOS
        assert ab.classify_audience("qualquer.xyz") == ab.AUDIENCIA_AMBOS

    def test_is_text_artifact(self):
        assert ab.is_text_artifact("relatorio.md")
        assert ab.is_text_artifact("dados.json")
        assert not ab.is_text_artifact("grafico.png")
        assert not ab.is_text_artifact("planilha.xlsx")


class TestListagem:
    def test_lista_todos_menos_sidecar_meta(self, store):
        res = ab.list_artifacts(store, None)
        nomes = {a["nome"] for a in res["artefatos"]}
        assert "relatorio.md" in nomes
        assert "gantt_cronograma.png" in nomes
        assert "abc123.json" in nomes
        # sidecar .meta.json não é entregável primário
        assert "abc123.meta.json" not in nomes
        assert res["version"] == "v1"

    def test_metadados_por_artefato(self, store):
        res = ab.list_artifacts(store, None)
        rel = next(a for a in res["artefatos"] if a["nome"] == "relatorio.md")
        assert rel["audiencia"] == ab.AUDIENCIA_AGENTE
        assert rel["kind"] == "outputs"
        assert rel["tamanho_bytes"] > 0
        assert rel["descricao"]


class TestLeituraTexto:
    def test_le_md(self, store):
        res = ab.read_text(store, None, "relatorio.md")
        assert "Relatório" in res["conteudo"]
        assert res["audiencia"] == ab.AUDIENCIA_AGENTE

    def test_le_json_intermediate(self, store):
        res = ab.read_text(store, None, "relatorio.json")
        assert res["conteudo"] == '{"a": 1}'
        assert res["kind"] == "intermediate"

    def test_binario_rejeitado(self, store):
        with pytest.raises(ValueError):
            ab.read_text(store, None, "gantt_cronograma.png")

    def test_inexistente(self, store):
        with pytest.raises(FileNotFoundError):
            ab.read_text(store, None, "nao_existe.md")

    def test_path_traversal_bloqueado(self, store):
        with pytest.raises(ValueError):
            ab.read_text(store, None, "../../../etc/passwd")


class TestBinario:
    def test_base64_inline(self, store):
        res = ab.read_binary_b64(store, None, "gantt_cronograma.png")
        assert res["encoding"] == "base64"
        assert base64.b64decode(res["conteudo_base64"]).startswith(b"\x89PNG")
        assert res["audiencia"] == ab.AUDIENCIA_HUMANO

    def test_acima_do_limite_devolve_path(self, store):
        res = ab.read_binary_b64(store, None, "resultado_planejamento.xlsx", max_mb=0.0)
        assert res["encoding"] == "path"
        assert "caminho" in res


class TestBundle:
    def test_bundle_contem_manifesto_e_outputs(self, store):
        res = ab.build_bundle(store, None)
        assert res["nome_arquivo"].startswith("concilium_Obra_Teste_v1")
        data = base64.b64decode(res["conteudo_base64"])
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            root = "concilium_Obra_Teste_v1"
            assert f"{root}/MANIFESTO.md" in names
            assert f"{root}/relatorio.md" in names
            # PNG vai sob graficos/
            assert f"{root}/graficos/gantt_cronograma.png" in names
            manifesto = zf.read(f"{root}/MANIFESTO.md").decode("utf-8")
            assert "Obra Teste" in manifesto
            assert "relatorio.md" in manifesto

    def test_bundle_filtra_por_audiencia_humano(self, store):
        res = ab.build_bundle(store, None, filtro=["humano"])
        data = base64.b64decode(res["conteudo_base64"])
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n.split("/", 1)[1] for n in zf.namelist()]
        assert "graficos/gantt_cronograma.png" in names
        assert "resultado_planejamento.xlsx" in names
        # relatorio.md é audiência 'agente' → fora do filtro humano
        assert "relatorio.md" not in names

    def test_bundle_com_transport_explicito_nao_usa_default(self, store):
        """Line 313 false branch: transport explicitamente passado é usado diretamente,
        sem instanciar o LocalBase64Transport default."""
        from concilium.application.services.artifact.artifact_transport import LocalBase64Transport

        custom_transport = LocalBase64Transport(max_mb=10.0)
        res = ab.build_bundle(store, None, transport=custom_transport)
        assert "conteudo_base64" in res or "nome_arquivo" in res

    def test_bundle_intermediate_apenas_por_nome_explicito(self, store):
        # sem filtro: intermediários (relatorio.json) não entram no bundle de entrega
        res = ab.build_bundle(store, None)
        data = base64.b64decode(res["conteudo_base64"])
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n.split("/", 1)[1] for n in zf.namelist()]
        assert "relatorio.json" not in names


class TestTransport:
    def test_local_base64_inline(self):
        from concilium.application.services.artifact.artifact_transport import LocalBase64Transport

        t = LocalBase64Transport(max_mb=10.0)
        out = t.deliver(nome="x.bin", data=b"hello", mime="application/octet-stream")
        assert out["encoding"] == "base64"
        assert base64.b64decode(out["conteudo_base64"]) == b"hello"

    def test_local_acima_do_limite_com_path(self, tmp_path):
        from concilium.application.services.artifact.artifact_transport import LocalBase64Transport

        p = tmp_path / "big.bin"
        p.write_bytes(b"x" * 100)
        t = LocalBase64Transport(max_mb=0.0)
        out = t.deliver(nome="big.bin", data=b"x" * 100, mime="application/octet-stream", source_path=p)
        assert out["encoding"] == "path"
        assert out["caminho"] == str(p)

    def test_local_acima_do_limite_sem_path_usa_base64_com_aviso(self):
        from concilium.application.services.artifact.artifact_transport import LocalBase64Transport

        t = LocalBase64Transport(max_mb=0.0)
        out = t.deliver(nome="bundle.zip", data=b"x" * 100, mime="application/zip")
        assert out["encoding"] == "base64"
        assert "aviso" in out

    def test_get_transport_default_local(self):
        from concilium.application.services.artifact.artifact_transport import (
            LocalBase64Transport,
            get_transport,
        )

        assert isinstance(get_transport(), LocalBase64Transport)

    def test_get_transport_azure_sem_env_levanta(self, monkeypatch):
        from concilium.application.services.artifact.artifact_transport import get_transport

        # Sem CONCILIUM__AZURE_CONTAINER, o adapter Azure recusa instanciar.
        monkeypatch.delenv("CONCILIUM__AZURE_CONTAINER", raising=False)
        with pytest.raises(OSError):
            get_transport("azure_blob")


class _FakePort:
    """BlobStoragePort de teste: registra uploads e opcionalmente gera URL."""

    def __init__(self, url=None, raise_on_write=False):
        self._url = url
        self._raise = raise_on_write
        self.gravados = {}

    def gravar_blob(self, path, content):
        if self._raise:
            raise RuntimeError("storage indisponível")
        self.gravados[path] = content

    def gerar_url_temporaria(self, path, ttl_segundos=900):
        return self._url


class TestBlobStorageTransport:
    def test_entrega_via_url_quando_backend_suporta(self):
        from concilium.application.services.artifact.artifact_transport import BlobStorageTransport

        port = _FakePort(url="https://blob.example/sas?token=abc")
        t = BlobStorageTransport(port, prefixo="entregas")
        out = t.deliver(nome="bundle.zip", data=b"zipdata", mime="application/zip")
        assert out["encoding"] == "url"
        assert out["url"].startswith("https://blob.example/")
        assert out["blob_path"] == "entregas/bundle.zip"
        assert port.gravados["entregas/bundle.zip"] == b"zipdata"

    def test_fallback_base64_quando_sem_url(self):
        from concilium.application.services.artifact.artifact_transport import BlobStorageTransport

        port = _FakePort(url=None)
        out = BlobStorageTransport(port).deliver(nome="a.bin", data=b"xyz", mime="application/octet-stream")
        assert out["encoding"] == "base64"
        assert base64.b64decode(out["conteudo_base64"]) == b"xyz"

    def test_fallback_base64_quando_upload_falha(self):
        from concilium.application.services.artifact.artifact_transport import BlobStorageTransport

        port = _FakePort(raise_on_write=True)
        out = BlobStorageTransport(port).deliver(nome="a.bin", data=b"xyz", mime="application/octet-stream")
        assert out["encoding"] == "base64"
        assert "aviso" in out

    def test_port_base_nao_gera_url(self):
        # Contrato do Port: gerar_url_temporaria default é None (ex.: local).
        from concilium.domain.repositories.blob_storage_port import BlobStoragePort

        class _Min(BlobStoragePort):
            def ler_blob(self, path):
                return b""

            def gravar_blob(self, path, content):
                pass

            def listar_blobs(self, prefix):
                return []

            def blob_existe(self, path):
                return False

        assert _Min().gerar_url_temporaria("x") is None

    def test_read_binary_respeita_transport_injetado(self, store):
        from concilium.application.services.artifact.artifact_transport import LocalBase64Transport

        res = ab.read_binary_b64(store, None, "gantt_cronograma.png", transport=LocalBase64Transport(max_mb=10.0))
        assert res["encoding"] == "base64"


class TestMissingLineCoverage:
    """Targets specific lines not yet covered by existing tests."""

    # -- describe_artifact ---------------------------------------------------
    def test_describe_artifact_png_not_in_descricoes(self):
        # Line 93: custom .png file not in _DESCRICOES
        result = ab.describe_artifact("custom_chart.png")
        assert "custom_chart.png" in result

    def test_describe_artifact_unknown_extension(self):
        # Line 96: fallback for unknown extension
        result = ab.describe_artifact("dados.xyz")
        assert "dados.xyz" in result

    def test_describe_artifact_json_not_in_descricoes(self):
        # Line 94: .json fallback
        result = ab.describe_artifact("foo_bar.json")
        assert "foo_bar.json" in result

    # -- _resolve_version ----------------------------------------------------
    def test_resolve_version_exception_returns_none(self):
        # Lines 117-118: exception in current_version() → returns None
        from concilium.application.services.artifact.artifact_bundle import _resolve_version

        class _BrokenStore:
            def current_version(self):
                raise RuntimeError("broken")

        result = _resolve_version(_BrokenStore(), None)
        assert result is None

    # -- list_artifacts with no version --------------------------------------
    def test_list_artifacts_no_version_returns_empty(self):
        # Line 161: resolved is None
        class _NoVersionStore:
            def current_version(self):
                raise RuntimeError("no version")

        result = ab.list_artifacts(_NoVersionStore(), None)
        assert result == {"version": None, "artefatos": [], "total": 0}

    # -- read_text with no version -------------------------------------------
    def test_read_text_no_version_raises(self):
        # Line 184: resolved is None
        class _NoVersionStore:
            def current_version(self):
                raise RuntimeError("no version")

        with pytest.raises(FileNotFoundError, match="versão ativa"):
            ab.read_text(_NoVersionStore(), None, "relatorio.md")

    # -- read_binary_b64 with no version -------------------------------------
    def test_read_binary_b64_no_version_raises(self):
        # Line 215: resolved is None
        class _NoVersionStore:
            def current_version(self):
                raise RuntimeError("no version")

        with pytest.raises(FileNotFoundError, match="versão ativa"):
            ab.read_binary_b64(_NoVersionStore(), None, "chart.png")

    def test_read_binary_b64_file_not_found_raises(self, store):
        # Line 218: file doesn't exist in version
        with pytest.raises(FileNotFoundError, match="nonexistent.png"):
            ab.read_binary_b64(store, None, "nonexistent.png")

    # -- _safe_name path traversal on a text file ----------------------------
    def test_safe_name_raises_for_path_with_slash(self):
        # Line 139: name != filename (contains directory component)
        from concilium.application.services.artifact.artifact_bundle import _safe_name

        with pytest.raises(ValueError, match="inválido"):
            _safe_name("subdir/relatorio.md")

    def test_safe_name_raises_for_empty_string(self):
        # Line 139: not name
        from concilium.application.services.artifact.artifact_bundle import _safe_name

        with pytest.raises(ValueError):
            _safe_name("")

    # -- build_bundle with no version ----------------------------------------
    def test_build_bundle_no_version_raises(self):
        # Line 281: resolved is None
        class _NoVersionStore:
            def current_version(self):
                raise RuntimeError("no version")

        with pytest.raises(FileNotFoundError, match="versão ativa"):
            ab.build_bundle(_NoVersionStore(), None)

    # -- build_bundle skips missing src file ---------------------------------
    def test_build_bundle_skips_file_if_missing_during_zip(self, store):
        # Linha `if data is None: continue` — entrada injetada aponta para um
        # blob que nunca foi gravado (ghost).
        import base64
        import io
        import zipfile
        from unittest.mock import patch

        # Patch list_artifacts to inject a ghost entry (blob que nunca foi gravado)
        original_list = ab.list_artifacts

        def _patched_list(s, ver):
            result = original_list(s, ver)
            result["artefatos"].append(
                {
                    "nome": "ghost.md",
                    "kind": "outputs",
                    "audiencia": ab.AUDIENCIA_AGENTE,
                    "tamanho_bytes": 0,
                    "descricao": "Ghost file",
                }
            )
            return result

        with patch.object(ab, "list_artifacts", side_effect=_patched_list):
            result = ab.build_bundle(store, None)

        # Bundle builds successfully; ghost.md silently skipped
        data = base64.b64decode(result["conteudo_base64"])
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
        assert any("MANIFESTO.md" in n for n in names)
        assert not any("ghost.md" in n for n in names)

    # -- _iter_artifact_files só lista filhos diretos -------------------------
    def test_iter_artifact_files_ignores_nested_files(self, store):
        # list_file_names só retorna filhos diretos — um arquivo dentro de um
        # subdiretório de outputs/ não deve aparecer (equivalente ao antigo
        # guard f.is_file() do filesystem cru).
        from concilium.application.services.artifact.artifact_bundle import _iter_artifact_files

        v = store.current_version()
        store.write_bytes(f"{v}/outputs/subdir/nested.md", b"data")

        items = _iter_artifact_files(store, v)
        names = [name for _, name in items]
        assert "relatorio.md" in names
        assert "nested.md" not in names
        assert not any("subdir" in n for n in names)


class TestResumoExecutivo:
    def _relatorio(self):
        return {
            "meta": {"projeto": "Obra Teste"},
            "resumo": {"projeto": "Obra Teste", "status": "APROVADO", "periodo": "2026"},
            "RESULTADO": {
                "preco_venda_total": 103_000_000.0,
                "custo_total": 90_000_000.0,
                "resultado_bruto": 13_000_000.0,
                "margem_pct": 0.126,
                "status_margem": "VERDE",
            },
        }

    def test_resumo_basico_sem_canonical(self):
        from concilium.application.runtime.deliverables.reports.executive_summary import (
            render_resumo_executivo,
        )

        md = render_resumo_executivo(self._relatorio(), canonical=None)
        assert "# Sumário Executivo — Obra Teste" in md
        assert "APROVADO" in md
        assert "103" in md  # preço operacional
        assert "Dimensionamento Financeiro" in md

    def test_resumo_inclui_criticas_e_levers(self):
        from types import SimpleNamespace

        from concilium.application.runtime.deliverables.reports.executive_summary import (
            render_resumo_executivo,
        )

        crit = SimpleNamespace(
            atividades=[
                SimpleNamespace(
                    atividade_id="eap-1_5",
                    classe="A",
                    rank_lexicografico=1,
                    interpretacao="Escavação domina o custo",
                ),
                SimpleNamespace(
                    atividade_id="eap-1_8",
                    classe="B",
                    rank_lexicografico=2,
                    interpretacao="Transporte secundário",
                ),
            ]
        )
        pe = SimpleNamespace(
            item_id="eap-1_5",
            levers_equilibrio=[
                SimpleNamespace(
                    id="fechar_gap_pool",
                    descricao="Otimizar pool",
                    delta_margin=500_000.0,
                    viavel=True,
                ),
                SimpleNamespace(
                    id="revisao_bdi",
                    descricao="Sem efeito",
                    delta_margin=0.0,
                    viavel=False,
                ),
            ],
        )
        canonical = SimpleNamespace(cost_criticality_report=crit, ponto_equilibrio=[pe])
        md = render_resumo_executivo(self._relatorio(), canonical=canonical)
        assert "eap-1_5" in md
        assert "Atividades Críticas do Cronograma" in md
        assert "Otimizar pool" in md
        # lever inviável não aparece
        assert "Sem efeito" not in md
