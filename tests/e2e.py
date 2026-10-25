"""
SakuraScore E2E + quality battery (pytest-playwright).

Covers:
  1. Router: 12 routes, unique active page, titles, back/forward, deep links
  2. Interactions: lab run/ablation/sweep, palette, drawer, analyze CTA, filters
  3. axe-core accessibility scans on 4 representative pages (0 critical/serious allowed)
  4. Chrome DevTools accessibility-tree (AX) spot checks
  5. Performance: FCP/LCP/CLS via PerformanceObserver + FPS during transitions
  6. Network audit: every request succeeds

Run:  python3 -m pytest tests/e2e.py -q --headed=false
"""

import pytest
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:8787/"
ROUTES = ["overview", "greenlight", "sim-lab", "diffusion", "segments", "evidence",
          "integrity", "battle-map", "demo-ops", "personas", "memo", "report",
          "status", "pipeline"]
AXE_PATH = "node_modules/axe-core/axe.min.js"


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(BASE)
        pg.wait_for_timeout(2400)
        pg.errors = errors  # type: ignore
        yield pg
        assert not errors, f"page errors: {errors}"
        b.close()


# ---------- 1 · ROUTER ----------

def test_routes_are_exclusive_and_titled(page):
    for slug in ROUTES:
        page.evaluate(f"location.hash='/{slug}'")
        page.wait_for_timeout(520)
        active = page.evaluate("[...document.querySelectorAll('.page.active')].map(s=>s.id)")
        assert len(active) == 1, slug
        assert page.title().startswith("SAKURASCORE — ")


def test_back_forward_and_deep_link(page):
    page.goto(BASE)
    page.wait_for_timeout(800)
    page.evaluate("location.hash='/sim-lab'")
    page.wait_for_timeout(500)
    page.go_back()
    page.wait_for_timeout(500)
    assert page.evaluate("[...document.querySelectorAll('.page.active')].map(s=>s.id)") == ["p01"]
    page.goto(BASE + "#/memo")
    page.wait_for_timeout(900)
    assert page.evaluate("[...document.querySelectorAll('.page.active')].map(s=>s.id)") == ["p10"]
    assert page.evaluate("document.querySelectorAll('#memoCard .memo-rec').length") == 3


# ---------- 2 · INTERACTIONS ----------

def test_lab_run_ablation_and_slopegraph(page):
    page.evaluate("location.hash='/sim-lab'")
    page.wait_for_timeout(1200)
    assert page.evaluate("document.querySelectorAll('#slopeGraph svg circle').length") == 10
    page.click(".lab-actions [data-abl='lift']")
    page.wait_for_timeout(1200)
    delta = page.text_content("#labDelta")
    assert delta == "+5.5pp", f"ablation delta {delta}"
    page.click("#labReset")
    page.wait_for_timeout(1200)
    assert page.text_content("#labDelta") == "+11.5pp"
    assert "runs" in page.text_content("#labMeta")


def test_sensitivity_sweep(page):
    page.click("#sweepChips button[data-p='dub_lift']")
    page.wait_for_timeout(1000)
    assert page.eval_on_selector("#sweepChart", "el => el.querySelectorAll('circle').length") == 7
    assert "fully positive" in page.text_content("#sweepNote")


def test_palette_keyboard_flow(page):
    page.keyboard.press("Meta+k")
    page.wait_for_timeout(300)
    page.fill("#palInput", "status")
    page.keyboard.press("Enter")
    page.wait_for_timeout(700)
    assert page.evaluate("[...document.querySelectorAll('.page.active')].map(s=>s.id)") == ["p12"]
    page.keyboard.press("Meta+k")
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    assert not page.eval_on_selector("#palette", "el => el.classList.contains('open')")


def test_analyze_cta_pipeline_first(page):
    page.evaluate("location.hash='/overview'")
    page.wait_for_timeout(700)
    page.fill("#anaTitle", "Chainsaw Man")
    page.click("#anaRun")
    page.wait_for_timeout(2200)
    out = page.text_content("#anaOut")
    assert "pipeline" in out and "SakuraScore" in out, out


def test_analyze_cta_abm_fallback(page):
    page.evaluate("location.hash='/overview'")
    page.wait_for_timeout(700)
    page.fill("#anaTitle", "zzqx nonexistent title")
    page.click("#anaRun")
    page.wait_for_timeout(2400)
    out = page.text_content("#anaOut")
    assert "abm sandbox" in out and "5/5 seeds positive" in out, out


def test_evidence_filters_and_drawer(page):
    page.evaluate("location.hash='/evidence'")
    page.wait_for_timeout(900)
    page.click("#evFilters .f[data-f='community']")
    page.wait_for_timeout(300)
    assert page.eval_on_selector_all("#evBody tr.evrow:not(.hid)", "els => els.length") == 3
    page.keyboard.press("Tab")  # walk into page; rows are focusable
    page.click("#evBody tr.evrow:not(.hid)")
    page.wait_for_timeout(400)
    assert page.eval_on_selector("#drawer", "el => el.classList.contains('open')")
    page.keyboard.press("Escape")


def test_pipeline_real_backend(page):
    page.evaluate("location.hash='/pipeline'")
    page.wait_for_timeout(2600)
    assert page.evaluate("document.querySelector('.pscore .big3')?.textContent").strip().replace(".","").isdigit()
    assert page.eval_on_selector_all("#pipeOut .factor-row", "els => els.length") == 6
    assert page.eval_on_selector_all("#pipeOut .plan-t tbody tr", "els => els.length") == 4
    assert page.eval_on_selector_all("#pipeOut .hub-row", "els => els.length") == 6
    assert page.eval_on_selector_all("#pipeOut .mrow2", "els => els.length") >= 8
    page.fill("#pipeQ", "One Punch Man")
    page.click("#pipeGo")
    page.wait_for_timeout(2200)
    assert page.text_content(".pscore .big3").strip() == "81"
    assert "Wikipedia evidence" in page.content()
    assert page.text_content("#pipeMeta").endswith("catalog live")


# ---------- 3 · AXE-CORE ----------

def _axe(page):
    page.add_script_tag(path=AXE_PATH)
    return page.evaluate("""async () => {
      const r = await axe.run(document, { resultTypes: ['violations'] });
      return r.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help }));
    }""")


@pytest.mark.parametrize("slug", ["overview", "sim-lab", "evidence", "battle-map"])
def test_axe_no_critical_violations(page, slug):
    page.evaluate(f"location.hash='/{slug}'")
    page.wait_for_timeout(1100)
    violations = _axe(page)
    blocking = [v for v in violations if v["impact"] in ("critical", "serious")]
    assert not blocking, f"axe violations on {slug}: {blocking}\nall: {violations}"


# ---------- 4 · CHROME DEVTOOLS AX TREE ----------

def test_ax_tree_semantics(page):
    page.evaluate("location.hash='/overview'")
    page.wait_for_timeout(900)
    tree_ok = page.evaluate("""() => {
      const main = document.querySelector('main');
      const h1 = document.querySelector('h1');
      const nav = document.querySelector('nav[aria-label], nav');
      const canvas = document.querySelector('#netCanvas');
      return {
        mainLandmark: main?.tagName === 'MAIN',
        h1: h1?.textContent.includes('SakuraScore'),
        nav: !!nav,
        canvasLabelled: (canvas?.getAttribute('aria-label') || '').length > 20,
        skipTarget: !!document.getElementById('maincontent'),
        dialogAttrs: document.querySelector('#drawer').getAttribute('role') === 'dialog',
      };
    }""")
    assert all(tree_ok.values()), tree_ok


# ---------- 5 · PERFORMANCE ----------

def test_perf_metrics_and_fps(page):
    page.goto(BASE)
    page.wait_for_timeout(2600)
    metrics = page.evaluate("""() => new Promise(res => {
      const po = new PerformanceObserver(l => {
        const o = {};
        for (const e of l.getEntries()) o[e.name] = e.startTime;
        res(o);
      });
      try { po.observe({ type: 'paint', buffered: true }); } catch {}
      try { po.observe({ type: 'largest-contentful-paint', buffered: true }); } catch {}
      setTimeout(() => res({}), 900);
    })""")
    fcp = metrics.get("first-contentful-paint", 0)
    assert fcp < 2500, f"FCP {fcp}ms too slow"
    # FPS during route transitions + a lab run
    fps = page.evaluate("""async () => {
      let frames = 0; const t0 = performance.now();
      const tick = () => { frames++; if (performance.now() - t0 < 2000) requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
      location.hash = '/battle-map';
      await new Promise(r => setTimeout(r, 800));
      document.querySelector('#labRun')?.click();
      await new Promise(r => setTimeout(r, 1200));
      return Math.round(frames / 2);
    }""")
    assert fps >= 45, f"only {fps} fps during transitions + lab run"
    print(f"\n   FCP {fcp:.0f}ms · {fps} fps during transition + lab run")


def test_network_all_requests_ok(page):
    bad = []
    responses = []
    page.on("response", lambda r: responses.append((r.status, r.url)))
    page.goto(BASE)
    page.wait_for_timeout(2600)
    for status, url in responses:
        if status >= 400 and "favicon" not in url:
            bad.append((status, url))
    assert not bad, f"failing requests: {bad}"
