import gymnasium as gym
import numpy as np
from gymnasium import spaces


class PositionSizingEnv(gym.Env):
    """
    Custom Environment that follows gym interface for Position Sizing.
    The agent receives market state and CNN confidence, and must decide
    what percentage of risk to allocate (from 0 to 1).
    """

    metadata = {"render_modes": ["human"]}

    def __init__(self, initial_balance=10000.0, max_risk_per_trade=0.01):
        super().__init__()

        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.max_risk_per_trade = max_risk_per_trade

        # Action space: continuous from 0.0 to 1.0 (fraction of max_risk_per_trade)
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)

        # Observation space:
        # [0]: Volatility (0.0 - 1.0 normalized)
        # [1]: CNN Confidence (0.0 - 1.0)
        # [2]: Trend Strength (ADX normalized 0.0 - 1.0)
        # [3]: Win Rate of recent trades (0.0 - 1.0)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)

        self.current_step = 0
        self.max_steps = 1000

    def step(self, action):
        # Action is risk multiplier (0 to 1)
        risk_multiplier = float(action[0])

        # Risk amount
        risk_amount = self.balance * self.max_risk_per_trade * risk_multiplier

        # Simulated market outcome (in reality, this comes from historical backtest steps)
        # Simplified outcome simulation based on confidence and trend
        confidence = self._current_obs[1]

        # Simple probabilistic reward
        success_prob = 0.4 + (0.4 * confidence)  # 40% to 80% win rate
        is_win = np.random.random() < success_prob

        if is_win:
            reward = risk_amount * 1.5  # 1.5 R:R
            self.balance += reward
        else:
            reward = -risk_amount
            self.balance -= risk_amount

        self.current_step += 1
        done = self.current_step >= self.max_steps or self.balance <= 0
        truncated = False

        # Next state observation
        self._current_obs = self._get_observation()

        # Bonus reward for growing account smoothly, penalty for large drawdowns
        return self._current_obs, reward, done, truncated, {}

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.balance = self.initial_balance
        self.current_step = 0
        self._current_obs = self._get_observation()
        return self._current_obs, {}

    def _get_observation(self):
        # In a real training scenario, this pulls from a historical dataframe
        return np.array(
            [
                np.random.random(),  # Volatility
                np.random.random(),  # CNN Confidence
                np.random.random(),  # Trend Strength
                np.random.random(),  # Win Rate
            ],
            dtype=np.float32,
        )

    def render(self):
        print(f"Step: {self.current_step}, Balance: {self.balance:.2f}")


# Example of how to train this with stable-baselines3:
# from stable_baselines3 import PPO
# env = PositionSizingEnv()
# model = PPO("MlpPolicy", env, verbose=1)
# model.learn(total_timesteps=10000)
# model.save("ppo_position_sizer")
