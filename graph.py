#
#   Copyright 2009 Benjamin Mellor
#
#   This file is part of Fundy.
#
#   Fundy is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from utils import dot_node, dot_link, rset

class NodePtr(object):
    """
    A NodePtr is a reference to a node.

    It can be dynamically reassigned. All other objects that want to refer to a
    node should do it through a NodePtr, allowing the reference to be
    over-written in place to point to a new node. Otherwise, this would be
    possible in Python, but not in RPython as it is not possible to change the
    __class__ to a different subclass of Node.

    The primary reason for this explicit indirection is that reduction of a node
    should be able to replace the original node with its reduction in-place, or
    other references to the same node would have to reduce it again.
    """
    def __init__(self, node):
        self.node = node

    # XXX: The eq and hash methods need to be defined for passing to r_dict
    # in the construction of each node's rset to hold NodePtrs of the node's
    # types. They are defined so that two NodePtrs pointing to the same node
    # will be considered the "same" NodePtr. The reason for not using the
    # special names __eq__ and __hash__ is that RPython does not understand
    # these special methods, which would introduce a subtle behavioural
    # difference between the translated and untranslated interpreters.
    def eq(self, other):
        return self.node is other.node

    # FIXME: Cannot use ``hash()`` in RPython.
    def hash(self):
        return 0

    def add_type(self, typeptr):
        self.node.add_type(typeptr)

    def nodeid(self):
        """
        Return a unique identifier for the node pointed at.
        """
        return self.node.nodeid()

    def reduce_WHNF_inplace(self):
        """
        Replace the pointed at node with the result of reducing that node
        to weak head normal form.
        """
        self.node = self.node.reduce_WHNF()

    def get_applied_node(self, argument_ptr):
        """
        Apply the pointed at node to argument, returning a new node.
        """
        return self.node.apply(argument_ptr)

    def get_instantiated_node(self, replace_this_ptr, with_this_ptr):
        """
        Instantiate the node inside this ptr, returning a new node. The graph
        under the new node is the result of copying the graph under the original
        ptr's node, but replacing all references to replace_this with
        references to with_this.
        replace_this and with_this are both node pointers, not nodes.
        """
        return self.node.instantiate(replace_this_ptr, with_this_ptr)

    def get_instantiated_node_ptr(self, replace_this_ptr, with_this_ptr):
        """
        Like get_instantiated_node, but return a new NodePtr pointing to the
        node instead of returning the node directly. Convenience function for
        the deeper levels of instantiation that are creating new pointers to new
        nodes, as opposed to the top level of instantiation that is returning a
        node for a pointer being reduced to overwrite its node with.
        """
        new_node = self.node.instantiate(replace_this_ptr, with_this_ptr)
        if new_node is self.node:
            # shouldn't make a new pointer to the same node
            return self
        else:
            return NodePtr(new_node)

    def __repr__(self, toplevel=True):
        """
        NOT_RPYTHON:
        """
        # toplevel is just to make sure that the repr for a NodePtr says that
        # it's a NodePtr, whereas the repr for a node doesn't, but only at
        # the top level, so the graph is easier to read
        if toplevel:
            return '*(%s)' % self.node.__repr__(False)
        else:
            return self.node.__repr__(toplevel)

    def dot(self, already_seen=None):
        """
        NOT_RPYTHON: Yield dot format description of the graph under this node.

        already_seen should be a set of nodes (not node pointers!) already seen,
        that will be ignored. Defaults to nothing, so is mostly only needed when
        implementing a dot method.

        Forwards to the node object itself. Will yield each graph element
        separately.
        """
        for dot in self.node.dot(already_seen):
            yield dot


class Node(object):
    """
    Base class for the different kinds of node.

    The methods here do not modify the nodes, they return new nodes.

    Nodes should have NodePtr data members, not refer directly to other Nodes.
    """
    def __init__(self):
        self.types = rset(NodePtr.eq, NodePtr.hash)

    def nodeid(self):
        """
        Return a unique identifier for this node.
        """
        return id(self)

    def reduce_WHNF(self):
        """
        Return a Node that is the result of reducing this Node to weak head
        normal form. Either returns a new Node, or self.
        """
        return self     # by default reduction doesn't change nodes

    def instantiate(self, replace_this_ptr, with_this_ptr):
        """
        Instantiate a node, returning a node that is the result of replacing
        one ptr with another in the subgraph under this node. Returns self
        only in the case where it is absolutely known that replace_this_ptr
        cannot occur in the subgraph under this node (basically at leaf nodes).
        """
        raise NotImplementedError

    def apply(self, argument_ptr):
        """
        Apply a node to an argument, returning a node that is the result of
        the application.
        """
        raise TypeError   # only lambdas and builtins can be applied

    def to_string(self):
        raise NotImplementedError

    def add_type(self, typeptr):
        self.types.add(typeptr)

    def __repr__(self, toplevel=True):
        """
        NOT_RPYTHON:
        """
        return "NODE_WITHOUT_REPR"

    def dot(self, already_seen=None):
        """
        NOT_RPYTHON: Yield a description of the graph under this node.
        """
        if already_seen is None:
            already_seen = set()

        if self not in already_seen:
            already_seen.add(self)
            yield dot_node(self.nodeid(), shape='tripleoctagon',
                           label='UNRENDERABLE', color='red')
            for dot in self.dot_types(already_seen):
                yield dot

    @classmethod
    def add_instantiate_fn(cls, *attr_names):
        """
        NOT_RPYTHON: Add an instantiation function to the class.

        This is to define the common instantiation pattern in one place:

            for each attr:
                if attr is the thing to replace, replace it
                else replace attr with its own instantiation
            if all replacement attrs are the same as the original, return self
            else return new node created with the replacement attrs

        This function is not RPython, but the function it returns must be,
        which is why it is defined by eval()ing a string instead of using the
        perfectly adequate capabilities of Python.

        Manually defining an instantiation function that does this logic can
        be replaced by:

        class FOO:
            ...
        FOO.add_instantiate_fn(attr1, attr2, ..., attrN)

        attr1, attr2, ..., attrN must all be the names of data members of FOO
        nodes, and must all be of type NodePtr. Constructing a valid FOO must
        also be able to be acomplished by FOO(attr1, attr2, ..., attrN) (i.e.
        in the same order as the attributes appeared in the call to
        add_instantiate_fn).
        """
        conj_fragments = []
        arg_fragments = []
        func_fragments = ["def instantiate(self, replace_this_ptr, "
                                           "with_this_ptr):\n"]
        for name in attr_names:
            s = ("    if self.%(name)s is replace_this_ptr:\n"
                 "        new_%(name)s = with_this_ptr\n"
                 "    else:\n"
                 "        new_%(name)s = self.%(name)s."
                                    "get_instantiated_node_ptr("
                                        "replace_this_ptr, with_this_ptr)\n"
                ) % {'name': name}
            func_fragments.append(s)
            conj_fragments.append("new_%(name)s is self.%(name)s" %
                                        {'name': name})
            arg_fragments.append("new_%(name)s" % {'name': name})

        conj_fragments.append('replace_this_ptr is not None')
        func_fragments += ["    if ", ' and '.join(conj_fragments), ":\n"
                           "        return self\n"
                           "    else:\n"
                           "        return ", cls.__name__, "(",
                                        ', '.join(arg_fragments), ")\n"]

        func_str = ''.join(func_fragments)
        exec func_str
        cls.instantiate = instantiate
    # end def add_instantiate_fn

    def dot_types(self, already_seen=None):
        """
        NOT_RPYTHON:
        """
        if already_seen is None:
            already_seen = set()

        for typeptr in self.types:
            yield dot_link(self.nodeid(), typeptr.nodeid(),
                           color='cyan', style='dashed')
            for dot in typeptr.dot(already_seen):
                yield dot


    @classmethod
    def add_dot_fn(cls, self_spec, **attrs):
        """
        NOT_RPYTHON: Add a dot method to the class.

        This is to define the common dot render pattern in one place:

            if haven't already seen self:
                record that have seen self
                yield render of self as a node (with various parameters)
                for each attr:
                    yield render of link to attr (with various parameters)
                    yield whatever attr.dot() yields
                for each type:
                    yield render of link to type
                    yield whaever type.dot() yields

        self_spec should be a dictionary of parameters for the graph node to be
        rendered for nodes of this class: color (note US spelling!), shape, etc.

        Each extra keyword argument should be the name of an attribute that
        holds a NodePtr. Its value should be a dictionary of parameters for the
        link to be rendered.

        Manually defining a dot function that does this logic can be replaced
        by:

        class FOO:
            ...
        FOO.add_dot_fn(dict(...), attr1=dict(...), ..., attrN=dict(...))

        This function is not RPython, and the methods it creates do not have to
        be RPython at the moment either, as actually viewing the dot files that
        can be generated by these methods depends on PyGame, which is obviously
        not RPython, and so is only available when running on top of CPython.
        """
        # Compare with the hackery in add_instantiate_fn above;
        # this sort of thing is so much easier in Python than RPython.
        # Will be a pain to convert this if graph viewing is ever supported at
        # runtime in the translated interpreter.
        def dot(self, already_seen=None):
            """
            NOT_RPYTHON: autogenerated dot method for class %s
            """ % cls.__name__
            if already_seen is None:
                already_seen = set()

            if self not in already_seen:
                already_seen.add(self)

                local_self_spec = self_spec.copy()
                for k in local_self_spec:
                    if callable(local_self_spec[k]):
                        local_self_spec[k] = local_self_spec[k](self)

                yield dot_node(self.nodeid(), **local_self_spec)

                for attr_name, link_spec in attrs.items():
                    local_link_spec = link_spec.copy()
                    for k in local_link_spec:
                        if callable(local_link_spec[k]):
                            local_link_spec[k] = local_link_spec[k](self)

                    attr_val = getattr(self, attr_name)
                    if attr_val is not None:
                        yield dot_link(self.nodeid(), attr_val.nodeid(),
                                       **local_link_spec)
                        for thing in attr_val.dot(already_seen):
                            yield thing

                for dot in self.dot_types(already_seen):
                    yield dot
        # end def dot

        cls.dot = dot
    # end def add_dot_fn
# end class Node


class ApplicationNode(Node):
    def __init__(self, functor, argument):
        Node.__init__(self)
        self.functor = functor
        self.argument = argument

    def reduce_WHNF(self):
        self.functor.reduce_WHNF_inplace()
        # self.functor should now be a lambda node or a builtin node
        new_node = self.functor.get_applied_node(self.argument)
        # now try to reduce the result, in case it returned another application
        return new_node.reduce_WHNF()

    def __repr__(self, toplevel=True):
        """
        NOT_RPYTHON:
        """
        return 'Application(%s to %s)' % (self.functor.__repr__(False),
                                          self.argument.__repr__(False))

ApplicationNode.add_instantiate_fn('functor', 'argument')
ApplicationNode.add_dot_fn(dict(shape='ellipse', label='apply'),
                           functor=dict(color='red', label='f'),
                           argument=dict(color='purple', label='a'))

class LambdaNode(Node):
    def __init__(self, parameter, body):
        Node.__init__(self)
        self.parameter = parameter
        self.body = body

    def apply(self, argument):
        if self.body is self.parameter:     # if the body is just the param
            return argument.node            # just return the arg node now
        return self.body.get_instantiated_node(self.parameter, argument)

    def instantiate(self, replace_this_ptr, with_this_ptr):
        # TODO: this assertion was causing test failures, and removing it
        # doesn't cause any; maybe my reasoning is wrong and it's not actually
        # necessary; investigate!
        #assert replace_this_ptr is not self.parameter, ("Don't instantiate "
        #        "a lambda replacing its parameter, apply it to something")

        if self.body is replace_this_ptr:
            new_body = with_this_ptr
        else:
            new_body = self.body.get_instantiated_node_ptr(replace_this_ptr,
                                                           with_this_ptr)

        if new_body is self.body and replace_this_ptr is not None:
            return self
        else:
            # Make a new lambda node with a new parameter node, but then have
            # to instantiate the body *again* to replace references to the old
            # lambda's parameter node with the new parameter node. The old
            # lambda's parameter cannot just be reused, as the original lambda
            # might still be referenced from somewhere, and if one lambda ends
            # up inside the other, then we have two lambdas both trying to bind
            # the same free variable. If they could be guaranteed to remain
            # disjoint, this actually wouldn't be a problem, as it is only
            # *references* to a parameter that get replaced.
            new_param = Param()
            new_body = new_body.get_instantiated_node_ptr(self.parameter,
                                                          new_param)
            return LambdaNode(new_param, new_body)

    def __repr__(self, toplevel=True):
        """
        NOT_RPYTHON:
        """
        return 'LAMBDA %s --> %s' % (self.parameter.__repr__(False),
                                     self.body.__repr__(False))

LambdaNode.add_dot_fn(dict(shape='octagon', label='lambda'),
                      parameter=dict(color='blue', label='p'),
                      body=dict(color='green'))


class ParameterNode(Node):
    # used in __repr__ of ParameterNode, should not be needed by translation
    _param_dict = {}

    # parameter nodes don't actually hold any information other than
    # their identity, so there's no __init__ function

    def instantiate(self, replace_this_ptr, with_this_ptr):
        # parameters have no children, so do not need to make a copy as it will
        # always be identical to the original (and this simplifies instantiation
        # of lambda nodes, which assume they can just reuse the parameter node)
        return self

    def __repr__(self, toplevel=True):
        """
        NOT_RPYTHON:
        """
        if not self in self._param_dict:
            self._param_dict[self] = 'v%d' % len(self._param_dict)
        return self._param_dict[self]

ParameterNode.add_dot_fn(dict(shape='octagon', label='param', color='blue'))


class FixfindNode(Node):
    """
    This implements the Y combinator, which finds the fixpoint of lambda terms.
    """
    def apply(self, argument):
        return ApplicationNode(argument.get_instantiated_node_ptr(None, None),
                               Application(Y, argument))

    def instantiate(self, replace_this_ptr, with_this_ptr):
        # Y node has no substructure, so don't make a copy
        return self

    def __repr__(self, toplevel=True):
        return "Y"

FixfindNode.add_dot_fn(dict(shape='ellipse', label='Y', color='green'))


class BuiltinNode(Node):
    def __init__(self):
        Node.__init__(self)

    def __repr__(self, toplevel=True):
        """
        NOT_RPYTHON:
        """
        return 'BUILTIN %s' % self.func.func_name

    def dot(self, already_seen=None):
        """
        NOT_RPYTHON:
        """
        if already_seen is None:
            already_seen = set()

        # NOTE: here we depend on all descendent classes of BuiltinNode
        # having a func member (which we could not do in RPython, unless they
        # all had the same type). But this is Python, so we can just override
        # this method anywhere the assumption doesn't hold.
        if self not in already_seen:
            already_seen.add(self)
            yield dot_node(self.nodeid(), shape='octagon', color='green',
                           label=self.func.func_name)
            for dot in self.dot_types(already_seen):
                yield dot


class TypeswitchNode(Node):
    def __init__(self, cases):
        self.cases = cases

    def apply(self, argument):
        argument.reduce_WHNF_inplace()
        for c in self.cases:
            assert isinstance(c.node, ConsNode)
            case_type = c.node.a
            case_ret = c.node.b
            case_type.reduce_WHNF_inplace()
            if argument.node.types.contains(case_type):
                return case_ret.node
        raise TypeError("typeswitch found no match")

    def instantiate(self, replace_this_ptr, with_this_ptr):
        new_cases = []
        for c in self.cases:
            if c is replace_this_ptr:
                new_cases.append(with_this_ptr)
            else:
                new_cases.append(c.get_instantiated_node_ptr(replace_this_ptr,
                                                             with_this_ptr))
        return TypeswitchNode(new_cases)

    def __repr__(self, toplevel=True):
        """
        NOT_RPYTHON:
        """
        cases = ["case %s return %s" % (c.node.a.__repr__(toplevel),
                                        c.node.b.__repr__(toplevel))
                 for c in self.cases]
        return "typeswitch: [%s]" % ', '.join(cases)

    def dot(self, already_seen=None):
        """
        NOT_RPYTHON:
        """
        if already_seen is None:
            already_seen = set()

        if self not in already_seen:
            yield dot_node(self.nodeid(), shape='octagon', label='typeswitch',
                           color='cyan')
            for case in self.cases:
                yield dot_link(self.nodeid(), case.nodeid(), color='cyan')
                for thing in case.dot(already_seen):
                    yield thing


class ValueNode(Node):
    """
    Base class for nodes containing values.
    """
    pass


class ConsNode(ValueNode):
    """
    Cons node contains two other nodes. (pointers!)
    """
    def __init__(self, a, b):
        Node.__init__(self)
        self.a = a
        self.b = b

    def to_string(self):
        return self.a.node.to_string() + " . " + self.b.node.to_string()

    def __repr__(self, toplevel=True):
        """
        NOT_RPYTHON:
        """
        return '% . %' % (self.a.__repr__(toplevel), self.b.__repr__(toplevel))

    @staticmethod
    def make_tree(leaves):
        """
        Return a (pointer to) a tree of Cons nodes with the given leaves.

        The elements of leaves must be NodePtrs. This function will always
        generate trees with the same "shape" for the same number of inputs.
        i.e. make_tree(a1, a2, ... aN) and make_tree(b1, b2, ... bN) will put
        a1 and b1 in analagous positions, etc.
        """
        if len(leaves) == 1:
            return leaves[0]
        else:
            pivot = len(leaves) / 2
            left = leaves[:pivot]
            right = leaves[pivot:]
            return Cons(ConsNode.make_tree(left), ConsNode.make_tree(right))

ConsNode.add_instantiate_fn('a', 'b')
ConsNode.add_dot_fn(dict(shape='box', color='maroon', label='cons'),
                    a=dict(color='maroon', label='a'),
                    b=dict(color='maroon', label='b'))


class PrimitiveNode(ValueNode):
    def __init__(self):
        Node.__init__(self)

    def instantiate(self, replace_this_ptr, with_this_ptr):
        return self

    def eq(self, other):
        raise NotImplementedError

    def __repr__(self, toplevel=True):
        return 'VALUE %s' % self.to_repr()
PrimitiveNode.add_dot_fn(dict(shape='box', color='purple',
                         label=lambda self:self.to_repr()))

class LabelledValueNode(PrimitiveNode):
    """
    Represents a value that contains no information other than its identity.
    """
    def __init__(self, name=None):
        PrimitiveNode.__init__(self)
        self.name = name

    def to_string(self):
        if self.name:
            return self.name
        else:
            return "<void>"

    to_repr = to_string

    def eq(self, other):
        return self.name == other.name


def Application(functor, argument):
    """
    Helper function to make pointers to new application nodes
    """
    return NodePtr(ApplicationNode(functor, argument))

def Lambda(param, body):
    """
    Helper function to make pointers to new lambda nodes
    """
    return NodePtr(LambdaNode(param, body))

def Param():
    """
    Helper function to make pointers to new parameter nodes
    """
    return NodePtr(ParameterNode())

def Typeswitch(cases):
    """
    Helper function to make pointers to new typeswitch nodes.
    """
    return NodePtr(TypeswitchNode(cases))

def Cons(a, b):
    """
    Helper function to make pointers to new cons nodes.
    """
    return NodePtr(ConsNode(a, b))

def LabelledValue(name=None):
    """
    Helper function to make pointers to new empty value nodes.
    """
    return NodePtr(LabelledValueNode(name))

# define the Y combinator; don't really need a function to make new ones!
Y = NodePtr(FixfindNode())
