import time
from typing import Dict


class Debouncer:
    def __init__(self, debounce_time_ms: int = 50):
        self.debounce_time = debounce_time_ms / 1000.0  # Convert to seconds
        self.last_press_times = {}
        
    def should_process(self, button_id: int) -> bool:
        """Check if button press should be processed based on debounce timing"""
        current_time = time.time()
        
        if button_id in self.last_press_times:
            time_since_last = current_time - self.last_press_times[button_id]
            
            if time_since_last < self.debounce_time:
                return False
                
        self.last_press_times[button_id] = current_time
        return True
        
    def reset(self):
        """Reset all debounce timers"""
        self.last_press_times.clear()