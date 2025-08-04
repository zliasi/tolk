# tolk

Fast parser and IO framework.

A C engine locates bytes, Python decides what they mean. Files are opened
lazily and only the regions you ask for are ever read or parsed, so pulling
three numbers out of a gigabyte log costs kilobytes of work. Format knowledge
lives in declarative TOML specs rather than code, so teaching tolk a new file
type means writing a spec, not patching the engine.

Requires Python 3.11 or newer. The C engine is optional, a pure-Python
backend with the same interface takes over when it is not built.

## Installation

```
git clone https://github.com/zliasi/tolk
pip install ./tolk
```

## Usage

Nothing to use yet. See CHANGELOG.md for what has landed.

## License

MIT, see LICENSE.
