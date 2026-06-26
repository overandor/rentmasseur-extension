from PIL import Image, ImageDraw
import sys

for size in [16, 48, 128]:
    img = Image.new('RGBA', (size, size), (26, 26, 31, 255))
    d = ImageDraw.Draw(img)
    pad = size // 6
    d.rounded_rectangle([pad, pad, size-pad, size-pad], radius=size//8, fill=(204, 139, 74, 255))
    cx, cy = size // 2, size // 2
    r = size // 5
    d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(255, 255, 255, 255))
    img.save(f'/Users/alep/Downloads/02_AI_Agents/rentmasseur-extension/icon{size}.png')

print('Icons generated')
