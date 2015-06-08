"""
.. module:: draw

.. moduleauthor:: Vincenzo Arcidiacono <vinci1it2000@gmail.com>

"""

__author__ = 'Vincenzo Arcidiacono'

import re
from networkx.classes.digraph import DiGraph
from networkx.drawing import *
from .constants import START, SINK
import matplotlib.pyplot as plt
from .dispatcher_utils import SubDispatch
from graphviz import Digraph
from itertools import count

node_label_regex = re.compile('(^|[^(_ )])(_)[^(_ )]', re.IGNORECASE)


def under_rpl(match_obj):
    return match_obj.group(0).replace('_', ' ')


def replace_under_score(s):
    s, n = node_label_regex.subn(under_rpl, s)
    while n:
        s, n = node_label_regex.subn(under_rpl, s)
    return s


def plot_dsp(dsp, pos=None, workflow=False, title='Dispatcher', fig=None):
    """
    Draw the graph of a Dispatcher with Matplotlib.

    :param dsp:
        A dispatcher that identifies the model adopted.
    :type dsp: dispatcher.dispatcher.Dispatcher

    :param pos:
       A dictionary with nodes as keys and positions as values.
       If not specified a spring layout positioning will be computed.
    :type pos: dictionary, optional

    :param workflow:
       If True the workflow graph will be plotted, otherwise the dispatcher map.
    :type workflow: bool, DiGraph, optional

    :return:
        A dictionary with figures.
    :rtype: dict

    Example::

        >>> import matplotlib.pyplot as plt
        >>> from dispatcher import Dispatcher, SubDispatch
        >>> sub_dsp = Dispatcher()
        >>> def fun(a):
        ...     return a + 1, a - 1
        >>> sub_dsp.add_function('fun', fun, ['a'], ['b', 'c'])
        'fun'
        >>> dispatch = SubDispatch(sub_dsp, ['a', 'c'], returns='list')
        >>> dsp = Dispatcher()
        >>> dsp.add_data('_i_n_p_u_t', default_value={'a': 3})
        '_i_n_p_u_t'
        >>> class noStr(object):
        ...     def __str__(self):
        ...         raise ValueError
        >>> dsp.add_data('_i_', default_value=noStr())
        '_i_'
        >>> dsp.add_function('dispatch', dispatch, ['_i_n_p_u_t'], ['e', 'f'])
        'dispatch'
        >>> w, o = dsp.dispatch()

        >>> #f1 = plot_dsp(dsp)
        >>> #f2 = plot_dsp(dsp, workflow=True)
        >>> plt.show()
    """
    figs = []

    if workflow:
        g = workflow if isinstance(workflow, DiGraph) else dsp.workflow
        dfl = {}
    else:
        g = dsp.dmap
        dfl = dsp.default_values

    if pos is None:
        pos = spring_layout(g)

    data, function = ([], [])

    for k, v in g.node.items():
        n = dsp.nodes.get(k, {})
        if n:
            data_type = n['type']
            eval(data_type).append(k)

            f = n.get('function', None)

            if data_type == 'function' and isinstance(f, SubDispatch):
                w = v.get('workflow', False)
                t = '%s:%s' %(title, k)
                figs.append(plot_dsp(f.dsp, title=t, workflow=w))


    if fig is None:
        fig = plt.figure()

    fig.suptitle(title)
    fig = {title: (fig, figs)}

    label_nodes = {k: replace_under_score(k) for k in g.node}

    for k, v in dfl.items():
        try:
            s = '%s:%s' % (replace_under_score(k), str(v))
        except:
            s = replace_under_score(k)

        label_nodes.update({k: s})

    if START in g.node:
        label_nodes[START] = 'start'
        draw_networkx_nodes(
            g, pos, node_shape='^', nodelist=[START], node_color='b')

    draw_networkx_nodes(g, pos, node_shape='o', nodelist=data, node_color='r')
    draw_networkx_nodes(
        g, pos, node_shape='s', nodelist=function, node_color='y')
    draw_networkx_labels(g, pos, labels=label_nodes)

    label_edges = {}

    for u, v, a in g.edges_iter(data=True):

        try:
            s = str(a['value'])
        except:
            s = ''

        label_edges.update({(u, v): s})

    draw_networkx_edges(g, pos, alpha=0.5)
    draw_networkx_edge_labels(g, pos, edge_labels=label_edges)

    plt.axis('off')

    return fig


def plot_dsp_graphviz(dsp, workflow=False, title='Dispatcher', dot=None, cnt=None):
    """
    Draw the graph of a Dispatcher with Graphviz.

    :param dsp:
        A dispatcher that identifies the model adopted.
    :type dsp: dispatcher.dispatcher.Dispatcher

    :param pos:
       A dictionary with nodes as keys and positions as values.
       If not specified a spring layout positioning will be computed.
    :type pos: dictionary, optional

    :param workflow:
       If True the workflow graph will be plotted, otherwise the dispatcher map.
    :type workflow: bool, DiGraph, optional

    :return:
        A dictionary with figures.
    :rtype: dict

    Example::

        >>> from dispatcher import Dispatcher, SubDispatch
        >>> sub_dsp = Dispatcher()
        >>> def fun(a):
        ...     return a + 1, a - 1
        >>> sub_dsp.add_function('fun', fun, ['a'], ['b', 'c'])
        'fun'
        >>> dispatch = SubDispatch(sub_dsp, ['a', 'c'], returns='list')
        >>> dsp = Dispatcher()
        >>> dsp.add_data('_i_n_p_u_t', default_value={'a': 3})
        '_i_n_p_u_t'
        >>> class noStr(object):
        ...     def __str__(self):
        ...         raise ValueError
        >>> dsp.add_data('_i_', default_value=noStr())
        '_i_'
        >>> dsp.add_function('dispatch', dispatch, ['_i_n_p_u_t'], ['e', 'f'])
        'dispatch'
        >>> w, o = dsp.dispatch()

        >>> f1 = plot_dsp_graphviz(dsp, workflow=True)
        >>> f1.view()
        'main.gv.pdf'
    """

    if workflow:
        g = workflow if isinstance(workflow, DiGraph) else dsp.workflow
        dfl = {}
    else:
        g = dsp.dmap
        dfl = dsp.default_values

    if dot is None:
        dot = Digraph('main', format='svg')
        dot.node_attr.update(style='filled')
        cnt = count(0).__next__

    dot_name = dot.name
    dot_node = dot.node

    def id_node(k):
        return '%s_%s' %(dot_name, hash(k))

    if START in g.node:
        kw = {'shape': 'triangle', 'fillcolor': 'orange'}
        dot_node(id_node(START), 'start', **kw)

    for k, v in g.node.items():
        n = dsp.nodes.get(k, {})
        if n:
            data_label = k

            data_type = n['type']

            if data_type == 'function':

                fun = n.get('function', None)

                kw = {'shape': 'box', 'fillcolor': 'springgreen'}

                if isinstance(fun, SubDispatch):
                    sub = Digraph('cluster_%s' % cnt())

                    w = v.get('workflow', False)
                    t = '%s:%s' %(title, k)
                    sub = plot_dsp_graphviz(fun.dsp, w, t, sub, cnt)

                    sub.body.extend([
                        'style=filled',
                        'fillcolor=gray',
                        'color=black'
                    ])

                    dot.subgraph(sub)
                    kw.update({
                        'color': 'black',
                        'fillcolor': 'gray'
                    })

            elif data_type == 'data':
                kw = {'shape': 'oval', 'fillcolor': 'cyan'}
                try:
                    data_label = '%s\n default = %s' % (k, str(dfl[k]))
                except:
                    pass

            else:
                continue

            dot.node(id_node(k), data_label, **kw)

    for u, v, a in g.edges_iter(data=True):
        try:
            kw = {'label': str(a['value'])}
        except:
            kw = {}
        dot.edge(id_node(u), id_node(v), **kw)

    dot.body.append('label = "%s"'% title)
    dot.body.append('splines = ortho')

    return dot
