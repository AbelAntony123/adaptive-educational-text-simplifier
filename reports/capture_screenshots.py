"""Capture screenshots of the app's states with headless Edge or Chrome (no extra packages).

Starts the app in demo (mock) mode on its own port, drives it like a user and saves 2x PNG files into
reports/screenshots/. No API key is needed or used, and no Gemini request is made.

    .venv\\Scripts\\python reports\\capture_screenshots.py
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "screenshots"
APP_PORT, DEBUG_PORT = 8504, 9333
WIDTH, TALL = 1280, 4400
BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)


class Page:
    def __init__(self, ws_url: str):
        self.ws = connect(ws_url, max_size=None)
        self.next_id = 0

    def call(self, method: str, **params):
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.next_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]

    def js(self, expression: str):
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        return result["result"].get("value")

    def wait_text(self, text: str, timeout: float = 25.0) -> None:
        end = time.time() + timeout
        while time.time() < end:
            if self.js(f"document.body.innerText.includes({json.dumps(text)})"):
                return
            time.sleep(0.3)
        body = self.js("document.body.innerText") or ""
        start = body.find("Results")
        raise TimeoutError(f"Text not found on the page: {text!r}. Page after 'Results': {body[start:start + 700]!r}")

    def settle(self, seconds: float = 1.2) -> None:
        time.sleep(seconds)
        self.js("document.fonts.ready.then(() => true)")

    def _center(self, selector: str, text: str, index: int = 0):
        script = f"""(() => {{
            const hits = [...document.querySelectorAll({json.dumps(selector)})]
                .filter(e => ({json.dumps(text)} === '' || (e.innerText && e.innerText.trim().includes({json.dumps(text)})))
                             && e.getBoundingClientRect().width > 0);
            const el = hits[{index}];
            if (!el) return null;
            el.scrollIntoView({{block: 'center'}});
            const r = el.getBoundingClientRect();
            return {{x: r.x + r.width / 2, y: r.y + r.height / 2}};
        }})()"""
        return self.js(script)

    def click(self, selector: str, text: str, index: int = 0) -> None:
        point = None
        for _ in range(40):
            point = self._center(selector, text, index)
            if point:
                break
            time.sleep(0.25)
        if not point:
            hint = self.js(
                "({testids: [...new Set([...document.querySelectorAll('[data-testid]')].map(e => e.dataset.testid))]"
                ".filter(t => /elect|idebar|Combo/i.test(t)), comboboxes: document.querySelectorAll('[role=combobox]').length,"
                " baseweb: [...new Set([...document.querySelectorAll('[data-baseweb]')].map(e => e.dataset.baseweb))]})"
            )
            raise LookupError(f"Nothing to click: {selector} containing {text!r}. Page hints: {hint}")
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", type=kind, x=point["x"], y=point["y"], button="left", clickCount=1)
        self.settle(0.9)

    def choose_scenario(self, label: str) -> None:
        # Type to filter the options, then press Enter (works for options that are scrolled out of view).
        self.click('[data-testid="stSelectbox"]', "")
        time.sleep(0.5)
        self.call("Input.insertText", text=label)
        time.sleep(0.6)
        for kind in ("keyDown", "keyUp"):
            self.call("Input.dispatchKeyEvent", type=kind, key="Enter", code="Enter", windowsVirtualKeyCode=13, nativeVirtualKeyCode=13)
        self.settle(1.6)

    def shot(self, name: str, clip: dict | None = None, scale: float = 2.0) -> Path:
        OUT.mkdir(parents=True, exist_ok=True)
        params = {"format": "png", "captureBeyondViewport": False}
        if clip:
            params["clip"] = {**clip, "scale": 1}
        data = self.call("Page.captureScreenshot", **params)["data"]
        path = OUT / f"{name}.png"
        path.write_bytes(base64.b64decode(data))
        print("saved", path.name, f"({path.stat().st_size // 1024} KB)")
        return path

    def rect_of(self, js_selector_expression: str, pad: int = 14) -> dict:
        r = self.js(f"""(() => {{
            const el = {js_selector_expression};
            if (!el) return null;
            const b = el.getBoundingClientRect();
            return {{x: b.x, y: b.y, w: b.width, h: b.height}};
        }})()""")
        if not r:
            raise LookupError(f"Element not found: {js_selector_expression}")
        return {"x": max(r["x"] - pad, 0), "y": max(r["y"] - pad, 0), "width": r["w"] + 2 * pad, "height": r["h"] + 2 * pad}

    def card(self, contains: str) -> dict:
        """Rect of the smallest bordered card whose text contains ``contains``."""
        selector = '[class*="st-key-card-"]'
        expression = f"""[...document.querySelectorAll('{selector}')]
            .filter(e => (e.innerText || e.textContent || '').includes({json.dumps(contains)}) && e.getBoundingClientRect().width > 0)
            .sort((a, b) => (a.innerText || '').length - (b.innerText || '').length)[0]"""
        try:
            return self.rect_of(expression)
        except LookupError:
            found = self.js(f"[...document.querySelectorAll('{selector}')].map(e => (e.innerText || '').slice(0, 40))")
            print("Bordered cards on the page:", found)
            raise


def set_viewport(page: Page, width: int, height: int, scale: float, mobile: bool = False) -> None:
    page.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=scale, mobile=mobile)


def run_simplify(page: Page) -> None:
    page.click("button", "Simplify text")
    page.settle(2.2)


def main() -> int:
    browser = next((path for path in BROWSERS if Path(path).exists()), None)
    if not browser:
        print("No Edge or Chrome found.")
        return 1
    real = "--real" in sys.argv[1:]  # also make ONE real Gemini request (about 4 calls) for a real-result screenshot
    env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SIMPLIFIER_BACKEND_MODULE")}
    if not real:
        env["SIMPLIFIER_BACKEND_MODULE"] = ""  # demo shots only: the real backend stays disconnected
    else:
        env.pop("SIMPLIFIER_BACKEND_MODULE", None)  # the app reads its own .env file (key never leaves it)
    app = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true", "--server.port", str(APP_PORT)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    profile = tempfile.mkdtemp(prefix="shots-")
    edge = subprocess.Popen(
        [browser, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}", f"--user-data-dir={profile}",
         "--disable-gpu", "--hide-scrollbars", "--no-first-run", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://localhost:{APP_PORT}/_stcore/health", timeout=1)
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/list", timeout=1))
                ws_url = next(t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        else:
            print("The app or the browser did not start.")
            return 1

        page = Page(ws_url)
        page.call("Page.enable")
        set_viewport(page, WIDTH, TALL, 2)
        page.call("Page.navigate", url=f"http://localhost:{APP_PORT}")
        page.wait_text("Adaptive Educational Text Simplifier")
        page.settle(2.5)

        # 1. Home and input
        page.shot("01_home", clip={"x": 0, "y": 0, "width": WIDTH, "height": 960})

        # 2. A normal demo result at Beginner
        page.click("button", "Use sample text")
        run_simplify(page)
        page.wait_text("Verification: PASS")
        page.settle(1.2)
        page.shot("02_result_texts", clip=page.card("Original text"))
        page.shot("03_verification_and_types", clip=page.card("Key facts preserved"))
        page.shot("04_metrics", clip=page.card("How to read these numbers"))

        # 3. Word-level changes
        page.click("summary", "Show what changed")
        page.settle(1.0)
        page.shot("05_word_by_word_changes", clip=page.card("Original text"))

        # 4. Hard cases from the demo scenarios
        page.choose_scenario("Verification fails")
        run_simplify(page)
        page.wait_text("Verification: FAIL")
        page.shot("06_verification_fails", clip=page.card("Key facts preserved"))

        page.choose_scenario("Verification not run")
        run_simplify(page)
        page.wait_text("Verification: NOT RUN")
        page.shot("07_verification_not_run", clip=page.rect_of("document.querySelector('.badge-row')", pad=16))
        page.shot("08_not_run_verification_card", clip=page.card("No individual check details"))

        page.choose_scenario("Some metrics missing")
        run_simplify(page)
        page.wait_text("N/A")
        page.shot("09_missing_metrics_na", clip=page.card("How to read these numbers"))

        page.choose_scenario("Quota used up")
        run_simplify(page)
        page.wait_text("What you can do")
        page.settle(1.0)
        top = page.rect_of("[...document.querySelectorAll('.step')].find(e => e.innerText.includes('Results'))", pad=0)
        page.shot("10_quota_error", clip={"x": 0, "y": top["y"], "width": WIDTH, "height": 640})

        # 5. History tab with the chart
        page.choose_scenario("Normal result")
        run_simplify(page)
        page.click("button", "Intermediate")
        run_simplify(page)
        page.click('[data-testid="stTab"]', "History")
        page.settle(1.8)
        page.shot("11_history", clip=page.rect_of(
            "[...document.querySelectorAll('[data-testid=\"stTabPanel\"]')].find(e => e.innerText.includes('Open a previous result'))", pad=10))

        # 6. Real-backend mode, no key (sidebar switches and .env note)
        page.click("label", "Real backend")
        page.settle(1.5)
        page.shot("12_real_mode_sidebar", clip=page.rect_of("document.querySelector('label').closest('section')", pad=0))

        # 6b. One real Gemini result (only with --real)
        if real:
            page.click('[data-testid="stTab"]', "Simplify")
            page.click("button", "Use sample text")
            run_simplify(page)
            page.wait_text("REAL BACKEND", timeout=170)  # not "Verification:", which the earlier demo result also shows
            page.settle(1.8)
            page.shot("14_real_result_badges_and_texts", clip=page.card("Original text"))
            page.shot("15_real_verification_types", clip=page.card("Local check"))
            page.shot("16_real_metrics", clip=page.card("How to read these numbers"))
            run_simplify(page)  # same text and level again: should reuse the saved result
            page.wait_text("REUSED RESULT", timeout=30)
            page.shot("17_real_reused_result", clip=page.rect_of("document.querySelector('.badge-row')", pad=16))

        # 7. A phone-sized view
        page.click("label", "Demo with mock data")
        set_viewport(page, 390, 844, 2, mobile=True)
        page.call("Page.navigate", url=f"http://localhost:{APP_PORT}")
        page.wait_text("Adaptive Educational Text Simplifier")
        page.settle(2.5)
        page.shot("13_phone_view", clip={"x": 0, "y": 0, "width": 390, "height": 844})
        print("Done.")
        return 0
    finally:
        edge.terminate()
        app.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
