"""Live one-minute forecast/verification/online-learning loop.

At each minute:
1. use only closed 1m EURUSD data available now;
2. forecast the next 5-minute path;
3. persist the forecast before its target exists;
4. after five minutes, compare forecast with the observed closed price;
5. update the online calibration state only from that resolved outcome.
"""
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.experiments import combined
from engine.live_feed import closed_1m_rows

STATE_PATH = Path("research/live_state.json")
PRED_PATH = Path("research/live_predictions.jsonl")
FRICTION = 0.00002
HORIZON = 5
SLEEP_SECONDS = 60

def utcnow():
    return datetime.now(timezone.utc)

def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()

def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"bias": 0.0, "resolved": 0, "correct": 0, "errors": [], "last_prediction": None}

def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

def append_prediction(row):
    PRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PRED_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")

def read_predictions():
    if not PRED_PATH.exists():
        return []
    return [json.loads(x) for x in PRED_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]

def predict(closes, state):
    if len(closes) < 12:
        raise RuntimeError("need at least 12 closed one-minute prices")
    # Reuse the research engine on the information set that existed at prediction time.
    # Bias is learned only from previously resolved five-minute outcomes.
    s = combined({"EURUSD": closes, "GBPUSD": closes, "USDJPY": closes, "DXY": closes})
    adjusted_score = max(-1.0, min(1.0, s.score + state["bias"]))
    direction = "UP" if adjusted_score > 0.12 else "DOWN" if adjusted_score < -0.12 else "FLAT"
    predicted_return = adjusted_score * 0.0005
    return s, direction, adjusted_score, predicted_return

def settle(rows, latest_ts, latest_price, state):
    changed = False
    for row in rows:
        if row.get("resolved_at") or datetime.fromisoformat(row["target_ts"]) > latest_ts:
            continue
        actual = latest_price / row["entry_price"] - 1.0
        predicted = row["predicted_return"]
        error = actual - predicted
        # Online calibration: residual EWMA, bounded to avoid runaway feedback.
        state["bias"] = max(-0.5, min(0.5, 0.90 * state["bias"] + 0.10 * error / 0.0005))
        state["resolved"] += 1
        hit = (predicted > 0 and actual > FRICTION) or (predicted < 0 and actual < -FRICTION) or (abs(predicted) <= FRICTION and abs(actual) <= FRICTION)
        state["correct"] += int(hit)
        state["errors"].append(error)
        state["errors"] = state["errors"][-500:]
        row["actual_return"] = actual
        row["error"] = error
        row["hit"] = hit
        row["resolved_at"] = iso(latest_ts)
        changed = True
    return changed

def git_commit():
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    subprocess.run(["git","config","user.name","github-actions[bot]"], check=False)
    subprocess.run(["git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com"], check=False)
    subprocess.run(["git","add",str(STATE_PATH),str(PRED_PATH)], check=False)
    if subprocess.run(["git","diff","--cached","--quiet"]).returncode == 0:
        return
    subprocess.run(["git","commit","-m","chore: persist live five-minute forecast evidence [skip ci]"], check=False)
    subprocess.run(["git","push"], check=False)

def cycle():
    now = utcnow()
    rows = closed_1m_rows("EURUSD", now)
    if not rows:
        raise RuntimeError("no closed one-minute EURUSD data")
    latest_ts, latest_price = rows[-1]
    state = load_state()
    predictions = read_predictions()

    changed = settle(predictions, latest_ts, latest_price, state)

    last = state.get("last_prediction")
    if not last or last != iso(latest_ts):
        closes = [p for _, p in rows[-60:]]
        signal, direction, score, predicted_return = predict(closes, state)
        target_ts = latest_ts + timedelta(minutes=HORIZON)
        row = {
            "prediction_ts": iso(latest_ts),
            "target_ts": iso(target_ts),
            "entry_price": latest_price,
            "direction": direction,
            "score": score,
            "confidence": signal.confidence,
            "regime": signal.regime,
            "contradiction": signal.contradiction,
            "predicted_return": predicted_return,
            "status": "PENDING",
            "engine": "COMBINATION+ONLINE-CALIBRATION",
        }
        append_prediction(row)
        state["last_prediction"] = iso(latest_ts)
        changed = True
        print(json.dumps(row, sort_keys=True))

    state["last_cycle_at"] = iso(now)
    state["accuracy"] = state["correct"] / state["resolved"] if state["resolved"] else None
    save_state(state)
    if changed:
        git_commit()

def main():
    cycles = int(os.environ.get("LIVE_CYCLES", "5"))
    for i in range(cycles):
        try:
            cycle()
        except Exception as exc:
            print(f"LIVE_CYCLE_ERROR: {type(exc).__name__}: {exc}")
        if i + 1 < cycles:
            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    main()
