# P25 — enforce and audit main branch protection (owner runbook)

**Current state (2026-10-24):** private repository, main CI
[40105736439](https://github.com/brunolnetto/concilium/actions/runs/40105736439)
passed 10/10 checks, but the GitHub branch API reported protected=false.
Thus W1 issue #25 is 4/5, and W2 stays blocked. Committing this document
does not satisfy branch protection.

## Prerequisites

- Keep brunolnetto/concilium **private**. GitHub requires Pro (personal)
  or Team/Enterprise (organization) for protected branches in private repos.
  Do not change visibility to work around an account plan.
- The connected ChatGPT GitHub App cannot write repository Administration.
  Use the owner's GitHub CLI authentication with repository admin access
  on a machine where the repository is checked out. Never send tokens to chat.
- Run on current main after CI completes. The script refuses stale/missing
  CI contexts or racing main commits.
- The policy requires **pull requests and all checks**, but no mandatory
  second person's approval (required_approving_review_count=0), making it
  feasible for a solo maintainer.

## Apply and audit (only the owner can mutate GitHub settings)

    gh auth status
    git switch main
    git pull --ff-only
    python scripts/formalism_main_protection.py --plan
    python scripts/formalism_main_protection.py --apply \
      --confirm brunolnetto/concilium:main
    python scripts/formalism_main_protection.py

The final command performs a **read-only audit** (also the default).
It returns nonzero until the actual GitHub API confirms a protected main,
strict required checks, enforcement on admins, PR requirement,
no force pushes or deletions, and linear history. A successful PUT request
alone is not sufficient.

If GitHub returns 403/404, verify account plan and admin permissions.
**Do not close #25** on a 403, green workflow, or nonzero audit result.

## Required check contexts

The script requires these exact names from a successful main commit:

- Economic Contract Evidence (required)
- Formalism Reference (independent)
- Formalism Reference Py3.12
- Formalism Reference Py3.13
- Tests
- Lint
- Type Check
- Dependency Lock (Docker parity)
- MCP Proxy (standalone)
- Detect changes

GitHub Actions may report duplicate attempts. Names must be unique across
workflows to avoid ambiguous required statuses.

## Falsify mergeability after policy enforcement is enabled

The remaining acceptance criterion is behavioral, not only a REST read.
Use a disposable PR with **only a comment** in
src/concilium/application/scheduling/economic_regime_contracts.py,
without a normative specification or golden economic JSON change.

1. Create a fresh branch from main and submit the comment-only change.
   Never merge it. The evidence gate classifies economic file paths.
2. Confirm that Economic Contract Evidence (required) is red with the
   missing specification/golden error, rather than infrastructure error.
3. Confirm that **GitHub itself blocks merge** under branch protection.
   Capture the PR URL, failing check URL, and branch-protection audit.
4. Close the disposable PR and delete the remote/local probe branch.
   Verify no economics code was merged.
5. Link evidence to #25, mark the final acceptance checkbox, close #25,
   then and only then mark W1 accepted in epic #8 and release W2.

The intentional red PR proves the **server-side merge gate**; a script that
returns exit code 1 is not enough.

## Scope boundaries

- W1 protection does not prove project optimality. The P16 fixed-layer
  120-versus-92 counterexample remains issue #16.
- Azure OIDC remains BLOCKED on missing client/tenant identity (run 40096185790).
  A controlled authenticated deployment is required to claim deploy success.
- This bootstrap is a supporting tool, **not an additional mandatory P25
  DAG package**. The sole blocker remains the external administrative rule
  and a verified rejection of a noncompliant PR.
