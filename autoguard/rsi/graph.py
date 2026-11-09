"""Grafo RSI: etapas inyectadas, sin acceso de escritura al evaluador."""
from langgraph.graph import END, START, StateGraph


def build_graph(stages):
    """Compila las seis etapas; cada callable recibe y devuelve el estado dict."""
    graph = StateGraph(dict)
    names = ['recolector', 'analista', 'mejorador', 'evaluador', 'linaje', 'meta']
    previous = START
    for name in names:
        graph.add_node(name, stages[name])
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph.compile()
