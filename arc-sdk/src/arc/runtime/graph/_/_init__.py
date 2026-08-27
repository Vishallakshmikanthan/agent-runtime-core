# Graph module

class ExecutionContext:
    pass


class ExecutionGraph:
    def kinds(self):
        return []


def build_execution_graph(plan, observable=True, streaming=False):
    return ExecutionGraph()