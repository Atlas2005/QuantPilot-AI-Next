# Data-Source Field Mapping

Phase 4A adds provisional field-mapping templates for future manual data-source prototypes.

## Target Daily OHLCV Contract

Templates map source fields into the Phase 3 daily bar contract:

- `symbol`
- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`
- `adjustment`
- `asset_type`

## Template Purpose

Templates describe expected mapping shape only. They are not final provider mappings and are not adapter code.

## Provisional Field Names

When real source field names are uncertain, templates use provisional placeholders. These must be manually verified during a future approved prototype.

## Field Normalization

The helper normalizes field names by trimming whitespace, lowercasing, converting hyphens to underscores, and collapsing whitespace into underscores.

## Limitations

Phase 4A does not fetch data, inspect live provider schemas, install provider packages, validate market truth, or resolve adjustment methodology.

## Future Refinement

After manual prototype results, templates may be revised with observed source fields, validation notes, and provider-specific limitations before any adapter work begins.

