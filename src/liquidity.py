import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass(frozen=True)
class LiquiditySweep:
    time: pd.Timestamp
    swept_side: str
    liquidity_price: float
    liquidity_origin: pd.Timestamp


def identify_liquidity_pools(df: pd.DataFrame, structural_events: pd.DataFrame) -> tuple[pd.DataFrame, list[LiquiditySweep]]:
    df = df.copy()

    df["is_active_pool_at_end"] = False
    df["liquidity_pool"] = np.nan

    active_highs = {}
    active_lows = {}
    sweep_events = []

    events_by_time = {}

    for event in structural_events.itertuples():
        events_by_time.setdefault(
            event.structural_confirmed_time,
            []
        ).append(event)

    for row in df.itertuples():
        idx = row.Index

        current_high = row.High
        current_low = row.Low
        current_close = row.Close

        # check active liquidity for being valid
        # upside
        for liquidity_idx, value in list(active_highs.items()):
            if current_high > value:
                active_highs.pop(liquidity_idx, None)
                df.at[liquidity_idx, "is_active_pool_at_end"] = False

                if current_close < value:
                    sweep_events.append(
                        LiquiditySweep(
                            time=idx,
                            swept_side="high",
                            liquidity_price=value,
                            liquidity_origin=liquidity_idx,
                        )
                    )
        # downside
        for liquidity_idx, value in list(active_lows.items()):
            if current_low < value:
                active_lows.pop(liquidity_idx, None)
                df.at[liquidity_idx, "is_active_pool_at_end"] = False

                if current_close > value:
                    sweep_events.append(
                        LiquiditySweep(
                            time=idx,
                            swept_side="low",
                            liquidity_price=value,
                            liquidity_origin=liquidity_idx,
                        )
                    )

        current_events = events_by_time.get(idx, [])

        for event in current_events:
            liquidity_idx = event.pivot_time

            if event.pivot_time not in df.index:
                raise ValueError(
                    f"Structural event pivot {event.pivot_time} "
                    f"is missing from candle timeline"
                )

            # add new liquidity into active pools
            if pd.notna(event.structural_high):
                df.at[liquidity_idx, "liquidity_pool"] = event.structural_high
                df.at[liquidity_idx, "is_active_pool_at_end"] = True
                active_highs[liquidity_idx] = event.structural_high

            if pd.notna(event.structural_low):
                df.at[liquidity_idx, "liquidity_pool"] = event.structural_low
                df.at[liquidity_idx, "is_active_pool_at_end"] = True
                active_lows[liquidity_idx] = event.structural_low

    return df, sweep_events


def main():
    from src.config import StructureConfig, SAMPLE_DATA_PATH
    from src.data_loader import load_market_data
    from src.market_structure import identify_structure

    config = StructureConfig()

    df = load_market_data(SAMPLE_DATA_PATH)

    structured_df, structural_events = identify_structure(df, config)

    liquidity_df, sweep_events = identify_liquidity_pools(structured_df, structural_events)

    print(f"Structural events: {len(structural_events)}")
    print(f"Liquidity sweeps: {len(sweep_events)}")
    print(
        f"Active liquidity pools: "
        f"{liquidity_df['is_active_pool_at_end'].sum()}"
    )


if __name__ == '__main__':
    main()