# P25 CI baseline and verified repairs (2026-10-22)

## Cause and scope

The existing CI installed `fastmcp>=3.2.4` while application code and
tests imported `mcp.server.fastmcp.FastMCP`, an API available in the
native MCP Python SDK v1 but not v2. The dependency declaration made
installation resolution select an incompatible SDK and aborted collection.

P25-A (#27) declares `mcp>=1.16,<2`, plus the missing PyYAML dependency.
The latest fully executed run of #27 (head `260f590d`) completed:
**14,983 passed; 2 failed; 284 deselected; no collection errors**.
The two failures were stale test expectations about material costs:
the actual Skill 05 calculation is now nonzero for physical material
consumption. P25-B (#30) updates those assertions to independently
computed expected material expenses and retains the MAT category
within monthly cost reconciliation.

## Quality corrections (P25-B)

- Preserve decimal/physical material computations; never set a cost
  back to zero just to make an obsolete test pass.
- Resolve seven real source type diagnostics without disabling `ty`.
- Check stream `reconfigure` capabilities before manipulating MCP
  proxy encodings, failing closed for incompatible streams.
- Repair Ruff violations including duplicate dictionary keys in
  test fixtures. This must be validated by CI, not assumed correct.
- Keep reference-oracle golden fixtures in #29 independent of these
  production test assertions.

## Commands and merge gates

```bash
python -m pytest tests -q --tb=short -m "not slow and not flaky"
python -m ruff check src/concilium tests --ignore B008
ty check src
(cd tools/mcp-proxy && ty check proxy.py && python -m pytest tests -q)
```

The CI configuration runs for PRs with base `main`.
#30 therefore temporarily targets `main` for verifiable checks and
contains #27's commits in its ancestry. Integrate the complete stack only
when the required jobs pass; do not separately cherry-pick duplicate fixes
from #27 after #30 merges.
