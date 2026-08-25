"""Shared input/output locations for the training scripts."""

from pathlib import Path

HERE = Path(__file__).resolve().parent

# Datasets produced by data-simulation/ (see that folder's README).
SIMULATION_DIR = HERE.parent / "data-simulation" / "output"
PLANT_SIMULATION_FILE = SIMULATION_DIR / "plant_simulation.csv"
TRAINING_DATA_FILE = SIMULATION_DIR / "training_data.csv"

# Everything this folder produces: scaled arrays, trained models, results.
OUTPUT_DIR = HERE / "output"
MODEL_DIR = HERE / "models"
RESULTS_DIR = HERE / "results"

for d in (OUTPUT_DIR, MODEL_DIR, RESULTS_DIR):
    d.mkdir(exist_ok=True)
