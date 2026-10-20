"""Builds custom glyphs into the project's Font Awesome OTF font.

Adds:
- 0xE001: floppy-disk-arrow-down (Save As: floppy disk with small down arrow cutout badge at bottom-right)
"""

import os
from booleanOperations.booleanGlyph import BooleanGlyph
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont


def add_custom_icons_to_font(font_path: str):
    font = TTFont(font_path)
    cff = font["CFF "].cff
    top_dict = cff.topDictIndex[0]
    charstrings = top_dict.CharStrings

    floppy_cs = charstrings["floppy-disk"]
    arrow_cs = charstrings["arrow-down"]

    # 1. Base floppy glyph
    bg_floppy = BooleanGlyph()
    floppy_cs.draw(bg_floppy.getPen())

    # 2. Circular cutout mask at bottom-right
    # Center (cx=350, cy=40), radius=125
    cx, cy = 350, 40
    r_cutout = 125
    k = 0.5522847498 * r_cutout

    bg_cutout = BooleanGlyph()
    pen = bg_cutout.getPen()
    pen.moveTo((cx + r_cutout, cy))
    pen.curveTo((cx + r_cutout, cy + k), (cx + k, cy + r_cutout), (cx, cy + r_cutout))
    pen.curveTo((cx - k, cy + r_cutout), (cx - r_cutout, cy + k), (cx - r_cutout, cy))
    pen.curveTo((cx - r_cutout, cy - k), (cx - k, cy - r_cutout), (cx, cy - r_cutout))
    pen.curveTo((cx + k, cy - r_cutout), (cx + r_cutout, cy - k), (cx + r_cutout, cy))
    pen.closePath()

    # 3. Scaled & centered down arrow inside the cutout
    # arrow original bounds: (0, -64, 384, 448) -> center is (192, 192)
    scale = 0.44
    tx = cx - 192 * scale
    ty = cy - 192 * scale
    bg_arrow = BooleanGlyph()
    tpen = TransformPen(bg_arrow.getPen(), (scale, 0, 0, scale, tx, ty))
    arrow_cs.draw(tpen)

    # 4. Composite: (Floppy minus circular cutout) union (down arrow)
    composite_glyph = bg_floppy.difference(bg_cutout).union(bg_arrow)

    # 5. Compile into CFF CharString
    gname = "floppy-disk-arrow-down"
    ucode = 0xE001

    t2_pen = T2CharStringPen(448, charstrings)
    composite_glyph.draw(t2_pen)
    new_cs = t2_pen.getCharString()
    new_cs.private = top_dict.Private

    if gname in charstrings.charStrings:
        idx = charstrings.charStrings[gname]
        charstrings.charStringsIndex[idx] = new_cs
    else:
        charstrings.charStringsIndex.append(new_cs)
        charstrings.charStrings[gname] = len(charstrings.charStringsIndex) - 1
        order = font.getGlyphOrder()
        order.append(gname)
        font.setGlyphOrder(order)

    font["hmtx"][gname] = (448, 0)

    # 6. Map to unicode 0xE001
    cmap = font["cmap"]
    for table in cmap.tables:
        if table.isUnicode():
            table.cmap[ucode] = gname

    font.save(font_path)
    print(f"Successfully baked '{gname}' (\\u{ucode:04x}) into {font_path}")


if __name__ == "__main__":
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_font = os.path.join(
        repo_root, "src", "vvv", "fonts", "Font Awesome 7 Free-Solid-900.otf"
    )
    add_custom_icons_to_font(target_font)
