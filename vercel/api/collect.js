/*
 * Vercel Serverless Function: /api/collect
 * Collects metrics from the RentMasseur Chrome extension or any client
 * and forwards them to the Hugging Face Space OS backend.
 */

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const HF_SPACE_URL = process.env.HF_SPACE_URL || '';
  const HF_TOKEN = process.env.HF_TOKEN || '';

  try {
    const payload = req.body;
    const enriched = {
      ...payload,
      source: 'vercel',
      vercel_region: process.env.VERCEL_REGION || 'unknown',
      collected_at: new Date().toISOString(),
    };

    // Forward to HF Space
    if (HF_SPACE_URL) {
      await fetch(`${HF_SPACE_URL}/api/os/ingest`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(HF_TOKEN ? { Authorization: `Bearer ${HF_TOKEN}` } : {}),
        },
        body: JSON.stringify(enriched),
      });
    }

    // Also store in Vercel KV or just return
    return res.status(200).json({
      status: 'collected',
      payload: enriched,
      hf_forwarded: Boolean(HF_SPACE_URL),
    });
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
}
