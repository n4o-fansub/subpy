from typing import IO, Any

from ass_parser.ass_file import AssFile, _collect_section_info_list
from ass_parser.ass_sections import (
    AssBaseSection,
    AssEventList,
    AssKeyValueMapping,
    AssScriptInfo,
    AssStringTable,
    AssStyleList,
)
from ass_parser.ass_sections.const import EVENTS_SECTION_NAME, SCRIPT_INFO_SECTION_NAME, STYLES_SECTION_NAME

__all__ = (
    "ExtendedAssFile",
    "AssAegisubProjectGarbage",
)
AEGI_PROJECT_GARBAGE = "Aegisub Project Garbage"


class AssAegisubProjectGarbage(AssKeyValueMapping):
    """ASS Aegisub project garbage."""

    def __init__(self) -> None:
        """Initialize self."""
        super().__init__(AEGI_PROJECT_GARBAGE)


class ExtendedAssFile:
    """ASS file (master container for all ASS stuff)."""

    def __init__(self) -> None:
        """Initialize self."""
        self.script_info = AssScriptInfo()
        self.project_garbage = AssAegisubProjectGarbage()
        self.events = AssEventList()
        self.styles = AssStyleList()
        self.extra_sections: list[AssBaseSection] = []

    def consume_ass_stream(self, handle: IO[str]) -> None:
        """Load ASS from the specified source.

        Clears the existing content.

        :param handle: a readable stream
        """
        self.script_info.clear()
        self.events.clear()
        self.styles.clear()
        self.extra_sections.clear()
        for section_info in _collect_section_info_list(handle):
            section: AssBaseSection
            if section_info.name == STYLES_SECTION_NAME:
                self.styles.consume_ass_lines(section_info.lines)
            elif section_info.name == EVENTS_SECTION_NAME:
                self.events.consume_ass_lines(section_info.lines)
            elif section_info.name == SCRIPT_INFO_SECTION_NAME:
                self.script_info.consume_ass_lines(section_info.lines)
            elif section_info.name == AEGI_PROJECT_GARBAGE:
                self.project_garbage.consume_ass_lines(section_info.lines)
            elif section_info.is_tabular:
                section = AssStringTable(name=section_info.name)
                section.consume_ass_lines(section_info.lines)
                self.extra_sections.append(section)
            else:
                section = AssKeyValueMapping(name=section_info.name)
                section.consume_ass_lines(section_info.lines)
                self.extra_sections.append(section)

    def __eq__(self, other: Any) -> bool:
        """Check for equality.

        :param other: other object
        :return: whether objects are equal
        """
        if not isinstance(other, (AssFile, ExtendedAssFile)):
            return False
        is_base_true = (
            self.script_info == other.script_info
            and self.events == other.events
            and self.styles == other.styles
            and self.extra_sections == other.extra_sections
        )
        if isinstance(other, ExtendedAssFile):
            return is_base_true and self.project_garbage == other.project_garbage
        return is_base_true
