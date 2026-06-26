(function () {
  'use strict';

  const PANEL_ID = 'rm-booker-panel';
  let panel = null;

  const BOOKING_SERVER = 'http://localhost:3000';
  const HF_SPACE_API = 'https://josephrw-rentmasseur-optimizer.hf.space/api/ingest';

  function getSlugFromPath() {
    const providerMatch = window.location.pathname.match(/\/provider\/([^/]+)/);
    if (providerMatch) return providerMatch[1];
    const rootMatch = window.location.pathname.match(/^\/([^/]+)$/);
    return rootMatch ? rootMatch[1] : null;
  }

  function extractProfileData() {
    const data = {
      name: '',
      location: '',
      rate: '',
      isAvailable: false,
      url: window.location.href,
      slug: getSlugFromPath(),
    };

    const h1 = document.querySelector('h1');
    if (h1) data.name = h1.innerText.trim();

    if (!data.name) {
      const titleMatch = document.title.match(/^(.+?)\s*[-|]/);
      if (titleMatch) data.name = titleMatch[1].trim();
    }

    const bodyText = document.body.innerText;
    const rateMatch = bodyText.match(/\$\d+(?:\/hr| per hour|\.\d{2})/i);
    if (rateMatch) data.rate = rateMatch[0];

    data.isAvailable = /available now|available today|open now/i.test(bodyText);

    const locMatch = bodyText.match(/([A-Z][a-z]+(?:\s[A-Z][a-z]+)?,\s*(?:NY|NJ|CA|TX|FL|IL|PA|OH|GA|NC|MI))/);
    if (locMatch) data.location = locMatch[1];

    return data;
  }

  function providerSlug(data) {
    return data.slug || (data.name || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  }

  async function fetchAvailability(slug) {
    try {
      const res = await fetch(`${BOOKING_SERVER}/api/availability/${slug}`);
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  function createPanel(data, availability) {
    if (panel) return;

    panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.className = 'rm-booker-panel';

    const remote = availability || {};
    const status = remote.status || (data.isAvailable ? 'available' : 'unknown');
    const statusClass = status === 'available' ? 'available' : 'unknown';
    const statusText = status === 'available' ? 'Available' : 'Status unknown';
    const checkedAt = remote.checked_at ? `Checked ${new Date(remote.checked_at).toLocaleString()}` : 'Live page only';
    const sourceBadge = remote.mode ? `<br><span class="rm-badge">${remote.mode}</span>` : '';

    const slug = providerSlug(data);
    const bookUrl = `${BOOKING_SERVER}/widget.html?provider=${encodeURIComponent(slug)}&source=rentmasseur`;
    const verifyUrl = `${BOOKING_SERVER}/verify.html?provider=${encodeURIComponent(slug)}&source=rentmasseur`;

    panel.innerHTML = `
      <button class="rm-close" id="rm-close-btn">&times;</button>
      <h3>${escapeHtml(data.name || 'Masseur')}</h3>
      <div class="rm-meta">
        <span class="rm-status ${statusClass}"></span>${statusText}
        ${sourceBadge}
        <br>${escapeHtml(checkedAt)}
        ${data.location ? '<br>' + escapeHtml(data.location) : ''}
        ${data.rate ? '<br>' + escapeHtml(data.rate) : ''}
      </div>
      <a class="rm-btn" href="${bookUrl}" target="_blank">
        Book Now
      </a>
      <a class="rm-btn rm-btn-verify" href="${verifyUrl}" target="_blank">
        Verify Video Call
      </a>
      <button class="rm-btn rm-btn-secondary" id="rm-check-avail">
        Check Availability
      </button>
    `;

    document.body.appendChild(panel);

    document.getElementById('rm-close-btn').addEventListener('click', () => {
      panel.remove();
      panel = null;
    });

    document.getElementById('rm-check-avail').addEventListener('click', async () => {
      try {
        const res = await fetch(`${BOOKING_SERVER}/api/availability/${slug}`);
        if (!res.ok) throw new Error('Provider not found');
        const result = await res.json();
        alert(`${result.name}: ${result.status}\nLast checked: ${new Date(result.checked_at).toLocaleString()}`);
      } catch (e) {
        alert('Could not connect to booking server. Make sure it is running on localhost:3000');
      }
    });
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  async function sendMetricsToHF(data) {
    try {
      const payload = {
        url: window.location.href,
        slug: data.slug,
        name: data.name,
        location: data.location,
        rate: data.rate,
        is_available: data.isAvailable,
        timestamp: new Date().toISOString(),
        source: 'chrome_extension'
      };
      await fetch(HF_SPACE_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      console.log('[RM] Metrics sent to HF Space');
    } catch (e) {
      console.warn('[RM] Could not send metrics to HF Space:', e);
    }
  }

  async function init() {
    if (window.location.pathname === '/' || window.location.pathname === '/home') return;

    const data = extractProfileData();
    if (!data.name) return;

    const slug = providerSlug(data);
    const availability = await fetchAvailability(slug);

    // Send first-party metrics to HF Space (user is logged in, no automation)
    sendMetricsToHF(data);

    setTimeout(() => {
      createPanel(data, availability);
    }, 2000);
  }

  // Handle SPA navigation
  let lastUrl = location.href;
  new MutationObserver(() => {
    const url = location.href;
    if (url !== lastUrl) {
      lastUrl = url;
      if (panel) { panel.remove(); panel = null; }
      setTimeout(init, 1500);
    }
  }).observe(document, { subtree: true, childList: true });

  init();
})();
