"""
Sensor Buffer for Rolling Window
=================================
Maintains last 60 samples for LSTM/CNN inference.
"""

import numpy as np
from collections import deque


class SensorBuffer:
    """
    Rolling buffer that stores last N sensor readings.

    Usage:
        buffer = SensorBuffer(window_size=60, n_features=40)

        # Add new sample
        buffer.add_sample(features_scaled)

        # Check if ready
        if buffer.is_ready():
            sequence = buffer.get_sequence()
            # Use sequence for LSTM/CNN
    """

    def __init__(self, window_size=60, n_features=40):
        """
        Initialize buffer.

        Args:
            window_size (int): Number of samples to store (default: 60)
            n_features (int): Number of features per sample (default: 40)
        """
        self.window_size = window_size
        self.n_features = n_features

        # Use deque for efficient FIFO operations
        self.buffer = deque(maxlen=window_size)

        #print(f"✅ SensorBuffer initialized: window={window_size}, features={n_features}")

    def add_sample(self, features):
        """
        Add new sample to buffer.

        Args:
            features (np.array): (40,) array of scaled features
        """
        # Convert to 1D array if needed
        if features.ndim == 2:
            features = features.flatten()

        # Add to buffer (automatically removes oldest if full)
        self.buffer.append(features)

    def get_sequence(self):
        """
        Get sequence for LSTM/CNN (60 x 40 array).

        Returns:
            np.array: (window_size, n_features) array
        """
        # If buffer not full yet, pad with zeros
        if len(self.buffer) < self.window_size:
            # Pad beginning with zeros
            padding_needed = self.window_size - len(self.buffer)
            padding = [np.zeros(self.n_features)] * padding_needed
            return np.array(padding + list(self.buffer))

        # Buffer is full - return as numpy array
        return np.array(list(self.buffer))

    def is_ready(self):
        """
        Check if buffer has enough samples for reliable prediction.

        Returns:
            bool: True if buffer has at least window_size samples
        """
        return len(self.buffer) >= self.window_size

    def size(self):
        """Current number of samples in buffer"""
        return len(self.buffer)

    def clear(self):
        """Clear all samples from buffer"""
        self.buffer.clear()

    def __len__(self):
        return len(self.buffer)

    def __repr__(self):
        return f"SensorBuffer(size={len(self.buffer)}/{self.window_size}, features={self.n_features})"


