/*
 * Vercel Serverless Function: /api/bios
 * Returns top-scoring bio candidates from the HF Space OS backend.
 */

export default async function handler(req, res) {
  const HF_SPACE_URL = process.env.HF_SPACE_URL || '';
  try {
    if (!HF_SPACE_URL) {
      return res.status(200).json({ bios: [], note: 'HF_SPACE_URL not set' });
    }
    const resp = await fetch(`${HF_SPACE_URL}/api/os/bios`);
    const data = await resp.json();
    return res.status(200).json(data);
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
}
