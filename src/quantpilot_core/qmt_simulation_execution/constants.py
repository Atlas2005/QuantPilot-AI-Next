"""Versioned constants for the QMT broker-simulation order protocol."""

from __future__ import annotations

from pathlib import Path


SCHEMA_VERSION = 1
PROTOCOL_VERSION = "qmt_simulation_order_loop_v1"
ENVIRONMENT = "broker_simulation"
ACCOUNT_TYPE = "STOCK"
ORDER_KIND = "shares_limit"
STRATEGY_NAME = "quantpilot_sim_v1"

EXECUTION_RELATIVE_PATH = Path("execution")
INTENTS_RELATIVE_PATH = EXECUTION_RELATIVE_PATH / "intents"
ACKNOWLEDGEMENTS_RELATIVE_PATH = EXECUTION_RELATIVE_PATH / "acknowledgements"
STATE_RELATIVE_PATH = EXECUTION_RELATIVE_PATH / "state"
ACCOUNT_BINDING_KEY_RELATIVE_PATH = Path("state") / "account_binding_key_v1.hex"

MAX_INTENT_BYTES = 16 * 1024
MAX_RESULT_BYTES = 64 * 1024
MAX_STATE_BYTES = 16 * 1024
MAX_INTENT_ID_LENGTH = 64
MAX_RUN_LABEL_LENGTH = 128
MAX_FAILURE_CODE_LENGTH = 80
MAX_FAILURE_TYPE_LENGTH = 128
MAX_BROKER_REFERENCE_LENGTH = 128
MAX_STATUS_TEXT_LENGTH = 128
MAX_QUANTITY = 2_147_483_647
MAX_LIMIT_PRICE = 1_000_000_000.0
MAX_FUTURE_SKEW_SECONDS = 300.0
MAX_INTENT_LIFETIME_SECONDS = 86_400.0
MAX_DEAL_RECORDS = 10_000
MAX_ORDER_RECORDS = 10_000
MAX_REPORTING_FILLS = 10_000

INTENT_HMAC_DOMAIN = b"quantpilot:qmt-simulation-order-intent:v1\0"
ACCOUNT_BINDING_HMAC_DOMAIN = b"quantpilot:qmt-account-binding:v1\0"
ACCOUNT_BINDING_KEY_BYTES = 32

ACCEPTANCE_LIMITATION = (
    "qmt_live_trading_mode_with_broker_simulation_account_only"
)

INTENT_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "protocol_version",
        "intent_id",
        "created_at",
        "expires_at",
        "environment",
        "expected_redacted_account_id",
        "account_type",
        "symbol",
        "side",
        "quantity",
        "order_kind",
        "limit_price",
        "source_order_digest",
        "explicit_submit",
        "intent_hmac",
    }
)
INTENT_OPTIONAL_KEYS = frozenset({"run_label"})

STATE_KEYS = frozenset(
    {
        "schema_version",
        "protocol_version",
        "intent_id",
        "updated_at",
        "status",
        "expected_redacted_account_id",
        "passorder_attempted",
        "failure_code",
    }
)

RESULT_KEYS = frozenset(
    {
        "schema_version",
        "protocol_version",
        "intent_id",
        "generated_at",
        "status",
        "expected_redacted_account_id",
        "symbol",
        "side",
        "requested_quantity",
        "limit_price",
        "strategy_name",
        "user_order_id",
        "passorder_attempted",
        "broker_order_reference",
        "system_order_id",
        "order_status",
        "submission_status",
        "filled_quantity",
        "average_fill_price",
        "deal_count",
        "failure_code",
        "failure_type",
        "latest_snapshot_sequence",
        "acceptance_limitation",
    }
)

STATUSES = frozenset(
    {
        "received",
        "claimed",
        "submission_attempted",
        "broker_acknowledged",
        "partially_filled",
        "filled",
        "rejected",
        "expired",
        "uncertain",
    }
)

TERMINAL_STATUSES = frozenset({"filled", "rejected", "expired"})
REJECTED_ORDER_STATUS_CODES = frozenset({57, "57"})
REJECTED_ORDER_STATUS_TEXT = frozenset(
    {"rejected", "reject", "invalid", "waste", "废单"}
)
SAFE_BROKER_STATUS_TEXT = frozenset(
    {
        "observed",
        "pending",
        "accepted",
        "acknowledged",
        "partially_filled",
        "filled",
        "rejected",
        "cancelled",
        "unknown",
    }
)
