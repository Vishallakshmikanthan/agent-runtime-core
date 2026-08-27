# Flight recorder module

class FlightRecorder:
    def next_step_number(self, session_id):
        return 1
    
    def build_step(self, session_id, step_number, step_type, name, input_data=None, error=None, latency_ms=0.0, output_text=None):
        pass
    
    def record(self, step):
        return step
    
    def trace(self, session_id):
        return []