import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

load_dotenv()

class MLDataLoader:
    """
    Extracts historical OHLCV data from TimescaleDB and prepares it for CNN/RL training.
    """
    def __init__(self):
        # Default fallback if not in env
        db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/alghrest")
        self.engine = create_engine(db_url)

    def fetch_historical_data(self, symbol: str, start_date: str, end_date: str, timeframe: str = '1h') -> pd.DataFrame:
        """
        Fetch OHLCV data for a specific symbol.
        In a real scenario, this queries the timescale hypertable.
        """
        query = f"""
        SELECT time, open, high, low, close, volume 
        FROM ohlcv_data 
        WHERE symbol = '{symbol}' 
        AND timeframe = '{timeframe}'
        AND time >= '{start_date}' AND time <= '{end_date}'
        ORDER BY time ASC;
        """
        
        try:
            df = pd.read_sql(query, self.engine)
            df.set_index('time', inplace=True)
            print(f"Loaded {len(df)} rows for {symbol}")
            return df
        except Exception as e:
            print(f"Database error: {e}")
            # Return dummy data for illustration
            dates = pd.date_range(start_date, end_date, freq='1h')
            import numpy as np
            df = pd.DataFrame(
                np.random.randn(len(dates), 5) * 10 + 100, 
                index=dates, 
                columns=['open', 'high', 'low', 'close', 'volume']
            )
            return df

    def create_windows(self, df: pd.DataFrame, window_size: int = 64):
        """
        Convert time series dataframe into sliding windows for CNN training.
        Returns features X (N, window_size, 5) and dummy targets Y.
        """
        import numpy as np
        data = df.values
        X, Y = [], []
        
        for i in range(len(data) - window_size - 1):
            window = data[i:(i + window_size)]
            # Simple dummy logic for target: 2 if next close is higher, 0 if lower
            future_close = data[i + window_size, 3] # 3 is close
            current_close = window[-1, 3]
            
            target = 2 if future_close > current_close else 0
            
            X.append(window)
            Y.append(target)
            
        return np.array(X), np.array(Y)

if __name__ == "__main__":
    loader = MLDataLoader()
    df = loader.fetch_historical_data("BTC/USDT", "2023-01-01", "2023-12-31")
    X, Y = loader.create_windows(df, window_size=64)
    print(f"Created {len(X)} training windows of shape {X.shape}.")
