"""
This module contains code for interacting with hit graphs.
A Graph is a namedtuple of matrices X, Ri, Ro, y.
"""

from collections import namedtuple
from typing import List

import numpy as np


# A Graph is a namedtuple of matrices (X, Ri, Ro, y)
Graph = namedtuple('Graph', ['X', 'Ri', 'Ro', 'y'])
Graph_V2 = namedtuple('Graph', ['X', 'edge_index', 'y'])


def graph_to_sparse(graph):
    Ri_rows, Ri_cols = graph.Ri.nonzero()
    Ro_rows, Ro_cols = graph.Ro.nonzero()
    return dict(X=graph.X, y=graph.y,
                Ri_rows=Ri_rows, Ri_cols=Ri_cols,
                Ro_rows=Ro_rows, Ro_cols=Ro_cols)

def save_graph_v2(graph:Graph_V2, filename):
    assert isinstance(graph, Graph_V2)
    return np.savez(filename, **dict(X=graph.X,
                                   edge_index=graph.edge_index,
                                   y=graph.y))

def sparse_to_graph(X, Ri_rows, Ri_cols, Ro_rows, Ro_cols, y, dtype=np.uint8):
    n_nodes, n_edges = X.shape[0], Ri_rows.shape[0]
    Ri = np.zeros((n_nodes, n_edges), dtype=dtype)
    Ro = np.zeros((n_nodes, n_edges), dtype=dtype)
    Ri[Ri_rows, Ri_cols] = 1
    Ro[Ro_rows, Ro_cols] = 1
    return Graph(X, Ri, Ro, y)


def save_graph(graph, filename):
    """Write a single graph to an NPZ file archive"""
    np.savez(filename, **graph_to_sparse(graph))


def save_graphs(graphs, filenames):
    for graph, filename in zip(graphs, filenames):
        save_graph(graph, filename)


def save_graphs_new(graphs):
    for graph_data_chunk in graphs:
        if graph_data_chunk.processed_object is None:
            continue
        processed_graph: Graph = graph_data_chunk.processed_object
        save_graph(processed_graph,
                   graph_data_chunk.output_name)


def load_graph(filename):
    """Reade a single graph NPZ"""
    with np.load(filename) as f:
        return sparse_to_graph(**dict(f.items()))

def load_graph_v2(filename) -> Graph_V2:
    with np.load(filename, allow_pickle=True) as f:
        return Graph_V2(**dict(f.items()))