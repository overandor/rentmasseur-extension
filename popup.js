document.getElementById('saveBtn').addEventListener('click', () => {
  const url = document.getElementById('serverUrl').value.trim();
  chrome.storage.local.set({ bookingServerUrl: url }, () => {
    const status = document.getElementById('status');
    status.textContent = 'Saved!';
    status.className = 'status ok';
    setTimeout(() => { status.textContent = ''; status.className = 'status'; }, 1500);
  });
});

document.getElementById('openBookings').addEventListener('click', () => {
  chrome.storage.local.get('bookingServerUrl', (data) => {
    const url = data.bookingServerUrl || 'http://localhost:3000';
    chrome.tabs.create({ url });
  });
});

// Load saved URL on open
chrome.storage.local.get('bookingServerUrl', (data) => {
  if (data.bookingServerUrl) {
    document.getElementById('serverUrl').value = data.bookingServerUrl;
  }
});
