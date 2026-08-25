# ML Training

Trains the 3 stage predictive maintenance pipeline that ships in `SwatDashboard/PythonMlService`. Run in order:

```
pip install -r requirements.txt
python prepare_dataset.py
python train_stage1_anomaly_detection.py
python train_stage2_state_classification.py
python train_stage3_component_identification.py
python evaluate_pipeline.py
```

Each stage trains a few candidate models, evaluates all of them on both the training split and the held-out simulation set (see `../data-simulation/README.md`), and picks a winner. `evaluate_pipeline.py` then chains the three winners together and checks how error compounds stage to stage.

| Stage | Question it answers | Candidates | Picked |
|---|---|---|---|
| 1 | Is this row normal or anomalous | Autoencoder, isolation forest, XGBoost | XGBoost |
| 2 | Anomaly, degrading, or faulted | XGBoost, LSTM, 1D CNN | LSTM |
| 3 | Which of the 10 components | LightGBM, MLP, XGBoost | XGBoost |

Results land in `results/`, trained models in `models/`, processed arrays in `output/`.

## experimental_cascading_autoencoder.py

A fully unsupervised alternative explored alongside the supervised pipeline above: three autoencoders chained together, each trained on a different slice of the state space, using reconstruction error instead of a learned classifier. It performed worse and isn't deployed, kept here because it was a genuine part of the exploration. Writes to its own `experimental_output/` folder so it never touches the real models.
