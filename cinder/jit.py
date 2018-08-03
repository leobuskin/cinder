import ctypes
import types

from cinder import (
    bytecode,
    ir,
    JitFunction,
)
from ctypes import pythonapi
from peachpy import *
from peachpy.x86_64 import *
from typing import Tuple

dllib = ctypes.CDLL(None)
dllib.dlsym.restype = ctypes.c_void_p

# Caller saved registers: r10, r11, parameter passing regs (rdi, rsi, rdx, rcx, r8, r9)
# Callee saved registers: rbx, rbp, rsp (implicitly), r12 - r15,


def pysym(name):
    return dllib.dlsym(pythonapi._handle, name)


def incref(pyobj, temp, amount=1):
    """Increment the reference count of a PyObject.

    Args:
        pyobj: A register storing a pointer to the PyObject whose refcount is being incremented
        temp: A temporary register
        amount: How much to increment the reference count by
    """
    MOV(temp, [pyobj])
    LEA(temp, [temp + amount])
    MOV([pyobj], temp)


def decref(pyobj, temp, amount=1):
    """Decrement the reference count of a PyObject.

    Args:
        pyobj: A register storing a pointer to the PyObject whose refcount is being deceremented.
        temp: A temporary register
        amount: How much to decrement the reference count by
    """
    MOV(temp, [pyobj])
    LEA(temp, [temp - amount])
    MOV([pyobj], temp)


def load_fast(args, index):
    # TODO(mpage): Error handling
    MOV(r12, [args + index * 8])
    incref(r12, rsi)
    PUSH(r12)


def load_attr(name):
    """Call PyObject_GetAttr(<tos>, name) and push the result.

    Args:
        name: The name being looked up. This should be an ordinary Python object retrieved from the
            co_names tuple of the code object that is being jit compiled.
    """
    # TODO(mpage): Error handling
    POP(rdi)
    MOV(rsi, id(name))
    MOV(rdx, pysym(b'PyObject_GetAttr'))
    PUSH(rdi)
    CALL(rdx)
    POP(rdi)
    decref(rdi, rsi)
    PUSH(rax)

def unary_not():
    # TODO(mpage): Error handling around call to PyObject_IsTrue
    false_label = Label()
    done_label = Label()
    POP(r13)
    MOV(rdi, r13)
    MOV(rdx, pysym(b'PyObject_IsTrue'))
    CALL(rdx)
    decref(r13, r14)
    CMP(rax, 0)
    JNZ(false_label)
    MOV(r13, id(True))
    incref(r13, r14)
    PUSH(r13)
    JMP(done_label)
    LABEL(false_label)
    MOV(r13, id(False))
    incref(r13, r14)
    PUSH(r13)
    LABEL(done_label)


def return_value():
    # Top of stack contains PyObject*
    # TODO(mpage): Decref any remaining items on the stack
    POP(rax)
    RETURN(rax)


_SUPPORTED_INSTRUCTIONS = {
    ir.LoadAttr,
    ir.LoadRef,
    ir.ReturnValue,
    ir.UnaryOperation,
}


def compile(func):
    code = func.__code__
    cfg = bytecode.disassemble(code.co_code)
    blocks = list(cfg)
    if len(blocks) != 1:
        raise ValueError('Can only compile single basic blocks right now')
    block = blocks[0]
    for instr in block.instructions:
        if instr.__class__ not in _SUPPORTED_INSTRUCTIONS:
            raise ValueError(f'Cannot compile {instr}')
    args = Argument(ptr())
    with Function(func.__name__, (args,), uint64_t) as ppfunc:
        LOAD.ARGUMENT(r12, args)
        for instr in block.instructions:
            if isinstance(instr, ir.LoadRef):
                if instr.pool == ir.VarPool.LOCALS:
                    load_fast(r12, instr.index)
                else:
                    raise ValueError('Can only load arguments')
            elif isinstance(instr, ir.LoadAttr):
                load_attr(code.co_names[instr.index])
            elif isinstance(instr, ir.ReturnValue):
                return_value()
            elif isinstance(instr, ir.UnaryOperation):
                if instr.kind != ir.UnaryOperationKind.NOT:
                    raise ValueError('Can only encode unary not')
                unary_not()
    loaded = ppfunc.finalize(abi.detect()).encode().load()
    return JitFunction(loaded, loaded.loader.code_address)
