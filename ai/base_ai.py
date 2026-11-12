class BaseAI:
    """Base class for AI behaviors."""
    
    def __init__(self):
        pass
    
    def update(self, team, opponents, ball, current_time):
        """Update AI decisions for a team."""
        raise NotImplementedError("Subclasses must implement update method")