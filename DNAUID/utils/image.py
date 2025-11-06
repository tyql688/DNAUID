from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from gsuid_core.utils.image.image_tools import crop_center_img

ICON = Path(__file__).parent.parent.parent / "ICON.png"
TEXT_PATH = Path(__file__).parent / "texture2d"


def get_dna_bg(w: int, h: int, bg: str = "bg") -> Image.Image:
    img = Image.open(TEXT_PATH / f"{bg}.jpg").convert("RGBA")
    return crop_center_img(img, w, h)


async def download_pic_from_url(
    path: Path,
    pic_url: str,
    size: Optional[Tuple[int, int]] = None,
) -> Image.Image:
    path.mkdir(parents=True, exist_ok=True)

    name = pic_url.split("/")[-1]
    _path = path / name
    if not _path.exists():
        from gsuid_core.utils.download_resource.download_file import download

        await download(pic_url, path, name, tag="[DNA]")

    img = Image.open(_path)
    if size:
        img = img.resize(size)

    return img.convert("RGBA")
