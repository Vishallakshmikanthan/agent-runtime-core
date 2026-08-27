# Middleware pipeline module

class MiddlewarePipeline:
    def __init__(self, middleware_factory):
        pass
    
    def execute(self, request, invoke):
        return {"metadata": {"raw_response": None}}