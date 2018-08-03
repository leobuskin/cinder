from cinder import jit


def identity(x):
    return x


class Foo:
    def __init__(self, bar):
        self.bar = bar


def get_bar(x):
    return x.bar


def invert(x):
    return not x


def test_load_fast_and_return_value():
    foo = jit.compile(identity)
    assert foo(100) == 100


def test_load_attr():
    x = jit.compile(get_bar)
    foo = Foo('testing 123')
    assert x(foo) == 'testing 123'


def test_invert():
    jit_invert = jit.compile(invert)
    assert jit_invert(False) == True
    assert jit_invert(True) == False
    assert jit_invert(1) == False
