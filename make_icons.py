import struct, zlib, os

def make_png(size, color, filename):
    # Simple solid color PNG generator
    sig = b'\x89PNG\r\n\x1a\n'
    
    # IHDR: width, height, bit depth, color type, compression, filter, interlace
    ihdr_data = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    ihdr = struct.pack('>I', len(ihdr_data)) + b'IHDR' + ihdr_data
    ihdr += struct.pack('>I', zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff)
    
    # Image data: each row starts with filter byte 0, then RGBA pixels
    raw = b''
    for _ in range(size):
        raw += b'\x00'  # filter byte
        for _ in range(size):
            raw += bytes(color)
    
    compressed = zlib.compress(raw)
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed
    idat += struct.pack('>I', zlib.crc32(b'IDAT' + compressed) & 0xffffffff)
    
    # IEND
    iend = struct.pack('>I', 0) + b'IEND'
    iend += struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
    
    with open(filename, 'wb') as f:
        f.write(sig + ihdr + idat + iend)

base = '/Users/alep/Downloads/02_AI_Agents/rentmasseur-extension'
# Dark bg (#1a1a1f = 26,26,31), accent (#cc8b4a = 204,139,74), white center
make_png(16,  (204, 139, 74, 255), os.path.join(base, 'icon16.png'))
make_png(48,  (204, 139, 74, 255), os.path.join(base, 'icon48.png'))
make_png(128, (204, 139, 74, 255), os.path.join(base, 'icon128.png'))
print('done')
