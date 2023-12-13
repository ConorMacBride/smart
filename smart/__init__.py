__all__ = ["__version__"]

try:
    from smart._version import __version__
except ImportError:
    __version__ = None
