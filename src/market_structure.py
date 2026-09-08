import pandas as pd
from src.config import StructureConfig


def identify_swings(df: pd.DataFrame, lookback: int, lookforward: int) -> pd.DataFrame:
    df = df.copy()

    high = df["High"]
    low = df["Low"]

    past_highest = high.rolling(lookback + 1).max()
    past_lowest = low.rolling(lookback + 1).min()
    future_highest = high.shift(-lookforward).rolling(lookforward).max()
    future_lowest = low.shift(-lookforward).rolling(lookforward).min()

    swing_high = (
        (high == past_highest) &
        (high >= future_highest)
    )
    swing_low = (
        (low == past_lowest) &
        (low <= future_lowest)
    )

    df["swing_high"] = high.where(swing_high)
    df["swing_low"] = low.where(swing_low)

    df["swing_high_confirmed"] = high.where(swing_high).shift(lookforward)
    df["swing_low_confirmed"] = low.where(swing_low).shift(lookforward)

    return df


def confirm_structural_swings(df: pd.DataFrame, lookforward: int) -> pd.DataFrame:
    events = []

    for i in range(len(df)):
        if pd.notna(df["swing_high"].iloc[i]):
            pivot_time = df.index[i]

            if i + lookforward < len(df):
                raw_confirmed_time = df.index[i + lookforward]
            else:
                raw_confirmed_time = None

            events.append({
                "pivot_time": pivot_time,
                "raw_confirmed_time": raw_confirmed_time,
                "type": "swing_high",
                "value": df["swing_high"].iloc[i]
            })

        if pd.notna(df["swing_low"].iloc[i]):
            pivot_time = df.index[i]

            if i + lookforward < len(df):
                raw_confirmed_time = df.index[i + lookforward]
            else:
                raw_confirmed_time = None

            events.append({
                "pivot_time": pivot_time,
                "raw_confirmed_time": raw_confirmed_time,
                "type": "swing_low",
                "value": df["swing_low"].iloc[i]
            })

    events = pd.DataFrame(events)
    events["is_structural_swing"] = False

    structural_events = []

    for i in range(len(events)):
        current_event = events.iloc[i].to_dict()

        if not structural_events:
            structural_events.append(current_event)
            continue

        previous_event = structural_events[-1]

        if current_event["type"] != previous_event["type"]:
            structural_events[-1]["structural_confirmed_time"] = current_event["raw_confirmed_time"]
            structural_events[-1]["is_structural_swing"] = True

            structural_events.append(current_event)

        elif current_event["type"] == "swing_high":
            if current_event["value"] > previous_event["value"]:
                structural_events[-1] = current_event

        elif current_event["type"] == "swing_low":
            if current_event["value"] < previous_event["value"]:
                structural_events[-1] = current_event

    structural_df = pd.DataFrame(structural_events)

    confirmed = structural_df[
        structural_df["is_structural_swing"] == True
        ].copy()

    confirmed["structural_high"] = confirmed["value"].where(
        confirmed["type"] == "swing_high"
    )
    confirmed["structural_low"] = confirmed["value"].where(
        confirmed["type"] == "swing_low"
    )

    return confirmed


def build_events_by_time(events: pd.DataFrame) -> dict:
    events_by_time = {}

    for event in events.itertuples():
        events_by_time.setdefault(
            event.structural_confirmed_time,
            []
        ).append(event)

    return events_by_time


def label_structural_swings(structural_df: pd.DataFrame) -> pd.DataFrame:
    df = structural_df.copy()

    df["label"] = None

    last_high = None
    last_low = None

    for i in range(len(df)):
        event = df.iloc[i]

        label = None

        if event["type"] == "swing_high":
            current_high = event["value"]

            if last_high is not None:
                if current_high > last_high:
                    label = "HH"
                elif current_high < last_high:
                    label = "LH"
                else:
                    label = None
            else:
                label = None

            last_high = current_high

        elif event["type"] == "swing_low":
            current_low = event["value"]

            if last_low is not None:
                if current_low < last_low:
                    label = "LL"
                elif current_low > last_low:
                    label = "HL"
                else:
                    label = None
            else:
                label = None

            last_low = current_low

        df.iat[i, df.columns.get_loc("label")] = label


    return df


def identify_bos(df: pd.DataFrame, events_by_time: dict) -> pd.DataFrame:
    trend = None

    protected_low = None
    protected_high = None

    last_structural_high = None
    last_structural_low = None

    last_structural_label = None

    structured_df = []

    for row in df.itertuples():
        idx = row.Index

        current_candle_close = row.Close

        # updating structural state; accounting for both cases for same candle/timestamp
        current_events = events_by_time.get(idx, [])
        for event in current_events:
            current_label = event.label

            if pd.notna(event.structural_high):
                last_structural_high = event.structural_high

            if pd.notna(event.structural_low):
                last_structural_low = event.structural_low

            # finding initial trend and structural extremes
            if pd.notna(current_label):

                if trend is None:
                    if last_structural_label == "HL" and current_label == "HH":
                        trend = 1
                        protected_low = last_structural_low

                    elif last_structural_label == "LH" and current_label == "LL":
                        trend = -1
                        protected_high = last_structural_high

                last_structural_label = current_label

            if trend == 1 and pd.notna(event.structural_low):
                protected_low = event.structural_low

            if trend == -1 and pd.notna(event.structural_high):
                protected_high = event.structural_high

        # evaluating bos on this candle
        bos = None
        bos_level = None

        # checking for bullish bos
        if (
                protected_high is not None
                and trend == -1
                and current_candle_close > protected_high
        ):
            bos = "bullish"
            bos_level = protected_high

            trend = 1

            protected_high = None
            protected_low = last_structural_low

        # checking for bearish bos
        elif (
                protected_low is not None
                and trend == 1
                and current_candle_close < protected_low
        ):
            bos = "bearish"
            bos_level = protected_low

            trend = -1

            protected_low = None
            protected_high = last_structural_high

        structured_df.append({
            "Time": row.Index,
            "Open": row.Open,
            "High": row.High,
            "Low": row.Low,
            "Close": row.Close,
            "weekday": row.weekday,

            "swing_high": row.swing_high,
            "swing_low": row.swing_low,
            "swing_high_confirmed": row.swing_high_confirmed,
            "swing_low_confirmed": row.swing_low_confirmed,

            "bos": bos,
            "bos_level": bos_level
        })

    structured_df = pd.DataFrame(structured_df)
    structured_df = structured_df.set_index("Time", drop=False)

    return structured_df


def identify_structure(df: pd.DataFrame, config: StructureConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_with_swing = identify_swings(df, config.lookback, config.lookforward)

    structural_events = confirm_structural_swings(df_with_swing, config.lookforward)

    labeled_events = label_structural_swings(structural_events)

    events_by_time = build_events_by_time(labeled_events)

    structured_df = identify_bos(df_with_swing, events_by_time)

    return structured_df, labeled_events


def main():
    from src.data_loader import load_market_data
    from src.config import SAMPLE_DATA_PATH

    df = load_market_data(SAMPLE_DATA_PATH)

    config = StructureConfig()

    structured_df, labeled_events = identify_structure(df, config)

    print(f"Candles processed: {len(structured_df)}")
    print(f"Structural events: {len(labeled_events)}")
    print(f"BOS events: {structured_df['bos'].notna().sum()}")

    print(structured_df[structured_df["bos"].notna()].tail())


if __name__ == "__main__":
    main()