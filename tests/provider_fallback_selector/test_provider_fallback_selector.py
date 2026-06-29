from enum import Enum

from quantpilot_core.provider_fallback_selector import (
    ProviderAvailability,
    ProviderCandidateName,
    ProviderCandidateStatus,
    ProviderFallbackPreference,
    ProviderFallbackSelectionRequest,
    build_candidate_statuses,
    build_default_fallback_order,
    select_provider_candidate,
)


def status(name, availability, reason=""):
    return ProviderCandidateStatus(name=name, availability=availability, reason=reason)


def request(candidates, preference=ProviderFallbackPreference.AKSHARE_FIRST):
    return ProviderFallbackSelectionRequest(
        candidates=tuple(candidates),
        preference=preference,
    )


def test_akshare_first_order() -> None:
    assert build_default_fallback_order(ProviderFallbackPreference.AKSHARE_FIRST) == (
        ProviderCandidateName.AKSHARE,
        ProviderCandidateName.BAOSTOCK,
    )


def test_baostock_first_order() -> None:
    assert build_default_fallback_order(ProviderFallbackPreference.BAOSTOCK_FIRST) == (
        ProviderCandidateName.BAOSTOCK,
        ProviderCandidateName.AKSHARE,
    )


def test_selects_akshare_when_both_available_and_akshare_first() -> None:
    result = select_provider_candidate(
        request(
            [
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.AVAILABLE),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.AVAILABLE),
            ]
        )
    )

    assert result.selected_provider is ProviderCandidateName.AKSHARE
    assert result.can_attempt_fetch is True


def test_selects_baostock_when_both_available_and_baostock_first() -> None:
    result = select_provider_candidate(
        request(
            [
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.AVAILABLE),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.AVAILABLE),
            ],
            preference=ProviderFallbackPreference.BAOSTOCK_FIRST,
        )
    )

    assert result.selected_provider is ProviderCandidateName.BAOSTOCK


def test_falls_back_to_baostock_when_akshare_missing() -> None:
    result = select_provider_candidate(
        request(
            [
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.MISSING),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.AVAILABLE),
            ]
        )
    )

    assert result.selected_provider is ProviderCandidateName.BAOSTOCK
    assert "akshare missing" in result.warnings


def test_falls_back_to_akshare_when_baostock_missing() -> None:
    result = select_provider_candidate(
        request(
            [
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.AVAILABLE),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.MISSING),
            ],
            preference=ProviderFallbackPreference.BAOSTOCK_FIRST,
        )
    )

    assert result.selected_provider is ProviderCandidateName.AKSHARE
    assert "baostock missing" in result.warnings


def test_no_provider_selected_when_both_missing() -> None:
    result = select_provider_candidate(
        request(
            [
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.MISSING),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.MISSING),
            ]
        )
    )

    assert result.selected_provider is None
    assert result.can_attempt_fetch is False
    assert result.reasons == ("no_available_provider",)


def test_disabled_provider_is_not_selected() -> None:
    result = select_provider_candidate(
        request(
            [
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.DISABLED),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.AVAILABLE),
            ]
        )
    )

    assert result.selected_provider is ProviderCandidateName.BAOSTOCK
    assert "akshare disabled" in result.warnings


def test_unhealthy_provider_is_not_selected() -> None:
    result = select_provider_candidate(
        request(
            [
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.UNHEALTHY),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.AVAILABLE),
            ]
        )
    )

    assert result.selected_provider is ProviderCandidateName.BAOSTOCK
    assert "akshare unhealthy" in result.warnings


def test_absent_candidate_is_treated_as_missing() -> None:
    result = select_provider_candidate(
        request([status(ProviderCandidateName.AKSHARE, ProviderAvailability.AVAILABLE)])
    )

    assert result.selected_provider is ProviderCandidateName.AKSHARE
    assert "baostock missing: not reported" in result.warnings


def test_duplicate_candidate_status_last_wins() -> None:
    result = select_provider_candidate(
        request(
            [
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.MISSING),
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.AVAILABLE),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.MISSING),
            ]
        )
    )

    assert result.selected_provider is ProviderCandidateName.AKSHARE


def test_warnings_include_skipped_provider_issues() -> None:
    result = select_provider_candidate(
        request(
            [
                status(
                    ProviderCandidateName.AKSHARE,
                    ProviderAvailability.MISSING,
                    "optional package missing",
                ),
                status(
                    ProviderCandidateName.BAOSTOCK,
                    ProviderAvailability.UNHEALTHY,
                    "preflight failed",
                ),
            ]
        )
    )

    assert "akshare missing: optional package missing" in result.warnings
    assert "baostock unhealthy: preflight failed" in result.warnings


def test_suggested_next_action_for_selected_case() -> None:
    result = select_provider_candidate(
        request([status(ProviderCandidateName.AKSHARE, ProviderAvailability.AVAILABLE)])
    )

    assert "small sample fetch" in result.suggested_next_action
    assert "small_sample_data_gate" in result.suggested_next_action


def test_suggested_next_action_for_no_selected_case() -> None:
    result = select_provider_candidate(request(()))

    assert "Install or enable" in result.suggested_next_action
    assert "fake/offline fixture" in result.suggested_next_action


class FakeDependencyStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"


def test_build_candidate_statuses_maps_dependency_statuses() -> None:
    statuses = build_candidate_statuses(
        FakeDependencyStatus.AVAILABLE,
        FakeDependencyStatus.MISSING,
    )

    assert statuses == (
        ProviderCandidateStatus(
            ProviderCandidateName.AKSHARE,
            ProviderAvailability.AVAILABLE,
        ),
        ProviderCandidateStatus(
            ProviderCandidateName.BAOSTOCK,
            ProviderAvailability.MISSING,
        ),
    )


def test_no_network_or_real_provider_dependency_is_needed() -> None:
    result = select_provider_candidate(
        request([status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.AVAILABLE)])
    )

    assert result.selected_provider is ProviderCandidateName.BAOSTOCK
