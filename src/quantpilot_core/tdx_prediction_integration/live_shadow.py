"""Live-shadow adapter that feeds PR130 completed bars to the shared engine."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from quantpilot_core.real_data_provider import (
    Level1MarketDataSink,
    NormalizedIntradayBar,
    NormalizedLevel1Event,
)
from quantpilot_core.tdx_manual_signal_bridge import write_prediction_signals_atomic
from quantpilot_core.tdx_prediction_integration.engine import (
    TDXPredictionEngineV1,
    prediction_signal_record,
)


class LiveShadowPredictionSink(Level1MarketDataSink):
    """Compose an existing market-data store with material prediction export."""

    def __init__(
        self,
        delegate: Level1MarketDataSink,
        engine: TDXPredictionEngineV1,
        *,
        output_dir: str,
    ) -> None:
        self.delegate = delegate
        self.engine = engine
        self.output_dir = output_dir
        self.publish_count = 0
        self.last_json_path: str | None = None
        self.last_csv_path: str | None = None

    def prime(self, historical_bars: Sequence[NormalizedIntradayBar]) -> None:
        self.engine.process_completed_bars(historical_bars)
        self._publish_if_available()

    def persist_market_data(
        self,
        events: Sequence[NormalizedLevel1Event],
        bars: Sequence[NormalizedIntradayBar],
    ) -> None:
        self.delegate.persist_market_data(events, bars)
        material = self.engine.process_completed_bars(bars)
        if material:
            self._publish_if_available()

    def report(self) -> dict[str, Any]:
        return {
            "prediction_engine": "tdx_prediction_engine_v1",
            "prediction_count": len(self.engine.all_predictions),
            "material_signal_count": len(self.engine.material_signals),
            "tdx_publish_count": self.publish_count,
            "tdx_json_path": self.last_json_path,
            "tdx_csv_path": self.last_csv_path,
            "broker_or_order_api_calls": False,
            "deepseek_live_calls": False,
        }

    def _publish_if_available(self) -> None:
        records = tuple(prediction_signal_record(signal) for signal in self.engine.material_signals)
        if not records:
            return
        self.last_json_path, self.last_csv_path = write_prediction_signals_atomic(
            records,
            self.output_dir,
        )
        self.publish_count += 1
