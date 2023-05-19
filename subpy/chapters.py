import re
from dataclasses import dataclass

from .extended_ass import ExtendedAssFile

__all__ = (
    "Chapter",
    "get_chapters_from_ass",
    "generate_chapter_file",
)
chapter_re = re.compile(r"{(.*)}.*")


@dataclass
class Chapter:
    name: str
    milisecond: int


def get_chapters_from_ass(ass_file: ExtendedAssFile):
    chapters: dict[str, Chapter] = {}
    for event in ass_file.events:
        if not event.is_comment:
            continue
        if event.effect != "chapter" or event.actor != "chapter":
            continue
        if (ev_match := chapter_re.match(event.text)) is not None:
            if (ev_text := ev_match.group(1)).strip() != "":
                chapters[ev_text] = Chapter(ev_text, event.start)
    return chapters


def milisecond_to_timestamp(milis: int):
    h = milis // 3600000
    milis %= 3600000
    mm = milis // 60000
    milis %= 60000
    ss = milis // 1000
    milis %= 1000
    return f"{h:02d}:{mm:02d}:{ss:02d}.{milis:03d}"


def generate_chapter_file(chapter_data: list[Chapter]):
    """
    CHAPTER01=00:00:00.000
    CHAPTER01NAME=Chapter 1
    """

    chapters_lines: list[str] = []
    counter = 1
    for chp in chapter_data:
        chapter_txt = f"CHAPTER{counter:02d}"
        chapter_txt += f"={milisecond_to_timestamp(chp.milisecond)}"
        chapter_txt += f"\nCHAPTER{counter:02d}NAME={chp.name}"
        chapters_lines.append(chapter_txt)
        counter += 1
    if not chapters_lines:
        return None
    return "\n\n".join(chapters_lines)
