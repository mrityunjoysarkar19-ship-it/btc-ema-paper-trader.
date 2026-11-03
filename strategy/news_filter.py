"""News blackout utilities. CSV timestamps must include UTC or an explicit timezone."""
from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
import pandas as pd

REQUIRED_COLUMNS = {"event", "timestamp_utc"}

def load_news_events(uploaded_bytes: bytes | None = None, csv_path: str = "data/news_events.csv"):
    """Return sorted event records and UTC blackout intervals.

    CSV columns: event,timestamp_utc,blackout_before_min,blackout_after_min
    timestamp_utc must be ISO-8601 with Z or an explicit UTC offset.
    """
    if uploaded_bytes:
        frame = pd.read_csv(BytesIO(uploaded_bytes))
    else:
        try:
            frame = pd.read_csv(csv_path)
        except FileNotFoundError:
            return [], []
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError("News CSV missing columns: " + ", ".join(sorted(missing)))
    events, intervals = [], []
    for _, row in frame.iterrows():
        raw = str(row["timestamp_utc"]).strip()
        if not raw or raw.lower() == "nan":
            continue
        stamp = pd.Timestamp(raw)
        if stamp.tzinfo is None:
            raise ValueError(f"Event '{row['event']}' timestamp needs Z or an explicit UTC offset.")
        stamp = stamp.tz_convert("UTC")
        before = max(0, int(row.get("blackout_before_min", 60) if pd.notna(row.get("blackout_before_min", 60)) else 60))
        after = max(0, int(row.get("blackout_after_min", 60) if pd.notna(row.get("blackout_after_min", 60)) else 60))
        start = stamp - pd.Timedelta(minutes=before)
        end = stamp + pd.Timedelta(minutes=after)
        events.append({"event": str(row["event"]), "timestamp": stamp, "start": start, "end": end})
        intervals.append((start, end, str(row["event"])))
    events.sort(key=lambda x: x["timestamp"])
    return events, intervals

def blackout_reason(timestamp, intervals):
    """Return event name if timestamp is inside a blackout interval, else None."""
    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    for start, end, event in intervals:
        if start <= ts <= end:
            return event
    return None
