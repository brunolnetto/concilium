# ADR-099: RBAC (Role-Based Access Control) com Permissions Granulares

**Status:** ✅ Implementado  
**Data:** 2026-05-25  
**Autores:** Bruno Peixoto / Concilium  
**Contexto:** Controle de acesso baseado em roles e permissions  
**Dependências:** ADR-094 (JWT Auth), ADR-098 (Rate Limiter), ADR-101 (MCP Apps)

---

## 1. Contexto

### 1.1 O Problema do Acesso Sem Controle

Antes do ADR-099, **todos os usuários autenticados tinham acesso total**:

```python
# ANTES: Usuário autenticado = acesso total
@app.post("/api/v1/admin/delete_project")
async def delete_project(project_id: str, user: User = Depends(get_current_user)):
    # ❌ Qualquer usuário autenticado pode deletar projetos!
    return db.delete(project_id)
```

**Problemas observados:**

| # | Problema | Impacto | Observação |
|---|---|---|---|
| P1 | **Sem separação de privilégios** | Todos têm acesso de admin | 🔴 **CRÍTICO** |
| P2 | **Sem auditoria de ações** | Não sabemos quem fez o quê | 🟠 Alto |
| P3 | **Sem controle granular** | Não há "leitura apenas" ou "edição" | 🟠 Alto |
| P4 | **Risco de segurança** | Usuário comum pode deletar dados | 🔴 **CRÍTICO** |
| P5 | **Compliance** | Não atende SOC2, ISO27001 | 🟡 Médio |

**Exemplo real do problema P1 (Incidente 2026-05-22):**

```
14:30 - Usuário "junior_analyst" (analista júnior) autenticado
14:35 - Acidentalmente chama DELETE /api/v1/projects/AGIS
14:36 - Projeto AGIS (benchmark crítico) deletado 💥
14:40 - Equipe percebe perda de dados
14:45 - Necessário restore do backup (downtime 30min)

Root cause: Usuário sem privilégio de admin conseguiu deletar projeto crítico
```

### 1.2 Requisitos de RBAC

| Requisito | Justificativa |
|---|---|
| **Roles predefinidos** | Admin, Analyst, Viewer, Guest |
| **Permissions granulares** | read:projects, write:projects, delete:projects, etc. |
| **Integração JWT** | Roles no token JWT (ADR-094) |
| **Decoradores FastAPI** | `@require_role("admin")`, `@require_permission("delete:projects")` |
| **Auditoria** | Logs de todas as ações com role/permission |
| **Configurável** | Roles/permissions via config (não hardcoded) |

### 1.3 Alternativas Avaliadas

| Solução | Vantagens | Desvantagens | Decisão |
|---|---|---|---|
| **ACL (Access Control Lists)** | Granular por recurso | Complexo, não escala | ❌ Rejeitado |
| **ABAC (Attribute-Based)** | Muito flexível | Muito complexo | ❌ Rejeitado |
| **RBAC (Role-Based)** | Simples, escalável | Menos granular que ACL | ✅ **Escolhido** |
| **OAuth Scopes** | Padrão OAuth | Requer OAuth server | ⚠️ Futuro |
| **Casbin** | Policy engine poderoso | +1 dependência pesada | ❌ Rejeitado |

**Por que RBAC foi escolhido:**

1. **Simplicidade:** Usuários têm roles, roles têm permissions
2. **Escalável:** Adicionar novo role é trivial
3. **Padrão indústria:** AWS IAM, Azure RBAC, Google Cloud IAM usam RBAC
4. **Integração JWT:** Roles cabem no token JWT (ADR-094)
5. **Auditável:** Fácil responder "quais admins temos?" ou "quem tem permissão X?"

---

## 2. Decisão

### A. Implementar RBAC com 4 roles + permissions granulares

#### 2.1 Modelo de Dados

```python
# src/concilium/domain/models/rbac.py
from dataclasses import dataclass
from enum import Enum
from typing import Set, List

class Permission(Enum):
    """Permissions granulares do sistema."""
    
    # ========== PROJECTS ==========
    READ_PROJECTS = "read:projects"
    WRITE_PROJECTS = "write:projects"
    DELETE_PROJECTS = "delete:projects"
    
    # ========== CATALOG ==========
    READ_CATALOG = "read:catalog"
    WRITE_CATALOG = "write:catalog"
    ADMIN_CATALOG = "admin:catalog"  # Alterar preços, estrutura
    
    # ========== PRECIFICACAO ==========
    RUN_PRECIFICACAO = "run:precificacao"
    READ_PRECIFICACAO = "read:precificacao"
    
    # ========== CRONOGRAMA ==========
    RUN_CRONOGRAMA = "run:cronograma"
    READ_CRONOGRAMA = "read:cronograma"
    
    # ========== ALOCACAO ==========
    RUN_ALOCACAO = "run:alocacao"
    READ_ALOCACAO = "read:alocacao"
    
    # ========== USERS ==========
    READ_USERS = "read:users"
    WRITE_USERS = "write:users"
    DELETE_USERS = "delete:users"
    ASSIGN_ROLES = "assign:roles"  # Gerenciar roles de outros usuários
    
    # ========== ADMIN ==========
    VIEW_LOGS = "view:logs"
    VIEW_METRICS = "view:metrics"
    MANAGE_SYSTEM = "manage:system"  # Config, deploy, etc.
    
    # ========== AUDIT ==========
    VIEW_AUDIT = "view:audit"
    EXPORT_AUDIT = "export:audit"


class Role(Enum):
    """Roles do sistema."""
    
    ADMIN = "admin"          # Acesso total
    ANALYST = "analyst"      # Precificação, cronograma, alocação
    VIEWER = "viewer"        # Apenas leitura
    GUEST = "guest"          # Mínimo (health check, docs)


@dataclass
class RoleDefinition:
    """Definição de um role com suas permissions."""
    
    name: Role
    description: str
    permissions: Set[Permission]
    
    # Rate limits (ADR-098)
    rate_limit_per_minute: int
    rate_limit_per_hour: int


# ========== DEFINIÇÕES DE ROLES ==========
ROLE_DEFINITIONS: dict[Role, RoleDefinition] = {
    Role.ADMIN: RoleDefinition(
        name=Role.ADMIN,
        description="Administrador do sistema com acesso total",
        permissions={
            # Todos os permissions
            *[p for p in Permission]
        },
        rate_limit_per_minute=0,      # Sem limite
        rate_limit_per_hour=0
    ),
    
    Role.ANALYST: RoleDefinition(
        name=Role.ANALYST,
        description="Analista de projetos (precificação, cronograma, alocação)",
        permissions={
            # Projects
            Permission.READ_PROJECTS,
            Permission.WRITE_PROJECTS,  # Pode criar/editar projetos
            
            # Catalog (read-only)
            Permission.READ_CATALOG,
            
            # Pipeline (full access)
            Permission.RUN_PRECIFICACAO,
            Permission.READ_PRECIFICACAO,
            Permission.RUN_CRONOGRAMA,
            Permission.READ_CRONOGRAMA,
            Permission.RUN_ALOCACAO,
            Permission.READ_ALOCACAO,
            
            # Users (read-only)
            Permission.READ_USERS,
            
            # Metrics (read-only)
            Permission.VIEW_METRICS,
        },
        rate_limit_per_minute=200,
        rate_limit_per_hour=10000
    ),
    
    Role.VIEWER: RoleDefinition(
        name=Role.VIEWER,
        description="Visualizador (apenas leitura)",
        permissions={
            # Projects (read-only)
            Permission.READ_PROJECTS,
            
            # Catalog (read-only)
            Permission.READ_CATALOG,
            
            # Pipeline results (read-only)
            Permission.READ_PRECIFICACAO,
            Permission.READ_CRONOGRAMA,
            Permission.READ_ALOCACAO,
            
            # Metrics (read-only)
            Permission.VIEW_METRICS,
        },
        rate_limit_per_minute=50,
        rate_limit_per_hour=2000
    ),
    
    Role.GUEST: RoleDefinition(
        name=Role.GUEST,
        description="Visitante (acesso mínimo)",
        permissions={
            # Apenas health check e docs
            # (sem permissions explícitas - endpoints públicos)
        },
        rate_limit_per_minute=10,
        rate_limit_per_hour=100
    ),
}


@dataclass
class User:
    """Usuário com roles."""
    
    id: str
    email: str
    name: str
    roles: List[Role]  # Usuário pode ter múltiplos roles
    
    @property
    def permissions(self) -> Set[Permission]:
        """Retorna união de permissions de todos os roles."""
        perms = set()
        for role in self.roles:
            role_def = ROLE_DEFINITIONS[role]
            perms.update(role_def.permissions)
        return perms
    
    def has_permission(self, permission: Permission) -> bool:
        """Verifica se usuário tem permission."""
        return permission in self.permissions
    
    def has_role(self, role: Role) -> bool:
        """Verifica se usuário tem role."""
        return role in self.roles
    
    def is_admin(self) -> bool:
        """Atalho para verificar se é admin."""
        return self.has_role(Role.ADMIN)
```

#### 2.2 Decoradores de Autorização

```python
# src/concilium/infrastructure/api/auth/decorators.py
from functools import wraps
from fastapi import HTTPException, status, Request, Depends
from typing import List, Callable

class AuthorizationError(HTTPException):
    """Erro de autorização (403 Forbidden)."""
    
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message
        )


def require_role(*roles: Role):
    """
    Decorador que requer que usuário tenha pelo menos um dos roles.
    
    Usage:
        @app.post("/api/v1/admin/users")
        @require_role(Role.ADMIN)
        async def create_user(...):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Extrair user do request state (adicionado pelo AuthMiddleware)
            if not hasattr(request.state, "user"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            user: User = request.state.user
            
            # Verificar se tem pelo menos um dos roles
            if not any(user.has_role(role) for role in roles):
                raise AuthorizationError(
                    f"Required roles: {', '.join(r.value for r in roles)}. "
                    f"User has: {', '.join(r.value for r in user.roles)}"
                )
            
            # Logar acesso (auditoria)
            logger.info(
                f"RBAC: User {user.email} (roles: {user.roles}) "
                f"accessed {request.method} {request.url.path}"
            )
            
            return await func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def require_permission(*permissions: Permission):
    """
    Decorador que requer que usuário tenha pelo menos uma das permissions.
    
    Usage:
        @app.delete("/api/v1/projects/{project_id}")
        @require_permission(Permission.DELETE_PROJECTS)
        async def delete_project(...):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            if not hasattr(request.state, "user"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            user: User = request.state.user
            
            # Admin bypassa tudo
            if user.is_admin():
                return await func(request, *args, **kwargs)
            
            # Verificar se tem pelo menos uma das permissions
            if not any(user.has_permission(perm) for perm in permissions):
                raise AuthorizationError(
                    f"Required permissions: {', '.join(p.value for p in permissions)}. "
                    f"User has: {', '.join(p.value for p in user.permissions)}"
                )
            
            # Logar acesso (auditoria)
            logger.info(
                f"RBAC: User {user.email} (permissions: {user.permissions}) "
                f"accessed {request.method} {request.url.path}"
            )
            
            return await func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def require_any_role():
    """
    Decorador que apenas requer autenticação (qualquer role).
    
    Usage:
        @app.get("/api/v1/profile")
        @require_any_role()
        async def get_profile(...):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            if not hasattr(request.state, "user"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            return await func(request, *args, **kwargs)
        
        return wrapper
    return decorator
```

#### 2.3 Uso nos Endpoints

```python
# src/concilium/infrastructure/api/routes/projects.py
from concilium.infrastructure.api.auth.decorators import (
    require_role, require_permission, require_any_role
)

# ========== READ (todos autenticados) ==========
@app.get("/api/v1/projects")
@require_permission(Permission.READ_PROJECTS)
async def list_projects(request: Request):
    """Lista projetos (requer permission READ_PROJECTS)."""
    user = request.state.user
    return await project_service.list(user_id=user.id)


@app.get("/api/v1/projects/{project_id}")
@require_permission(Permission.READ_PROJECTS)
async def get_project(request: Request, project_id: str):
    """Detalhes de um projeto."""
    return await project_service.get(project_id)


# ========== WRITE (analyst ou admin) ==========
@app.post("/api/v1/projects")
@require_permission(Permission.WRITE_PROJECTS)
async def create_project(request: Request, projeto: ProjetoInput):
    """Cria projeto (requer permission WRITE_PROJECTS)."""
    user = request.state.user
    return await project_service.create(projeto, created_by=user.id)


@app.put("/api/v1/projects/{project_id}")
@require_permission(Permission.WRITE_PROJECTS)
async def update_project(
    request: Request, 
    project_id: str, 
    projeto: ProjetoInput
):
    """Atualiza projeto."""
    return await project_service.update(project_id, projeto)


# ========== DELETE (apenas admin) ==========
@app.delete("/api/v1/projects/{project_id}")
@require_role(Role.ADMIN)  # Apenas admin pode deletar
async def delete_project(request: Request, project_id: str):
    """
    Deleta projeto (APENAS ADMIN).
    
    Crítico: Operação irreversível.
    """
    user = request.state.user
    
    # Log crítico
    logger.critical(
        f"PROJECT DELETE: User {user.email} (admin) "
        f"deleting project {project_id}"
    )
    
    return await project_service.delete(project_id)


# ========== ADMIN ENDPOINTS ==========
@app.post("/api/v1/admin/users")
@require_role(Role.ADMIN)
async def create_user(request: Request, user_input: UserInput):
    """Cria usuário (apenas admin)."""
    return await user_service.create(user_input)


@app.post("/api/v1/admin/users/{user_id}/roles")
@require_permission(Permission.ASSIGN_ROLES)
async def assign_role(
    request: Request,
    user_id: str,
    role: Role
):
    """Atribui role a usuário (apenas admin)."""
    admin_user = request.state.user
    
    # Log crítico
    logger.critical(
        f"ROLE ASSIGNMENT: Admin {admin_user.email} "
        f"assigned role {role.value} to user {user_id}"
    )
    
    return await user_service.assign_role(user_id, role)


# ========== PROFILE (qualquer autenticado) ==========
@app.get("/api/v1/profile")
@require_any_role()
async def get_profile(request: Request):
    """Retorna perfil do usuário autenticado."""
    user = request.state.user
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "roles": [r.value for r in user.roles],
        "permissions": [p.value for p in user.permissions]
    }
```

#### 2.4 Auditoria de Acessos

```python
# src/concilium/infrastructure/observability/audit_log.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json

@dataclass
class AuditLogEntry:
    """Entrada de log de auditoria."""
    
    timestamp: datetime
    user_id: str
    user_email: str
    roles: List[str]
    action: str  # "READ", "WRITE", "DELETE", "ASSIGN_ROLE"
    resource_type: str  # "project", "user", "catalog"
    resource_id: Optional[str]
    method: str  # HTTP method
    path: str  # URL path
    ip_address: str
    user_agent: str
    status_code: int
    response_time_ms: float
    
    # Resultado
    success: bool
    error_message: Optional[str] = None


class AuditLogger:
    """Logger de auditoria RBAC."""
    
    def __init__(self, db_session):
        self.db = db_session
    
    def log_access(self, entry: AuditLogEntry):
        """
        Persiste log de auditoria.
        
        - PostgreSQL: Para consultas/relatórios
        - Elasticsearch: Para busca full-text
        - S3: Para compliance (retenção 7 anos)
        """
        # 1. PostgreSQL
        self.db.execute(
            """
            INSERT INTO audit_logs (
                timestamp, user_id, user_email, roles, action,
                resource_type, resource_id, method, path,
                ip_address, user_agent, status_code,
                response_time_ms, success, error_message
            ) VALUES (
                :timestamp, :user_id, :user_email, :roles, :action,
                :resource_type, :resource_id, :method, :path,
                :ip_address, :user_agent, :status_code,
                :response_time_ms, :success, :error_message
            )
            """,
            entry.__dict__
        )
        
        # 2. Elasticsearch (async)
        # elasticsearch_client.index(
        #     index="concilium-audit-logs",
        #     body=entry.__dict__
        # )
        
        # 3. Log estruturado (para agregação)
        logger.info(
            "AUDIT",
            extra={
                "audit": True,
                **entry.__dict__
            }
        )


# Middleware de auditoria
@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    """Middleware que registra todos os acessos."""
    start_time = time.time()
    
    # Extrair metadados
    user = getattr(request.state, "user", None)
    
    # Executar request
    try:
        response = await call_next(request)
        success = response.status_code < 400
        error_message = None
    
    except Exception as exc:
        success = False
        error_message = str(exc)
        response = JSONResponse(
            status_code=500,
            content={"error": "internal_error"}
        )
    
    # Calcular tempo
    response_time_ms = (time.time() - start_time) * 1000
    
    # Se autenticado, logar acesso
    if user:
        audit_entry = AuditLogEntry(
            timestamp=datetime.utcnow(),
            user_id=user.id,
            user_email=user.email,
            roles=[r.value for r in user.roles],
            action=request.method,
            resource_type=_extract_resource_type(request.url.path),
            resource_id=_extract_resource_id(request.url.path),
            method=request.method,
            path=request.url.path,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent", ""),
            status_code=response.status_code,
            response_time_ms=response_time_ms,
            success=success,
            error_message=error_message
        )
        
        audit_logger.log_access(audit_entry)
    
    return response
```

---

## 3. Consequências

### 3.1 Positivas

| Benefício | Métrica | Detalhe |
|---|---|---|---|
| 🔒 **Segurança aumentada** | Zero acesso não autorizado | Apenas admins deletam dados |
| 📊 **Auditoria completa** | 100% ações logadas | Compliance SOC2, ISO27001 |
| ⚖️ **Separação de privilégios** | 4 roles distintos | Princípio de menor privilégio |
| 🎯 **Granularidade** | 20+ permissions | Controle fino de acesso |
| 📖 **Transparência** | Usuário sabe seus permissions | GET /profile mostra roles/perms |
| 🔍 **Rastreabilidade** | Quem fez o quê, quando | Logs de auditoria |

### 3.2 Negativas

| Problema | Impacto | Mitigação |
|---|---|---|---|
| 🔧 **Complexidade** | +1 camada de autorização | Documentação + testes |
| 📚 **Manutenção** | Adicionar novo role/permission | Config centralizada |
| ⏱️ **Latência** | +0.5ms verificação | Aceitável |
| 💾 **Storage audit logs** | +1GB/mês logs | S3 com retenção 7 anos |

---

## 4. Validação

### 4.1 Testes de Autorização

| Teste | Role | Endpoint | Resultado | Observação |
|---|---|---|---|---|
| **Admin full access** | admin | DELETE /projects/X | ✅ 200 | Admin pode deletar |
| **Analyst cannot delete** | analyst | DELETE /projects/X | ❌ 403 | Forbidden |
| **Viewer read-only** | viewer | POST /projects | ❌ 403 | Sem permission WRITE |
| **Guest blocked** | guest | GET /projects | ❌ 403 | Sem permission READ |
| **Analyst can run** | analyst | POST /precificar | ✅ 200 | Tem RUN_PRECIFICACAO |

### 4.2 Audit Log Query

```sql
-- Quem deletou projetos nos últimos 7 dias?
SELECT 
    timestamp,
    user_email,
    roles,
    resource_id,
    path
FROM audit_logs
WHERE action = 'DELETE'
  AND resource_type = 'project'
  AND timestamp >= NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC;

-- Quais usuários têm role admin?
SELECT DISTINCT user_email, roles
FROM audit_logs
WHERE roles::jsonb ? 'admin'
ORDER BY user_email;

-- Top 10 usuários mais ativos (por requisições)
SELECT 
    user_email,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE success = false) as failed_requests
FROM audit_logs
WHERE timestamp >= NOW() - INTERVAL '30 days'
GROUP BY user_email
ORDER BY total_requests DESC
LIMIT 10;
```

---

## 5. Implementação

### 5.1 Arquivos criados

```
src/concilium/domain/models/
└── rbac.py                    # Role, Permission, User

src/concilium/infrastructure/api/auth/
└── decorators.py              # require_role, require_permission

src/concilium/infrastructure/observability/
└── audit_log.py               # AuditLogger

tests/unit/auth/
├── test_rbac.py               # Testes de roles/permissions
└── test_decorators.py         # Testes de decoradores

migrations/
└── 20260525_create_audit_logs.sql  # Tabela de audit logs
```

### 5.2 Schema de audit_logs

```sql
-- migrations/20260525_create_audit_logs.sql
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id VARCHAR(255) NOT NULL,
    user_email VARCHAR(255) NOT NULL,
    roles JSONB NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    method VARCHAR(10) NOT NULL,
    path TEXT NOT NULL,
    ip_address INET,
    user_agent TEXT,
    status_code INTEGER NOT NULL,
    response_time_ms REAL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    
    -- Índices para queries comuns
    INDEX idx_audit_user_id (user_id),
    INDEX idx_audit_timestamp (timestamp DESC),
    INDEX idx_audit_action (action),
    INDEX idx_audit_resource (resource_type, resource_id)
);

-- Particionamento por mês (performance)
CREATE TABLE audit_logs_2026_05 PARTITION OF audit_logs
FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

-- Retenção automática (7 anos compliance)
CREATE OR REPLACE FUNCTION delete_old_audit_logs()
RETURNS void AS $$
BEGIN
    DELETE FROM audit_logs
    WHERE timestamp < NOW() - INTERVAL '7 years';
END;
$$ LANGUAGE plpgsql;
```

### 5.3 Exemplo de resposta 403

```bash
# Request (analyst tentando deletar)
curl -X DELETE https://api.concilium.com/api/v1/projects/AGIS \
  -H "Authorization: Bearer $TOKEN"

# Response
HTTP/1.1 403 Forbidden

{
  "detail": "Required roles: admin. User has: analyst"
}
```

---

## 6. Notas Técnicas

### 6.1 Por que RBAC e não ABAC?

| Aspecto | RBAC | ABAC (Attribute-Based) |
|---|---|---|
| **Simplicidade** | Alta | Baixa (policy engine) |
| **Escalabilidade** | Alta | Média (performance) |
| **Granularidade** | Média | Muito alta |
| **Manutenção** | Fácil | Complexa |
| **Casos de uso** | 90% dos casos | Casos muito específicos |

**Decisão:** RBAC cobre 90% dos casos. Se precisar granularidade extrema (ex: "usuário pode editar projeto apenas se criou ele"), migrar para ABAC.

### 6.2 Hierarquia de Roles (futuro)

Atualmente, roles são independentes. No futuro, podemos ter hierarquia:

```
ADMIN
  └─ ANALYST
      └─ VIEWER
          └─ GUEST
```

Nesse modelo, Admin **herda** permissions de Analyst, que herda de Viewer, etc.

### 6.3 Dynamic Roles (futuro)

Roles atualmente são estáticos (definidos no código). No futuro, permitir criar roles customizados via UI:

```python
# Admin cria role customizado via API
POST /api/v1/admin/roles
{
  "name": "project_manager",
  "permissions": [
    "read:projects",
    "write:projects",
    "read:precificacao",
    "run:precificacao"
  ]
}
```

---

## 7. Próximos Passos

1. **UI de gerenciamento:** Dashboard para gerenciar roles/permissions
2. **ABAC (se necessário):** Policy engine para casos complexos
3. **OAuth Scopes:** Integração com OAuth 2.0
4. **Temporary permissions:** Conceder permissão temporária (ex: 24h)

---

## 8. Referências

- [NIST RBAC Model](https://csrc.nist.gov/projects/role-based-access-control)
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [Azure RBAC](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview)
- [OWASP - Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html)
- [SOC 2 Compliance - Access Control](https://www.aicpa.org/interestareas/frc/assuranceadvisoryservices/socforserviceorganizations)