"""Generate the Game Launcher app icon (icon.ico).

Design: a rounded-square tile with a violet-to-indigo diagonal gradient,
a soft pink glow, and a white gamepad (d-pad + coloured ABXY buttons) so it
reads instantly as "games" instead of a generic glyph. Drawn 4x and
downscaled for smooth anti-aliased edges.
"""
from PIL import Image, ImageDraw, ImageFilter

BASE = 256          # final largest icon size
S = 4               # supersample factor
N = BASE * S        # 1024 drawing canvas


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def background():
    img = Image.new("RGB", (N, N))
    px = img.load()
    top = (167, 139, 250)      # violet-400
    bottom = (49, 10, 101)     # deep indigo
    for y in range(N):
        for x in range(N):
            t = (x + y) / (2 * N - 2)
            px[x, y] = lerp(top, bottom, t)
    img = img.convert("RGBA")

    # pink glow, top-right
    glow = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [int(N * 0.45), -int(N * 0.35), int(N * 1.15), int(N * 0.55)],
        fill=(236, 72, 153, 110),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(int(N * 0.12)))
    img.alpha_composite(glow)

    # cyan depth glow, bottom-left
    glow2 = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(glow2).ellipse(
        [-int(N * 0.25), int(N * 0.5), int(N * 0.55), int(N * 1.2)],
        fill=(34, 211, 238, 55),
    )
    glow2 = glow2.filter(ImageFilter.GaussianBlur(int(N * 0.12)))
    img.alpha_composite(glow2)
    return img


def gamepad_layer(color):
    """White gamepad (body + two grips) on a transparent layer."""
    layer = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(
        [0.22 * N, 0.42 * N, 0.78 * N, 0.62 * N], radius=0.06 * N, fill=color
    )
    d.ellipse([0.22 * N, 0.54 * N, 0.40 * N, 0.78 * N], fill=color)   # left grip
    d.ellipse([0.60 * N, 0.54 * N, 0.78 * N, 0.78 * N], fill=color)   # right grip
    return layer


def main():
    img = background()

    # drop shadow under the gamepad
    shadow = gamepad_layer((20, 8, 40, 130)).filter(ImageFilter.GaussianBlur(int(N * 0.016))
    )
    img.alpha_composite(shadow, (0, int(N * 0.02)))
    img.alpha_composite(gamepad_layer((255, 255, 255, 255)))

    d = ImageDraw.Draw(img)
    violet = (124, 58, 237, 255)

    # d-pad (cross), left side
    cx, cy = 0.36 * N, 0.50 * N
    d.rounded_rectangle(
        [cx - 0.021 * N, cy - 0.065 * N, cx + 0.021 * N, cy + 0.065 * N],
        radius=0.018 * N, fill=violet,
    )
    d.rounded_rectangle(
        [cx - 0.065 * N, cy - 0.021 * N, cx + 0.065 * N, cy + 0.021 * N],
        radius=0.018 * N, fill=violet,
    )

    # ABXY buttons (diamond), right side
    bx, by = 0.64 * N, 0.50 * N
    r = 0.028 * N
    dx, dy = 0.062 * N, 0.062 * N
    buttons = [
        ((bx, by - dy), (250, 204, 21, 255)),   # Y yellow (top)
        ((bx - dx, by), (59, 130, 246, 255)),   # X blue (left)
        ((bx + dx, by), (239, 68, 68, 255)),    # B red (right)
        ((bx, by + dy), (34, 197, 94, 255)),    # A green (bottom)
    ]
    for (x, y), col in buttons:
        d.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill=(20, 8, 40, 90))
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)

    # center menu dot
    d.ellipse([0.497 * N, 0.487 * N, 0.517 * N, 0.507 * N], fill=(120, 113, 140, 255))

    # round the corners of the whole tile
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, N - 1, N - 1], radius=int(0.20 * N), fill=255
    )
    img.putalpha(mask)

    icon = img.resize((BASE, BASE), Image.LANCZOS)
    icon.save("icon.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Saved icon.ico with sizes 256/128/64/48/32/16")


if __name__ == "__main__":
    main()
