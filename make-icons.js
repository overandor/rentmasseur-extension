const fs = require('fs');
const zlib = require('zlib');

function crc32(buf) {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let j = 0; j < 8; j++) {
      c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    }
    table[i] = c >>> 0;
  }
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) {
    c = table[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  }
  return (c ^ 0xFFFFFFFF) >>> 0;
}

function makePng(size, r, g, b, filename) {
  const sig = Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
  
  // IHDR
  const ihdrData = Buffer.alloc(13);
  ihdrData.writeUInt32BE(size, 0);
  ihdrData.writeUInt32BE(size, 4);
  ihdrData[8] = 8;  // bit depth
  ihdrData[9] = 6;  // color type RGBA
  ihdrData[10] = 0; // compression
  ihdrData[11] = 0; // filter
  ihdrData[12] = 0; // interlace
  const ihdrType = Buffer.from('IHDR');
  const ihdrCrc = crc32(Buffer.concat([ihdrType, ihdrData]));
  const ihdr = Buffer.concat([Buffer.from([0,0,0,13]), ihdrType, ihdrData, Buffer.alloc(4)]);
  ihdr.writeUInt32BE(ihdrCrc, 17);
  
  // Raw image data
  const rowLen = 1 + size * 4;
  const raw = Buffer.alloc(size * rowLen);
  for (let y = 0; y < size; y++) {
    raw[y * rowLen] = 0; // filter byte
    for (let x = 0; x < size; x++) {
      const idx = y * rowLen + 1 + x * 4;
      raw[idx] = r;
      raw[idx + 1] = g;
      raw[idx + 2] = b;
      raw[idx + 3] = 255;
    }
  }
  
  const compressed = zlib.deflateSync(raw);
  const idatType = Buffer.from('IDAT');
  const idatCrc = crc32(Buffer.concat([idatType, compressed]));
  const idatLen = Buffer.alloc(4);
  idatLen.writeUInt32BE(compressed.length, 0);
  const idatCrcBuf = Buffer.alloc(4);
  idatCrcBuf.writeUInt32BE(idatCrc, 0);
  const idat = Buffer.concat([idatLen, idatType, compressed, idatCrcBuf]);
  
  // IEND
  const iendType = Buffer.from('IEND');
  const iendCrc = crc32(iendType);
  const iend = Buffer.concat([Buffer.from([0,0,0,0]), iendType, Buffer.alloc(4)]);
  iend.writeUInt32BE(iendCrc, 8);
  
  const png = Buffer.concat([sig, ihdr, idat, iend]);
  fs.writeFileSync(filename, png);
}

const base = '/Users/alep/Downloads/02_AI_Agents/rentmasseur-extension';
// Accent color: #cc8b4a = 204, 139, 74
makePng(16,  204, 139, 74, `${base}/icon16.png`);
makePng(48,  204, 139, 74, `${base}/icon48.png`);
makePng(128, 204, 139, 74, `${base}/icon128.png`);

fs.writeFileSync(`${base}/icons_done.txt`, 'done');
