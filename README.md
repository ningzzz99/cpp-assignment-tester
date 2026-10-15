# cppgrader — C++ Assignment Tester and AI Debugging Assistant

> **Status: early development (Phase 1).** Only the project foundation exists.
> **Security:** this is a development prototype. It executes compiled native code
> and is **not** a sandbox. Only run your own trusted programs.

## Problem statement and motivation
_TODO_

## Features and architecture
_TODO (planned: compiler, runner, comparator, reporter, sanitizer mode, optional Ollama explanations)_

## Prerequisites (macOS)
- Python 3.9+
- Apple Clang: `xcode-select --install`
- Optional: [Ollama](https://ollama.com) with `qwen2.5-coder:1.5b` (later phases)

## Setup and usage
From the repository root:

```bash
PYTHONPATH=src python3 -m cppgrader.cli --check          # verify prerequisites
PYTHONPATH=src python3 -m cppgrader.cli --check --smoke  # also compile + run the example
```

## Test-case JSON format
_TODO (Phase 3)_

## Ollama integration
_TODO (Phase 8)_

## Running tests and benchmarks
```bash
python3 -m pip install -e ".[dev]"   # installs pytest
python3 -m pytest
```

## Known limitations and security considerations
- Not safe for untrusted submissions; subprocess timeouts are not a sandbox.

## Future improvements
_TODO_

## License
_To be chosen._
