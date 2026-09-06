#!/usr/bin/env python3
"""Generate the Joblooper mark from the original craft photograph.

The mark is a photograph of a paper-craft parrot set inside the pentagon badge
the dashboard header already used. The craft is never redrawn: the photograph is
cropped, its paper background lifted, and its own pixels are carried through
into every artefact.

Three files are generated from one source, so the browser tab, the dashboard
header and the desktop shortcut are the same image:

    dashboard/app-icon.svg     favicon and header, no visible watermark
    assets/app-mark.svg        large presentation version, watermarked
    assets/joblooper.ico.b64   six-size Windows icon

The source photograph at assets/parrot-source.(png|jpg) is git-ignored on
purpose. Publishing only the small derivative is the measure that actually
limits reuse: the original never enters the public repository. See NOTICE for
the copyright position.

    python tools/build_app_icon.py            # rewrite the generated artefacts
    python tools/build_app_icon.py --check    # verify they are current

Pillow is read here at build time only. The generated artefacts are committed,
so nobody installing Joblooper needs it, and the badge still builds without it.
"""
import argparse
import base64
import glob
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_B64 = os.path.join(ROOT, 'assets', 'joblooper.ico.b64')
ICON_SVG = os.path.join(ROOT, 'dashboard', 'app-icon.svg')
MARK_SVG = os.path.join(ROOT, 'assets', 'app-mark.svg')
SOURCE_GLOB = os.path.join(ROOT, 'assets', 'parrot-source.*')
SIZES = (16, 32, 48, 64, 128, 256)
EMBED = 256              # longest edge of the published derivative
SAFE_AREA = 0.72         # craft width inside the pentagon, leaving its corners

# The repository address is the attribution. The bare owner handle is a
# registered personal identifier that the public-mirror scanner allows only
# inside this exact URL, so the mark carries the address and nothing else.
REPOSITORY = 'https://github.com/razaumair2203-ux/Pub-JobLooper'

DESIGN = 64.0
INK = (0x12, 0x18, 0x2b)
EDGE = (0x4d, 0xd9, 0xe8)
# A soft light field behind the craft. The parrot's beak is dark grey and would
# disappear into the badge without it, and it reads as the paper the craft is
# cut from.
LEAF = (0xf4, 0xf1, 0xea)
LEAF_RADIUS = 21.5


def pentagon(cx, cy, radius, rotation=-90.0):
    """The five points of the badge, drawn point-up like the header mark."""
    return [(cx + radius * math.cos(math.radians(rotation + index * 72)),
             cy + radius * math.sin(math.radians(rotation + index * 72)))
            for index in range(5)]


BADGE = pentagon(32, 34, 28)


def _in_polygon(x, y, points):
    inside = False
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
                inside = not inside
    return inside


def _near_edge(x, y, points, width):
    """Whether a point lies within `width` of the polygon's boundary."""
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length ** 2))
        if math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)) <= width / 2:
            return True
    return False


def source_path():
    for path in sorted(glob.glob(SOURCE_GLOB)):
        if os.path.isfile(path):
            return path
    return None


BACKGROUND_THRESHOLD = 30
"""Maximum saturation, 0-255, at which a bright pixel counts as bare paper.

Colour distance cannot separate paint from paper here: the craft is watercolour,
so its lightest pinks sit closer to white than the paper's own ruled lines do,
and a distance flood large enough to clear the lines eats the bird. Saturation
separates them cleanly instead -- paper and its ruling are near-grey however
bright, while every part of the craft carries colour. The parrot's white eye is
also near-grey, so it is protected by connectivity rather than by colour: the
flood only reaches what touches the border.
"""


def load_artwork(threshold=BACKGROUND_THRESHOLD):
    """Crop the craft out of its paper, lift the background, and square it.

    Nothing about the craft is redrawn. Background is classified by saturation
    and then removed by flooding inward from the border, so enclosed pale areas
    of the craft -- the eye -- survive because they never touch the edge.
    """
    path = source_path()
    if not path:
        return None
    from PIL import Image, ImageChops, ImageDraw, ImageEnhance

    image = Image.open(path).convert('RGBA')
    # Bounded working size: the published derivative is small, and the original
    # resolution is deliberately not carried into the repository.
    image.thumbnail((1024, 1024), Image.LANCZOS)

    hsv = image.convert('RGB').convert('HSV')
    saturation, value = hsv.getchannel('S'), hsv.getchannel('V')
    # Bright and unsaturated is paper; anything carrying colour is the craft.
    paperish = Image.eval(saturation, lambda s: 255 if s <= threshold else 0)
    bright = Image.eval(value, lambda v: 255 if v >= 120 else 0)
    candidate = ImageChops.multiply(paperish, bright).convert('L')

    # Keep only the region connected to the border, so the eye survives.
    canvas = candidate.convert('RGB')
    marker = (255, 0, 255)
    step = max(1, min(canvas.size) // 160)
    seeds = ([(x, 0) for x in range(0, canvas.width, step)]
             + [(x, canvas.height - 1) for x in range(0, canvas.width, step)]
             + [(0, y) for y in range(0, canvas.height, step)]
             + [(canvas.width - 1, y) for y in range(0, canvas.height, step)])
    for seed in seeds:
        if canvas.getpixel(seed) == (255, 255, 255):
            ImageDraw.floodfill(canvas, seed, marker, thresh=0)
    red, _green, _blue = canvas.split()
    background = ImageChops.multiply(
        Image.eval(red, lambda r: 255 if r == 255 else 0),
        Image.eval(canvas.split()[1], lambda g: 255 if g == 0 else 0))
    image.putalpha(Image.composite(
        Image.new('L', image.size, 0), image.getchannel('A'),
        background.convert('L')))

    bounds = image.getbbox()
    if bounds:
        image = image.crop(bounds)
    # Gentle correction only: the craft's own colours, cleaned up.
    image = ImageEnhance.Color(image).enhance(1.18)
    image = ImageEnhance.Contrast(image).enhance(1.06)

    # Pad so the craft sits inside the pentagon's angled sides rather than
    # being sliced by them.
    side = int(max(image.size) / SAFE_AREA)
    square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    square.paste(image, ((side - image.width) // 2,
                         int(side * 0.46 - image.height / 2)))
    return square.resize((EMBED, EMBED), Image.LANCZOS)


def _png_bytes(image):
    from io import BytesIO
    buffer = BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def _raw_png(size, rgba):
    raw = b''.join(b'\0' + rgba[row * size * 4:(row + 1) * size * 4]
                   for row in range(size))

    def chunk(tag, payload):
        body = tag + payload
        return (struct.pack('>I', len(payload)) + body
                + struct.pack('>I', zlib.crc32(body) & 0xffffffff))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9))
            + chunk(b'IEND', b''))


def render(size, artwork=None):
    """One square icon: the pentagon badge with the craft clipped inside it."""
    scale = DESIGN / size
    art = None
    if artwork is not None:
        art = artwork.resize((size, size)).load()
    out = bytearray()
    for row in range(size):
        py = (row + 0.5) * scale
        for column in range(size):
            px = (column + 0.5) * scale
            if not _in_polygon(px, py, BADGE):
                out += b'\0\0\0\0'
                continue
            if art is None:
                # Outline only. A filled dark pentagon vanishes into a dark
                # header, which is exactly how it shipped and looked broken.
                out += (bytes(EDGE + (255,)) if _near_edge(px, py, BADGE, 2.2)
                        else b'\0\0\0\0')
                continue
            pixel = INK + (255,)
            # The light field only exists to carry the craft. Without artwork it
            # is a pale blob that reads as a broken image, so it is not drawn.
            if art is not None and (px - 32) ** 2 + (py - 34) ** 2 <= LEAF_RADIUS ** 2:
                pixel = LEAF + (255,)
            if art is not None:
                red, green, blue, alpha = art[column, row]
                if alpha:
                    blend = alpha / 255
                    pixel = (int(red * blend + pixel[0] * (1 - blend)),
                             int(green * blend + pixel[1] * (1 - blend)),
                             int(blue * blend + pixel[2] * (1 - blend)), 255)
            if _near_edge(px, py, BADGE, 1.8):
                pixel = EDGE + (255,)
            out += bytes(pixel)
    return bytes(out)


def build_ico(artwork=None):
    """A Vista-style ICO: every entry is a complete PNG."""
    images = [(size, _raw_png(size, render(size, artwork))) for size in SIZES]
    header = struct.pack('<HHH', 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    directory, payload = b'', b''
    for size, data in images:
        directory += struct.pack(
            '<BBBBHHII', 0 if size >= 256 else size, 0 if size >= 256 else size,
            0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)
    return header + directory + payload


def _points(polygon):
    return ' '.join(f'{x:.2f},{y:.2f}' for x, y in polygon)


def build_svg(artwork=None, watermark=False):
    """The badge as vector art, with the photograph embedded and clipped.

    The craft is carried as its own pixels rather than traced, so the mark stays
    the child's work and not an interpretation of it.
    """
    encoded_art = ''
    if artwork is not None:
        encoded_art = base64.b64encode(_png_bytes(artwork)).decode('ascii')
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg"',
        '     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
        '     xmlns:dc="http://purl.org/dc/elements/1.1/"',
        f'     viewBox="0 0 {int(DESIGN)} {int(DESIGN)}" role="img"',
        '     aria-label="Joblooper">',
        '  <title>Joblooper</title>',
        '  <desc>A paper-craft parrot inside the Joblooper pentagon.</desc>',
        '  <metadata>',
        '    <rdf:RDF>',
        f'      <rdf:Description rdf:about="{REPOSITORY}">',
        '        <dc:title>Joblooper</dc:title>',
        f'        <dc:source>{REPOSITORY}</dc:source>',
        '        <dc:type>StillImage</dc:type>',
        '        <dc:rights>Artwork and photograph (c) 2026, all rights '
        'reserved, not licensed under the MIT licence. The Joblooper name and '
        f'mark are reserved. See NOTICE at {REPOSITORY}.</dc:rights>',
        '      </rdf:Description>',
        '    </rdf:RDF>',
        '  </metadata>',
        '  <!-- Generated by tools/build_app_icon.py. Do not edit by hand. -->',
        '  <defs>',
        f'    <clipPath id="badge"><polygon points="{_points(BADGE)}"/></clipPath>',
        '  </defs>',
    ]
    if encoded_art:
        lines.append('  <polygon points="%s" fill="#%02x%02x%02x"/>' % (
            (_points(BADGE),) + INK))
    if encoded_art:
        lines.append('  <circle cx="32" cy="34" r="%s" fill="#%02x%02x%02x"/>' % (
            (LEAF_RADIUS,) + LEAF))
    if encoded_art:
        lines += [
            '  <g clip-path="url(#badge)">',
            f'    <image x="0" y="0" width="{int(DESIGN)}" height="{int(DESIGN)}"',
            '           preserveAspectRatio="xMidYMid meet"',
            f'           href="data:image/png;base64,{encoded_art}"/>',
            '  </g>',
        ]
    lines.append(
        '  <polygon points="%s" fill="none" stroke="#%02x%02x%02x" '
        'stroke-width="%s" stroke-linejoin="round" opacity="%s"/>' % (
            (_points(BADGE),) + EDGE
            + ((2.0, '0.9') if encoded_art else (3.0, '1'))))
    if watermark:
        # Only on the large rendition: at favicon size this is unreadable, and
        # an unreadable watermark protects nothing.
        lines.append(
            '  <text x="32" y="62.4" text-anchor="middle" font-size="2.5"'
            ' font-family="ui-monospace,SFMono-Regular,Menlo,monospace"'
            f' fill="#ffffff" opacity="0.55">{REPOSITORY}</text>')
    lines.append('</svg>')
    return '\n'.join(lines) + '\n'


def artefacts(threshold=BACKGROUND_THRESHOLD):
    artwork = load_artwork(threshold)
    return artwork, (
        (ICON_SVG, build_svg(artwork)),
        (MARK_SVG, build_svg(artwork, watermark=True)),
        (ICON_B64, base64.b64encode(build_ico(artwork)).decode('ascii') + '\n'),
    )


def check(threshold=BACKGROUND_THRESHOLD):
    """Verify the committed mark, with or without the source photograph.

    The photograph is deliberately absent from the public mirror, so a check
    that regenerates and compares can only run where the source exists. Anywhere
    else -- every public clone, and CI -- it would compare the real mark against
    a badge-only rebuild and fail forever. There, the artefacts are verified for
    integrity instead: present, non-trivial, carrying the badge, the rights
    statement and the repository address, with the visible watermark on the
    large mark alone.
    """
    stored = {}
    for path in (ICON_SVG, MARK_SVG, ICON_B64):
        try:
            with open(path, encoding='utf-8') as stream:
                stored[path] = stream.read().replace('\r\n', '\n')
        except OSError as error:
            print(f'app mark missing: {error}')
            return 1

    if source_path():
        _artwork, generated = artefacts(threshold)
        stale = [os.path.relpath(path, ROOT) for path, current in generated
                 if stored[path] != current]
        if stale:
            print('app mark is stale (' + ', '.join(stale)
                  + '); run python tools/build_app_icon.py')
            return 1
        print('app mark current, regenerated from the craft photograph')
        return 0

    problems = []
    for path in (ICON_SVG, MARK_SVG):
        name = os.path.relpath(path, ROOT)
        content = stored[path]
        if '<polygon' not in content:
            problems.append(f'{name}: badge outline missing')
        if REPOSITORY not in content:
            problems.append(f'{name}: repository address missing')
        if 'rights' not in content:
            problems.append(f'{name}: rights statement missing')
    if '<text' in stored[ICON_SVG]:
        problems.append('app-icon.svg: watermark belongs on the large mark only')
    if '<text' not in stored[MARK_SVG]:
        problems.append('app-mark.svg: visible watermark missing')
    if len(stored[ICON_B64].strip()) < 512:
        problems.append('joblooper.ico.b64: icon is implausibly small')
    if problems:
        print('app mark failed verification:')
        for problem in problems:
            print(f'  - {problem}')
        return 1
    print('app mark verified (no craft source here; integrity checked instead)')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='verify the generated mark is current')
    parser.add_argument('--background-threshold', type=int,
                        default=BACKGROUND_THRESHOLD,
                        help='how far the paper flood may travel from its own '
                             'colour; raise it if paper survives, lower it if '
                             'the craft is eaten into')
    args = parser.parse_args(argv)
    if args.check:
        return check(args.background_threshold)
    artwork, generated = artefacts(args.background_threshold)
    if artwork is None:
        print('No craft photograph found at assets/parrot-source.(png|jpg).')
        print('The badge is generated without it; add the photograph and rerun.')
    for path, current in generated:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(current)
        print(f'app mark written  {os.path.relpath(path, ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
