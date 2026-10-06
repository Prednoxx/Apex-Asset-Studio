"""Raster helpers for the Aero look: glossy pills and plates, glass panels, bokeh, light swooshes, and
an accent color picked from the mascot art. Everything is drawn with Pillow at 4x and downsampled.
"""
import colorsys
import math
import random
from functools import lru_cache
from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 4  # supersampling factor


def rgb(color, alpha=255):
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16), alpha)


def hexcolor(values): return '#%02x%02x%02x' % tuple(int(max(0, min(255, v))) for v in values[:3])


def shade(color, amount):
    """Lighten (amount > 0) or darken (amount < 0) a hex color."""
    r, g, b, _ = rgb(color)
    if amount >= 0: return hexcolor((r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount))
    return hexcolor((r * (1 + amount), g * (1 + amount), b * (1 + amount)))


def _vgradient(size, top, bottom):
    w, h = size
    column = Image.new('RGBA', (1, h))
    for y in range(h):
        k = y / max(1, h - 1)
        column.putpixel((0, y), tuple(int(a * (1 - k) + b * k) for a, b in zip(top, bottom)))
    return column.resize((w, h))


def _round_mask(size, radius):
    mask = Image.new('L', size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


@lru_cache(maxsize=256)
def pill(w, h, color, state='normal', radius=None, dark=True):
    """Glossy rounded plate: vertical gradient body, bright upper highlight, thin light rim, soft glow on hover."""
    w, h = max(8, int(w)), max(8, int(h))
    W, H = w * S, h * S
    r = min((radius if radius is not None else h // 2), w // 2, h // 2) * S
    pad = 0
    base = color
    if state == 'hover': base = shade(color, .12)
    if state == 'pressed': base = shade(color, -.18)
    if state == 'disabled': base = shade(color, -.35 if dark else .35)
    top, bottom = rgb(shade(base, .28)), rgb(shade(base, -.22))
    body = _vgradient((W, H), top, bottom)
    mask = _round_mask((W, H), r)
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    out.paste(body, (0, 0), mask)
    if state != 'disabled':
        # gloss: white highlight over the upper half, fading downward
        gloss = _vgradient((W, H // 2), (255, 255, 255, 120 if state != 'pressed' else 50), (255, 255, 255, 18))
        gmask = Image.new('L', (W, H), 0)
        ImageDraw.Draw(gmask).rounded_rectangle((S, S, W - S - 1, H // 2 + r // 3), radius=max(1, r - S), fill=255)
        layer = Image.new('RGBA', (W, H), (0, 0, 0, 0)); layer.paste(gloss, (0, 0))
        layer.putalpha(ImageChops.multiply(layer.getchannel('A'), gmask))
        out.alpha_composite(layer)
    rim = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle((0, 0, W - 1, H - 1), radius=r, outline=(255, 255, 255, 70 if state != 'disabled' else 25), width=S)
    ImageDraw.Draw(rim).rounded_rectangle((S, S, W - S - 1, H - S - 1), radius=max(1, r - S), outline=(0, 0, 0, 60), width=max(1, S // 2))
    out.alpha_composite(rim)
    if pad:
        glow = Image.new('RGBA', (W + pad * 2, H + pad * 2), (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle((pad // 2, pad // 2, W + pad * 1.5, H + pad * 1.5), radius=r + pad // 2, fill=rgb(color, 140))
        glow = glow.filter(ImageFilter.GaussianBlur(pad * .6))
        glow.alpha_composite(out, (pad, pad))
        out = glow.crop((pad, pad, pad + W, pad + H))
    return out.resize((w, h), Image.Resampling.LANCZOS)


@lru_cache(maxsize=64)
def field(w, h, fill, edge, focus=None, radius=5):
    """Rounded input field with a faint inner shadow along the top."""
    W, H = w * S, h * S
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=radius * S, fill=rgb(fill), outline=rgb(focus or edge), width=S if not focus else 2 * S)
    shadow = _vgradient((W - 4 * S, 3 * S), (0, 0, 0, 40), (0, 0, 0, 0))
    out.alpha_composite(shadow, (2 * S, (2 if focus else 1) * S))
    return out.resize((w, h), Image.Resampling.LANCZOS)


def bokeh(size, color, count, seed, rmin=10, rmax=60, alpha=(18, 60)):
    w, h = size
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    rng = random.Random(seed)
    for _ in range(count):
        r = rng.uniform(rmin, rmax); x = rng.uniform(-r, w + r); y = rng.uniform(-r, h + r)
        a = int(rng.uniform(*alpha))
        d.ellipse((x - r, y - r, x + r, y + r), fill=rgb(color, a), outline=rgb('#ffffff', min(255, a + 25)), width=1)
    return layer.filter(ImageFilter.GaussianBlur(1.2))


def swoosh(size, color, seed=1, alpha=70):
    """Frutiger Aero light ribbons: a few wide, soft curves across the canvas."""
    w, h = size
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    rng = random.Random(seed)
    for i in range(4):
        amp = h * rng.uniform(.10, .22); phase = rng.uniform(0, math.pi * 2); base = h * rng.uniform(.45, .8)
        thick = rng.uniform(2, 14)
        points = [(x, base + amp * math.sin(x / w * math.pi * 1.4 + phase)) for x in range(-20, w + 20, 6)]
        d.line(points, fill=rgb(color, int(alpha * (1 - i * .18))), width=int(thick))
    return layer.filter(ImageFilter.GaussianBlur(3))


def glass(background, box, tint, radius=16, blur=14, tint_alpha=70):
    """Frosted glass panel: blurs the background under box, tints it and adds a bright rim and top sheen."""
    x0, y0, x1, y1 = box
    region = background.crop(box).filter(ImageFilter.GaussianBlur(blur))
    panel = Image.new('RGBA', region.size, (0, 0, 0, 0)); panel.alpha_composite(region.convert('RGBA'))
    panel.alpha_composite(Image.new('RGBA', region.size, rgb(tint, tint_alpha)))
    sheen = _vgradient((region.width, region.height // 2), (255, 255, 255, 46), (255, 255, 255, 0))
    panel.alpha_composite(sheen)
    mask = _round_mask(region.size, radius)
    rim = Image.new('RGBA', region.size, (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle((0, 0, region.width - 1, region.height - 1), radius=radius, outline=(255, 255, 255, 90), width=1)
    panel.alpha_composite(rim)
    out = background.copy()
    out.paste(panel, (x0, y0), mask)
    return out


def orb(size, image, ring):
    """Circular avatar with a glass rim and a curved highlight (Aero 'orb')."""
    W = size * S
    out = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    disc = Image.new('RGBA', (W, W), rgb(shade(ring, -.25)))
    disc.alpha_composite(_vgradient((W, W), rgb(shade(ring, .25)), rgb(shade(ring, -.35))))
    art = image.resize((W, W), Image.Resampling.LANCZOS)
    disc.alpha_composite(art)
    mask = Image.new('L', (W, W), 0); ImageDraw.Draw(mask).ellipse((0, 0, W - 1, W - 1), fill=255)
    out.paste(disc, (0, 0), mask)
    hl = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse((W * .12, W * .03, W * .88, W * .5), fill=(255, 255, 255, 70))
    hl = hl.filter(ImageFilter.GaussianBlur(S * 1.5))
    hl.putalpha(ImageChops.multiply(hl.getchannel('A'), mask))
    out.alpha_composite(hl)
    ImageDraw.Draw(out).ellipse((S, S, W - S - 1, W - S - 1), outline=(255, 255, 255, 170), width=int(S * 1.5))
    return out.resize((size, size), Image.Resampling.LANCZOS)


def accent_from_image(image):
    """The art's most prominent saturated color (e.g. a plugsuit's red), or None."""
    small = image.convert('RGBA').copy(); small.thumbnail((120, 120))
    rgbimg = Image.new('RGB', small.size, (0, 0, 0)); rgbimg.paste(small, mask=small.getchannel('A'))
    alpha = small.getchannel('A')
    quant = rgbimg.quantize(16, method=Image.Quantize.MEDIANCUT)
    palette = quant.getpalette()
    counts = {}
    for index, a in zip(quant.getdata(), alpha.getdata()):
        if a > 128: counts[index] = counts.get(index, 0) + 1
    best, score = None, 0
    for index, count in counts.items():
        r, g, b = (v / 255 for v in palette[index*3:index*3+3])
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        if s < .45 or v < .35: continue
        value = count * (s ** 2) * v
        if value > score: best, score = (h, s, v), value
    if not best: return None
    h, s, v = best
    r, g, b = colorsys.hsv_to_rgb(h, min(1, max(.62, s)), min(.92, max(.78, v)))
    return hexcolor((r * 255, g * 255, b * 255))


def companion(accent):
    """A warm/cool partner color 30 degrees around the wheel, slightly lighter."""
    r, g, b, _ = rgb(accent)
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    r, g, b = colorsys.hsv_to_rgb((h + .075) % 1, max(.55, s * .9), min(1, v * 1.08 + .05))
    return hexcolor((r * 255, g * 255, b * 255))
