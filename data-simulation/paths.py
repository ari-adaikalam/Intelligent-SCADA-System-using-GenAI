"""Shared input/output locations for both simulator scripts."""

from pathlib import Path

HERE = Path(__file__).resolve().parent

# Cleaned baseline extract of the Kaggle SWaT dataset (real, healthy plant
# readings). See ../README.md, Dataset section, for where this comes from.
RAW_BASELINE_CSV = HERE / "clean_1.csv"

OUTPUT_DIR = HERE / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Written by plant_simulator.py. Random timing, long realistic idle
# stretches, held out entirely from training as the generalization check.
PLANT_SIMULATION_FILE = OUTPUT_DIR / "plant_simulation.csv"

# Written by scheduled_data_generator.py. Same physics, but every
# component and fault type gets guaranteed coverage. This is what the
# models actually train on.
TRAINING_DATA_FILE = OUTPUT_DIR / "training_data.csv"
