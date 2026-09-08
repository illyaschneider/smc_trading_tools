from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StructureConfig:
    lookback: int = 6
    lookforward: int = 3


SAMPLE_DATA_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "eurusd_h1_2019_2022_sample.csv"
)

