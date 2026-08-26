# HERMES

HERMES processes data from a TPX3Cam read out by a SPIDR board. It unpacks raw
`.tpx3` files into Parquet, groups pixel hits into photons, and groups photons
into events, writing one Parquet file per stage so times from different signals
stay on one comparable clock. HERMES can also drive an existing EMPIR
installation, but it does not ship or install EMPIR.

HERMES is two parts:

- A Python package (`hermes`) that loads a YAML config, runs the workflow, and
  records what happened.
- Three C++ programs the workflow calls — `hermes-tpx3-spidr` (unpacking),
  `hermes-photon-clusterer` (photon reconstruction), and
  `hermes-event-reconstructor` (event reconstruction).

The C++ programs are **built from source when HERMES is installed**. There are
no prebuilt binaries: the install compiles them with the compiler and libraries
your environment provides and places them on `PATH`, so the Python workflow
finds them by name.

## Use HERMES in your own pixi project

Add HERMES as a git dependency. Your project must also provide the C++ build
tools and libraries the backends compile against, from conda-forge:

```toml
# in your project's pyproject.toml (or pixi.toml)
[tool.pixi.dependencies]     # C++ build tools and libraries, from conda-forge
cxx-compiler = "*"
cmake = ">=3.20"
ninja = "*"
nlohmann_json = ">=3.11"
pyarrow = ">=18"             # brings the Arrow/Parquet C++ libraries cmake links against

[tool.pixi.pypi-dependencies]
hermes = { git = "https://github.com/lanl/HERMES.git", tag = "v3.2.0" }
```

Then install and use it:

```bash
pixi install                       # compiles the three backends from source
pixi run which hermes-tpx3-spidr   # the programs are now on PATH
```

```python
import hermes
```

In a config, name each backend by its program name (no path); HERMES finds it on
`PATH`:

```yaml
unpacking:
  program:
    executable_path: hermes-tpx3-spidr
```

### EMPIR is optional and separate

HERMES can run an EMPIR workflow if EMPIR is installed and its programs are on
`PATH`. HERMES does not install EMPIR. If a config names an EMPIR program that
is not on `PATH`, HERMES warns and exits instead of failing with a traceback.

## Develop HERMES from a clone

Install [pixi](https://pixi.sh):

```bash
curl -fsSL https://pixi.sh/install.sh | sh
```

Then install the environment. This compiles the three C++ backends from source
and puts them on `PATH` within the environment:

```bash
pixi install
```

Run an example workflow:

```bash
pixi run python examples/analysis/unpacking/run_unpacking.py
```

Run the Python tests:

```bash
pixi run python -m pytest
```

Build and run the C++ unit tests directly:

```bash
pixi run test-cpp-unpacker
pixi run test-cpp-photon-clusterer
pixi run test-cpp-event-reconstructor
```

### Evals

`evals/` holds known-good cases that pin down what a workflow should produce for
a given input. After changing unpacking, reconstruction, or workflow code, run
them and fix any deviation:

```bash
pixi run python evals/run_evals.py
```

## Copyright

© 2023. Triad National Security, LLC. All rights reserved.
This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
Department of Energy/National Nuclear Security Administration. All rights in the program are
reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
Security Administration. The Government is granted for itself and others acting on its behalf a
nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare 
derivative works, distribute copies to the public, perform publicly and display publicly, and to permit others to do so.

O4660
