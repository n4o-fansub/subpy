import argparse
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from pymkv import MKVFile, MKVTrack

from subpy import __version__ as subpy_version
from subpy.chapters import Chapter, generate_chapter_file, get_chapters_from_ass
from subpy.extended_ass import ExtendedAssFile
from subpy.fonts import find_fonts, validate_fonts
from subpy.merger import merge_ass_and_sync, parse_sync_timestamp
from subpy.properties import SyncPoint, read_and_parse_properties
from subpy.reader import read_ass
from subpy.utils import incr_layer
from subpy.writer import write_ass

CURRENT_DIR = Path(__file__).parent
COMMON_DIR = CURRENT_DIR / "common"

properties, raw_prop = read_and_parse_properties(CURRENT_DIR / "properties.yaml", CURRENT_DIR)

parser = argparse.ArgumentParser()
parser.add_argument("episode", type=int)

args = parser.parse_args()
episode: int = args.episode
current_episode = f"{episode:02d}"

basename = raw_prop.get("basename")
episode_meta = properties.get(current_episode)
if episode_meta is None:
    print(f"[!] Episode {current_episode} not found in properties.yaml")
    sys.exit(1)

print(f"[?] Processing episode {current_episode}...")
print(f"[?] Using basename: {basename}")
chapters_data: dict[str, Chapter] = {}
base_ass: ExtendedAssFile | None = None
base_ass_path: Path | None = None
fonts_folder: set[Path] = set()
total_scripts = 0
for fmt, paths in episode_meta.scripts.items():
    if len(paths) < 1:
        continue
    read_paths = paths[:]
    if base_ass is None:
        print(f"[+] Using {read_paths[0].name} as base ASS file!")
        base_ass_path = read_paths[0]
        base_ass = read_ass(read_paths[0])
        font_folder = paths[0].parent / "fonts"
        fonts_folder.add(font_folder)
        if "dialog" in fmt.lower():
            for line in base_ass.events:
                incr_layer(line, 50)
        chapters_data |= get_chapters_from_ass(base_ass)
        read_paths.pop(0)
        total_scripts += 1

    for path in read_paths:
        print(f"[+] Merging {fmt}: {path.name}")
        merge_ass = read_ass(path)
        font_folder = path.parent / "fonts"
        fonts_folder.add(font_folder)
        chapters_data |= get_chapters_from_ass(merge_ass)
        bump_layer = 50 if "dialog" in fmt.lower() else 0
        sync_time = episode_meta.syncs.get(fmt, SyncPoint("-", "-"))
        chapter_point = chapters_data.get(sync_time.chapter)
        sync_act = sync_time.value if sync_time.value != "-" else None
        try:
            sync_act = parse_sync_timestamp(sync_act or "-")
        except ValueError:
            sync_act = None
        if sync_act is None and chapter_point is not None:
            print(f'    [+] Syncing to chapter "{sync_time.chapter}" ({chapter_point.milisecond})')
            sync_act = chapter_point.milisecond
        merge_ass_and_sync(base_ass, merge_ass, sync_act, bump_layer, total_scripts, config=raw_prop)
        total_scripts += 1

if base_ass is None:
    print("[!] Somehow we got an empty episode case?")
    sys.exit(1)
if base_ass_path is None:
    print("[!] Somehow we got an empty episode case?")
    sys.exit(1)


basetitle = raw_prop.get("basetitle")
# Set script information
if basetitle is not None:
    base_ass.script_info["Title"] = f"{basetitle} - {current_episode}"
# base_ass.script_info["Original Translation"] = "Suaminya Kita Ikuyo"
# base_ass.script_info["Original Editing"] = "Suaminya Kita Ikuyo dan Suaminya Nijika-chan"
# base_ass.script_info["Original Timing"] = "Suaminya Kita Ikuyo"
base_ass.script_info["Synch Point"] = base_ass_path.stem  # type: ignore
base_ass.script_info["Script Updated By"] = f"SubPy/v{subpy_version} Script Merger"
base_ass.script_info["Update Details"] = f"Merged {total_scripts} scripts with SubPy/v{subpy_version} Script Merger"
# Set Aegisub project garbage
if base_ass.project_garbage.get("Video File"):
    # Seek to 0
    base_ass.project_garbage["Scroll Position"] = "0"
    base_ass.project_garbage["Active Line"] = "0"
    base_ass.project_garbage["Video Position"] = "0"

print("[+] Writing merged files!")
final_folder = CURRENT_DIR / "final"
final_folder.mkdir(parents=True, exist_ok=True)
final_file = final_folder / f"{basename}{current_episode}.merged.ass"
write_ass(base_ass, final_file)

print("[?] Validating fonts...")
ttfont, complete_fonts = find_fonts(list(fonts_folder))
font_report = validate_fonts(base_ass, ttfont, True, False)


def format_lines(lines, limit=10):
    sorted_lines = sorted(lines)
    if len(sorted_lines) > limit:
        sorted_lines = sorted_lines[:limit]
        sorted_lines.append("[...]")
    return " ".join(map(str, sorted_lines))


real_problems = False
for font, lines in sorted(font_report["missing_font"].items(), key=lambda x: x[0]):
    print(f"  - Could not find font {font} on line(s): {format_lines(lines)}")
    real_problems = True

for (font, reqweight, realweight), lines in sorted(font_report["faux_bold"].items(), key=lambda x: x[0]):
    print(
        f"  - Faux bold used for font {font} (requested weight {reqweight}, got {realweight}) "
        f"on line(s): {format_lines(lines)}"
    )

for font, lines in sorted(font_report["faux_italic"].items(), key=lambda x: x[0]):
    print(f"  - Faux italic used for font {font} on line(s): {format_lines(lines)}")

for (font, reqweight, realweight), lines in sorted(font_report["mismatch_bold"].items(), key=lambda x: x[0]):
    print(
        f"  - Requested weight {reqweight} but got {realweight} for font {font} " f"on line(s): {format_lines(lines)}"
    )

for font, lines in sorted(font_report["mismatch_italic"].items(), key=lambda x: x[0]):
    print(f"  - Requested non-italic but got italic for font {font} on line(s): " + format_lines(lines))

for font, lines in sorted(font_report["missing_glyphs_lines"].items(), key=lambda x: x[0]):
    missing = " ".join(f"{g}(U+{ord(g):04X})" for g in sorted(font_report["missing_glyphs"][font]))
    print(f"  - Font {font} is missing glyphs {missing} " f"on line(s): {format_lines(lines)}")

if real_problems:
    sys.exit(1)

print("[+] Creating font collection zip...")
# Make fonts collections
font_zip = final_folder / f"{basename}{current_episode}.fonts.zip"
with ZipFile(str(font_zip), "w", compression=ZIP_DEFLATED) as zipf:
    for font in complete_fonts:
        zipf.write(str(font), arcname=font.name)
    zipf.comment = f"Generated with SubPy/v{subpy_version} Script Merger".encode("utf-8")

print("[+] Preparing .mks file...")
mkv = MKVFile()
for font in complete_fonts:
    mkv.add_attachment(str(font))

chapter_txts = generate_chapter_file(list(chapters_data.values()))
chapter_file = final_folder / f"{basename}{current_episode}.chapters.txt"
if chapter_txts is not None:
    print(f"[+] Generating chapter file for {current_episode}")
    chapter_file.write_text(chapter_txts, encoding="utf-8")
    mkv.chapters(str(chapter_file), "ind")
if (eptitle := episode_meta.title) is not None:
    merge_title = f"#{current_episode} - {eptitle}"
    if basetitle is not None:
        merge_title = f"{basetitle} - {merge_title}"
    mkv.title = merge_title
mkv.add_track(
    MKVTrack(
        str(final_file),
        0,
        "Bahasa Indonesia oleh Interrobang?!",
        "ind",
        default_track=True,
    )
)
mks_file = final_folder / f"{basename}{current_episode}.mks"
print(f"[+] Writing .mks file to {mks_file.name}")
mkv.mux(str(mks_file))
