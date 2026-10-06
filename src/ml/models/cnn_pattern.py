import torch
import torch.nn as nn
from torch.nn import functional


class CandlestickCNN(nn.Module):
    """
    CNN model for recognizing candlestick patterns.
    Input shape: (Batch, Channels, Sequence_Length)
    Example: (Batch, 5, 64) -> 5 channels (OHLCV), 64 time periods.
    """

    def __init__(self, sequence_length: int = 64, num_classes: int = 3):
        """
        num_classes: 3 -> (0: Bearish, 1: Neutral, 2: Bullish)
        """
        super().__init__()

        # 1D Convolutions over the time dimension
        self.conv1 = nn.Conv1d(in_channels=5, out_channels=32, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm1d(32)

        self.conv2 = nn.Conv1d(in_channels=32, out_channels=64, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(64)

        self.conv3 = nn.Conv1d(in_channels=64, out_channels=128, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm1d(128)

        self.pool = nn.MaxPool1d(kernel_size=2, stride=2)

        # Calculate flattened size
        self.flattened_size = 128 * (sequence_length // 8)

        self.fc1 = nn.Linear(self.flattened_size, 256)
        self.dropout = nn.Dropout(0.5)
        self.fc2 = nn.Linear(256, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (B, 5, Seq)
        x = self.pool(functional.relu(self.bn1(self.conv1(x))))
        x = self.pool(functional.relu(self.bn2(self.conv2(x))))
        x = self.pool(functional.relu(self.bn3(self.conv3(x))))

        x = x.view(x.size(0), -1)  # Flatten
        x = functional.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)
        return x

    def predict(self, x: torch.Tensor) -> int:
        """Helper to get class prediction (0, 1, or 2)"""
        with torch.no_grad():
            outputs = self.forward(x)
            _, predicted = torch.max(outputs.data, 1)
        return int(predicted.item())
