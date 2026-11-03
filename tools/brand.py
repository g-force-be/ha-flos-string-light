"""Brand icon for Home Assistant, rendered from docs/images/icon.svg.

Writes custom_components/flos_string/brand/icon.png (256 x 256) and icon@2x.png (512 x 512), the files
Home Assistant 2026.3+ and HACS pick up from an integration's own brand/ folder. Renders with the installed
Chrome (headless) and optimises the PNGs with Pillow.

Usage: python tools/brand.py            (Chrome elsewhere: set CHROME=<path to chrome>)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "images" / "icon.svg"
BRAND = ROOT / "custom_components" / "flos_string" / "brand"
SIZES = {"icon.png": 256, "icon@2x.png": 512}

CHROME_CANDIDATES = [
    os.environ.get("CHROME", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    sys.exit("Chrome not found; set CHROME to its path.")


def render(chrome: str, svg: str, size: int, target: Path, workdir: Path) -> None:
    page = workdir / f"icon-{size}.html"
    page.write_text(
        "<!doctype html><style>html,body{margin:0;background:transparent}"
        f"svg{{display:block;width:{size}px;height:{size}px}}</style>{svg}",
        encoding="utf-8",
    )
    shot = workdir / f"icon-{size}.png"
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--default-background-color=00000000",
            f"--window-size={size},{size}",
            f"--screenshot={shot}",
            page.as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    with Image.open(shot) as image:
        if image.size != (size, size):
            sys.exit(f"{target.name}: Chrome rendered {image.size}, expected {size} x {size}")
        image.convert("RGBA").save(target, optimize=True)
    print("wrote", target.relative_to(ROOT).as_posix())


def main() -> None:
    chrome = find_chrome()
    svg = SOURCE.read_text(encoding="utf-8")
    BRAND.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, size in SIZES.items():
            render(chrome, svg, size, BRAND / name, Path(tmp))


if __name__ == "__main__":
    main()
