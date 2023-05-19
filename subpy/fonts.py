# Adapted from https://github.com/TypesettingTools/Myaamori-Aegisub-Scripts/blob/master/scripts/fontvalidator/fontvalidator.py  # noqa

from __future__ import annotations
import collections

import itertools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from fontTools.misc import encodingTools
from fontTools.ttLib import ttFont

from .extended_ass import ExtendedAssFile

__all__ = (
    "deduplicates_fonts",
    "get_fonts",
    "find_fonts",
    "validate_fonts",
)
TAG_PATTERN = re.compile(r"\\\s*([^(\\]+)(?<!\s)\s*(?:\(\s*([^)]+)(?<!\s)\s*)?")
INT_PATTERN = re.compile(r"^[+-]?\d+")
LINE_PATTERN = re.compile(r"(?:\{(?P<tags>[^}]*)\}?)?(?P<text>[^{]*)")
TEXT_WHITESPACE_PATTERN = re.compile(r"\\[nNh]")


@dataclass
class State:
    font: str
    italic: int
    weight: int
    drawing: bool


def strip_fontname(s: str):
    if s.startswith("@"):
        return s[1:]
    else:
        return s


def parse_int(s: str) -> int:
    if match := INT_PATTERN.match(s):
        return int(match.group(0))
    else:
        return 0


def parse_tags(s: str, state: State, line_style: State, styles: dict[str, State]) -> State:
    for match in TAG_PATTERN.finditer(s):
        value, paren = match.groups()

        def get_tag(name, *exclude):
            if value.startswith(name) and not any(value.startswith(ex) for ex in exclude):
                args = []
                if paren is not None:
                    args.append(paren)
                if len(stripped := value[len(name) :].lstrip()) > 0:
                    args.append(stripped)
                return args
            else:
                return None

        if (args := get_tag("fn")) is not None:
            if len(args) == 0:
                font = line_style.font
            else:
                font = strip_fontname(args[0])
            state.font = font
        elif (args := get_tag("b", "blur", "be", "bord")) is not None:
            weight = None if len(args) == 0 else parse_int(args[0])
            if weight is None:
                transformed = None
            elif weight == 0:
                transformed = 400
            elif weight in (1, -1):
                transformed = 700
            elif 100 <= weight <= 900:
                transformed = weight
            else:
                transformed = None

            state.weight = transformed or line_style.weight
        elif (args := get_tag("i", "iclip")) is not None:
            slant = None if len(args) == 0 else parse_int(args[0])
            state.italic = slant == 1 if slant in (0, 1) else line_style.italic
        elif (args := get_tag("p", "pos", "pbo")) is not None:
            scale = 0 if len(args) == 0 else parse_int(args[0])
            state.drawing = scale != 0
        elif (args := get_tag("r")) is not None:
            if len(args) == 0:
                style = line_style
            else:
                if (style := styles.get(args[0])) is None:
                    print(rf"Warning: \r argument {args[0]} does not exist; defaulting to line style")
                    style = line_style
            state.font = style.font
            state.italic = style.italic
            state.weight = style.weight
        elif (args := get_tag("t")) is not None:
            if len(args) > 0:
                state = parse_tags(args[0], state, line_style, styles)

    return state


def parse_text(text: str) -> str:
    return re.sub(TEXT_WHITESPACE_PATTERN, " ", text)


def parse_line(line: str, line_style: State, styles: dict[str, State]) -> Generator[tuple[State, str], None, None]:
    state = line_style
    for tags, text in LINE_PATTERN.findall(line):
        if len(tags) > 0:
            state = parse_tags(tags, state, line_style, styles)
        if len(text) > 0:
            yield state, parse_text(text)


class Font:
    def __init__(self, fontfile, font_number=0):
        self.fontfile = fontfile
        self.font = ttFont.TTFont(fontfile, fontNumber=font_number)
        self.num_fonts = getattr(self.font.reader, "numFonts", 1)
        self.postscript = self.font.has_key("CFF ")
        self.glyphs = self.font.getGlyphSet()

        os2 = self.font["OS/2"]
        self.weight = os2.usWeightClass  # type: ignore
        self.italic = os2.fsSelection & 0b1 > 0  # type: ignore
        self.slant = self.italic * 110
        self.width = 100

        self.names = [name for name in self.font["name"].names if name.platformID == 3 and name.platEncID in (0, 1)]  # type: ignore # noqa
        self.family_names = [name.string.decode("utf_16_be") for name in self.names if name.nameID == 1]
        self.full_names = [name.string.decode("utf_16_be") for name in self.names if name.nameID == 4]
        self.postscript_name = ""

        for name in self.font["name"].names:  # type: ignore
            if (
                name.nameID == 6
                and (encoding := encodingTools.getEncoding(name.platformID, name.platEncID, name.langID)) is not None
            ):
                self.postscript_name = name.string.decode(encoding).strip()

                # these are the two recommended formats, prioritize them
                if (name.platformID, name.platEncID, name.langID) in [(1, 0, 0), (3, 1, 0x409)]:
                    break

        exact_names = [self.postscript_name] if (self.postscript and self.postscript_name) else self.full_names
        self.exact_names = [
            name for name in exact_names if all(name.lower() != family.lower() for family in self.family_names)
        ]

        mac_italic = self.font["head"].macStyle & 0b10 > 0  # type: ignore
        if mac_italic != self.italic:
            print(f"warning: different italic values in macStyle and fsSelection for font {self.postscript_name}")

        # fail early if glyph tables can't be accessed
        self.missing_glyphs("")

    def missing_glyphs(self, text):
        if uniTable := self.font.getBestCmap():
            return [c for c in text if ord(c) not in uniTable]
        elif symbolTable := self.font["cmap"].getcmap(3, 0):  # type: ignore
            macTable = self.font["cmap"].getcmap(1, 0)  # type: ignore
            encoding = encodingTools.getEncoding(1, 0, macTable.language) if macTable else "mac_roman"
            missing = []
            for c in text:
                try:
                    if (c.encode(encoding)[0] + 0xF000) not in symbolTable.cmap:
                        missing.append(c)
                except UnicodeEncodeError:
                    missing.append(c)
            return missing
        else:
            print(f"warning: could not read glyphs for font {self}")

    def __repr__(self):
        return f"{self.postscript_name}(italic={self.italic}, weight={self.weight})"


class FontCollection:
    def __init__(self, fontfiles: list[tuple[str, str]]):
        self.fonts: list[Font] = []
        for name, f in fontfiles:
            try:
                font = Font(f)
                self.fonts.append(font)
                if font.num_fonts > 1:
                    for i in range(1, font.num_fonts):
                        self.fonts.append(Font(f, font_number=i))
            except Exception as e:
                print(f"Error reading {name}: {e}")

        self.cache = {}
        self.by_full: dict[str, Font] = {name.lower(): font for font in self.fonts for name in font.exact_names}
        self.by_family: dict[str, list[Font]] = {
            name.lower(): [font for (_, font) in fonts]
            for name, fonts in itertools.groupby(
                sorted([(family, font) for font in self.fonts for family in font.family_names], key=lambda x: x[0]),
                key=lambda x: x[0],
            )
        }

    def similarity(self, state: State, font: Font) -> int:
        return abs(state.weight - font.weight) + abs(state.italic * 100 - font.slant)

    def _match(self, state: State) -> tuple[Font | None, bool]:
        if exact := self.by_full.get(state.font):
            return exact, True
        elif family := self.by_family.get(state.font):
            return min(family, key=lambda font: self.similarity(state, font)), False
        else:
            return None, False

    def match(self, state: State) -> tuple[Font | None, bool]:
        state.font = state.font.lower()
        state.drawing = False
        try:
            return self.cache[state.font]
        except KeyError:
            font = self._match(state)
            self.cache[state.font] = font
            return font


def validate_fonts(
    doc: ExtendedAssFile, fonts: FontCollection, ignore_drawings: bool = True, warn_on_exact: bool = False
):
    report = {
        "missing_font": collections.defaultdict(set),
        "missing_glyphs": collections.defaultdict(set),
        "missing_glyphs_lines": collections.defaultdict(set),
        "faux_bold": collections.defaultdict(set),
        "faux_italic": collections.defaultdict(set),
        "mismatch_bold": collections.defaultdict(set),
        "mismatch_italic": collections.defaultdict(set),
    }

    styles = {
        style.name: State(strip_fontname(style.font_name), style.italic, 700 if style.bold else 400, False)
        for style in doc.styles
    }

    for i, line in enumerate(doc.events):
        if line.is_comment:
            continue
        nline = i + 1
        drawing_force = "\\p1" in line.text

        try:
            style = styles[line.style_name]
        except KeyError:
            print(f"Warning: unknown style {line.style_name} on line {nline}, assuming default styles")
            style = State("Arial", False, 400, False)

        for state, text in parse_line(line.text, style, styles):
            font, exact_match = fonts.match(state)

            if ignore_drawings and (state.drawing or drawing_force):
                continue

            if font is None:
                report["missing_font"][state.font].add(nline)
                continue

            if state.weight >= font.weight + 150:
                report["faux_bold"][state.font, state.weight, font.weight].add(nline)

            if state.weight <= font.weight - 150 and (not exact_match or warn_on_exact):
                report["mismatch_bold"][state.font, state.weight, font.weight].add(nline)

            if state.italic and not font.italic:
                report["faux_italic"][state.font].add(nline)

            if not state.italic and font.italic and (not exact_match or warn_on_exact):
                report["mismatch_italic"][state.font].add(nline)

            if not state.drawing:
                missing = font.missing_glyphs(text) or []
                report["missing_glyphs"][state.font].update(missing)
                if len(missing) > 0:
                    report["missing_glyphs_lines"][state.font].add(nline)

    return report


def deduplicates_fonts(fonts: list[Path]):
    joined_together: list[Path] = []
    _temp: list[str] = []
    for font in fonts:
        if font.name in _temp:
            continue
        _temp.append(font.name)
        joined_together.append(font)
    return joined_together


def get_fonts(path: Path) -> list[Path]:
    return list(path.glob("*.[to]t[fc]"))


def find_fonts(base_folder: Path | list[Path]) -> tuple[FontCollection, list[Path]]:
    base_folders = base_folder if isinstance(base_folder, list) else [base_folder]
    fonts: list[Path] = []
    for folder in base_folders:
        if not folder.exists():
            continue
        fonts.extend(get_fonts(folder))
    fonts = deduplicates_fonts(fonts)
    ft_forms = [(ff.name, str(ff)) for ff in fonts]
    return FontCollection(ft_forms), fonts
