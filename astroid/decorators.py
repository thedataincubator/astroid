# copyright 2003-2013 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
# contact http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This file is part of astroid.
#
# astroid is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by the
# Free Software Foundation, either version 2.1 of the License, or (at your
# option) any later version.
#
# astroid is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License
# for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with astroid. If not, see <http://www.gnu.org/licenses/>.
#
# The code in this file was originally part of logilab-common, licensed under
# the same license.

""" A few useful function/method decorators."""

import functools

import wrapt

from astroid import context as contextmod
from astroid import exceptions
from astroid import util


@wrapt.decorator
def cached(func, instance, args, kwargs):
    """Simple decorator to cache result of method calls without args."""
    cache = getattr(instance, '__cache', None)
    if cache is None:
        instance.__cache = cache = {}
    try:
        return cache[func]
    except KeyError:
        cache[func] = result = func(*args, **kwargs)
        return result


class cachedproperty(object):
    """ Provides a cached property equivalent to the stacking of
    @cached and @property, but more efficient.

    After first usage, the <property_name> becomes part of the object's
    __dict__. Doing:

      del obj.<property_name> empties the cache.

    Idea taken from the pyramid_ framework and the mercurial_ project.

    .. _pyramid: http://pypi.python.org/pypi/pyramid
    .. _mercurial: http://pypi.python.org/pypi/Mercurial
    """
    __slots__ = ('wrapped',)

    def __init__(self, wrapped):
        try:
            wrapped.__name__
        except AttributeError:
            util.reraise(TypeError('%s must have a __name__ attribute'
                                   % wrapped))
        self.wrapped = wrapped

    @property
    def __doc__(self):
        doc = getattr(self.wrapped, '__doc__', None)
        return ('<wrapped by the cachedproperty decorator>%s'
                % ('\n%s' % doc if doc else ''))

    def __get__(self, inst, objtype=None):
        if inst is None:
            return self
        val = self.wrapped(inst)
        setattr(inst, self.wrapped.__name__, val)
        return val


def path_wrapper(func):
    """return the given infer function wrapped to handle the path"""
    # TODO: switch this to wrapt after the monkey-patching is fixed (ceridwen)
    @functools.wraps(func)
    def wrapped(node, context=None, _func=func, **kwargs):
        """wrapper function handling context"""
        if context is None:
            context = contextmod.InferenceContext()
        if context.push(node):
            return

        yielded = set()
        generator = _func(node, context, **kwargs)
        try:
            while True:
                res = next(generator)
                # unproxy only true instance, not const, tuple, dict...
                if res.__class__.__name__ == 'Instance':
                    ares = res._proxied
                else:
                    ares = res
                if ares not in yielded:
                    yield res
                    yielded.add(ares)
        except StopIteration as error:
            # Explicit StopIteration to return error information, see
            # comment in raise_if_nothing_inferred.
            if len(error.args) > 0:
                raise StopIteration(error.args[0])
            else:
                raise StopIteration

    return wrapped


@wrapt.decorator
def yes_if_nothing_inferred(func, instance, args, kwargs):
    inferred = False
    for node in func(*args, **kwargs):
        inferred = True
        yield node
    if not inferred:
        yield util.Uninferable


@wrapt.decorator
def raise_if_nothing_inferred(func, instance, args, kwargs):
    '''All generators wrapped with raise_if_nothing_inferred *must*
    explicitly raise StopIteration with information to create an
    appropriate structured InferenceError.

    '''
    # TODO: Explicitly raising StopIteration in a generator will cause
    # a RuntimeError in Python >=3.7, as per
    # http://legacy.python.org/dev/peps/pep-0479/ .  Before 3.7 is
    # released, this code will need to use one of four possible
    # solutions: a decorator that restores the current behavior as
    # described in
    # http://legacy.python.org/dev/peps/pep-0479/#sub-proposal-decorator-to-explicitly-request-current-behaviour
    # , dynamic imports or exec to generate different code for
    # different versions, drop support for all Python versions <3.3,
    # or refactoring to change how these decorators work.  In any
    # event, after dropping support for Python <3.3 this code should
    # be refactored to use `yield from`.
    inferred = False
    try:
        generator = func(*args, **kwargs)
        while True:
            yield next(generator)
            inferred = True
    except StopIteration as error:
        if not inferred:
            if len(error.args) > 0:
                raise exceptions.InferenceError(**error.args[0])
            else:
                raise exceptions.InferenceError(
                    'StopIteration raised without any error information.')
