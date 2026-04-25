from collections import deque
import statistics
import logging

logger = logging.getLogger("ADS_Engine")

class VolatilityEstimator:
    """
    Simple rolling standard deviation of price changes.
    Does not require external TA libraries.
    """
    def __init__(self, window: int = 20):
        self.prices = deque(maxlen=window)

    def update(self, price: float):
        if price > 0:
            self.prices.append(price)

    def get_realized_vol(self) -> float:
        """Returns the standard deviation of recent price changes."""
        if len(self.prices) < 5:
            return 0.0
        
        try:
            # Calculate absolute price changes
            changes = [abs(self.prices[i] - self.prices[i-1]) 
                       for i in range(1, len(self.prices))]
            
            if len(changes) > 1:
                return statistics.stdev(changes)
            return 0.0
        except Exception as e:
            logger.debug(f"Volatility Calculation Error: {e}")
            return 0.0
