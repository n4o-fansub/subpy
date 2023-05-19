from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import cast

import yaml

__all__ = ("read_and_parse_properties",)


class _FormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def safe_format(s: str, d: dict):
    formatter = Formatter()
    try:
        return formatter.vformat(s, (), _FormatDict(d))
    except KeyError:
        return s


def bulk_update_value(data: dict | list, update_data: dict[str, str]):
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str):
                vv = safe_format(v, update_data)
                data[k] = vv
            elif isinstance(v, (dict, list)):
                bulk_update_value(v, update_data)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, (dict, list)):
                bulk_update_value(item, update_data)
            elif isinstance(item, str):
                data[i] = safe_format(item, update_data)


@dataclass
class SyncPoint:
    value: str
    chapter: str


@dataclass
class Subtitle:
    scripts: dict[str, list[Path]]
    syncs: dict[str, SyncPoint]
    title: str | None = field(default=None)


def walk_dot(dictionary: dict, dot_notation: str):
    for nota in dot_notation.split("."):
        dictionary = dictionary.get(nota, None)
        if dictionary is None:
            return None
    return dictionary


def expandpath(path_pattern) -> list[Path]:
    p = Path(path_pattern)
    return list(Path(p.parent).expanduser().glob(p.name))


def read_and_parse_properties(yaml_path: Path, base_path: Path) -> tuple[dict[str, Subtitle], dict]:
    data_text = yaml_path.read_text()
    pp = yaml.safe_load(data_text)
    to_be_changed = list(filter(lambda x: x not in ["subs", "syncs", "merge"], list(pp.keys())))
    update_this = {k: pp[k] for k in to_be_changed}
    update_this.pop("subsfolder", None)
    bulk_update_value(pp, update_this)
    subs_base = pp["subs"]
    merge_base = pp["merge"]
    syncs_base = pp.get("syncs", {})
    title_base = pp.get("titles", pp.get("title", {}))
    subtitles: dict[str, Subtitle] = {}
    for episode, subs_path in merge_base.items():
        eps = f"{int(episode):02d}"
        scripts: dict[str, list[Path]] = {}
        subsfolder = safe_format(pp.get("subsfolder", ""), {"EPISODE": eps})
        for sub_path in subs_path:
            fpath_r = cast(str, walk_dot(subs_base, sub_path))
            fpath = safe_format(fpath_r, {"EPISODE": eps, "subsfolder": subsfolder})
            fdot = str(sub_path.rsplit(".", 1)[-1])
            ssfdot: list[Path] = scripts.get(fdot, [])
            sspath = base_path / str(fpath)
            ssfdot.extend(expandpath(sspath))
            scripts[fdot] = ssfdot
        sync_data = syncs_base.get(eps, {})
        new_sync_data: dict[str, SyncPoint] = {}
        for key, value in sync_data.items():
            if isinstance(value, str):
                new_sync_data[key] = SyncPoint(value, value)
            elif isinstance(value, dict):
                syncn = value.get("value")
                syncch = value.get("chapter")
                if syncn is None and syncch is None:
                    continue
                new_sync_data[key] = SyncPoint(syncn or syncch or "-", syncch or syncn or "-")
        subtitles[eps] = Subtitle(scripts, new_sync_data, title_base.get(eps, None))
    return subtitles, pp
