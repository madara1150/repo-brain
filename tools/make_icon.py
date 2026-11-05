"""Render assets/icon-1024.png, icon.png (256) and icon.ico. Run once; the output is committed."""
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024


def gradient(size, c1, c2):
    base = Image.new("RGB", (size, size), c1)
    top = Image.new("RGB", (size, size), c2)
    v = Image.linear_gradient("L").resize((size, size))
    mask = Image.blend(v, v.rotate(90), 0.5)
    return Image.composite(top, base, mask)


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bg = gradient(S, (79, 70, 229), (14, 165, 233)).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=230, fill=255)
    img.paste(bg, (0, 0), mask)

    # chat bubble with soft shadow
    bubble = [190, 230, 834, 730]
    tail = [(330, 700), (300, 850), (470, 720)]
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([b + 16 if i % 2 else b for i, b in enumerate(bubble)], radius=150, fill=(15, 23, 42, 90))
    sd.polygon([(x, y + 16) for x, y in tail], fill=(15, 23, 42, 90))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(22)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(bubble, radius=150, fill=(255, 255, 255, 255))
    d.polygon(tail, fill=(255, 255, 255, 255))

    # a small commit graph inside: main line with a branch that merges back
    ink = (67, 56, 202, 255)
    teal = (8, 145, 178, 255)
    w = 34
    a, b, c = (360, 480), (512, 480), (664, 480)
    br = (512, 360)
    d.line([a, c], fill=ink, width=w)
    d.line([a, (436, 360), br, (588, 360), c], fill=teal, width=w, joint="curve")
    for (x, y), col in ((a, ink), (b, ink), (c, ink), (br, teal)):
        r = 52
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255), outline=col, width=w)
    # text lines under the graph
    for i, (x0, x1) in enumerate(((330, 694), (330, 590))):
        y = 590 + i * 62
        d.rounded_rectangle([x0, y - 16, x1, y + 16], radius=16, fill=(199, 210, 254, 255))

    img.save(os.path.join(ROOT, "assets", "icon-1024.png"))
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "assets", "icon.png"))
    img.save(os.path.join(ROOT, "assets", "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                                              (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
