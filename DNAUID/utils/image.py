from pathlib import Path

from PIL import Image

from gsuid_core.utils.image.image_tools import crop_center_img

ICON = Path(__file__).parent.parent.parent / "ICON.png"
TEXT_PATH = Path(__file__).parent / "texture2d"


def get_dna_bg(w: int, h: int, bg: str = "bg") -> Image.Image:
    img = Image.open(TEXT_PATH / f"{bg}.jpg").convert("RGBA")
    return crop_center_img(img, w, h)
