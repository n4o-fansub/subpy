"""ASS file reading routines."""
import io
from pathlib import Path
from typing import IO, TextIO, Union

from .extended_ass import ExtendedAssFile

__all__ = ("read_ass",)


def read_ass(source: Union[Path, IO[str], str]) -> ExtendedAssFile:
    """Read ASS from the specified source.

    Extended for subpy.

    :param source: a string, a readable stream, or a path
    :return: parsed ASS file
    """
    ass_file = ExtendedAssFile()
    handle: Union[TextIO, IO[str]]
    if isinstance(source, str):
        with io.StringIO(source) as handle:
            ass_file.consume_ass_stream(handle)
    elif isinstance(source, Path):
        with source.open("r", encoding="utf-8") as handle:
            ass_file.consume_ass_stream(handle)
    else:
        ass_file.consume_ass_stream(source)
    return ass_file
