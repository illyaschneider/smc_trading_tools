from pathlib import Path
import pandas as pd


def load_ohlc(filepath: str | Path) -> pd.DataFrame:
    filepath = Path(filepath)

    if _looks_like_tab_separated_file(filepath):
        df = _read_tab_separated_ohlc(filepath)
    else:
        df = pd.read_csv(filepath)

    df = _drop_saved_index_columns(df)

    required = {"Open", "High", "Low", "Close"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"Missing required OHLC columns: {sorted(missing)}")

    if "UTC" in df.columns:
        df["UTC"] = (
            df["UTC"]
            .str.replace(".000 UTC", "", regex=False)
            .str.replace(" UTC", "", regex=False)
        )
        df["Time"] = pd.to_datetime(
            df["UTC"],
            format="%d.%m.%Y %H:%M:%S"
        )
    elif "Time" in df.columns:
        df["Time"] = pd.to_datetime(df["Time"])
    else:
        raise ValueError("Dataset must contain either 'UTC' or 'Time'")

    df["weekday"] = df["Time"].dt.day_name()
    df.set_index("Time", inplace=True)

    df = df.drop(columns=["Volume"], errors="ignore")
    df = df.sort_index()

    if df.index.has_duplicates:
        raise ValueError("Duplicate timestamps found in market data")

    return df


def filter_sunday_candles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge Sunday candles into the following Monday candle.

    The resulting Monday candle uses:
    - Sunday's open
    - max(Sunday high, Monday high)
    - min(Sunday low, Monday low)
    - Monday's original close
    """
    df = df.copy()
    rows_to_drop = []

    for i in range(len(df) - 1):
        current_idx = df.index[i]
        next_idx = df.index[i + 1]

        current_is_sunday = df.at[current_idx, "weekday"] == "Sunday"
        next_is_monday = df.at[next_idx, "weekday"] == "Monday"

        if current_is_sunday and next_is_monday:
            df.at[next_idx, "Open"] = df.at[current_idx, "Open"]
            df.at[next_idx, "High"] = max(
                df.at[current_idx, "High"],
                df.at[next_idx, "High"]
            )
            df.at[next_idx, "Low"] = min(
                df.at[current_idx, "Low"],
                df.at[next_idx, "Low"]
            )

            rows_to_drop.append(current_idx)

    df = df.drop(index=rows_to_drop)

    return df


def _looks_like_tab_separated_file(path: Path) -> bool:
    with path.open("r", encoding="utf-8") as file:
        first_line = file.readline()

    return "\t" in first_line


def _read_tab_separated_ohlc(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8") as file:
        header = file.readline().strip().split("\t")
        first_data_row = file.readline().strip().split("\t")

    if len(first_data_row) == len(header) + 1:
        return pd.read_csv(
            path,
            sep="\t",
            header=0,
            names=[*header, "Spread"],
        )

    return pd.read_csv(path, sep="\t")


def _drop_saved_index_columns(df: pd.DataFrame) -> pd.DataFrame:
    saved_index_cols = [
        col for col in df.columns
        if str(col).startswith("Unnamed") or col == ""
    ]

    return df.drop(columns=saved_index_cols, errors="ignore")


def load_market_data(filepath: str | Path, merge_sunday: bool = True) -> pd.DataFrame:
    df = load_ohlc(filepath)

    if merge_sunday:
        df = filter_sunday_candles(df)

    return df