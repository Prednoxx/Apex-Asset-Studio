"""Raster helpers for the glossy theme family: pills and plates, glass panels, each theme's background picture,
check/radio marks, and an accent color picked from the mascot art. Small elements are drawn with Pillow at 4x
and downsampled.
"""
import colorsys
from functools import lru_cache
from pathlib import Path
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


def soft(image, radius):
    """Gaussian blur in premultiplied alpha, so transparent edges don't darken (no grey halos)."""
    return image.convert('RGBa').filter(ImageFilter.GaussianBlur(radius)).convert('RGBA')


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
def pill(w, h, color, state='normal', radius=None, dark=True, shine=1.0):
    """Glossy rounded plate: vertical gradient body, bright upper highlight, thin light rim.
    radius=None makes a full capsule; shine scales the highlight (0 = flat)."""
    w, h = max(8, int(w)), max(8, int(h))
    W, H = w * S, h * S
    r = min((radius if radius is not None else h // 2), w // 2, h // 2) * S
    pad = 0
    base = color
    if state == 'hover': base = shade(color, .12)
    if state == 'pressed': base = shade(color, -.18)
    if state == 'disabled': base = shade(color, -.35 if dark else .35)
    top, bottom = rgb(shade(base, .28 * shine)), rgb(shade(base, -.22 * shine))
    body = _vgradient((W, H), top, bottom)
    mask = _round_mask((W, H), r)
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    out.paste(body, (0, 0), mask)
    if state != 'disabled' and shine > 0:
        # gloss: white highlight over the upper half, fading downward
        gloss = _vgradient((W, H // 2), (255, 255, 255, int((120 if state != 'pressed' else 50) * shine)), (255, 255, 255, int(18 * shine)))
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
        glow = soft(glow, pad * .6)
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


def glass(background, box, tint, radius=16, blur=14, tint_alpha=70):
    """Frosted glass panel: blurs the background under box, tints it and adds a bright rim and top sheen."""
    x0, y0, x1, y1 = box
    region = soft(background.crop(box), blur)
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
    hl = soft(hl, S * 1.5)
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


ICON_SIZES = (256, 128, 64, 48, 32, 24, 16)


def icon_set(face, accent):
    """Round app icons at every Windows icon size. Small sizes get a tighter face crop and a bolder rim so the
    circle still reads at 16 px."""
    out = {}
    for size in ICON_SIZES:
        art = face
        if size <= 32:  # zoom in on the face so it isn't a smudge
            w, h = face.size; inset = int(w * .12)
            art = face.crop((inset, int(h * .06), w - inset, int(h * .06) + w - 2 * inset))
        render = max(size, 64)
        image = orb(render, art, accent)
        if size < render:
            image = image.resize((size, size), Image.Resampling.LANCZOS)
        out[size] = image
    return out


def save_ico(face, accent, path):
    images = icon_set(face, accent)
    images[256].save(path, format='ICO', sizes=[(s, s) for s in ICON_SIZES], append_images=[images[s] for s in ICON_SIZES[1:]])


# ---------------------------------------------------------------------------------------------- backdrops
# Each theme has a background picture (resources/backgrounds). backdrop() cover-crops it to the requested size
# around the picture's focus point and veils it toward the surface color so text stays readable: calm strips
# such as the header get a strong veil and a little blur, the splash shows the picture almost untouched.
# 'plain' is a soft gradient (used when effects are reduced or a picture is missing).
BACKGROUNDS = Path(__file__).resolve().parents[1] / 'resources' / 'backgrounds'
FOCUS = {'aero_night.jpg': (.85, .6), 'aero_day.jpg': (.85, .6), 'aqua.jpg': (.5, .62), 'eco.jpg': (.65, .55),
         'metro.jpg': (.35, .5), 'aurora.jpg': (.8, .55), 'sunburst.jpg': (.8, .6), 'sweetheart.jpg': (.35, .5)}


def _hexmix(a, b, k):
    return hexcolor(tuple(int(x * k + y * (1 - k)) for x, y in zip(rgb(a), rgb(b))))


@lru_cache(maxsize=12)
def _picture(name):
    with Image.open(BACKGROUNDS / name) as image:
        return image.convert('RGBA')


def _cover(image, w, h, focus):
    """Scale to cover w x h, then crop around the focus point (fractions of the picture)."""
    scale = max(w / image.width, h / image.height)
    sw, sh = max(w, round(image.width * scale)), max(h, round(image.height * scale))
    scaled = image.resize((sw, sh), Image.Resampling.LANCZOS if scale < 1 else Image.Resampling.BICUBIC)
    x = min(max(0, int(sw * focus[0] - w / 2)), sw - w); y = min(max(0, int(sh * focus[1] - h / 2)), sh - h)
    return scaled.crop((x, y, x + w, y + h))


def _plain(w, h, t, base):
    return _vgradient((w, h), rgb(_hexmix(t['accent'], base, .07 if not t['light'] else .04)), rgb(base))


@lru_cache(maxsize=24)
def _backdrop(kind, w, h, accent, light, base, energy):
    t = {'accent': accent, 'light': light}
    if kind == 'plain' or not (BACKGROUNDS / kind).is_file():
        return _plain(w, h, t, base)
    try:
        image = _cover(_picture(kind), w, h, FOCUS.get(kind, (.5, .5)))
    except OSError:
        return _plain(w, h, t, base)
    blur = (1 - energy) * 4
    if blur > .3: image = image.filter(ImageFilter.GaussianBlur(blur))
    veil = max(0., .9 - .9 * energy)
    if veil:
        image = Image.blend(image, Image.new('RGBA', (w, h), rgb(base)), veil)
    return image


def backdrop(kind, size, t, base=None, energy=1.0):
    """The theme's background picture at `size`. energy 1 = as is (splash); lower = calmer (viewport ~.6, header ~.5)."""
    w, h = max(2, int(size[0])), max(2, int(size[1]))
    image = _backdrop(kind, w, h, t['accent'], bool(t['light']), base or t['background'], round(energy, 2))
    return image.copy()


# ---------------------------------------------------------------------------------------------- text for PIL
_PIL_FONTS = {}
_FONT_FILES = {
    'regular': ('segoeui.ttf', 'NotoSans-Regular.ttf', 'DejaVuSans.ttf'),
    'light': ('segoeuil.ttf', 'segoeui.ttf', 'NotoSans-Light.ttf', 'DejaVuSans-ExtraLight.ttf', 'DejaVuSans.ttf'),
    'semibold': ('seguisb.ttf', 'segoeuib.ttf', 'NotoSans-SemiBold.ttf', 'DejaVuSans-Bold.ttf'),
}


def pil_font(size, weight='regular'):
    """A TrueType font for text drawn into images (viewport messages): Segoe UI on Windows, Noto/DejaVu elsewhere."""
    import os
    from PIL import ImageFont
    key = (int(size), weight)
    if key in _PIL_FONTS: return _PIL_FONTS[key]
    folders = [os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'), '/usr/share/fonts/truetype/noto',
               '/usr/share/fonts/truetype/dejavu', '/usr/share/fonts/truetype/google-fonts', '/Library/Fonts']
    font = None
    for name in _FONT_FILES.get(weight, _FONT_FILES['regular']):
        for folder in folders:
            path = os.path.join(folder, name)
            if os.path.exists(path):
                font = ImageFont.truetype(path, int(size)); break
        if font: break
    _PIL_FONTS[key] = font or ImageFont.load_default(size=int(size))
    return _PIL_FONTS[key]


def caption(image, headline, body, t, scale=1.0):
    """Centered message on a frosted glass card (viewport empty states). Returns a new image."""
    w, h = image.size
    if not headline and not body: return image
    big = pil_font(22 * scale, 'light'); small = pil_font(13 * scale)
    d = ImageDraw.Draw(image)
    def measure(text, font):
        if not text: return 0, 0
        box = d.textbbox((0, 0), text, font=font); return box[2] - box[0], box[3] - box[1]
    hw, hh = measure(headline, big)
    lines = []
    for paragraph in (body or '').split('\n'):  # wrap the body to the card width
        words, line = paragraph.split(), ''
        for word in words:
            trial = f'{line} {word}'.strip()
            if measure(trial, small)[0] > min(w - 80, 440 * scale) and line: lines.append(line); line = word
            else: line = trial
        if line: lines.append(line)
    lh = int(small.size * 1.45) if hasattr(small, 'size') else 18
    cw = max([hw] + [measure(l, small)[0] for l in lines]) + int(56 * scale)
    ch = (hh + int(14 * scale) if headline else 0) + lh * len(lines) + int(40 * scale)
    cw, ch = min(cw, w - 20), min(ch, h - 20)
    x0, y0 = (w - cw) // 2, int((h - ch) * .42)
    out = glass(image, (x0, y0, x0 + cw, y0 + ch), t['surface'], radius=int(14 * scale), blur=10, tint_alpha=150)
    d = ImageDraw.Draw(out); y = y0 + int(20 * scale)
    if headline:
        d.text((w // 2, y), headline, font=big, fill=rgb(t['text']), anchor='ma'); y += hh + int(14 * scale)
    for line in lines:
        d.text((w // 2, y), line, font=small, fill=rgb(t['muted']), anchor='ma'); y += lh
    return out


# ---------------------------------------------------------------------------------------------- small controls
def check_mark(size, fill, edge, mark=None, radius=4, shine=1.0):
    """Glossy rounded checkbox, optionally with a tick."""
    W = size * S
    out = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    body = pill(size, size, fill, 'normal', radius=radius, shine=shine).resize((W, W), Image.Resampling.LANCZOS)
    out.alpha_composite(body)
    ImageDraw.Draw(out).rounded_rectangle((S // 2, S // 2, W - S // 2 - 1, W - S // 2 - 1), radius=radius * S, outline=rgb(edge), width=int(S * 1.1))
    if mark:
        ImageDraw.Draw(out).line([(W * .24, W * .52), (W * .43, W * .7), (W * .77, W * .3)], fill=rgb(mark), width=int(S * 2), joint='curve')
    return out.resize((size, size), Image.Resampling.LANCZOS)


def radio_mark(size, fill, edge, dot=None, shine=1.0):
    W = size * S
    out = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    out.alpha_composite(pill(size, size, fill, 'normal', radius=size // 2, shine=shine).resize((W, W), Image.Resampling.LANCZOS))
    d = ImageDraw.Draw(out)
    d.ellipse((S // 2, S // 2, W - S // 2 - 1, W - S // 2 - 1), outline=rgb(edge), width=int(S * 1.1))
    if dot:
        dot_img = pill(max(4, size // 2), max(4, size // 2), dot, 'normal', radius=size // 4, shine=shine)
        dot_img = dot_img.resize((W // 2, W // 2), Image.Resampling.LANCZOS)
        mask = Image.new('L', dot_img.size, 0); ImageDraw.Draw(mask).ellipse((0, 0, dot_img.width - 1, dot_img.height - 1), fill=255)
        out.paste(dot_img, (W // 4, W // 4), mask)
    return out.resize((size, size), Image.Resampling.LANCZOS)
