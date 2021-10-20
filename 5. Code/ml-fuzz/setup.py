from setuptools import setup, Extension, find_packages
from Cython.Build import cythonize
import numpy as np

annotate = False
compiler_directives = {
    "language_level": 3
}

PREFIX = "/usr/local"

macros = [
    ("AFL_LIB", None),
    ("DOC_PATH", f"\"{PREFIX}/share/doc/afl\""),
    ("_FORTIFY_SOURCE", "2"),
    ("AFL_PATH", f"\"{PREFIX}/lib/afl\""),
    ("BIN_PATH", f"\"{PREFIX}/bin\"")
]
extra_compile_args = [
    "-O3"
    "-funroll-loops",
    "-Wall", "-g", "-Wno-pointer-sign",
    "-ldl"
]

extensions = [
    Extension("mlfuzz.fuzzer", sources=["src/fuzzer.pyx"],
              include_dirs=["src/afl", np.get_include()],
              define_macros=macros)
]


setup(
    name='mlfuzz',
    version='0.0.1',
    setup_requires=[
        'cython',
    ],
    # packages = find_packages(),

    # Cython has a way to visualise where interaction
    #  with Python objects and Python’s C-API is taking place.
    #  For this, pass the `annotate=True` parameter to cythonize().
    #  It produces a HTML file.
    ext_modules=cythonize(extensions, annotate=annotate,
                          compiler_directives=compiler_directives),
    zip_safe=False,
)
