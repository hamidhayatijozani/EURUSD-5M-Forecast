# Data contract

CSV columns:
timestamp,open,high,low,close,volume

Rules:
- timestamps are UTC ISO-8601
- rows are monotonically increasing
- forecast inputs may contain only rows timestamp <= prediction timestamp
- target rows are not available to the forecasting function
- production feeds must preserve the 5-minute candle boundary
