from pathlib import Path

from PIL import ImageFont

FONT_ORIGIN_PATH = Path(__file__).parent / "dna_fonts.ttf"
UNICODE_ORIGIN_PATH = Path(__file__).parent / "arial-unicode-ms-bold.ttf"
EMOJI_ORIGIN_PATH = Path(__file__).parent / "NotoColorEmoji.ttf"


def dna_font_origin(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_ORIGIN_PATH), size=size)


def unicode_font_origin(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(UNICODE_ORIGIN_PATH), size=size)


def emoji_font_origin(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(EMOJI_ORIGIN_PATH), size=size)


dna_10 = dna_font_origin(10)
dna_font_12 = dna_font_origin(12)
dna_font_14 = dna_font_origin(14)
dna_font_16 = dna_font_origin(16)
dna_font_15 = dna_font_origin(15)
dna_font_18 = dna_font_origin(18)
dna_font_20 = dna_font_origin(20)
dna_font_22 = dna_font_origin(22)
dna_font_23 = dna_font_origin(23)
dna_font_24 = dna_font_origin(24)
dna_font_25 = dna_font_origin(25)
dna_font_26 = dna_font_origin(26)
dna_font_28 = dna_font_origin(28)
dna_font_30 = dna_font_origin(30)
dna_font_32 = dna_font_origin(32)
dna_font_34 = dna_font_origin(34)
dna_font_36 = dna_font_origin(36)
dna_font_38 = dna_font_origin(38)
dna_font_40 = dna_font_origin(40)
dna_font_42 = dna_font_origin(42)
dna_font_44 = dna_font_origin(44)
dna_font_50 = dna_font_origin(50)
dna_font_58 = dna_font_origin(58)
dna_font_60 = dna_font_origin(60)
dna_font_62 = dna_font_origin(62)
dna_font_70 = dna_font_origin(70)
dna_font_84 = dna_font_origin(84)

unicode_font_12 = unicode_font_origin(12)
unicode_font_14 = unicode_font_origin(14)
unicode_font_16 = unicode_font_origin(16)
unicode_font_15 = unicode_font_origin(15)
unicode_font_18 = unicode_font_origin(18)
unicode_font_20 = unicode_font_origin(20)
unicode_font_22 = unicode_font_origin(22)
unicode_font_23 = unicode_font_origin(23)
unicode_font_24 = unicode_font_origin(24)
unicode_font_25 = unicode_font_origin(25)
unicode_font_26 = unicode_font_origin(26)
unicode_font_28 = unicode_font_origin(28)
unicode_font_30 = unicode_font_origin(30)
unicode_font_32 = unicode_font_origin(32)
unicode_font_34 = unicode_font_origin(34)
unicode_font_36 = unicode_font_origin(36)
unicode_font_38 = unicode_font_origin(38)
unicode_font_40 = unicode_font_origin(40)
unicode_font_42 = unicode_font_origin(42)
unicode_font_44 = unicode_font_origin(44)
unicode_font_50 = unicode_font_origin(50)
unicode_font_58 = unicode_font_origin(58)
unicode_font_60 = unicode_font_origin(60)
unicode_font_62 = unicode_font_origin(62)
unicode_font_70 = unicode_font_origin(70)
unicode_font_84 = unicode_font_origin(84)

emoji_font = emoji_font_origin(109)
