import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import numpy as np

# We'll mock the import for the CNN. In reality, it imports from ml.models.cnn_pattern
from ml.models.cnn_pattern import CandlestickCNN
# Mock import for RL model (could use stable-baselines3 loaded model)
# from stable_baselines3 import PPO

app = FastAPI(title="ALGHREST ML Inference Engine")

# Load models at startup
cnn_model = CandlestickCNN()
# cnn_model.load_state_dict(torch.load("path/to/weights.pth"))
cnn_model.eval()

# rl_model = PPO.load("path/to/ppo_position_sizer")

class PredictionRequest(BaseModel):
    symbol: str
    ohlcv_window: list[list[float]]  # List of [Open, High, Low, Close, Volume] x 64
    volatility: float
    trend_strength: float
    win_rate: float

class PredictionResponse(BaseModel):
    symbol: str
    signal: str  # BULLISH, BEARISH, NEUTRAL
    confidence: float
    recommended_risk_multiplier: float

@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    if len(request.ohlcv_window) != 64:
        raise HTTPException(status_code=400, detail="ohlcv_window must be exactly 64 periods")
    
    # 1. Prepare data for CNN: Shape -> (1, 5, 64)
    data = np.array(request.ohlcv_window).T  # Transpose to (5, 64)
    tensor_data = torch.tensor(data, dtype=torch.float32).unsqueeze(0)
    
    # 2. CNN Prediction
    with torch.no_grad():
        outputs = cnn_model(tensor_data)
        probabilities = torch.nn.functional.softmax(outputs, dim=1)
        confidence, predicted = torch.max(probabilities.data, 1)
        
    class_map = {0: "BEARISH", 1: "NEUTRAL", 2: "BULLISH"}
    signal = class_map[int(predicted.item())]
    conf_val = float(confidence.item())
    
    # 3. RL Position Sizing Prediction
    # Construct observation for RL model
    obs = np.array([
        request.volatility,
        conf_val,
        request.trend_strength,
        request.win_rate
    ], dtype=np.float32)
    
    # action, _states = rl_model.predict(obs, deterministic=True)
    # risk_mult = float(action[0])
    
    # Mocking RL action for now
    risk_mult = 0.5 if signal != "NEUTRAL" else 0.0

    return PredictionResponse(
        symbol=request.symbol,
        signal=signal,
        confidence=conf_val,
        recommended_risk_multiplier=risk_mult
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
