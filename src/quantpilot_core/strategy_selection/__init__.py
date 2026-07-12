"""Small strategy-selection contracts shared by evaluation and production."""

from quantpilot_core.strategy_selection.equal_weight import equal_weight_target_weights, rank_equal_weight_baseline

__all__ = ["equal_weight_target_weights", "rank_equal_weight_baseline"]
