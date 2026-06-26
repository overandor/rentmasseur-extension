/**
 * RentMasseur Rotator Engine — JavaScript
 * 
 * Unified rotation engine for bios, photos, prices, interviews, and blog posts.
 * Uses RL feedback (views, clicks, calls) to decide what to rotate and when.
 * Integrates with the Chrome extension for real-time optimization.
 * 
 * Usage in extension:
 *   const rotator = new RotatorEngine({ serverUrl: 'http://localhost:3000' });
 *   await rotator.init();
 *   const nextBio = await rotator.getNextBio();
 *   const nextPrice = await rotator.getNextPrice();
 */

class RotatorEngine {
  constructor(config = {}) {
    this.serverUrl = config.serverUrl || 'http://localhost:3000';
    this.rlState = null;
    this.rotationRules = {
      bio: { maxAgeHours: 24, minRewardThreshold: 5, rotateIfStale: true },
      photo: { maxAgeHours: 48, minRewardThreshold: 3, rotateIfStale: true },
      price: { maxAgeHours: 12, minRewardThreshold: 8, rotateIfStale: false },
      interview: { maxAgeHours: 72, minRewardThreshold: 2, rotateIfStale: true },
      blog: { maxAgeHours: 48, minRewardThreshold: 4, rotateIfStale: true },
    };
    this.rewardWeights = {
      views: 1, email_clicks: 5, phone_clicks: 10, booking_inquiries: 50,
      favorites: 3, messages: 8,
    };
  }

  async init() {
    await this.loadRLState();
    return this;
  }

  async loadRLState() {
    try {
      const resp = await fetch(`${this.serverUrl}/api/rl/state`);
      if (resp.ok) {
        this.rlState = await resp.json();
        return this.rlState;
      }
    } catch (e) {
      console.warn('Could not load RL state from server, using local');
    }
    this.rlState = this._defaultState();
    return this.rlState;
  }

  _defaultState() {
    return {
      bios: {}, photos: {}, prices: {}, interviews: {}, blogs: {},
      current: { bio: null, photo: null, price: null, interview: null, blog: null },
      rotations: { bio: 0, photo: 0, price: 0, interview: 0, blog: 0 },
      history: [],
    };
  }

  calculateReward(stats, ageHours) {
    let reward = 0;
    for (const [key, weight] of Object.entries(this.rewardWeights)) {
      reward += (stats[key] || 0) * weight;
    }
    reward -= (ageHours / 24) * 0.5; // stale penalty
    return Math.round(reward * 100) / 100;
  }

  shouldRotate(type, currentEntry, ageHours, deltaReward) {
    const rules = this.rotationRules[type];
    if (!rules) return false;

    if (rules.rotateIfStale && ageHours >= rules.maxAgeHours) {
      return { rotate: true, reason: `stale (${ageHours.toFixed(1)}h >= ${rules.maxAgeHours}h)` };
    }
    if (ageHours >= rules.maxAgeHours / 2 && deltaReward < rules.minRewardThreshold) {
      return { rotate: true, reason: `low reward (${deltaReward} < ${rules.minRewardThreshold} in ${ageHours.toFixed(1)}h)` };
    }
    if (ageHours >= 6 && deltaReward === 0) {
      return { rotate: true, reason: 'zero engagement for 6+ hours' };
    }
    return { rotate: false, reason: 'performing well' };
  }

  pickNext(items, type) {
    const entries = Object.entries(items);
    if (entries.length === 0) return null;

    // Sort by: least times used, then highest historical reward
    entries.sort((a, b) => {
      const aUses = a[1].timesUsed || 0;
      const bUses = b[1].timesUsed || 0;
      if (aUses !== bUses) return aUses - bUses;
      const aReward = a[1].totalReward || 0;
      const bReward = b[1].totalReward || 0;
      return bReward - aReward;
    });

    return entries[0];
  }

  async getNextBio() {
    if (!this.rlState) await this.init();
    return this.pickNext(this.rlState.bios, 'bio');
  }

  async getNextPrice() {
    if (!this.rlState) await this.init();
    return this.pickNext(this.rlState.prices, 'price');
  }

  async getNextPhoto() {
    if (!this.rlState) await this.init();
    return this.pickNext(this.rlState.photos, 'photo');
  }

  async getNextInterview() {
    if (!this.rlState) await this.init();
    return this.pickNext(this.rlState.interviews, 'interview');
  }

  async getNextBlog() {
    if (!this.rlState) await this.init();
    return this.pickNext(this.rlState.blogs, 'blog');
  }

  registerRotation(type, id, content, metadata = {}) {
    if (!this.rlState) this.rlState = this._defaultState();

    const store = this.rlState[type + 's'] || {};
    const prevId = this.rlState.current[type];
    if (prevId && store[prevId]) {
      store[prevId].endTime = new Date().toISOString();
    }

    store[id] = {
      content: content.slice(0, 500),
      ...metadata,
      startTime: new Date().toISOString(),
      totalReward: 0,
      deltaReward: 0,
      lastStats: {},
      timesUsed: (store[id]?.timesUsed || 0) + 1,
    };

    this.rlState[type + 's'] = store;
    this.rlState.current[type] = id;
    this.rlState.rotations[type] = (this.rlState.rotations[type] || 0) + 1;

    this.rlState.history.push({
      timestamp: new Date().toISOString(),
      type, id, action: 'rotate',
    });

    return this.rlState;
  }

  updateReward(type, id, stats) {
    if (!this.rlState) return;
    const store = this.rlState[type + 's'];
    if (!store || !store[id]) return;

    const entry = store[id];
    const prevStats = entry.lastStats || {};
    const delta = {};
    for (const key of Object.keys(this.rewardWeights)) {
      delta[key] = Math.max(0, (stats[key] || 0) - (prevStats[key] || 0));
    }

    const ageHours = entry.startTime
      ? (Date.now() - new Date(entry.startTime).getTime()) / 3600000
      : 0;

    const deltaReward = this.calculateReward(delta, ageHours);
    entry.deltaReward = deltaReward;
    entry.totalReward = (entry.totalReward || 0) + deltaReward;
    entry.lastStats = stats;
    entry.ageHours = Math.round(ageHours * 100) / 100;

    this.rlState.history.push({
      timestamp: new Date().toISOString(),
      type, id, action: 'reward',
      deltaReward, totalReward: entry.totalReward,
    });

    return entry;
  }

  getTopPerformers(type, n = 5) {
    if (!this.rlState) return [];
    const store = this.rlState[type + 's'] || {};
    return Object.entries(store)
      .sort((a, b) => (b[1].totalReward || 0) - (a[1].totalReward || 0))
      .slice(0, n);
  }

  getReport() {
    if (!this.rlState) return 'No RL state loaded';
    const lines = ['=== ROTATOR ENGINE REPORT ==='];
    for (const type of ['bio', 'photo', 'price', 'interview', 'blog']) {
      const store = this.rlState[type + 's'] || {};
      const rotations = this.rlState.rotations[type] || 0;
      const current = this.rlState.current[type];
      lines.push(`\n${type.toUpperCase()}: ${rotations} rotations, current=${current}`);
      const top = this.getTopPerformers(type, 3);
      for (const [id, data] of top) {
        lines.push(`  ${id}: reward=${data.totalReward || 0}, uses=${data.timesUsed || 0}`);
      }
    }
    return lines.join('\n');
  }

  async saveState() {
    try {
      await fetch(`${this.serverUrl}/api/rl/state`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.rlState),
      });
    } catch (e) {
      console.warn('Could not save RL state to server');
    }
  }
}

// Price rotation strategies
const PRICE_STRATEGIES = [
  { name: 'premium_peak', desc: 'High price during peak hours (evening/weekend)', base: 250, variance: 30 },
  { name: 'off_peak_deal', desc: 'Lower price for off-peak slots', base: 180, variance: 20 },
  { name: 'new_client_special', desc: 'First-time client discount', base: 150, variance: 15 },
  { name: 'loyalty_rate', desc: 'Returning client rate', base: 200, variance: 10 },
  { name: 'late_night_premium', desc: 'After-hours premium', base: 300, variance: 50 },
  { name: 'lunch_express', desc: 'Quick session lunch special', base: 120, variance: 10 },
  { name: 'weekend_warrior', desc: 'Weekend athletic recovery', base: 220, variance: 25 },
  { name: 'holiday_special', desc: 'Holiday seasonal rate', base: 200, variance: 40 },
  { name: 'last_minute', desc: 'Same-day booking discount', base: 170, variance: 15 },
  { name: 'package_deal', desc: 'Multi-session package rate', base: 190, variance: 20 },
];

function generatePrice(strategy, hour, dayOfWeek) {
  const s = strategy || PRICE_STRATEGIES[0];
  let price = s.base;

  // Peak hours: 6pm-11pm
  if (hour >= 18 && hour <= 23) price += s.variance * 0.5;
  // Late night: midnight-4am
  if (hour >= 0 && hour <= 4) price += s.variance * 0.8;
  // Weekend premium
  if (dayOfWeek === 0 || dayOfWeek === 6) price += s.variance * 0.3;
  // Add small random variance
  price += Math.round((Math.random() - 0.5) * s.variance * 0.2);

  return Math.max(80, Math.round(price));
}

// Export for Node.js and browser
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { RotatorEngine, PRICE_STRATEGIES, generatePrice };
}
if (typeof window !== 'undefined') {
  window.RotatorEngine = RotatorEngine;
  window.PRICE_STRATEGIES = PRICE_STRATEGIES;
  window.generatePrice = generatePrice;
}
