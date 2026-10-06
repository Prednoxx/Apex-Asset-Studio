"""Raster helpers for the glossy theme family: pills and plates, glass panels, themed backdrops (Aero ribbons,
glacier ice, Aqua bubbles, Eco hills, Metro skyline, Aurora curtains), check/radio marks, and an accent color
picked from the mascot art. Small elements are drawn with Pillow at 4x and downsampled.
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


def bokeh(size, color, count, seed, rmin=10, rmax=60, alpha=(18, 60)):
    w, h = size
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    rng = random.Random(seed)
    for _ in range(count):
        r = rng.uniform(rmin, rmax); x = rng.uniform(-r, w + r); y = rng.uniform(-r, h + r)
        a = int(rng.uniform(*alpha))
        d.ellipse((x - r, y - r, x + r, y + r), fill=rgb(color, a), outline=rgb('#ffffff', min(255, a + 25)), width=1)
    return soft(layer, 1.2)


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
    return soft(layer, 3)


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
# One painter per theme. Each returns an RGBA image of `size` built on `base` (the surface it sits on) and scales
# its decoration with `energy` (header strips are calmer than the splash). Used by the header, the splash screen,
# the theme cards and the 3D viewport, so every surface of a theme shares one look.

def _mix(a, b, k):
    """Blend RGBA tuple a over b by k."""
    return tuple(int(x * k + y * (1 - k)) for x, y in zip(a, b))


def _glow(size, box, color, alpha, blur):
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(box, fill=rgb(color, int(max(0, min(255, alpha)))))
    return soft(layer, blur)


def _sparkles(layer, w, h, count, seed, color, region=(0, 0, 1, 1), size=(1.5, 4), alpha=(90, 200)):
    d = ImageDraw.Draw(layer); rng = random.Random(seed)
    x0, y0, x1, y1 = region
    for _ in range(count):
        x = rng.uniform(x0, x1) * w; y = rng.uniform(y0, y1) * h; r = rng.uniform(*size); a = int(rng.uniform(*alpha))
        k = r * .28
        d.polygon([(x, y - r), (x + k, y - k), (x + r, y), (x + k, y + k), (x, y + r), (x - k, y + k), (x - r, y), (x - k, y - k)],
                  fill=rgb(color, a))


def _bd_aero(w, h, t, base, energy, seed):
    light = t['light']
    img = _vgradient((w, h), rgb(_hexmix(t['accent'], base, .20 if not light else .10)), rgb(base))
    img.alpha_composite(_glow((w, h), (w * .45, -h * .35, w * 1.25, h * .8), t['accent'], (90 if not light else 60) * energy, max(8, h * .18)))
    img.alpha_composite(_glow((w, h), (-w * .25, h * .5, w * .5, h * 1.5), t['accent2'], (60 if not light else 45) * energy, max(8, h * .18)))
    img.alpha_composite(swoosh((w, h), '#ffffff', seed=seed + 4, alpha=int((50 if not light else 110) * energy)))
    img.alpha_composite(bokeh((w, h), '#ffffff' if not light else t['accent'], int(10 + 14 * energy), seed,
                              max(3, h * .02), max(8, h * .09), alpha=(int(8 * energy), int(30 * energy) + 1)))
    return img


def _bd_glacier(w, h, t, base, energy, seed):
    light = t['light']
    top = _hexmix('#ffffff', base, .55) if light else _hexmix(t['accent'], base, .18)
    img = _vgradient((w, h), rgb(top), rgb(_hexmix(t['accent'], base, .10)))
    img.alpha_composite(_glow((w, h), (w * .2, -h * .5, w * .95, h * .45), '#ffffff' if light else t['accent2'], 120 * energy, max(10, h * .2)))
    # ice facets: large translucent shards leaning in from the edges
    facets = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(facets); rng = random.Random(seed)
    for i in range(9):
        cx = rng.uniform(-.1, 1.1) * w; cy = rng.uniform(.25, 1.15) * h; r = rng.uniform(.18, .45) * max(w * .5, h)
        pts = [(cx + r * math.cos(a) * rng.uniform(.5, 1), cy + r * math.sin(a) * rng.uniform(.3, .8))
               for a in sorted(rng.uniform(0, math.tau) for _ in range(5))]
        tint = '#ffffff' if i % 2 else t['accent']
        d.polygon(pts, fill=rgb(tint, int(rng.uniform(26, 60) * energy)))
        d.line(pts + pts[:1], fill=rgb('#ffffff', int(140 * energy)), width=max(1, int(h / 300)))
    img.alpha_composite(soft(facets, .6))
    # distant icy ridge along the bottom
    ridge = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(ridge); rng = random.Random(seed + 1)
    pts = [(0, h)]; x = 0
    while x < w:
        pts.append((x, h * rng.uniform(.74, .86))); x += rng.uniform(.05, .12) * w
    pts += [(w, h * .8), (w, h)]
    d.polygon(pts, fill=rgb(_hexmix('#ffffff', t['accent'], .7) if light else _hexmix(t['accent'], base, .3), int(150 * energy)))
    img.alpha_composite(soft(ridge, 1.2))
    sparkle = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    _sparkles(sparkle, w, h, int(26 * energy), seed + 2, '#ffffff', size=(1.5, max(2, h * .012)))
    img.alpha_composite(sparkle)
    return img


def _bd_aqua(w, h, t, base, energy, seed):
    light = t['light']
    top = _hexmix('#ffffff', base, .6) if light else _hexmix(t['accent2'], base, .25)
    bottom = _hexmix(t['accent'], base, .22 if light else .3)
    img = _vgradient((w, h), rgb(top), rgb(bottom))
    # caustic light shafts from the surface
    rays = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(rays); rng = random.Random(seed)
    for _ in range(7):
        x = rng.uniform(-.1, 1.0) * w; spread = rng.uniform(.03, .09) * w; lean = rng.uniform(.1, .35) * w
        d.polygon([(x, 0), (x + spread, 0), (x + spread + lean + spread, h), (x + lean, h)],
                  fill=rgb('#ffffff', int(rng.uniform(34, 70) * energy)))
    img.alpha_composite(soft(rays, max(6, w * .012)))
    # bubbles, denser toward the bottom
    bubbles = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(bubbles); rng = random.Random(seed + 1)
    for _ in range(int(34 * energy)):
        r = rng.uniform(.006, .035) * max(h, 120); x = rng.uniform(0, w); y = h * (1 - rng.random() ** 1.7)
        d.ellipse((x - r, y - r, x + r, y + r), fill=rgb('#ffffff', 22), outline=rgb('#ffffff', 120), width=max(1, int(r * .12)))
        d.ellipse((x - r * .55, y - r * .7, x - r * .05, y - r * .25), fill=rgb('#ffffff', 150))
    img.alpha_composite(soft(bubbles, .5))
    img.alpha_composite(swoosh((w, h), '#ffffff', seed=seed + 3, alpha=int(40 * energy)))
    return img


def _bd_eco(w, h, t, base, energy, seed):
    light = t['light']
    sky_top = _hexmix(t['accent2'], '#ffffff', .55) if light else _hexmix(t['accent2'], base, .35)
    img = _vgradient((w, h), rgb(sky_top), rgb(_hexmix('#ffffff', base, .5) if light else base))
    img.alpha_composite(_glow((w, h), (-w * .15, -h * .55, w * .45, h * .45), '#fffbe0', 170 * energy, max(10, h * .15)))
    clouds = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(clouds); rng = random.Random(seed)
    for _ in range(5):
        cx = rng.uniform(.1, 1) * w; cy = rng.uniform(.08, .35) * h; s = rng.uniform(.05, .11) * w
        for k in range(4):
            ox = (k - 1.5) * s * .55; d.ellipse((cx + ox - s * .45, cy - s * .3, cx + ox + s * .45, cy + s * .25), fill=rgb('#ffffff', int(110 * energy)))
    img.alpha_composite(soft(clouds, max(4, h * .02)))
    # two rolling hills with a glossy rim light
    for i, (cx, top_k, k) in enumerate(((.25, .72, .0), (.8, .8, .18))):
        top_k += (1 - energy) * .25  # calm strips keep the hills low, clear of text
        hill = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        green_top = shade(t['accent'], .25 - k); green_bottom = shade(t['accent'], -.25 - k)
        body = _vgradient((w, h), rgb(green_top), rgb(green_bottom))
        mask = Image.new('L', (w, h), 0)
        ImageDraw.Draw(mask).ellipse((cx * w - w * .9, top_k * h, cx * w + w * .9, top_k * h + h * 1.4), fill=int(255 * min(1, .55 + .5 * energy)))
        hill.paste(body, (0, 0), mask)
        rim = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(rim).ellipse((cx * w - w * .9, top_k * h, cx * w + w * .9, top_k * h + h * 1.4), outline=rgb('#ffffff', int(150 * energy)), width=max(2, int(h * .008)))
        hill.alpha_composite(soft(rim, 1.5))
        img.alpha_composite(hill)
    sparkle = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    _sparkles(sparkle, w, h, int(14 * energy), seed + 5, '#ffffff', region=(0, .45, 1, 1))
    img.alpha_composite(sparkle)
    return img


def _bd_metro(w, h, t, base, energy, seed):
    img = _vgradient((w, h), rgb(_hexmix(t['accent'], base, .16)), rgb(base))
    horizon = h * .7
    img.alpha_composite(_glow((w, h), (w * .1, horizon - h * .35, w * .9, horizon + h * .15), t['accent'], 110 * energy, max(10, h * .12)))
    city = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(city); rng = random.Random(seed)
    windows = Image.new('RGBA', (w, h), (0, 0, 0, 0)); dw = ImageDraw.Draw(windows)
    x = -rng.uniform(0, 30)
    tower = rgb(_hexmix('#ffffff', base, .07), int(255 * min(1, .6 + .4 * energy)))
    while x < w:
        bw = rng.uniform(.035, .09) * w; bh = rng.uniform(.12, .5) * h * (.6 + .4 * energy)
        d.rectangle((x, horizon - bh, x + bw, horizon), fill=tower)
        step = max(4, h * .018)
        for wy in range(int(horizon - bh + step), int(horizon - step), int(step)):
            for wx in range(int(x + step * .6), int(x + bw - step * .6), int(step)):
                if rng.random() < .28 and energy >= .55:  # calm strips (the header) skip lit windows behind text
                    dw.rectangle((wx, wy, wx + step * .35, wy + step * .35),
                                 fill=rgb(t['accent2'] if rng.random() < .35 else '#ffe2a8', int(rng.uniform(60, 170) * energy)))
        x += bw + rng.uniform(1, .012 * w)
    city.alpha_composite(windows)
    img.alpha_composite(city)
    # glossy reflection below the horizon
    reflection = city.transpose(Image.Transpose.FLIP_TOP_BOTTOM).crop((0, int(h - horizon), w, int(h - horizon) + int(h - horizon)))
    fade = _vgradient((w, reflection.height), (255, 255, 255, int(90 * energy)), (255, 255, 255, 0)).getchannel('A')
    reflection.putalpha(ImageChops.multiply(reflection.getchannel('A'), fade))
    floor = _vgradient((w, h - int(horizon)), rgb(_hexmix(t['accent'], base, .14)), rgb(base))
    img.alpha_composite(floor, (0, int(horizon)))
    img.alpha_composite(soft(reflection, 1.2), (0, int(horizon)))
    ImageDraw.Draw(img).line((0, horizon, w, horizon), fill=rgb(t['accent2'], int(120 * energy)), width=1)
    img.alpha_composite(swoosh((w, h), t['accent2'], seed=seed + 2, alpha=int(36 * energy)))
    return img


def _bd_aurora(w, h, t, base, energy, seed):
    img = _vgradient((w, h), rgb(_hexmix(t['accent2'], base, .10)), rgb(base))
    stars = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(stars); rng = random.Random(seed)
    for _ in range(int(w * h / 2500 * energy)):
        x, y = rng.uniform(0, w), rng.uniform(0, h * .8); a = int(rng.uniform(30, 150) * energy)
        d.point((x, y), fill=(255, 255, 255, a))
    img.alpha_composite(stars)
    curtains = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(curtains)
    for color, base_y, amp, phase, height, alpha in ((t['accent'], .52, .12, .3, .42, 210), (t['accent2'], .40, .1, 2.2, .34, 170),
                                                     (_hexmix(t['accent'], t['accent2'], .5), .62, .08, 4.0, .26, 130)):
        for x in range(0, w, 2):
            k = x / max(1, w)
            y = h * (base_y + amp * math.sin(k * math.pi * 2.2 + phase) + .03 * math.sin(k * 23 + phase))
            top = y - h * height * (.6 + .4 * math.sin(k * 9 + phase * 2) ** 2)
            strength = alpha * energy * (.55 + .45 * math.sin(k * 5 + phase) ** 2)
            steps = 12
            for s in range(steps):
                y0 = top + (y - top) * s / steps; y1 = top + (y - top) * (s + 1) / steps
                d.line((x, y0, x, y1), fill=rgb(color, int(strength * (s / steps) ** 1.6)), width=2)
    img.alpha_composite(soft(curtains, max(3, h * .012)))
    img.alpha_composite(_glow((w, h), (-w * .2, h * .75, w * 1.2, h * 1.6), t['accent'], 50 * energy, max(10, h * .15)))
    return img


def _bd_plain(w, h, t, base, energy, seed):
    return _vgradient((w, h), rgb(_hexmix(t['accent'], base, .07 if not t['light'] else .04)), rgb(base))


BACKDROPS = {'aero': _bd_aero, 'glacier': _bd_glacier, 'aqua': _bd_aqua, 'eco': _bd_eco, 'metro': _bd_metro,
             'aurora': _bd_aurora, 'plain': _bd_plain}


def _hexmix(a, b, k):
    return hexcolor(_mix(rgb(a), rgb(b), k))


def backdrop(kind, size, t, base=None, energy=1.0, seed=1):
    w, h = max(2, int(size[0])), max(2, int(size[1]))
    painter = BACKDROPS.get(kind, _bd_plain)
    base = base or t['background']
    out = Image.new('RGBA', (w, h), rgb(base))  # always opaque: the art is composited onto its base color
    out.alpha_composite(painter(w, h, t, base, energy, seed).convert('RGBA'))
    return out


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
