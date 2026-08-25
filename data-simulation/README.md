# Data Simulation

Two scripts, same physics engine, different purpose.

| Script | Purpose | Output |
|---|---|---|
| `plant_simulator.py` | Realistic, randomly timed plant behavior. Never used for training, held out entirely as the generalization check. | `output/plant_simulation.csv` |
| `scheduled_data_generator.py` | Same physics, but every component and fault type gets scheduled, guaranteed coverage. This is what the models train on. | `output/training_data.csv` |

## Why two generators

A purely random simulator (`plant_simulator.py`) behaves like the real plant: long healthy stretches, faults that happen when they happen. Left to chance, though, some component or anomaly combinations barely show up even across a 200 day run, not enough for a classifier to learn them.

`scheduled_data_generator.py` solves that by pre-scheduling a fixed number of degradation cycles per component and anomaly episodes per component/type pair, shuffling the list, then playing it back with short gaps in between. Everything else, the physics, the state machine, the noise model, is identical to the simulator on purpose, so a model trained on the scheduled data transfers to the simulator's more realistic distribution.

## What the physics covers

Each component (8 pumps, 2 valves) cycles through healthy, degrading, faulted, and startup states. While healthy it wears down at a slow random rate. Once it starts degrading, wear accelerates at a locked-in rate until it crosses a randomized fault threshold, at which point the component fails and its sensors, and its pump's motor temperature, current, and vibration, shift toward realistic failure signatures. A separate, independent process fires short transient anomalies (cavitation, valve chatter, flow oscillation, level jitter) on whatever component happens to be healthy at the time.

A minimum signal separation is enforced between states on every sensor, so even after realistic noise is layered on, the difference between healthy and anomalous stays learnable.

## Running

```
pip install -r requirements.txt
python plant_simulator.py --duration-days 200
python scheduled_data_generator.py
```

Both read `clean_1.csv` in this folder, a cleaned baseline extract of the source SWaT dataset. That file isn't checked into the repo, download it (along with the two generated datasets) from [the published dataset on Kaggle](https://www.kaggle.com/datasets/ariadaikalam/fyp-ml-dataset), or see the main README's Dataset section for the original source.
