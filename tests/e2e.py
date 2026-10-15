"""端到端验证 + 截图: python tests/e2e.py [base_url]"""
import sys, re, json
from playwright.sync_api import sync_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = "screenshots"
def run(name, vp):
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport=vp, device_scale_factor=2 if vp["width"] < 500 else 1)
        log = []
        pg.goto(BASE + "/#/login"); pg.fill("input[name=username]", "test"); pg.fill("input[name=password]", "test123456")
        pg.click("form button"); pg.wait_for_selector(".feat"); pg.screenshot(path=f"{OUT}/{name}-01-home.png", full_page=True); log.append("login ok")
        pg.goto(BASE + "/#/chapters?m=" + "判断推理"); pg.wait_for_selector(".lvl a"); pg.screenshot(path=f"{OUT}/{name}-02-chapters.png", full_page=True)
        pg.click(".lvl a >> nth=0"); pg.wait_for_selector(".opt"); pg.screenshot(path=f"{OUT}/{name}-03-question.png", full_page=True)
        wrong_seen = False
        for k in range(10):
            pg.wait_for_selector(".opt")
            # choose deliberately wrong on the first question, otherwise A
            q = pg.evaluate("1")
            pg.click(".opt >> nth=3" if k == 0 else ".opt >> nth=0"); pg.click("#sub"); pg.wait_for_selector(".verdict")
            txt = pg.inner_text(".verdict")
            if "答错" in txt and not wrong_seen:
                wrong_seen = True; pg.screenshot(path=f"{OUT}/{name}-04-result-wrong.png", full_page=True)
            elif "答对" in txt and k < 10: pg.screenshot(path=f"{OUT}/{name}-04b-result-right.png", full_page=True)
            pg.click("#nx")
        pg.wait_for_selector("text=本关完成"); log.append("level done, wrong_seen=%s" % wrong_seen)
        pg.goto(BASE + "/#/wrong"); pg.wait_for_selector(".wcard"); n = pg.locator(".wcard").count(); log.append(f"wrongbook items={n}")
        pg.screenshot(path=f"{OUT}/{name}-05-wrongbook.png", full_page=True)
        pg.goto(BASE + "/#/papers"); pg.wait_for_selector("[data-p]"); pg.screenshot(path=f"{OUT}/{name}-06-papers.png", full_page=True)
        pg.click("[data-p] >> nth=0"); pg.wait_for_selector("#sheet")
        for k in range(12):
            pg.click(".opt >> nth=%d" % (k % 4)); pg.wait_for_timeout(350)
        pg.wait_for_timeout(600); pg.screenshot(path=f"{OUT}/{name}-07-exam.png", full_page=True)
        pg.on("dialog", lambda d: d.accept()); pg.click("#hand"); pg.wait_for_selector("text=模块得分")
        log.append("exam submitted: " + pg.inner_text(".ring .c").replace("\n", " "))
        pg.screenshot(path=f"{OUT}/{name}-08-report.png", full_page=True)
        # figure & material questions via manual add to wrong book
        import sqlite3
        c = sqlite3.connect("data/tijing.db")
        f1 = c.execute("SELECT q.id FROM questions q JOIN papers p ON p.id=q.paper_id WHERE p.title LIKE '2020年11月21%' AND num=56").fetchone()[0]
        f2 = c.execute("SELECT q.id FROM questions q JOIN papers p ON p.id=q.paper_id WHERE p.title LIKE '2020年11月21%' AND num=101").fetchone()[0]
        for qid, tag in [(f1, "09-figure"), (f2, "10-material")]:
            pg.evaluate(f"fetch('/api/wrongbook/{qid}',{{method:'POST',headers:{{Authorization:'Bearer '+localStorage.getItem('tj_token')}}}})")
            pg.wait_for_timeout(300)
            pg.goto(BASE + f"/#/wpractice?q={qid}"); pg.wait_for_selector(".opt"); pg.wait_for_timeout(800)
            pg.screenshot(path=f"{OUT}/{name}-{tag}.png", full_page=True)
        log.append("manual add ok")
        # mark one mastered
        pg.goto(BASE + "/#/wrong"); pg.wait_for_selector("[data-ms]"); pg.click("[data-ms] >> nth=0"); pg.wait_for_timeout(800)
        log.append("mastery: " + pg.inner_text(".ring .c").replace("\n", " "))
        pg.screenshot(path=f"{OUT}/{name}-05b-wrongbook-mastered.png", full_page=True)
        b.close()
    return log
def figs():
    import sqlite3
    c = sqlite3.connect("data/tijing.db")
    return c.execute("SELECT q.module, (SELECT COUNT(*) FROM questions q2 WHERE q2.module=q.module AND q2.auto_grade=1 AND q2.id<q.id AND q2.paper_id IN (SELECT id FROM papers WHERE kind='objective')) FROM questions q JOIN images i ON i.question_id=q.id WHERE i.role='stem' AND q.module='判断推理' LIMIT 1").fetchone()
if __name__ == "__main__":
    print(run("desktop", {"width": 1280, "height": 800}))
    print(run("mobile", {"width": 390, "height": 844}))
