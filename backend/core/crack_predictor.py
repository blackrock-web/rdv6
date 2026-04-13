"""
ROADAI Crack Formation Predictor
================================
Analyzes historical damage accumulation and road health trends
to predict the likelihood and timeframe of new crack formations.
"""

from dataclasses import dataclass
from typing import List, Dict

@dataclass
class FormationForecast:
    risk_level: str  # none, low, medium, high, critical
    primary_reason: str
    days_to_formation: int
    confidence: float
    trend_slope: float

class CrackPredictor:
    """
    Time-series heuristic predictor for crack formation.
    In real-time video mode, it analyzes the accumulation rate of damage across recent frames.
    In historical mode (for predictions page), it analyzes week-over-week segment health.
    """
    
    def predict_from_history(self, history: List[Dict], current_health: float) -> FormationForecast:
        """
        Predict based on short-term frame history (e.g., from video tracking)
        history should contain: [{"total_damage_count": int}, ...]
        """
        if not history or len(history) < 5:
            return FormationForecast("none", "Insufficient data", 365, 0.0, 0.0)
            
        # Extract damage counts
        counts = [h.get("total_damage_count", 0) for h in history[-30:]]
        
        # Calculate trend (simple linear slope of damage accumulation)
        n = len(counts)
        if n < 2:
            return FormationForecast("none", "Stable", 365, 0.5, 0.0)
            
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(counts) / n
        
        numerator = sum((x[i] - x_mean) * (counts[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean)**2 for i in range(n))
        
        slope = numerator / denominator if denominator != 0 else 0.0
        
        # If damage is actively increasing in the sequence, risk is higher
        if slope > 0.5 and current_health < 80:
            risk = "critical"
            days = 7
            reason = "Rapid damage accumulation detected"
            conf = 0.85
        elif slope > 0.1 and current_health < 90:
            risk = "high"
            days = 30
            reason = "Steady damage growth"
            conf = 0.75
        elif current_health < 60:
            risk = "medium"
            days = 90
            reason = "Poor structural health"
            conf = 0.60
        elif current_health < 85:
            risk = "low"
            days = 180
            reason = "Minor wear and tear"
            conf = 0.50
        else:
            risk = "none"
            days = 365
            reason = "Stable healthy surface"
            conf = 0.90
            
        return FormationForecast(risk, reason, days, conf, round(slope, 3))
