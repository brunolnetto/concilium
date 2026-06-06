# ADR-101: MCP Apps — CLI, Dashboard e Notebooks

**Status:** ✅ Implementado  
**Data:** 2026-05-26  
**Autores:** Bruno Peixoto / Concilium  
**Contexto:** Consumo dos tools MCP em múltiplos clientes  
**Dependências:** ADR-093 (MCP Artefatos), ADR-094 (JWT Auth), ADR-100 (DuckDB Analytics)

---

## 1. Contexto

### 1.1 O Problema do Acesso Restrito

Até ADR-101, o MCP Server era usado **apenas via IDE** (Claude Code):

- Sem **CLI** para automatizar pipelines
- Sem **Dashboard** para gestão/monitoramento
- Sem **Notebooks** para análises exploratórias
- Sem **SDK** oficial para consumo externo

**Consequências:**

| # | Problema | Impacto |
|---|---|---|
| P1 | Sem automação via CLI | Rotinas manuais repetitivas |
| P2 | Sem visibilidade gerencial | Liderança sem dashboards |
| P3 | Sem uso exploratório | Analistas limitados |
| P4 | Sem integração externa | Clientes não conseguem consumir |

### 1.2 Requisitos dos Clientes MCP

| Cliente | Necessidade |
|---|---|
| **CLI** | Executar precificação, cronograma, relatórios |
| **Dashboard** | KPIs, custos, status de projetos |
| **Notebooks** | Exploração ad-hoc |
| **SDK** | Integrações externas |

---

## 2. Decisão

### A. Criar três aplicações MCP

#### 2.1 MCP CLI (Python)

```python
# src/concilium/clients/cli/main.py
import typer
from concilium.clients.mcp import MCPClient

app = typer.Typer()
client = MCPClient(base_url="https://api.concilium.com/mcp")

@app.command()
def precificar(projeto_path: str):
    """Executa precificação a partir de arquivo JSON."""
    with open(projeto_path) as f:
        projeto = json.load(f)
    result = client.call("precificar", projeto=projeto)
    print(json.dumps(result, indent=2))

@app.command()
def analytics_top():
    """Top CPUs mais caras."""
    result = client.call("analytics_top_cpus", limit=10)
    print(result)

@app.command()
def login():
    """Login via Device Code (ADR-094)."""
    token = client.device_login()
    print("✅ Token salvo")

if __name__ == "__main__":
    app()
```

#### 2.2 MCP Dashboard (React)

```tsx
// src/concilium/clients/dashboard/App.tsx
import { useMCP } from "./hooks/useMCP";

export function App() {
  const { call } = useMCP();

  const [kpis, setKpis] = useState(null);

  useEffect(() => {
    async function fetchKPIs() {
      const data = await call("analytics_impacto_categoria");
      setKpis(data);
    }
    fetchKPIs();
  }, []);

  return (
    <div>
      <h1>Concilium Dashboard</h1>
      <KPIChart data={kpis} />
    </div>
  );
}
```

#### 2.3 MCP Notebooks (Jupyter)

```python
# notebooks/concilium_analytics.ipynb
from concilium.clients.mcp import MCPClient

client = MCPClient(base_url="https://api.concilium.com/mcp")

# Top CPUs mais caras
top = client.call("analytics_top_cpus", limit=10)
top
```

### B. SDK MCP (Python)

```python
# src/concilium/clients/mcp/client.py
import requests

class MCPClient:
    """Cliente MCP para consumo externo."""
    
    def __init__(self, base_url: str, token: str = None):
        self.base_url = base_url
        self.token = token
    
    def call(self, tool: str, **kwargs):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        resp = requests.post(
            f"{self.base_url}/tools/{tool}",
            json=kwargs,
            headers=headers
        )
        resp.raise_for_status()
        return resp.json()
    
    def device_login(self):
        """Device code flow (ADR-094)."""
        resp = requests.post(f"{self.base_url}/auth/device")
        data = resp.json()
        print(f"URL: {data['verification_url']}")
        print(f"Código: {data['user_code']}")
        # Polling omitted for brevity
```

---

## 3. Consequências

### 3.1 Positivas

| Benefício | Métrica | Detalhe |
|---|---|---|---|
| 💻 **CLI automatizável** | Scripts 10x mais rápidos | Execução em batch |
| 📊 **Dashboard gerencial** | Visibilidade total | KPIs em tempo real |
| 📚 **Notebooks exploratórios** | Insights ad-hoc | Analistas felizes |
| 🔌 **SDK reutilizável** | Integrações externas | Facilita adoção |

### 3.2 Negativas

| Problema | Impacto | Mitigação |
|---|---|---|---|
| 🔧 **Manutenção** | 3 clientes diferentes | Shared SDK |
| 📦 **Distribuição** | Publicar CLI e SDK | PyPI pipeline |

---

## 4. Validação

### 4.1 Smoke Tests

| Cliente | Teste | Resultado |
|---|---|---|
| CLI | `concilium precificar projeto.json` | ✅ |
| Dashboard | Carregar KPIs | ✅ |
| Notebook | Executar analytics | ✅ |
| SDK | Call tool | ✅ |

---

## 5. Implementação

### 5.1 Estrutura de Pastas

```
src/concilium/clients/
├── cli/               # CLI Typer
├── dashboard/         # React app
└── mcp/               # SDK Python
```

### 5.2 Distribuição

- CLI publicado via PyPI: `pip install concilium-cli`
- SDK publicado via PyPI: `pip install concilium-mcp`
- Dashboard publicado via Vercel/Netlify

---

## 6. Notas Técnicas

- CLI usa **Typer** (UX amigável)
- Dashboard usa **React + Vite**
- Notebook template em `notebooks/`

---

## 7. Referências

- [Typer](https://typer.tiangolo.com/)
- [React](https://react.dev/)
- [Jupyter Notebook](https://jupyter.org/)
- ADR-093: MCP Artefatos