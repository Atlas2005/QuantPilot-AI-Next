#!/usr/bin/env python3
"""Report readiness with bounded read-only service probes and no provider or broker calls."""
from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlparse
from urllib.request import urlopen

from quantpilot_core.runtime_node.config import RuntimeConfig
from quantpilot_core.runtime_node.doctor import DoctorCheck, SUCCESSFUL_REQUIRED_STATUSES, collect_runtime_diagnostics


def _replace(checks: list[DoctorCheck], replacement: DoctorCheck) -> None:
    for index, check in enumerate(checks):
        if check.name == replacement.name:
            checks[index] = replacement
            return
    checks.append(replacement)


def _postgres_reachability(config: RuntimeConfig, timeout_seconds: float) -> DoctorCheck:
    if not config.reporting_enabled:
        return DoctorCheck("postgresql", "DISABLED", "reporting is disabled")
    dsn = os.environ.get("QUANTPILOT_POSTGRES_DSN")
    if not config.services.postgres_configured or not dsn:
        return DoctorCheck("postgresql", "NOT_READY", "required DSN is not configured", True)
    try:
        import psycopg

        connection = psycopg.connect(dsn, connect_timeout=max(1, int(timeout_seconds)))
        connection.close()
    except Exception as exc:
        return DoctorCheck("postgresql", "NOT_READY", f"configured but not reachable ({type(exc).__name__})", True)
    return DoctorCheck("postgresql", "REACHABLE", "configured and accepting connections", True)


def _grafana_reachability(config: RuntimeConfig, timeout_seconds: float) -> DoctorCheck:
    if not config.grafana_enabled:
        return DoctorCheck("grafana", "DISABLED", "Grafana is disabled")
    url = os.environ.get("QUANTPILOT_GRAFANA_URL")
    if not config.services.grafana_configured or not url:
        return DoctorCheck("grafana", "NOT_READY", "required local URL is not configured", True)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return DoctorCheck("grafana", "NOT_READY", "readiness checks are restricted to localhost", True)
    try:
        with urlopen(f"{url.rstrip('/')}/api/health", timeout=timeout_seconds) as response:
            reachable = response.status == 200
    except Exception as exc:
        return DoctorCheck("grafana", "NOT_READY", f"configured but not reachable ({type(exc).__name__})", True)
    return DoctorCheck("grafana", "REACHABLE" if reachable else "NOT_READY", "configured and HTTP health check passed" if reachable else "HTTP health check did not return 200", True)


def diagnostics_payload(*, probe_services: bool = True, timeout_seconds: float = 3.0) -> dict[str, object]:
    config = RuntimeConfig.from_environment()
    checks = list(collect_runtime_diagnostics(config, probe_services=probe_services, timeout_seconds=timeout_seconds))
    if probe_services:
        _replace(checks, _postgres_reachability(config, timeout_seconds))
        _replace(checks, _grafana_reachability(config, timeout_seconds))
    tushare_configured = bool(os.environ.get("TUSHARE_TOKEN"))
    checks.append(DoctorCheck("tushare_token", "CONFIGURED" if tushare_configured else "NOT_READY", "configured" if tushare_configured else "required encrypted runtime secret is missing", True))
    deepseek_configured = bool(os.environ.get("DEEPSEEK_API_KEY"))
    checks.append(DoctorCheck("deepseek_api_key", "CONFIGURED" if deepseek_configured else "OPTIONAL_NOT_CONFIGURED", "configured; live calls remain disabled" if deepseek_configured else "optional; live calls remain disabled"))
    return {
        "ok": all(check.status in SUCCESSFUL_REQUIRED_STATUSES for check in checks if check.required),
        "checks": [check.as_dict() for check in checks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--strict", action="store_true", help="return nonzero when required runtime dependencies are unavailable")
    parser.add_argument("--skip-services", action="store_true", help="validate service configuration without Docker or network probes")
    args = parser.parse_args(argv)
    payload = diagnostics_payload(probe_services=not args.skip_services)
    if args.format == "json":
        print(json.dumps(payload, sort_keys=True))
    else:
        for check in payload["checks"]:
            print(f"{check['status']:<14} {check['name']}: {check['detail']}")
    return 0 if not args.strict or payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
