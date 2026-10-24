"""Explicit owner-run branch-protection bootstrap for W1 issue #25.

Read-only by default. Applying requires eligible GitHub private-repo plan
and a gh identity with Administration:write. Never accepts a credential or
prints tokens. It cannot substitute for a blocked-negative-PR merge probe.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

REPO = "brunolnetto/concilium"
BRANCH = "main"
CONFIRM = f"{REPO}:{BRANCH}"

# Exact names from successful, main-branch GitHub Actions check runs.
REQUIRED_CHECKS = (
    "Economic Contract Evidence (required)",
    "Formalism Reference (independent)",
    "Formalism Reference Py3.12",
    "Formalism Reference Py3.13",
    "Tests",
    "Lint",
    "Type Check",
    "Dependency Lock (Docker parity)",
    "MCP Proxy (standalone)",
    "Detect changes",
)


class ProtectionError(RuntimeError):
    """Fail-closed policy or GitHub authorization error."""


def protection_payload() -> dict[str, Any]:
    """Require PRs and all numerical gates, including for administrators.

    Zero mandatory approvals permits a solo maintainer to merge a reviewed
    PR without requiring the impossible (self-approval), while still requiring
    a PR and every status check. Do not permit force pushes or deletions.
    """
    if len(REQUIRED_CHECKS) != len(set(REQUIRED_CHECKS)):
        raise ProtectionError("Required check names must be unique.")
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": list(REQUIRED_CHECKS),
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "required_approving_review_count": 0,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "require_last_push_approval": False,
        },
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_conversation_resolution": True,
        "block_creations": False,
        "lock_branch": False,
        "allow_fork_syncing": False,
    }


def gh_api(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Use the owner's existing gh login; no tokens appear in command/logs."""
    command = [
        "gh", "api", "--method", method,
        "-H", "Accept: application/vnd.github+json",
        path,
    ]
    if payload is not None:
        command += ["--input", "-"]
    try:
        result = subprocess.run(
            command, input=json.dumps(payload) if payload is not None else None,
            text=True, capture_output=True, check=False,
        )
    except FileNotFoundError as exc:
        raise ProtectionError("Install GitHub CLI (gh) and authenticate as a repository admin.") from exc
    if result.returncode:
        # Do not relay arbitrary response bodies: they might contain secrets.
        # Return only the numeric status with a generic owner-action reminder.
        raise ProtectionError(
            f"GitHub API refused {method} {path} (exit={result.returncode}). "
            "Check gh auth, repo Administration:write, and eligible private-repo "
            "branch-protection plan; no configuration was certified."
        )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProtectionError("GitHub returned invalid JSON; no policy certified.") from exc
    if not isinstance(data, dict):
        raise ProtectionError("GitHub returned an unexpected response type.")
    return data


def verify_checks(check_runs: dict[str, Any]) -> None:
    """Never enable unknown/stale check contexts or accept red main baseline."""
    runs = check_runs.get("check_runs")
    if not isinstance(runs, list):
        raise ProtectionError("Missing main commit check-run collection.")
    success = {x.get("name") for x in runs if isinstance(x, dict)
               and x.get("status") == "completed" and x.get("conclusion") == "success"}
    missing = set(REQUIRED_CHECKS) - success
    if missing:
        raise ProtectionError(
            f"Main baseline lacks successful required checks: {sorted(missing)}"
        )


def verify_policy(branch: dict[str, Any], protection: dict[str, Any]) -> None:
    """Verify effective server-side rule, not simply a successful PUT request."""
    if branch.get("protected") is not True:
        raise ProtectionError("main is not protected on GitHub.")
    checks = protection.get("required_status_checks")
    if not isinstance(checks, dict) or checks.get("strict") is not True:
        raise ProtectionError("Strict required status checks are missing.")
    configured = set(checks.get("contexts") or ())
    configured.update(
        x.get("context") for x in checks.get("checks", []) if isinstance(x, dict)
    )
    missing = set(REQUIRED_CHECKS) - configured
    if missing:
        raise ProtectionError(f"Effective required checks absent: {sorted(missing)}")
    if protection.get("enforce_admins", {}).get("enabled") is not True:
        raise ProtectionError("Administrators can bypass required checks.")
    if not isinstance(protection.get("required_pull_request_reviews"), dict):
        raise ProtectionError("Merges do not require pull requests.")
    for name in ("allow_force_pushes", "allow_deletions"):
        item = protection.get(name)
        if not isinstance(item, dict) or item.get("enabled") is not False:
            raise ProtectionError(f"Unsafe branch setting {name}.")
    linear = protection.get("required_linear_history")
    if not isinstance(linear, dict) or linear.get("enabled") is not True:
        raise ProtectionError("Linear history protection is missing.")


def audit() -> dict[str, str | int]:
    """Read-only verification. A 403 is NOT interpreted as protection enabled."""
    branch = gh_api(f"repos/{REPO}/branches/{BRANCH}")
    if branch.get("name") != BRANCH:
        raise ProtectionError("Branch lookup returned unexpected branch.")
    sha = (branch.get("commit") or {}).get("sha")
    if not isinstance(sha, str) or len(sha) != 40:
        raise ProtectionError("Cannot resolve a complete main commit SHA.")
    if branch.get("protected") is not True:
        raise ProtectionError("main remains unprotected.")
    policy = gh_api(f"repos/{REPO}/branches/{BRANCH}/protection")
    verify_policy(branch, policy)
    return {"branch": BRANCH, "sha": sha, "required_checks": len(REQUIRED_CHECKS)}


def apply(confirmation: str) -> dict[str, str | int]:
    """Opt-in mutation; refuse incorrect target, stale CI or unsupported plan."""
    if confirmation != CONFIRM:
        raise ProtectionError(f"Explicit --confirm {CONFIRM} is required.")
    repository = gh_api(f"repos/{REPO}")
    if repository.get("full_name", "").lower() != REPO.lower():
        raise ProtectionError("Repository identity mismatch.")
    if repository.get("private") is not True:
        raise ProtectionError("Unexpected repository visibility; refusing policy mutation.")
    branch = gh_api(f"repos/{REPO}/branches/{BRANCH}")
    sha = (branch.get("commit") or {}).get("sha")
    if not isinstance(sha, str) or len(sha) != 40:
        raise ProtectionError("Could not verify current main SHA.")
    verify_checks(gh_api(f"repos/{REPO}/commits/{sha}/check-runs?per_page=100"))
    # Avoid configuring against a moving baseline while CI is being pushed.
    latest = gh_api(f"repos/{REPO}/branches/{BRANCH}")
    if (latest.get("commit") or {}).get("sha") != sha:
        raise ProtectionError("main changed during preflight; retry with current CI.")
    gh_api(
        f"repos/{REPO}/branches/{BRANCH}/protection",
        method="PUT",
        payload=protection_payload(),
    )
    return audit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="Print intended policy; no GitHub writes")
    mode.add_argument("--apply", action="store_true", help="Configure via owner's admin gh auth")
    parser.add_argument("--confirm", default="", help=f"Required for --apply: {CONFIRM}")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(protection_payload(), indent=2))
        return 0
    try:
        outcome = apply(args.confirm) if args.apply else audit()
    except ProtectionError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "protected_verified", **outcome}, indent=2))
    print("NEXT: prove a noncompliant economic PR is rejected before closing #25.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
