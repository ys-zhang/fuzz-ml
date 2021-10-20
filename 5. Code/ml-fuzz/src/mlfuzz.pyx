import cython

if not cython.compiled:
    raise ImportError(f"{__file__} have not compiled")

