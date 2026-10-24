"""Independent fail-closed policy fixtures; no network calls or production imports."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/formalism_main_protection.py"
spec = importlib.util.spec_from_file_location("formalism_main_protection", SCRIPT)
assert spec and spec.loader
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def configured_protection() -> dict:
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": list(policy.REQUIRED_CHECKS),
            "checks": [],
        },
        "enforce_admins": {"enabled": True},
        "required_pull_request_reviews": {"required_approving_review_count": 0},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "required_linear_history": {"enabled": True},
    }


def branch(sha: str = "a" * 40, *, protected: bool = True) -> dict:
    return {"name": "main", "commit": {"sha": sha}, "protected": protected}


def baseline_checks() -> dict:
    return {
        "check_runs": [
            {"name": name, "conclusion": "success", "status": "completed"}
            for name in policy.REQUIRED_CHECKS
        ]
    }


def test_policy_requires_no_admin_bypass_and_enumerates_ten_unique_jobs() -> None:
    payload = policy.protection_payload()
    assert len(policy.REQUIRED_CHECKS) == len(set(policy.REQUIRED_CHECKS)) == 10
    assert payload["enforce_admins"] is True
    assert payload["required_status_checks"]["strict"] is True
    assert payload["required_status_checks"]["contexts"] == list(policy.REQUIRED_CHECKS)
    assert payload["required_pull_request_reviews"]["required_approving_review_count"] == 0
    assert payload["required_linear_history"] is True
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False
    assert payload["restrictions"] is None


def test_actual_verification_rejects_missing_checks_or_unprotected_main() -> None:
    with pytest.raises(policy.ProtectionError, match="not protected"):
        policy.verify_policy(branch(protected=False), configured_protection())
    insufficient = configured_protection()
    insufficient["required_status_checks"]["contexts"].remove(
        "Economic Contract Evidence (required)"
    )
    with pytest.raises(policy.ProtectionError, match="Effective required checks absent"):
        policy.verify_policy(branch(), insufficient)


def test_effective_protection_must_apply_to_admins_and_pull_requests() -> None:
    for field, replacement in (
        ("enforce_admins", {"enabled": False}),
        ("required_pull_request_reviews", None),
        ("allow_force_pushes", {"enabled": True}),
        ("allow_deletions", {"enabled": True}),
        ("required_linear_history", {"enabled": False}),
    ):
        response = configured_protection()
        response[field] = replacement
        with pytest.raises(policy.ProtectionError):
            policy.verify_policy(branch(), response)


def test_explicit_pr_bypass_allowances_are_rejected() -> None:
    for field in ("users", "teams", "apps"):
        effective = configured_protection()
        effective["required_pull_request_reviews"]["bypass_pull_request_allowances"] = {
            "users": [],
            "teams": [],
            "apps": [],
        }
        effective["required_pull_request_reviews"]["bypass_pull_request_allowances"][field] = [
            {"login": "exempt"}
        ]
        with pytest.raises(policy.ProtectionError, match="pull-request bypass"):
            policy.verify_policy(branch(), effective)


def test_green_main_checks_required_before_any_admin_mutation() -> None:
    policy.verify_checks(baseline_checks())
    bad = baseline_checks()
    bad["check_runs"] = [x for x in bad["check_runs"] if x["name"] != "Tests"]
    with pytest.raises(policy.ProtectionError, match="Tests"):
        policy.verify_checks(bad)


def test_only_proxy_may_be_conditionally_skipped_when_detector_passes() -> None:
    skipped_proxy = baseline_checks()
    proxy = next(x for x in skipped_proxy["check_runs"]
                 if x["name"] == "MCP Proxy (standalone)")
    proxy["conclusion"] = "skipped"
    policy.verify_checks(skipped_proxy)

    required_economics = baseline_checks()
    economics = next(x for x in required_economics["check_runs"]
                     if x["name"] == "Economic Contract Evidence (required)")
    economics["conclusion"] = "skipped"
    with pytest.raises(policy.ProtectionError, match="Economic Contract"):
        policy.verify_checks(required_economics)

    missing_detector = baseline_checks()
    detector = next(x for x in missing_detector["check_runs"]
                    if x["name"] == "Detect changes")
    detector["conclusion"] = "skipped"
    with pytest.raises(policy.ProtectionError, match="proxy detector"):
        policy.verify_checks(missing_detector)


def test_wrong_confirmation_never_contacts_github(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("no network calls permitted before confirmation")
    monkeypatch.setattr(policy, "gh_api", forbidden)
    with pytest.raises(policy.ProtectionError, match="confirm"):
        policy.apply("wrong")


def test_apply_requires_private_repo_and_rejects_a_moving_main(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    def fake_api(path, *, method="GET", payload=None):
        calls.append((method, path))
        if path.endswith("/protection"):
            raise AssertionError("never apply after main changed")
        if path == f"repos/{policy.REPO}":
            return {"full_name": policy.REPO, "private": True}
        if path.endswith("/check-runs?per_page=100"):
            return baseline_checks()
        if path.endswith("/branches/main"):
            number = sum(1 for _, name in calls if name.endswith("/branches/main"))
            return branch("a" * 40 if number == 1 else "b" * 40, protected=False)
        raise AssertionError(path)
    monkeypatch.setattr(policy, "gh_api", fake_api)
    with pytest.raises(policy.ProtectionError, match="main changed"):
        policy.apply(policy.CONFIRM)
    assert not any(method == "PUT" for method, _ in calls)


def test_audit_is_read_only_and_requires_actual_server_protection(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    def fake_api(path, *, method="GET", payload=None):
        calls.append((method, path))
        if path.endswith("/branches/main"):
            return branch(protected=False)
        raise AssertionError("must not treat an unprotected branch as protected")
    monkeypatch.setattr(policy, "gh_api", fake_api)
    with pytest.raises(policy.ProtectionError, match="remains unprotected"):
        policy.audit()
    assert all(method == "GET" for method, _ in calls)


def test_apply_preserves_an_existing_stricter_protection(monkeypatch) -> None:
    paths: list[tuple[str, str]] = []

    def fake_api(path, *, method="GET", payload=None):
        paths.append((method, path))
        if path == f"repos/{policy.REPO}":
            return {"full_name": policy.REPO, "private": True}
        if path.endswith("/branches/main"):
            return branch(protected=True)
        if path.endswith("/protection"):
            return configured_protection()
        raise AssertionError(path)

    monkeypatch.setattr(policy, "gh_api", fake_api)
    result = policy.apply(policy.CONFIRM)
    assert result["required_checks"] == len(policy.REQUIRED_CHECKS)
    assert all(method == "GET" for method, _ in paths)


def test_apply_success_requires_readback_from_github(monkeypatch) -> None:
    calls: list[str] = []
    expected = configured_protection()
    def fake_api(path, *, method="GET", payload=None):
        calls.append(f"{method} {path}")
        if path == f"repos/{policy.REPO}":
            return {"full_name": policy.REPO, "private": True}
        if path.endswith("/check-runs?per_page=100"):
            return baseline_checks()
        if path.endswith("/branches/main"):
            return branch(protected="PUT" in " ".join(calls))
        if method == "PUT" and path.endswith("/protection"):
            assert payload == policy.protection_payload()
            return {"required_status_checks": {"strict": True}}
        if path.endswith("/protection"):
            return expected
        raise AssertionError(path)
    monkeypatch.setattr(policy, "gh_api", fake_api)
    result = policy.apply(policy.CONFIRM)
    assert result == {"branch": "main", "sha": "a" * 40, "required_checks": 10}
    assert sum(x.startswith("PUT ") for x in calls) == 1
    assert calls[-1].endswith("/protection")


def test_cli_plan_does_not_contact_github(monkeypatch, capsys) -> None:
    monkeypatch.setattr(policy, "gh_api", lambda *args, **kwargs: pytest.fail("read-only plan called GitHub"))
    assert policy.main(["--plan"]) == 0
    assert "Economic Contract Evidence (required)" in capsys.readouterr().out
