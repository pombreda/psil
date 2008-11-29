"""PSIL: Python S-expresssion Intermediate Language

>>> eval(read("1"))
1
>>> eval(read("'(1 2 3)"))
[1, 2, 3]
>>> eval(read("(map (lambda (x) (* x x)) '(1 2 3))"))
[1, 4, 9]
>>> eval(read("(apply + '(1 2))"))
3

"""

import re

RE_NUMBER = re.compile(r"[-+]?\d+(\.\d+)?(e[-+]?\d+)?", re.IGNORECASE)
RE_SYMBOL = re.compile(r"[^ \t\n\)]+", re.IGNORECASE)

peval = eval

Symbols = {}

class SyntaxError(Exception):
    def __init__(self, s):
        Exception.__init__(self, s)

class UndefinedSymbolError(Exception):
    def __init__(self, s):
        Exception.__init__(self, s)

class SetNotSymbolError(Exception):
    pass

class Token(object):
    LPAREN = object()
    RPAREN = object()
    QUOTE  = object()
    QQUOTE = object()
    COMMA  = object()
    SPLICE = object()
    SYMBOL = object()
    NUMBER = object()
    STRING = object()

def tokenise(s):
    """
    >>> [x[1] for x in tokenise("1")]
    [1]
    >>> [x[1] for x in tokenise("()")]
    ['(', ')']
    >>> [x[1] for x in tokenise("a")]
    ['a']
    >>> [x[1] for x in tokenise("'a")]
    ["'", 'a']
    >>> [x[1] for x in tokenise('''"test"''')]
    ['test']
    >>> [x[1] for x in tokenise('''(a 1 "test" 'c)''')]
    ['(', 'a', 1, 'test', "'", 'c', ')']
    """
    i = 0
    while True:
        while i < len(s) and s[i] in " \t\n":
            i += 1
        if i >= len(s):
            break
        if   s[i] == "(":
            yield (Token.LPAREN, s[i])
            i += 1
        elif s[i] == ")":
            yield (Token.RPAREN, s[i])
            i += 1
        elif s[i] == "'":
            yield (Token.QUOTE, s[i])
            i += 1
        elif s[i] == "`":
            yield (Token.QQUOTE, s[i])
            i += 1
        elif s[i] == ",":
            if s[i+1] == "@":
                yield (Token.SPLICE, s[i:i+2])
                i += 2
            else:
                yield (Token.COMMA, s[i])
                i += 1
        elif s[i] == '"':
            j = s.index('"', i+1)
            yield (Token.STRING, peval(s[i:j+1]))
            i = j + 1
        elif s[i] == ";":
            i = s.index("\n", i+1)
        else:
            m = RE_NUMBER.match(s[i:])
            if m:
                if m.group(1) or m.group(2):
                    x = float(m.group(0))
                    yield (Token.NUMBER, x)
                else:
                    yield (Token.NUMBER, int(m.group(0)))
                i += m.end(0)
            else:
                m = RE_SYMBOL.match(s[i:])
                if m:
                    yield (Token.SYMBOL, m.group(0))
                    i += m.end(0)
                else:
                    raise SyntaxError(s[i:])

class Symbol(object):
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return "<%s>" % self.name
    names = {}
    @staticmethod
    def new(name):
        if name in Symbol.names:
            return Symbol.names[name]
        s = Symbol(name)
        Symbol.names[name] = s
        return s

Symbol.quote            = Symbol.new("quote")
Symbol.quasiquote       = Symbol.new("quasiquote")
Symbol.unquote          = Symbol.new("unquote")
Symbol.unquote_splicing = Symbol.new("unquote-splicing")

Symbol.define           = Symbol.new("define")
Symbol.defmacro         = Symbol.new("defmacro")
Symbol.if_              = Symbol.new("if")
Symbol.lambda_          = Symbol.new("lambda")
Symbol.set              = Symbol.new("set!")

def parse(tokens, next = None):
    if next is None:
        try:
            next = tokens.next()
        except StopIteration:
            return None
    t, v = next
    if t == Token.LPAREN:
        a = []
        while True:
            next = tokens.next()
            if next[0] == Token.RPAREN:
                break
            a.append(parse(tokens, next))
        return a
    elif t == Token.STRING:
        return v
    elif t == Token.NUMBER:
        return v
    elif t == Token.QUOTE:
        return [Symbol.quote, parse(tokens)]
    elif t == Token.QQUOTE:
        return [Symbol.quasiquote, parse(tokens)]
    elif t == Token.COMMA:
        return [Symbol.unquote, parse(tokens)]
    elif t == Token.SPLICE:
        return [Symbol.unquote_splicing, parse(tokens)]
    elif t == Token.SYMBOL:
        return Symbol.new(v)
    else:
        raise SyntaxError(next)

def read(s):
    """
    >>> read("1")
    1
    >>> read("()")
    []
    >>> read("a")
    <a>
    >>> read('''"test"''')
    'test'
    >>> read('''("test")''')
    ['test']
    >>> read('''(a 1 "test")''')
    [<a>, 1, 'test']
    >>> read("(a (b c) d)")
    [<a>, [<b>, <c>], <d>]
    >>> read("(+ 1 2)")
    [<+>, 1, 2]
    """
    return parse(tokenise(s))

class Scope(object):
    def __init__(self, parent = None):
        self.parent = parent
        self.symbols = {}
    def define(self, name, value):
        self.symbols[name] = value
        return value
    def set(self, name, value):
        s = self
        while s is not None:
            if name in s.symbols:
                s.symbols[name] = value
                return
            s = s.parent
        raise UndefinedSymbolError(name)
    def lookup(self, name):
        s = self
        while s is not None:
            r = s.symbols.get(name)
            if r is not None:
                return r
            s = s.parent
        return None
    def eval(self, s):
        if isinstance(s, list) and len(s) > 0:
            f = s[0]
            if isinstance(f, Symbol):
                if f is Symbol.define:
                    if isinstance(s[1], Symbol):
                        return self.define(s[1].name, self.eval(s[2]))
                    else:
                        return self.define(s[1][0].name, Function(s[1][1:], s[2:], self))
                if f is Symbol.defmacro:
                    return self.define(s[1].name, Macro(s[2], [s[3]], self))
                if f is Symbol.if_:
                    if self.eval(s[1]):
                        return self.eval(s[2])
                    else:
                        return self.eval(s[3])
                if f is Symbol.lambda_:
                    return Function(s[1], s[2:], self)
                if f is Symbol.quasiquote:
                    def qq(t, depth=1):
                        if isinstance(t, list):
                            if len(t) > 0 and isinstance(t[0], Symbol):
                                if t[0] is Symbol.quasiquote:
                                    return [t[0], qq(t[1], depth + 1)]
                                if t[0] is Symbol.unquote:
                                    if depth == 1:
                                        return self.eval(t[1])
                                    else:
                                        return [t[0], qq(t[1], depth - 1)]
                            r = []
                            for x in t:
                                if isinstance(x, list) and len(x) > 0 and isinstance(x[0], Symbol) and x[0] is Symbol.unquote_splicing:
                                    if depth == 1:
                                        r.extend(self.eval(x[1]))
                                    else:
                                        return [x[0], qq(x[1], depth - 1)]
                                else:
                                    r.append(qq(x, depth))
                            return r
                        else:
                            return t
                    return qq(s[1])
                if f is Symbol.quote:
                    return s[1]
                if f is Symbol.set:
                    if not isinstance(s[1], Symbol):
                        raise SetNotSymbolError(s[1])
                    val = self.eval(s[2])
                    self.set(s[1].name, val)
                    return val
                if f.name.startswith("."):
                    return apply(getattr(self.eval(s[1]), f.name[1:]), [self.eval(x) for x in s[2:]])
            fn = self.eval(f)
            if isinstance(fn, Macro):
                return self.eval(apply(fn, s[1:]))
            else:
                return apply(fn, [self.eval(x) for x in s[1:]])
        elif isinstance(s, Symbol):
            r = self.lookup(s.name)
            if r is None:
                # doctest seems to make __builtins__ a dict instead of a module
                if isinstance(__builtins__, dict) and s.name in __builtins__:
                    r = __builtins__[s.name]
                elif s.name in dir(__builtins__):
                    r = getattr(__builtins__, s.name)
                else:
                    raise UndefinedSymbolError(s.name)
            return r
        else:
            return s

class Function(object):
    def __init__(self, params, body, scope):
        self.params = []
        self.fixed = 0
        self.rest = None
        if isinstance(params, Symbol):
            self.rest = params
            params = []
        elif len(params) >= 2 and params[-2].name == ".":
            self.rest = params[-1]
            params = params[:-2]
        for p in params:
            if isinstance(p, list) and len(p) > 0 and isinstance(p[0], Symbol) and p[0].name == "o":
                self.params.append(p[1])
            else:
                self.params.append(p)
                self.fixed += 1
        self.body = body
        self.scope = scope
    def __call__(self, *args):
        scope = Scope(self.scope)
        if self.params is not None:
            if isinstance(self.params, list):
                assert len(args) >= self.fixed
                if self.rest is not None:
                    if len(args) > len(self.params):
                        scope.define(self.rest.name, list(args[len(self.params):]))
                    else:
                        scope.define(self.rest.name, None)
                else:
                    assert len(args) <= len(self.params)
                for p, a in zip(self.params, list(args) + [None] * (len(self.params) - len(args))):
                    scope.define(p.name, a)
            else:
                scope.define(self.params.name, list(args))
        r = None
        for b in self.body:
            r = scope.eval(b)
        return r

class Macro(Function):
    pass

def eval(s):
    """
    >>> eval(read("1"))
    1
    >>> eval(read("(+ 1 2 3)"))
    6
    >>> eval(read("((lambda (x) (* x x)) 3)"))
    9
    >>> eval(read("(define (test fn x y) ((if fn * +) x y))"))
    <__main__.Function object at 0x...>
    >>> eval(read("(test True 2 3)"))
    6
    >>> eval(read("(test False 2 3)"))
    5
    """
    return Globals.eval(s)

Globals = Scope()

Globals.symbols["macroexpand"] = lambda x: apply(Globals.lookup(x[0].name), x[1:])

Globals.symbols["+"]         = lambda *args: sum(args)
Globals.symbols["-"]         = lambda *args: -args[0] if len(args) == 1 else reduce(lambda x, y: x - y, args)
Globals.symbols["*"]         = lambda *args: reduce(lambda x, y: x * y, args, 1)
Globals.symbols["**"]        = lambda x, y: x ** y
Globals.symbols["/"]         = lambda *args: 1.0/args[0] if len(args) == 1 else reduce(lambda x, y: x / y, args)
Globals.symbols["//"]        = lambda *args: reduce(lambda x, y: x // y, args)
Globals.symbols["%"]         = lambda x, y: x % tuple(y) if isinstance(y, list) else x % y
Globals.symbols["<<"]        = lambda x, y: x << y
Globals.symbols[">>"]        = lambda x, y: x >> y
Globals.symbols["&"]         = lambda *args: reduce(lambda x, y: x & y, args, -1)
Globals.symbols["|"]         = lambda *args: reduce(lambda x, y: x | y, args, 0)
Globals.symbols["^"]         = lambda x, y: x ^ y
Globals.symbols["~"]         = lambda x: ~x
def _all(p, a):
    for i in range(len(a)-1):
        if not p(a[i], a[i+1]):
            return False
    return True
Globals.symbols["<"]         = lambda *args: _all(lambda x, y: x < y, args)
Globals.symbols[">"]         = lambda *args: _all(lambda x, y: x > y, args)
Globals.symbols["<="]        = lambda *args: _all(lambda x, y: x <= y, args)
Globals.symbols[">="]        = lambda *args: _all(lambda x, y: x >= y, args)
Globals.symbols["=="]        = lambda *args: _all(lambda x, y: x == y, args)
Globals.symbols["!="]        = lambda x, y: x != y
Globals.symbols["is"]        = lambda *args: _all(lambda x, y: x is y, args)
Globals.symbols["is-not"]    = lambda x, y: x is not y
Globals.symbols["in"]        = lambda x, y: x in y
Globals.symbols["not-in"]    = lambda x, y: x not in y
Globals.symbols["and"]       = lambda *args: _all(lambda x, y: x and y, args)
# TODO: and, or as macros?
Globals.symbols["not"]       = lambda x: not x

def _del(x, y):
    del x[y]
Globals.symbols["del"]       = _del
def _print(*a):
    print "".join(str(x) for x in a)
Globals.symbols["print"]     = _print
# TODO: raise
Globals.symbols["import"] = lambda x: Globals.define(x.name, __import__(x.name))
Globals.symbols["include"] = lambda x: include(x)

Globals.symbols["list"]     = lambda *args: list(args)
Globals.symbols["list?"]    = lambda x: isinstance(x, list)
Globals.symbols["cons"]     = lambda x, y: [x] + y if isinstance(y, list) else [x]
def _set_car(x, y): x[0] = y
Globals.symbols["set-car!"] = _set_car
Globals.symbols["car"]    = lambda x: x[0]
Globals.symbols["cdr"]    = lambda x: x[1:]
Globals.symbols["caar"]   = lambda x: x[0][0]
Globals.symbols["cadr"]   = lambda x: x[1]
Globals.symbols["cdar"]   = lambda x: x[0][1:]
Globals.symbols["cddr"]   = lambda x: x[2:]
Globals.symbols["caaar"]  = lambda x: x[0][0][0]
Globals.symbols["caadr"]  = lambda x: x[1][0]
#Globals.symbols["cadar"]  = lambda x: x[0][1][0] # TODO
#Globals.symbols["caddr"]  = lambda x: x[0][0][0]
#Globals.symbols["cdaar"]  = lambda x: x[0][0][0]
#Globals.symbols["cdadr"]  = lambda x: x[0][0][0]
#Globals.symbols["cddar"]  = lambda x: x[0][0][0]
#Globals.symbols["cdddr"]  = lambda x: x[0][0][0]
Globals.symbols["caaaar"] = lambda x: x[0][0][0][0]
#...
Globals.symbols["null?"]  = lambda x: isinstance(x, list) and len(x) == 0
Globals.symbols["append"] = lambda *args: reduce(lambda x, y: x + y, args)
Globals.symbols["reverse"] = lambda x: list(reversed(x))
Globals.symbols["list-tail"] = lambda x, y: x[y:]
Globals.symbols["list-ref"] = lambda x, y: x[y]

Globals.symbols["symbol?"] = lambda x: isinstance(x, Symbol)
Globals.symbols["symbol->string"] = lambda x: x.name
Globals.symbols["string->symbol"] = lambda x: Symbol.new(x)

Globals.symbols["format"] = lambda x, *y: x % y

def external(x):
    if isinstance(x, list):
        return "(" + " ".join(external(i) for i in x) + ")"
    if isinstance(x, Symbol):
        return x.name
    if isinstance(x, str):
        return '"' + re.sub('"', r'\"', x) + '"'
    return str(x)

def psil(s):
    t = tokenise(s)
    r = None
    while True:
        p = parse(t)
        if p is None:
            break
        r = eval(p)
    return r

def rep(s):
    r = psil(s)
    if r is not None:
        print external(r)

def include(fn):
    f = open(fn)
    text = f.read()
    f.close()
    m = re.match(r"#!.*?$", text, re.MULTILINE)
    if m is not None:
        text = text[m.end(0):]
    psil(text)

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        Globals.symbols["quit"] = lambda: sys.exit(0)
        try:
            import readline
        except ImportError:
            pass
        import traceback
        print "PSIL interactive mode"
        print "Use (quit) to exit"
        while True:
            try:
                s = raw_input("> ")
            except EOFError:
                print
                break
            try:
                rep(s)
            except SystemExit:
                raise
            except:
                traceback.print_exc()
    elif sys.argv[1] == "--test":
        import doctest
        doctest.testmod(optionflags=doctest.ELLIPSIS)
        doctest.testfile("psil.test", optionflags=doctest.ELLIPSIS)
        doctest.testfile("integ.test", optionflags=doctest.ELLIPSIS)
    else:
        include(sys.argv[1])
