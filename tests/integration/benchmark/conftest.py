"""Fixtures para testes de integração de benchmark.

NOTA: As fixtures de benchmark foram consolidadas em ../conftest.py para
evitar duplicação de execução entre testes em diferentes diretórios.

Fixtures disponíveis (definidas em ../conftest.py):
- golden_artifacts: Executa GOLDEN com ambos intents (RFI + RFP), ~55-65s
- golden_benchmark: Retorna canonical model de GOLDEN, ~15s
- agis_benchmark: Retorna canonical model de AGIS, ~60-100s
"""

# All fixtures have been moved to ../conftest.py for consolidation
