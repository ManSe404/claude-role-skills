"""Acme Index: index documents for search and stream answers over them.

The errors every module raises live here. Each module says what it does in its own docstring.
"""


class IndexingError(Exception):
    """A document could not be indexed. The message names the document or the path."""


class ParseError(IndexingError):
    """A file could not be read into text."""


class EmbedderError(IndexingError):
    """The embedding service could not be reached or sent a bad answer."""
