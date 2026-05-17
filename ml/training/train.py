import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from stable_baselines3 import PPO

# Import our custom modules
from ml.models.cnn_pattern import CandlestickCNN
from ml.models.rl_position_sizer import PositionSizingEnv
from ml.training.data_loader import MLDataLoader

def train_cnn(data_loader_obj, symbol="BTC/USDT", epochs=10, batch_size=32):
    print(f"\n--- Starting CNN Training for {symbol} ---")
    
    # 1. Fetch and prepare data
    print("Fetching historical data...")
    df = data_loader_obj.fetch_historical_data(symbol, "2023-01-01", "2023-12-31")
    X, Y = data_loader_obj.create_windows(df, window_size=64)
    
    if len(X) == 0:
        print("Not enough data to train CNN.")
        return

    # Convert to PyTorch tensors
    # X shape is (N, 64, 5). We need (N, 5, 64) for Conv1d
    X_tensor = torch.tensor(X, dtype=torch.float32).transpose(1, 2)
    Y_tensor = torch.tensor(Y, dtype=torch.long)
    
    dataset = TensorDataset(X_tensor, Y_tensor)
    train_loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    
    # 2. Initialize Model, Loss, Optimizer
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = CandlestickCNN(sequence_length=64, num_classes=3).to(device)
    
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    # 3. Training Loop
    model.train()
    for epoch in range(epochs):
        running_loss = 0.0
        correct = 0
        total = 0
        
        for batch_x, batch_y in train_loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            
            optimizer.zero_grad()
            outputs = model(batch_x)
            
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            _, predicted = torch.max(outputs.data, 1)
            total += batch_y.size(0)
            correct += (predicted == batch_y).sum().item()
            
        epoch_loss = running_loss / len(train_loader)
        epoch_acc = 100 * correct / total
        print(f"Epoch [{epoch+1}/{epochs}] | Loss: {epoch_loss:.4f} | Accuracy: {epoch_acc:.2f}%")
        
    # 4. Save the model
    os.makedirs("ml/weights", exist_ok=True)
    model_path = f"ml/weights/cnn_{symbol.replace('/', '_').lower()}.pth"
    torch.save(model.state_dict(), model_path)
    print(f"CNN Model saved to {model_path}")

def train_rl_agent(total_timesteps=50000):
    print("\n--- Starting RL Agent Training (Position Sizing) ---")
    
    # 1. Initialize custom Gymnasium environment
    env = PositionSizingEnv(initial_balance=10000.0, max_risk_per_trade=0.01)
    
    # 2. Initialize PPO Agent from stable-baselines3
    # MlpPolicy is a standard Neural Network policy for tabular/vector data
    model = PPO("MlpPolicy", env, verbose=1, learning_rate=0.0003, n_steps=2048)
    
    # 3. Train the model
    print(f"Training for {total_timesteps} timesteps...")
    model.learn(total_timesteps=total_timesteps)
    
    # 4. Save the agent
    os.makedirs("ml/weights", exist_ok=True)
    model_path = "ml/weights/ppo_position_sizer"
    model.save(model_path)
    print(f"RL Agent saved to {model_path}.zip")

if __name__ == "__main__":
    print("Initializing Data Loader...")
    loader = MLDataLoader()
    
    # Train the CNN model first (Feature Extractor)
    train_cnn(loader, symbol="BTC/USDT", epochs=5, batch_size=64)
    
    # Train the RL Position Sizing Agent
    train_rl_agent(total_timesteps=20000)
    
    print("\n✅ ML Pipeline Training Complete!")
