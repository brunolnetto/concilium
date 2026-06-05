from concilium.presentation.mcp_server._context import _runtime
from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

rt = _runtime()
cat = rt.load_catalogo('mendeslobo')
val = ValidadorCPUInsumo(RepositorioInsumo(cat))

erros = []
for c in cat.get('cpus', []):
    res = val.validar_cpu_completa(c)
    for r in res:
        if r.status != 'OK':
            erros.append((c.get('codigo'), r.codigo, r.mensagem))

# Também validar insumos diretamente
repo = RepositorioInsumo(cat)
for i in cat.get('insumos', []):
    # Unidade
    r_u = val.validar_unidade_normalizada(i)
    if r_u.status != 'OK':
        erros.append((i.get('codigo'), r_u.codigo, r_u.mensagem))
    # Categoria
    r_c = val.validar_categoria_permitida(i)
    if r_c.status != 'OK':
        erros.append((i.get('codigo'), r_c.codigo, r_c.mensagem))
    # Valores
    r_v = val.validar_valores_auditaveis(i)
    for rv in r_v:
        if rv.status != 'OK':
            erros.append((i.get('codigo'), rv.codigo, rv.mensagem))

for cod, code, msg in erros:
    print(f"[{code}] {cod}: {msg}")
