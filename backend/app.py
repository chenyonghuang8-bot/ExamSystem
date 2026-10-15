import os, json, time, datetime, threading, secrets, shutil, tempfile
import bcrypt, jwt
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from . import db, importer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "data")
SECRET_FILE = os.path.join(DATA, ".jwt_secret")
os.makedirs(DATA, exist_ok=True)
if not os.environ.get("TIJING_SECRET") and not os.path.exists(SECRET_FILE):
    open(SECRET_FILE, "w").write(secrets.token_hex(32))
SECRET = os.environ.get("TIJING_SECRET") or open(SECRET_FILE).read().strip()
LEVEL_SIZE = 10
DAILY_GOAL = int(os.environ.get("TIJING_DAILY_GOAL", "30"))
MODULES = importer.MODULES

C = db.init()
lock = threading.RLock()
def q(sql, args=()):
    with lock: return [dict(r) for r in C.execute(sql, args).fetchall()]
def q1(sql, args=()):
    r = q(sql, args); return r[0] if r else None
def ex(sql, args=()):
    with lock:
        cur = C.execute(sql, args); C.commit(); return cur.lastrowid

app = FastAPI(title="题境 API")
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware,
    allow_origins=["capacitor://localhost", "http://localhost", "https://localhost", "ionic://localhost"],
    allow_origin_regex=os.environ.get("TIJING_CORS_REGEX") or None,
    allow_methods=["*"], allow_headers=["*"], allow_credentials=False)

# ---------------- auth ----------------
class Cred(BaseModel):
    username: str
    password: str

def make_token(u): return jwt.encode({"uid": u["id"], "adm": bool(u["is_admin"]), "exp": int(time.time()) + 30 * 86400}, SECRET, algorithm="HS256")
def user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401, "请先登录")
    try: p = jwt.decode(authorization[7:], SECRET, algorithms=["HS256"])
    except Exception: raise HTTPException(401, "登录已过期")
    u = q1("SELECT id, username, is_admin FROM users WHERE id=?", (p["uid"],))
    if not u: raise HTTPException(401, "用户不存在")
    return u
def admin(u=Depends(user)):
    if not u["is_admin"]: raise HTTPException(403, "需要管理员权限")
    return u

def create_user(username, password, is_admin=0):
    h = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return ex("INSERT INTO users(username, pw_hash, is_admin) VALUES(?,?,?)", (username, h, is_admin))

@app.post("/api/register")
def register(c: Cred):
    un = c.username.strip()
    if not (2 <= len(un) <= 32) or len(c.password) < 6: raise HTTPException(400, "用户名 2-32 位，密码至少 6 位")
    if q1("SELECT id FROM users WHERE username=?", (un,)): raise HTTPException(400, "用户名已被占用")
    create_user(un, c.password)
    return login(Cred(username=un, password=c.password))

@app.post("/api/login")
def login(c: Cred):
    u = q1("SELECT * FROM users WHERE username=?", (c.username.strip(),))
    if not u or not bcrypt.checkpw(c.password.encode(), u["pw_hash"].encode()): raise HTTPException(400, "用户名或密码错误")
    return {"token": make_token(u), "user": {"id": u["id"], "username": u["username"], "is_admin": bool(u["is_admin"])}}

@app.get("/api/me")
def me(u=Depends(user)): return {**u, "is_admin": bool(u["is_admin"])}

# ---------------- question helpers ----------------
def media_url(p): return "/media/" + p.replace("#w=", "?w=")
def ser_question(qid, reveal=False):
    r = q1("SELECT * FROM questions WHERE id=?", (qid,))
    if not r: raise HTTPException(404, "题目不存在")
    imgs = q("SELECT role, path FROM images WHERE question_id=? ORDER BY ord", (qid,))
    opts = q("SELECT label, text FROM options WHERE question_id=? ORDER BY label", (qid,))
    for o in opts:
        o["images"] = [media_url(i["path"]) for i in imgs if i["role"] == f"opt_full:{o['label']}"]
    mat = None
    if r["material_id"]:
        m = q1("SELECT * FROM materials WHERE id=?", (r["material_id"],))
        mi = q("SELECT role, path FROM images WHERE material_id=? ORDER BY ord", (r["material_id"],))
        mat = {"id": m["id"], "text": m["text"], "full": [media_url(i["path"]) for i in mi if i["role"] == "material_full"],
               "images": [media_url(i["path"]) for i in mi if i["role"] == "material"]}
    paper = q1("SELECT id, title FROM papers WHERE id=?", (r["paper_id"],))
    out = {"id": r["id"], "num": r["num"], "module": r["module"], "qtype": r["qtype"], "stem": r["stem"], "auto_grade": bool(r["auto_grade"]),
           "stem_full": [media_url(i["path"]) for i in imgs if i["role"] == "stem_full"],
           "stem_images": [media_url(i["path"]) for i in imgs if i["role"] == "stem"],
           "option_images": [media_url(i["path"]) for i in imgs if i["role"] == "options"],
           "options": opts, "material": mat, "paper": paper}
    if reveal: out.update(reveal_part(r, imgs))
    return out
def reveal_part(r, imgs=None):
    if imgs is None: imgs = q("SELECT role, path FROM images WHERE question_id=? ORDER BY ord", (r["id"],))
    return {"answer": r["answer"], "analysis": r["analysis"],
            "analysis_full": [media_url(i["path"]) for i in imgs if i["role"] == "analysis_full"],
            "analysis_images": [media_url(i["path"]) for i in imgs if i["role"] == "analysis"]}
def norm(a): return "".join(sorted(set((a or "").upper().replace(",", "").replace(" ", ""))))

def record_wrong(uid, qid):
    ex("""INSERT INTO wrongbook(user_id,question_id,wrong_count,mastered,updated) VALUES(?,?,1,0,datetime('now','localtime'))
          ON CONFLICT(user_id,question_id) DO UPDATE SET wrong_count=wrong_count+1, mastered=0, updated=datetime('now','localtime')""", (uid, qid))

def module_qids(module):
    return [r["id"] for r in q("""SELECT q.id FROM questions q JOIN papers p ON p.id=q.paper_id
        WHERE q.module=? AND q.auto_grade=1 AND p.kind='objective' ORDER BY p.exam_date DESC, p.id, q.num""", (module,))]

# ---------------- home & practice ----------------
def streak(uid):
    days = {r["d"] for r in q("SELECT DISTINCT date(ts) d FROM attempts WHERE user_id=?", (uid,))}
    d = datetime.date.today(); n = 0
    if d.isoformat() not in days: d -= datetime.timedelta(days=1)
    while d.isoformat() in days: n += 1; d -= datetime.timedelta(days=1)
    return n

def module_progress(uid):
    done = {r["question_id"] for r in q("SELECT DISTINCT question_id FROM attempts WHERE user_id=?", (uid,))}
    out = []
    for m in MODULES:
        ids = module_qids(m)
        levels = [ids[i:i + LEVEL_SIZE] for i in range(0, len(ids), LEVEL_SIZE)]
        cleared = 0
        for lv in levels:
            if all(i in done for i in lv): cleared += 1
            else: break
        acc = q1(f"SELECT COUNT(*) n, SUM(correct) c FROM attempts a JOIN questions q ON q.id=a.question_id WHERE a.user_id=? AND q.module=?", (uid, m))
        out.append({"module": m, "total": len(ids), "levels": len(levels), "cleared": cleared, "answered": len([i for i in ids if i in done]),
                    "accuracy": round((acc["c"] or 0) / acc["n"] * 100) if acc["n"] else None})
    return out

@app.get("/api/home")
def home(u=Depends(user)):
    uid = u["id"]
    t = q1("SELECT COUNT(*) n, SUM(correct) c FROM attempts WHERE user_id=? AND date(ts)=date('now','localtime')", (uid,))
    wb = q1("SELECT COUNT(*) n, SUM(mastered) m FROM wrongbook WHERE user_id=?", (uid,))
    return {"user": u["username"], "is_admin": bool(u["is_admin"]), "today": t["n"], "today_correct": t["c"] or 0, "goal": DAILY_GOAL, "streak": streak(uid),
            "modules": module_progress(uid), "wrong_open": (wb["n"] or 0) - (wb["m"] or 0), "wrong_total": wb["n"] or 0,
            "papers": q1("SELECT COUNT(*) n FROM papers WHERE kind='objective'")["n"],
            "total_questions": q1("SELECT COUNT(*) n FROM questions WHERE auto_grade=1")["n"],
            "last_exam": q1("SELECT e.id, e.score, e.total, p.title FROM exams e JOIN papers p ON p.id=e.paper_id WHERE e.user_id=? AND submitted IS NOT NULL ORDER BY e.id DESC LIMIT 1", (uid,))}

@app.get("/api/modules")
def modules(u=Depends(user)): return module_progress(u["id"])

@app.get("/api/practice")
def practice(module: str, level: int = 1, u=Depends(user)):
    ids = module_qids(module)
    lv = ids[(level - 1) * LEVEL_SIZE: level * LEVEL_SIZE]
    if not lv: raise HTTPException(404, "没有这个关卡")
    return {"module": module, "level": level, "levels": (len(ids) + LEVEL_SIZE - 1) // LEVEL_SIZE, "questions": [ser_question(i) for i in lv]}

class Ans(BaseModel):
    question_id: int
    chosen: str
    mode: str = "practice"

@app.post("/api/answer")
def answer(a: Ans, u=Depends(user)):
    r = q1("SELECT * FROM questions WHERE id=?", (a.question_id,))
    if not r: raise HTTPException(404)
    if not r["auto_grade"]: return {"correct": None, **reveal_part(r)}
    ok = norm(a.chosen) == norm(r["answer"])
    ex("INSERT INTO attempts(user_id,question_id,chosen,correct,mode) VALUES(?,?,?,?,?)", (u["id"], r["id"], norm(a.chosen), int(ok), a.mode))
    if not ok: record_wrong(u["id"], r["id"])
    elif a.mode == "wrongbook":
        ex("UPDATE wrongbook SET updated=datetime('now','localtime') WHERE user_id=? AND question_id=?", (u["id"], r["id"]))
    wb = q1("SELECT wrong_count, mastered FROM wrongbook WHERE user_id=? AND question_id=?", (u["id"], r["id"]))
    return {"correct": ok, "chosen": norm(a.chosen), "in_wrongbook": bool(wb), "wrong_count": wb["wrong_count"] if wb else 0, **reveal_part(r)}

# ---------------- wrong book ----------------
@app.get("/api/wrongbook")
def wrongbook(module: str = None, u=Depends(user)):
    rows = q("""SELECT w.*, q.module, q.stem, q.num, p.title FROM wrongbook w JOIN questions q ON q.id=w.question_id JOIN papers p ON p.id=q.paper_id
                WHERE w.user_id=? ORDER BY w.mastered, w.updated DESC""", (u["id"],))
    total = len(rows); mastered = sum(r["mastered"] for r in rows)
    counts = {m: sum(1 for r in rows if r["module"] == m and not r["mastered"]) for m in MODULES}
    if module: rows = [r for r in rows if r["module"] == module]
    for r in rows: r["stem"] = (r["stem"] or "")[:90]
    return {"total": total, "mastered": mastered, "rate": round(mastered / total * 100) if total else 0, "counts": counts, "items": rows}

@app.post("/api/wrongbook/{qid}")
def wb_add(qid: int, u=Depends(user)):
    ex("""INSERT INTO wrongbook(user_id,question_id,wrong_count,manual) VALUES(?,?,0,1)
          ON CONFLICT(user_id,question_id) DO UPDATE SET mastered=0, manual=1""", (u["id"], qid)); return {"ok": True}

@app.post("/api/wrongbook/{qid}/mastered")
def wb_master(qid: int, value: int = 1, u=Depends(user)):
    ex("UPDATE wrongbook SET mastered=?, updated=datetime('now','localtime') WHERE user_id=? AND question_id=?", (value, u["id"], qid)); return {"ok": True}

@app.delete("/api/wrongbook/{qid}")
def wb_del(qid: int, u=Depends(user)):
    ex("DELETE FROM wrongbook WHERE user_id=? AND question_id=?", (u["id"], qid)); return {"ok": True}

@app.get("/api/wrongbook/practice")
def wb_practice(module: str = None, qid: int = None, u=Depends(user)):
    sql = "SELECT w.question_id FROM wrongbook w JOIN questions q ON q.id=w.question_id WHERE w.user_id=? AND w.mastered=0"
    args = [u["id"]]
    if module: sql += " AND q.module=?"; args.append(module)
    if qid: sql += " AND w.question_id=?"; args.append(qid)
    ids = [r["question_id"] for r in q(sql + " ORDER BY w.wrong_count DESC LIMIT 20", args)]
    return {"questions": [ser_question(i) for i in ids]}

@app.get("/api/question/{qid}")
def get_question(qid: int, reveal: int = 0, u=Depends(user)): return ser_question(qid, reveal=bool(reveal))

# ---------------- papers & mock exam ----------------
@app.get("/api/papers")
def papers(u=Depends(user)):
    ps = q("SELECT id, title, exam_date, kind, qcount, duration_min FROM papers ORDER BY exam_date DESC, id")
    for p in ps:
        p["gradable"] = q1("SELECT COUNT(*) n FROM questions WHERE paper_id=? AND auto_grade=1", (p["id"],))["n"]
        b = q1("SELECT MAX(score) s FROM exams WHERE user_id=? AND paper_id=? AND submitted IS NOT NULL", (u["id"], p["id"]))
        p["best"] = b["s"]
    return ps

@app.get("/api/papers/{pid}")
def paper_detail(pid: int, u=Depends(user)):
    p = q1("SELECT * FROM papers WHERE id=?", (pid,))
    if not p: raise HTTPException(404)
    ids = [r["id"] for r in q("SELECT id FROM questions WHERE paper_id=? ORDER BY num", (pid,))]
    return {"paper": p, "questions": [ser_question(i, reveal=p["kind"] == "subjective") for i in ids]}

class ExamStart(BaseModel):
    paper_id: int
    minutes: int = None

@app.post("/api/exams")
def exam_start(s: ExamStart, u=Depends(user)):
    p = q1("SELECT * FROM papers WHERE id=? AND kind='objective'", (s.paper_id,))
    if not p: raise HTTPException(404, "试卷不存在")
    mins = s.minutes or p["duration_min"]
    eid = ex("INSERT INTO exams(user_id,paper_id,deadline) VALUES(?,?,?)", (u["id"], p["id"], time.time() + mins * 60))
    return exam_get(eid, u)

@app.get("/api/exams/{eid}")
def exam_get(eid: int, u=Depends(user)):
    e = q1("SELECT * FROM exams WHERE id=? AND user_id=?", (eid, u["id"]))
    if not e: raise HTTPException(404)
    p = q1("SELECT id, title, duration_min FROM papers WHERE id=?", (e["paper_id"],))
    ids = [r["id"] for r in q("SELECT id FROM questions WHERE paper_id=? AND auto_grade=1 ORDER BY num", (e["paper_id"],))]
    done = e["submitted"] is not None
    return {"id": eid, "paper": p, "deadline": e["deadline"], "now": time.time(), "answers": json.loads(e["answers"] or "{}"), "submitted": done,
            "report": json.loads(e["report"]) if e["report"] else None, "questions": [ser_question(i, reveal=done) for i in ids]}

class ExamAns(BaseModel):
    answers: dict

@app.put("/api/exams/{eid}/answers")
def exam_save(eid: int, a: ExamAns, u=Depends(user)):
    e = q1("SELECT * FROM exams WHERE id=? AND user_id=?", (eid, u["id"]))
    if not e or e["submitted"]: raise HTTPException(400, "考试已结束")
    ex("UPDATE exams SET answers=? WHERE id=?", (json.dumps(a.answers), eid)); return {"ok": True}

@app.post("/api/exams/{eid}/submit")
def exam_submit(eid: int, a: ExamAns = None, u=Depends(user)):
    e = q1("SELECT * FROM exams WHERE id=? AND user_id=?", (eid, u["id"]))
    if not e: raise HTTPException(404)
    if e["submitted"]: return exam_get(eid, u)
    answers = a.answers if a and a.answers else json.loads(e["answers"] or "{}")
    qs = q("SELECT id, module, answer FROM questions WHERE paper_id=? AND auto_grade=1 ORDER BY num", (e["paper_id"],))
    per = {}; score = 0; wrong = []
    for r in qs:
        ch = norm(answers.get(str(r["id"]), ""))
        m = per.setdefault(r["module"], {"total": 0, "correct": 0, "blank": 0})
        m["total"] += 1
        if not ch: m["blank"] += 1
        ok = bool(ch) and ch == norm(r["answer"])
        if ok: score += 1; m["correct"] += 1
        if ch:
            ex("INSERT INTO attempts(user_id,question_id,chosen,correct,mode) VALUES(?,?,?,?,?)", (u["id"], r["id"], ch, int(ok), "exam"))
        if ch and not ok: record_wrong(u["id"], r["id"]); wrong.append(r["id"])
    used = int(min(time.time(), e["deadline"]) - datetime.datetime.fromisoformat(e["started"]).timestamp())
    rep = {"score": score, "total": len(qs), "per_module": per, "wrong": wrong, "answered": sum(1 for v in answers.values() if v), "used_sec": max(used, 0)}
    ex("UPDATE exams SET answers=?, submitted=datetime('now','localtime'), score=?, total=?, report=? WHERE id=?",
       (json.dumps(answers), score, len(qs), json.dumps(rep), eid))
    return exam_get(eid, u)

@app.get("/api/exams")
def exams(u=Depends(user)):
    return q("SELECT e.id, e.paper_id, e.started, e.submitted, e.score, e.total, p.title FROM exams e JOIN papers p ON p.id=e.paper_id WHERE e.user_id=? ORDER BY e.id DESC LIMIT 30", (u["id"],))

# ---------------- admin import ----------------
JOBS = {}
@app.post("/api/admin/import")
async def admin_import(question_pdf: UploadFile = File(...), answer_pdf: UploadFile = File(None), u=Depends(admin)):
    up = os.path.join(DATA, "uploads", time.strftime("%Y%m%d%H%M%S"))
    os.makedirs(up, exist_ok=True)
    qp = os.path.join(up, os.path.basename(question_pdf.filename)); open(qp, "wb").write(await question_pdf.read())
    ap = None
    if answer_pdf is not None and answer_pdf.filename:
        ap = os.path.join(up, os.path.basename(answer_pdf.filename)); open(ap, "wb").write(await answer_pdf.read())
    jid = secrets.token_hex(4); JOBS[jid] = {"status": "running", "file": question_pdf.filename}
    def work():
        try:
            import fitz
            ocr_dir = os.path.join(DATA, "ocr"); os.makedirs(ocr_dir, exist_ok=True)
            if ap and len("".join(p.get_text() for p in fitz.open(ap)).strip()) < 200:
                JOBS[jid]["status"] = "ocr"
                from .ocr import ocr_pdf
                open(os.path.join(ocr_dir, os.path.basename(ap) + ".txt"), "w").write(ocr_pdf(ap))
            JOBS[jid]["status"] = "parsing"
            log = []
            with lock:
                c2 = db.conn(); s = importer.import_pair(c2, qp, ap, ocr_dir, log); c2.commit()
                c2.execute("INSERT INTO import_log(report) VALUES(?)", (json.dumps(log, ensure_ascii=False),)); c2.commit()
            JOBS[jid].update(status="done", result=s)
        except Exception as e:
            JOBS[jid].update(status="error", error=str(e))
    threading.Thread(target=work, daemon=True).start()
    return {"job": jid}

@app.get("/api/admin/import/{jid}")
def admin_job(jid: str, u=Depends(admin)): return JOBS.get(jid) or {"status": "unknown"}

@app.get("/api/admin/stats")
def admin_stats(u=Depends(admin)):
    ps = q("""SELECT p.id, p.title, p.kind, p.qcount, (SELECT COUNT(*) FROM questions WHERE paper_id=p.id AND answer IS NOT NULL) answered,
              (SELECT COUNT(DISTINCT question_id) FROM images i JOIN questions qq ON qq.id=i.question_id WHERE qq.paper_id=p.id AND i.role NOT LIKE 'analysis%') with_images,
              (SELECT COUNT(*) FROM questions WHERE paper_id=p.id AND parse_flags IS NOT NULL) flagged FROM papers p ORDER BY p.exam_date DESC""")
    return {"papers": ps, "users": q1("SELECT COUNT(*) n FROM users")["n"]}

# ---------------- static ----------------
os.makedirs(importer.MEDIA, exist_ok=True)
app.mount("/media", StaticFiles(directory=importer.MEDIA), name="media")
FRONT = os.path.join(ROOT, "frontend")
app.mount("/static", StaticFiles(directory=FRONT), name="static")
@app.get("/sw.js")
def sw(): return FileResponse(os.path.join(FRONT, "sw.js"), media_type="application/javascript")
@app.get("/manifest.webmanifest")
def mf(): return FileResponse(os.path.join(FRONT, "manifest.webmanifest"), media_type="application/manifest+json")
@app.get("/{path:path}")
def index(path: str):
    if path.startswith("api/"): raise HTTPException(404)
    return FileResponse(os.path.join(FRONT, "index.html"), headers={"Cache-Control": "no-cache"})
