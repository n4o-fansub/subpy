# A quick synchronization script for the repository.

import urllib.request
from pathlib import Path
from zipfile import ZipFile

WORKING_DIR = Path.cwd()
DOWNLOAD_PATH = "https://github.com/n4o-fansub/subpy/archive/refs/heads/master.zip"

def download_with_urllib(url: str):
    print("Downloading...")
    urllib.request.urlretrieve(url, "subpy.zip")
    print("Downloaded!")


def _extract_target(filename: str, target_path: Path, zip_obj: ZipFile):
    target_write = zip_obj.open(filename)
    with target_path.open("wb") as target:
        target.write(target_write.read())

def extract_zip():
    print("Extracting zip...")
    with ZipFile("subpy.zip", "r") as zipObj:
        all_file = zipObj.namelist()
        
        for file in all_file:
            filename = file.replace("subpy-master/", "")
            if filename == "main.py":
                target_name = WORKING_DIR / filename
                _extract_target(file, target_name, zipObj)
            elif filename.startswith("subpy/"):
                fn_test = filename.replace("subpy/", "")
                if fn_test == "":
                    (WORKING_DIR / filename).mkdir(parents=True, exist_ok=True)
                    continue
                fn_split = filename.split("/")
                target_name = WORKING_DIR / fn_split[0]
                for fn in fn_split[1:]:
                    target_name = target_name / fn
                _extract_target(file, target_name, zipObj)

    print("Extracted!")

download_with_urllib(DOWNLOAD_PATH)
extract_zip()
if (WORKING_DIR / "subpy.zip").exists():
    (WORKING_DIR / "subpy.zip").unlink()
print("Done!")
