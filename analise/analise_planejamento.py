import pandas as pd
import networkx as nx
from collections import defaultdict


# ─────────────────────────────────────────────
# LEITURA E CONSTRUÇÃO
# ─────────────────────────────────────────────

def ler_tabela(caminho_arquivo, aba=None):
    """
    Lê uma planilha .xlsx ou .csv e retorna um DataFrame com colunas [fonte, destino].
    Se for .xlsx e aba=None, lê a primeira aba.
    """
    if caminho_arquivo.lower().endswith(".xlsx"):
        df = pd.read_excel(caminho_arquivo, sheet_name=0 if aba is None else aba)
    elif caminho_arquivo.lower().endswith(".csv"):
        df = pd.read_csv(caminho_arquivo)
    else:
        raise ValueError("Formato não suportado. Use .xlsx ou .csv")

    if isinstance(df, dict):
        print("⚠️ Múltiplas abas detectadas, usando a primeira.")
        df = list(df.values())[0]

    df.columns = [str(col).strip().lower() for col in df.columns]

    if not {"fonte", "destino"}.issubset(df.columns):
        raise ValueError("A planilha deve ter colunas 'fonte' e 'destino'")

    df = df.copy()
    df["fonte"] = df["fonte"].astype(str).str.strip()
    df["destino"] = df["destino"].astype(str).str.strip()
    df = df.dropna(subset=["fonte", "destino"])

    return df


def construir_dicionario_dependencias(caminho_arquivo, aba=None):
    df = ler_tabela(caminho_arquivo, aba=aba)
    dependencias = defaultdict(set)
    for _, row in df.iterrows():
        dependencias[row["fonte"]].add(row["destino"])
    return {k: sorted(v) for k, v in dependencias.items()}


def carregar_grafo(caminho_arquivo, aba=None):
    df = ler_tabela(caminho_arquivo, aba=aba)
    G = nx.DiGraph()
    for _, row in df.iterrows():
        G.add_edge(row["fonte"], row["destino"])
    return G


# ─────────────────────────────────────────────
# MÉTRICAS E CICLOS
# ─────────────────────────────────────────────

def calcular_metricas(G):
    metricas = pd.DataFrame({"no": list(G.nodes)})
    metricas["grau_saida"] = [G.out_degree(n) for n in G.nodes]
    metricas["grau_entrada"] = [G.in_degree(n) for n in G.nodes]
    metricas["centralidade_grau"] = list(nx.degree_centrality(G).values())
    metricas["betweenness"] = list(nx.betweenness_centrality(G).values())
    max_in = max(dict(G.in_degree()).values(), default=1) or 1
    metricas["convergencia"] = metricas["grau_entrada"] / max_in
    return metricas


def detectar_componentes_ciclicos(G):
    scc = list(nx.strongly_connected_components(G))
    ciclos_reais = [comp for comp in scc if len(comp) > 1]
    contagem = {node: 0 for node in G.nodes}
    for comp in ciclos_reais:
        for node in comp:
            contagem[node] += 1
    return ciclos_reais, contagem


def adicionar_info_ciclos(metricas, contagem_ciclos):
    metricas["participa_ciclo"] = metricas["no"].map(lambda x: contagem_ciclos.get(x, 0) > 0)
    metricas["qtd_ciclos"] = metricas["no"].map(lambda x: contagem_ciclos.get(x, 0))
    return metricas


def podar_folhas_iterativo(G):
    G = G.copy()
    etapas = []
    while True:
        folhas = [n for n in G.nodes if G.out_degree(n) == 0]
        if not folhas:
            break
        etapas.append((len(G.nodes), folhas.copy()))
        G.remove_nodes_from(folhas)
    return G, etapas


def numero_ciclos_independentes(G):
    E = G.number_of_edges()
    N = G.number_of_nodes()
    if N == 0:
        return 0
    undirected = G.to_undirected()
    P = nx.number_connected_components(undirected) if undirected.number_of_nodes() > 0 else 0
    return E - N + P


# ─────────────────────────────────────────────
# SEPARAÇÃO SEMÂNTICA
# ─────────────────────────────────────────────

def classificar_aresta(u, v, camadas):
    c_u = camadas.get(u, -1)
    c_v = camadas.get(v, -1)
    if c_u == -1 or c_v == -1:
        return "DESCONHECIDO"
    if c_u < c_v:
        return "FORWARD"
    elif c_u == c_v:
        return "LOOP_INTERNO"
    return "FEEDBACK_TEMPORAL"


def separar_grafo_semantico(G, camadas):
    G_dag = nx.DiGraph()
    G_loops = nx.DiGraph()
    feedback_edges = []
    classificacao = []

    for u, v in G.edges:
        tipo = classificar_aresta(u, v, camadas)
        classificacao.append((u, v, tipo))
        if tipo == "FORWARD":
            G_dag.add_edge(u, v)
        elif tipo == "LOOP_INTERNO":
            G_loops.add_edge(u, v)
        elif tipo == "FEEDBACK_TEMPORAL":
            feedback_edges.append((u, v))

    return G_dag, G_loops, feedback_edges, classificacao


def exportar_semantico(classificacao, nome_arquivo="classificacao_arestas.xlsx"):
    df = pd.DataFrame(classificacao, columns=["fonte", "destino", "tipo"])
    df.to_excel(nome_arquivo, index=False)
    print(f"\n📁 Arquivo gerado: {nome_arquivo}")


# ─────────────────────────────────────────────
# FEEDBACKS E AJUSTES
# ─────────────────────────────────────────────

def classificar_feedback_semantico(u, v):
    base = {"DADOS", "MÃO DE OBRA", "EQUIPAMENTOS", "QSMS", "TOP", "LAB"}
    controle = {"PLANEJAMENTO", "CRONOGRAMA", "PONTO DE EQUILIBRIO"}
    resultado = {"RESULTADO"}

    if v in base:
        return "RUIDO (não deveria alterar dados base)"
    if u in resultado and v in controle:
        return "UTIL (feedback de controle)"
    if u in {"PRODUÇÕES", "CPU", "EQUIPE"} and v in controle:
        return "UTIL (aprendizado operacional)"
    if u == "ADM" and v in base:
        return "RUIDO (admin alterando base)"
    return "ANALISAR"


def inserir_no_ajustes(G, feedback_classificado):
    G_novo = G.copy()
    for u, v, tipo in feedback_classificado:
        if "UTIL" in tipo:
            nome_ajuste = f"AJUSTES_{u}_PARA_{v}"
            if G_novo.has_edge(u, v):
                G_novo.remove_edge(u, v)
            G_novo.add_node(nome_ajuste)
            G_novo.add_edge(u, nome_ajuste)
            G_novo.add_edge(nome_ajuste, v)
    return G_novo


# ─────────────────────────────────────────────
# PIPELINE (ETAPAS ENCAPSULADAS)
# ─────────────────────────────────────────────

def etapa_carregar(caminho, camadas):
    """Etapa 1 — Leitura e construção do grafo."""
    dependencias = construir_dicionario_dependencias(caminho)
    G = carregar_grafo(caminho)

    print("Dependências:")
    for origem, destinos in dependencias.items():
        print(f"  {origem} → {', '.join(destinos)}")

    return G, dependencias


def etapa_metricas(G):
    """Etapa 2 — Cálculo de métricas e detecção de ciclos."""
    metricas = calcular_metricas(G)
    ciclos, contagem_ciclos = detectar_componentes_ciclicos(G)
    metricas = adicionar_info_ciclos(metricas, contagem_ciclos)
    metricas = metricas.sort_values(
        by=["participa_ciclo", "betweenness"],
        ascending=[False, False]
    )

    print("\n📊 Métricas finais:")
    print(metricas)

    print(f"\n🔁 Componentes cíclicos reais: {len(ciclos)}")
    for i, comp in enumerate(ciclos, 1):
        print(f"  {i}: {sorted(comp)}")

    return metricas, ciclos


def etapa_poda(G):
    """Etapa 3 — Poda iterativa de folhas e número ciclomático."""
    G_final, etapas = podar_folhas_iterativo(G)
    M = numero_ciclos_independentes(G)
    ciclos_basis = nx.cycle_basis(G.to_undirected())

    print(f"\n🔢 Número ciclomático (graus de liberdade): {M}")

    print("\n📉 Processo de poda:")
    for i, (qtd, folhas) in enumerate(etapas, 1):
        print(f"  Etapa {i}: {qtd} nós → removendo {folhas}")

    print("\n🧠 Núcleo restante:")
    print(f"  {sorted(G_final.nodes)}")

    print(f"\n📉 Ciclos da base ({len(ciclos_basis)}):")
    for i, ciclo in enumerate(ciclos_basis, 1):
        print(f"  Ciclo {i}: {ciclo}")

    return G_final, M, ciclos_basis


def etapa_semantica(G, camadas):
    """Etapa 4 — Separação semântica do grafo por camadas."""
    G_dag, G_loops, feedback_edges, classificacao = separar_grafo_semantico(G, camadas)

    print(f"\n➡️  Arestas FORWARD (DAG): {G_dag.number_of_edges()}")
    print(f"🔁 Arestas LOOP_INTERNO:  {G_loops.number_of_edges()}")
    print(f"⏳ Arestas FEEDBACK:       {len(feedback_edges)}")

    if nx.is_directed_acyclic_graph(G_dag):
        print("\n✅ DAG estrutural válida")
    else:
        print("\n❌ Ainda há ciclos na DAG (rever camadas)")

    exportar_semantico(classificacao)

    return G_dag, G_loops, feedback_edges, classificacao


def etapa_feedbacks(G, feedback_edges):
    """Etapa 5 — Classificação dos feedbacks e inserção de nós de ajuste."""
    print("\n🧠 Classificação dos feedbacks:")
    feedback_classificado = []
    for u, v in feedback_edges:
        tipo = classificar_feedback_semantico(u, v)
        feedback_classificado.append((u, v, tipo))
        print(f"  {u} → {v} = {tipo}")

    print("\n🔧 Inserindo nós de AJUSTES...")
    print(f"{feedback_classificado}")
    G_ajustado = inserir_no_ajustes(G, feedback_classificado)

    print(f"\n📈 Impacto nos ciclos:")
    print(f"  Antes:  {G.number_of_edges()} arestas")
    print(f"  Depois: {G_ajustado.number_of_edges()} arestas")

    return feedback_classificado, G_ajustado


def executar_pipeline(caminho, camadas):
    """
    Pipeline completa de análise do grafo de dependências.

    Etapas:
        1. Carregar grafo e dependências
        2. Calcular métricas e detectar ciclos
        3. Podar folhas e calcular número ciclomático
        4. Separação semântica por camadas
        5. Classificar feedbacks e inserir nós de ajuste

    Args:
        caminho: Caminho para o arquivo .xlsx ou .csv com colunas [fonte, destino].
        camadas: Dicionário {nó: int} mapeando cada nó à sua camada semântica.

    Returns:
        Dicionário com os artefatos produzidos por cada etapa.
    """
    G, dependencias = etapa_carregar(caminho, camadas)
    metricas, ciclos = etapa_metricas(G)
    G_final, M, ciclos_basis = etapa_poda(G)
    G_dag, G_loops, feedback_edges, classificacao = etapa_semantica(G, camadas)
    feedback_classificado, G_ajustado = etapa_feedbacks(G, feedback_edges)

    return {
        "grafo_original": G,
        "dependencias": dependencias,
        "metricas": metricas,
        "ciclos": ciclos,
        "nucleo": G_final,
        "numero_ciclomatico": M,
        "ciclos_basis": ciclos_basis,
        "dag": G_dag,
        "loops": G_loops,
        "feedbacks": feedback_classificado,
        "grafo_ajustado": G_ajustado,
    }


# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    CAMINHO = r"C:\Users\GustavoArruda\Downloads\Analise Teste.xlsx"

    CAMADAS = {
        "DADOS": 0, "MÃO DE OBRA": 0, "EQUIPAMENTOS": 0,
        "QSMS": 0, "TOP": 0, "LAB": 0, "PRATICABILIDADE": 0,

        "PLANEJAMENTO": 1, "CRONOGRAMA": 1,
        "PONTO DE EQUILIBRIO": 1, "ADM": 1,

        "PRODUÇÕES": 2, "EQUIPE": 2, "CPU": 2,
        "Escavação e Carga": 2, "MOB": 2,

        "RESULTADO": 3, "BDI": 3,
    }

    resultados = executar_pipeline(CAMINHO, CAMADAS)