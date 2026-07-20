"""
RentMasseur API Client — bounded, production-ready HTTP client.

Confirmed endpoints only. No guesswork. No spam.
"""

import json
import logging
import os
import re
import time
from typing import Optional, Dict, Any

import requests

log = logging.getLogger("rm_api")

BASE = "https://rentmasseur.com"
API = f"{BASE}/api/v1"

_PROXY_URL = os.environ.get("PROXY_URL", "")
_PROXY_SECRET = os.environ.get("PROXY_SECRET", "")

if _PROXY_URL:
    _PROXY_URL = _PROXY_URL.rstrip("/")
    API = f"{_PROXY_URL}/api/v1"
    BASE = _PROXY_URL
    log.info("Using proxy: %s", _PROXY_URL)


class RentMasseurAPI:
    """Direct API client for rentmasseur.com using confirmed endpoints."""

    def __init__(self, min_request_interval: float = 2.0):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{BASE}/settings",
            "Origin": BASE,
        })
        if _PROXY_SECRET:
            self.session.headers["X-Proxy-Secret"] = _PROXY_SECRET
        self.csrf = None
        self.logged_in = False
        self.username = None
        self.last_request = 0.0
        self.min_request_interval = min_request_interval
        self._read_cache = {}
        self._cache_ttl = 15.0

    def _wait(self):
        """Respectful rate limiting between requests."""
        elapsed = time.time() - self.last_request
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request = time.time()

    def _get(self, path: str, params: Optional[Dict] = None) -> requests.Response:
        self._wait()
        return self.session.get(f"{API}{path}", params=params, timeout=15)

    def _cached_get(self, path: str, cache_key: str = None) -> Dict:
        """GET with in-memory TTL cache for read endpoints."""
        key = cache_key or path
        now = time.time()
        cached = self._read_cache.get(key)
        if cached and (now - cached[0]) < self._cache_ttl:
            return cached[1]
        resp = self._get(path)
        resp.raise_for_status()
        data = resp.json()
        self._read_cache[key] = (now, data)
        return data

    def invalidate_cache(self, *keys: str):
        """Invalidate specific cache keys after a mutation."""
        for k in keys:
            self._read_cache.pop(k, None)

    def invalidate_all(self):
        self._read_cache.clear()

    def _post(self, path: str, json_data: Dict) -> requests.Response:
        self._wait()
        return self.session.post(f"{API}{path}", json=json_data, timeout=15)

    def _put(self, path: str, json_data: Dict) -> requests.Response:
        self._wait()
        return self.session.put(f"{API}{path}", json=json_data, timeout=15)

    def _get_csrf(self) -> str:
        resp = self.session.get(f"{BASE}/login")
        m = re.search(r'csrf["\s:=]+([A-Za-z0-9+/=]{20,})', resp.text)
        if m:
            self.csrf = m.group(1)
            return self.csrf
        for cookie in self.session.cookies:
            if "csrf" in cookie.name.lower() or "token" in cookie.name.lower():
                self.csrf = cookie.value
                return self.csrf
        return ""

    def login(self, username: str, password: str) -> bool:
        """Login via API and store bearer token."""
        self.username = username
        csrf = self._get_csrf()
        self._wait()
        resp = self.session.post(f"{API}/login", json={
            "email": username,
            "password": password,
            "csrf": csrf,
            "remember": True,
        })
        if resp.status_code != 200:
            log.error("Login failed: %d %s", resp.status_code, resp.text[:200])
            return False
        try:
            data = resp.json()
        except Exception:
            log.error("Login response not JSON (captcha/block?): %s", resp.text[:300])
            return False
        token = data.get("accessToken")
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.logged_in = True
        log.info("Login OK as %s", username)
        return True

    def load_cookies(self, cookies: list):
        """Load cookies from a saved session (e.g. from Selenium)."""
        for c in cookies:
            self.session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
        self.logged_in = True

    # ------------------------------------------------------------------
    # Confirmed read endpoints
    # ------------------------------------------------------------------

    def get_dashboard(self) -> Dict:
        return self._cached_get("/account/dashboard", "dashboard")

    def get_availability(self) -> Dict:
        return self._cached_get("/account/dashboard/availability", "availability")

    def set_availability(self, option: int = 1, duration: int = 5) -> Dict:
        """
        Set availability.
        option: 0=Not Set, 1=Available, 2=Not Available
        duration: index from timePeriods (0=1h, 1=2h, ..., 5=6h)
        """
        resp = self._put("/account/dashboard/availability", {"option": option, "duration": duration})
        resp.raise_for_status()
        self.invalidate_cache("availability")
        return resp.json()

    def get_ad_statistics(self) -> Dict:
        return self._cached_get("/account/dashboard/ad-statistics", "ad_statistics")

    def get_keeponline(self) -> Dict:
        return self._cached_get("/account/keeponline", "keeponline")

    def get_about(self) -> Dict:
        return self._cached_get("/settings/about", "about")

    def get_mailbox(self, page: int = 1, folder: int = 1, sort: int = 1) -> Dict:
        resp = self._get("/mailbox", params={"page": page, "folder": folder, "sort": sort})
        resp.raise_for_status()
        return resp.json()

    def get_blogs(self, page: int = 1) -> Dict:
        resp = self._get("/blogs", params={"page": page})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Confirmed write endpoints
    # ------------------------------------------------------------------

    def set_visibility(self, visible: bool) -> Dict:
        resp = self._put("/settings/visibility", {"isAdHidden": not visible})
        resp.raise_for_status()
        self.invalidate_cache("keeponline", "dashboard")
        return resp.json()

    def set_sms_alerts(self, enabled: bool) -> Dict:
        resp = self._put("/settings/sms", {"sms": enabled})
        resp.raise_for_status()
        self.invalidate_cache("dashboard")
        return resp.json()

    def set_track_actions(self, enabled: bool) -> Dict:
        resp = self._put("/settings/track-actions", {"trackActions": enabled})
        resp.raise_for_status()
        self.invalidate_cache("dashboard")
        return resp.json()

    def set_about(self, headline: str, description: str) -> Dict:
        resp = self._put("/settings/about", {"headline": headline, "description": description})
        resp.raise_for_status()
        self.invalidate_cache("about")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "raw": resp.text[:500]}

    # ------------------------------------------------------------------
    # Blog endpoints
    # ------------------------------------------------------------------

    def get_blog(self, blog_id: str) -> Dict:
        resp = self._get(f"/blogs/{blog_id}")
        resp.raise_for_status()
        return resp.json()

    def create_blog(self, title: str, body: str, tags: list = None) -> Dict:
        payload = {"title": title, "body": body}
        if tags:
            payload["tags"] = tags
        resp = self._post("/blogs", payload)
        resp.raise_for_status()
        self.invalidate_cache("blogs")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "raw": resp.text[:500]}

    def update_blog(self, blog_id: str, title: str = None, body: str = None) -> Dict:
        payload = {}
        if title:
            payload["title"] = title
        if body:
            payload["body"] = body
        resp = self._put(f"/blogs/{blog_id}", payload)
        resp.raise_for_status()
        self.invalidate_cache("blogs")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "raw": resp.text[:500]}

    def delete_blog(self, blog_id: str) -> Dict:
        self._wait()
        resp = self.session.delete(f"{API}/blogs/{blog_id}", timeout=15)
        resp.raise_for_status()
        self.invalidate_cache("blogs")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "raw": resp.text[:500]}

    # ------------------------------------------------------------------
    # Search (confirmed working 2026-07-09)
    # ------------------------------------------------------------------

    def search_masseurs(self, city: str = "manhattan-ny", page: int = 1) -> Dict:
        resp = self._post("/search", {"searchCity": city, "page": page, "skipUsers": "0"})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Profile visit (read-only profile fetch)
    # ------------------------------------------------------------------

    def visit_profile(self, username: str) -> Dict:
        self._wait()
        resp = self.session.get(f"{API}/profile/{username}", timeout=15)
        try:
            return resp.json()
        except Exception:
            return {"status": "visited", "username": username, "http": resp.status_code}

    def get_profile(self, username: str) -> Dict:
        return self._cached_get(f"/profile/{username}", f"profile_{username}")

    # ------------------------------------------------------------------
    # Photo / Gallery endpoints
    # ------------------------------------------------------------------

    def get_photos(self) -> Dict:
        """Fetch current photo gallery order and metadata."""
        return self._cached_get("/settings/photos", "photos")

    def reorder_photos(self, photo_ids: list) -> Dict:
        """Reorder photos by sending ordered list of photo IDs."""
        resp = self._put("/settings/photos/reorder", {"order": photo_ids})
        resp.raise_for_status()
        self.invalidate_cache("photos")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "raw": resp.text[:500]}

    def delete_photo(self, photo_id: str) -> Dict:
        """Delete a photo from the gallery."""
        self._wait()
        resp = self.session.delete(f"{API}/settings/photos/{photo_id}", timeout=15)
        resp.raise_for_status()
        self.invalidate_cache("photos")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "raw": resp.text[:500]}

    def upload_photo(self, file_path: str, caption: str = "") -> Dict:
        """Upload a new photo to the gallery."""
        import mimetypes
        self._wait()
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, mimetypes.guess_type(file_path)[0] or "image/jpeg")}
            data = {"caption": caption} if caption else {}
            resp = self.session.post(f"{API}/settings/photos", files=files, data=data, timeout=30)
        resp.raise_for_status()
        self.invalidate_cache("photos")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "raw": resp.text[:500]}

    # ------------------------------------------------------------------
    # Audit — verify all endpoints are live
    # ------------------------------------------------------------------

    def audit_endpoints(self) -> Dict:
        """Test all confirmed endpoints and return status report."""
        results = {}
        tests = [
            ("dashboard", lambda: self.get_dashboard()),
            ("availability", lambda: self.get_availability()),
            ("ad_statistics", lambda: self.get_ad_statistics()),
            ("keeponline", lambda: self.get_keeponline()),
            ("about", lambda: self.get_about()),
            ("mailbox", lambda: self.get_mailbox()),
            ("search", lambda: self.search_masseurs()),
            ("photos", lambda: self.get_photos()),
        ]
        for name, fn in tests:
            try:
                fn()
                results[name] = "OK"
            except Exception as e:
                results[name] = f"FAIL: {e}"
        return results

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def send_message(self, username: str, message: str) -> Dict:
        resp = self._post("/mailbox/send", {"username": username, "message": message})
        resp.raise_for_status()
        self.invalidate_cache("mailbox")
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "raw": resp.text[:500]}

    def get_conversation(self, username: str, page: int = 1) -> Dict:
        resp = self._get(f"/mailbox/conversation/{username}", params={"page": page})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Search (read-only)
    # ------------------------------------------------------------------

    def search(self, city: str = "manhattan-ny", available_only: bool = False,
               page: int = 1, skip: int = 0) -> Dict:
        body = {"searchCity": city, "page": page, "skipUsers": str(skip)}
        if available_only:
            body["available"] = 1
        resp = self._post("/search", body)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Full status
    # ------------------------------------------------------------------

    def full_status(self) -> Dict:
        return {
            "dashboard": self.get_dashboard(),
            "availability": self.get_availability(),
            "stats": self.get_ad_statistics(),
            "keeponline": self.get_keeponline(),
            "about": self.get_about(),
            "interview": self.get_interview(),
        }

