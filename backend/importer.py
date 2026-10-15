"""题境 题库导入: 试题PDF + 答案PDF -> SQLite.  用法: python -m backend.importer QDIR ADIR [--ocr-dir DIR]"""
import fitz, re, os, sys, json, glob, collections
from . import db

MEDIA = os.environ.get("TIJING_MEDIA", os.path.join(os.path.dirname(__file__), "..", "data", "media"))
WATER = re.compile(r"上岸真题库|saztk|更多真题")
MODMAP = [("公共基础知识", "常识判断"), ("常识判断", "常识判断"), ("常识", "常识判断"), ("言语", "言语理解与表达"),
          ("判断推理", "判断推理"), ("数量关系", "数量关系"), ("资料分析", "资料分析")]
MODULES = ["常识判断", "言语理解与表达", "判断推理", "数量关系", "资料分析"]
HDR = re.compile(r"^\s*(第[一二三四五六七八九十]+部分|[一二三四五六七八九十]+、)\s*(.*)")
QSTART = re.compile(r"^\s*(\d{1,3})\s*(?:[.．、]\s*(.*)|$)")
OPT = re.compile(r"(?<![A-Za-z])([A-D])\s*[、.．]")
MAT = re.compile(r"^\s*(（[一二三四五六七八九十]+）|[一二三四五六七八九十]+、|根据.{0,30}(资料|材料)|阅读.{0,10}(材料|文字|资料)|材料[一二三四五六0-9]?[：:])")

def norm_name(fn):
    s = os.path.splitext(os.path.basename(fn))[0]
    for t in ["（答案+解析）", "（答案）", "（解析）", "答案解析", "试题", "答案", "解析", "笔试", " ", "\u3000"]:
        s = s.replace(t, "")
    return s

def module_of(text):
    for k, v in MODMAP:
        if k in text: return v
    return None

# ---------- low level extraction ----------
def page_items(doc, pno, img_freq):
    """returns sorted list of items: ('line', y0, y1, x0, x1, text, has_inline) / ('fig', rect)"""
    page = doc[pno]; H = page.rect.height; W = page.rect.width
    d = page.get_text("dict")
    raw, imgs = [], []
    for b in d["blocks"]:
        if b["type"] == 1:
            r = fitz.Rect(b["bbox"])
            if r.width < 3 or r.height < 3: continue
            if img_freq.get(sig(r), 0) > 3: continue  # repeated logo/watermark
            if r.width > W * 0.9 and r.height > H * 0.9: continue  # full-page bg
            imgs.append(r); continue
        for l in b["lines"]:
            t = "".join(s["text"] for s in l["spans"])
            if not t.strip(): continue
            xs = []
            for sp in l["spans"]:
                n = max(1, len(sp["text"])); x0, x1 = sp["bbox"][0], sp["bbox"][2]
                xs += [x0 + (x1 - x0) * k / n for k in range(len(sp["text"]))]
            raw.append([fitz.Rect(l["bbox"]), t, xs])
    # vector drawings -> clusters
    try:
        dr = [fitz.Rect(p["rect"]) for p in page.get_drawings()]
    except Exception:
        dr = []
    dr = [r for r in dr if not (r.height < 2.5 and r.width > 0) and not (r.width < 2.5 and r.height > H * 0.5) and r.width < W * 0.95 and (r.width > 4 or r.height > 4)]
    for r in cluster(dr):
        if r.width > 25 and r.height > 18: imgs.append(r)
    imgs = cluster(imgs, gap=3)
    # merge lines on same row (y-centre within tolerance), order by x
    raw = [x for x in raw if not WATER.search(x[1])]
    xsmap = {id(x[1]): x[2] for x in raw}
    raw = [x for x in raw if not ((x[0].y0 > H * 0.9 or x[0].y1 < H * 0.06) and x[0].x0 > W * 0.3 and re.fullmatch(r"\s*\d{1,3}(\s*/\s*\d{1,3})?\s*", x[1]))]
    raw.sort(key=lambda x: (x[0].y0 + x[0].y1) / 2)
    groups = []
    for r, t, _xs in raw:
        cy = (r.y0 + r.y1) / 2
        if groups and abs(groups[-1][0] - cy) < 4.5: groups[-1][1].append((r, t, _xs))
        else: groups.append([cy, [(r, t, _xs)]])
    lines = []
    for cy, g in groups:
        g.sort(key=lambda x: x[0].x0)
        rr = fitz.Rect(g[0][0]); txt = ""; xs = []
        for i, (r, t, x_) in enumerate(g):
            rr |= r
            if i == 1 and re.fullmatch(r"\s*\d{1,3}\s*", txt) and not re.match(r"\s*[.．、]", t):
                k = len(txt) - len(txt.lstrip()); txt = txt.strip() + "、"; xs = xs[k:k + len(txt) - 1]; xs.append(xs[-1] if xs else r.x0)
            txt += t; xs += x_
        lines.append([rr, txt, xs])
    items = []
    used = set()
    for r, t, xs in lines:
        inline = [i for i, im in enumerate(imgs) if im.height < 40 and abs((im.y0 + im.y1) / 2 - (r.y0 + r.y1) / 2) < max(8, r.height)]
        for i in inline: used.add(i)
        rr = fitz.Rect(r)
        for i in inline: rr |= imgs[i]
        k = len(t) - len(t.lstrip()); ts = t.strip()
        items.append(("line", pno, rr, ts, bool(inline), xs[k:k + len(ts)]))
    for i, im in enumerate(imgs):
        if i in used: continue
        # skip figure fully covering text lines? keep
        items.append(("fig", pno, im, "", False, []))
    items.sort(key=lambda it: (it[1], it[2].y0, it[2].x0))
    return items

def sig(r): return (round(r.x0 / 5), round(r.y0 / 5), round(r.width / 5), round(r.height / 5))

def cluster(rects, gap=6):
    rects = [fitz.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False; out = []
        for r in rects:
            for o in out:
                g = fitz.Rect(o.x0 - gap, o.y0 - gap, o.x1 + gap, o.y1 + gap)
                if g.intersects(r):
                    o |= r; changed = True; break
            else:
                out.append(fitz.Rect(r))
        rects = out
    return rects

def doc_items(doc):
    freq = collections.Counter()
    for p in doc:
        for b in p.get_text("dict")["blocks"]:
            if b["type"] == 1: freq[sig(fitz.Rect(b["bbox"]))] += 1
    its = []
    for i in range(len(doc)): its += page_items(doc, i, freq)
    return its

def render(doc, pno, rect, path, pad=3, dpi=160, vpad=None):
    page = doc[pno]; vpad = pad if vpad is None else vpad
    r = fitz.Rect(rect.x0 - pad, rect.y0 - vpad, rect.x1 + pad, rect.y1 + vpad) & page.rect
    if r.is_empty or r.width < 2 or r.height < 2: return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.get_pixmap(clip=r, dpi=dpi).save(path)
    return path

class Seg:
    def __init__(self): self.text = []; self.x1 = []; self.bands = {}; self.inline = False; self.figs = []
    def add_line(self, pno, r, t, inl):
        self.text.append(t); self.x1.append(r.x1); self.inline |= inl
        b = self.bands.get(pno); self.bands[pno] = (b | r) if b else fitz.Rect(r)
    def txt(self):
        if not self.x1: return join_lines(self.text)
        right = max(self.x1); out = []
        for i, t in enumerate(self.text):
            out.append(t)
            if i < len(self.text) - 1 and self.x1[i] < right - 45 and len(t) > 0: out.append("\n")
        return re.sub(r"\s*\n\s*", "\n", join_lines(out)).strip()

def join_lines(ls):
    s = ""
    for t in ls:
        if t == "\n": s += "\n"; continue
        if s and re.search(r"[A-Za-z0-9]$", s) and re.match(r"[A-Za-z0-9]", t): s += " "
        s += t
    return s.strip()

# ---------- question PDF ----------
def parse_questions(doc):
    items = doc_items(doc)
    qs, mats = [], []
    module, qtype = None, "single"
    cur = None; mat = None; seg = None; state = None
    in_header = False; title_lines = []
    for kind, pno, r, t, inl, xs in items:
        if kind == "fig":
            if cur is None and mat is None: continue
            if state == "mat" or (cur is None and mat is not None):
                mat["seg"].figs.append((pno, r))
            elif cur is not None and module == "资料分析" and state == "D":
                mat = {"seg": Seg(), "module": module}; mats.append(mat); state = "mat"; mat["seg"].figs.append((pno, r))
            elif cur is not None and state == "D" and cur["opts"]["D"].text and "".join(cur["opts"]["D"].text).strip():
                cur["tail"].append((pno, r))
            elif cur is not None:
                cur["figs"].append((pno, r, "stem" if state == "stem" else "options"))
            continue
        if in_header:
            if t.endswith("。") or t.endswith("答案。") or len(t) < 3: in_header = False
            continue
        m = HDR.match(t)
        if m and (module_of(m.group(2)) or "选择" in m.group(2) or "判断题" in m.group(2)) and len(t) > 6 and (state in (None, "D", "mat", "opts") or not cur):
            mm = module_of(m.group(2))
            if mm or not module: module = mm or "常识判断"
            qtype = "multi" if "多项" in t or "多选" in t else ("tf" if "判断题" in t else "single")
            in_header = not t.endswith("。"); state = "hdr"; mat = None
            continue
        if cur is None and module is None:
            title_lines.append(t)
        qm = QSTART.match(t)
        expect = (qs[-1]["num"] + 1) if qs else 1
        if qm and int(qm.group(1)) == expect:
            if module is None: module = "常识判断"
            prev = cur
            cur = {"tail": [], "tail_labels": None, "num": expect, "module": module, "qtype": qtype, "stem": Seg(), "opts": collections.OrderedDict(), "figs": [], "mat": mat if module in ("资料分析", "言语理解与表达") or (mat and state == "mat") else None}
            if state != "mat" and module != "资料分析": cur["mat"] = None
            if module == "资料分析" and mat is not None: cur["mat"] = mat
            if prev is not None and prev["tail"] and prev["module"] == module:
                cur["figs"] += [(p_, r_, "stem") for p_, r_ in prev["tail"]]; cur["pre_labels"] = prev["tail_labels"]; prev["tail"] = []
            qs.append(cur); state = "stem"; seg = cur["stem"]
            rest = (qm.group(2) or "").strip()
            if rest: t = rest
            else: continue
        elif cur is not None and state == "D" and MAT.match(t) and module in ("资料分析", "言语理解与表达", "判断推理"):
            mat = {"seg": Seg(), "module": module}; mats.append(mat); state = "mat"; seg = mat["seg"]
        elif state == "hdr" and module == "资料分析":
            mat = {"seg": Seg(), "module": module}; mats.append(mat); state = "mat"; seg = mat["seg"]
        if cur is None and state != "mat": continue
        if state == "hdr": continue
        if state == "D" and cur["tail"] and re.fullmatch(r"(\s*[A-D]\s*[、.．]\s*[A-D]?\s*)+", t):
            cur["tail_labels"] = t; continue
        # label-only line under a figure, e.g. "A、AB、BC、CD、D" or "A B C D"
        if state in ("stem", "A", "B", "C", "D") and re.fullmatch(r"(\s*[A-D]\s*[、.．]?\s*[A-D]?\s*){2,}", t) and (cur["figs"] or cur["tail"]):
            for lab in "ABCD":
                if lab not in cur["opts"]:
                    sg = Seg(); sg.text = [""]; cur["opts"][lab] = sg
            state = "D"; seg = cur["opts"]["D"]; continue
        # split options
        if state in ("stem", "A", "B", "C", "D") and qtype != "tf" or state in ("stem",):
            pos = 0; pieces = []
            for om in OPT.finditer(t):
                lab = om.group(1)
                nxt = "A" if state == "stem" else (chr(ord(state) + 1) if state != "D" else None)
                if pieces: nxt = chr(ord(pieces[-1][0]) + 1) if pieces[-1][0] != "D" else None
                if lab == nxt:
                    pieces.append((lab, om.start(), om.end()))
            if pieces:
                pre = t[:pieces[0][1]].strip()
                if pre: seg.add_line(pno, r, pre, inl)
                L = max(1, len(t))
                for i, (lab, s_, e) in enumerate(pieces):
                    end = pieces[i + 1][1] if i + 1 < len(pieces) else len(t)
                    seg = Seg(); cur["opts"][lab] = seg; state = lab
                    if len(xs) == len(t) and e < len(t):
                        pr = fitz.Rect(xs[e] - 1, r.y0, (xs[end] - 1) if end < len(t) else r.x1, r.y1)
                    elif len(pieces) > 1:
                        pr = fitz.Rect(r.x0 + r.width * s_ / L, r.y0, r.x0 + r.width * end / L if end < len(t) else r.x1, r.y1)
                    else: pr = fitz.Rect(r)
                    seg.add_line(pno, pr, t[e:end].strip(), inl)
                continue
        if seg is not None: seg.add_line(pno, r, t, inl)
    for q in qs:
        if q["tail"]: q["figs"] += [(p_, r_, "options") for p_, r_ in q["tail"]]
        if len(q["opts"]) < 4 and (q["figs"] or q.get("pre_labels")):
            for lab in "ABCD":
                if lab not in q["opts"]:
                    sg = Seg(); sg.text = [""]; q["opts"][lab] = sg
            q["opts"] = collections.OrderedDict(sorted(q["opts"].items()))
    return qs, mats, join_lines(title_lines[:3])

# ---------- answer PDF ----------
ANS = re.compile(r"(?:正确答案(?:为|是)|答案(?:为|是|[：:])|【答案】)\s*[：:]?\s*([A-D](?:\s*[A-D、,，])*)")
def clean_ans(s): return "".join(sorted(set(re.findall(r"[A-D]", s))))

def parse_answers_text(doc):
    items = doc_items(doc)
    blocks = {}; cur = None; last = 0; grid = {}
    for kind, pno, r, t, inl, xs in items:
        if kind == "fig":
            if cur: blocks[cur]["figs"].append((pno, r))
            continue
        gt = re.findall(r"(?<!\d)(\d{1,3})\s*[、.．]\s*([A-D]{1,4})(?![A-Za-z\u4e00-\u9fff])", t)
        if gt and re.fullmatch(r"(\s*\d{1,3}\s*[、.．]\s*[A-D]{1,4}\s*)+", t):
            for n_, a_ in gt: grid.setdefault(int(n_), a_)
            continue
        qm = QSTART.match(t)
        if qm and int(qm.group(1)) == last + 1 and (qm.group(2) is None or len(t) < 200):
            last = cur = int(qm.group(1)); blocks[cur] = {"seg": Seg(), "figs": []}
            rest = (qm.group(2) or "").strip()
            if not rest: continue
            t = rest
        if cur: blocks[cur]["seg"].add_line(pno, r, t, inl)
    out = {}
    for n, b in blocks.items():
        txt = b["seg"].txt(); am = ANS.findall(txt)
        out[n] = {"answer": clean_ans(am[-1]) if am else grid.get(n), "analysis": txt, "seg": b["seg"], "figs": b["figs"]}
    for n, a in grid.items():
        if n not in out: out[n] = {"answer": a, "analysis": None, "seg": None, "figs": []}
    return out

def parse_answers_ocr(text, nq):
    lines = [l.strip() for l in text.splitlines()]
    grid_tok = re.compile(r"(?<!\d)(\d{1,3})\s*[、.,，．:：]\s*([A-D])(?![A-Za-z])")
    g = {}
    blocks = {}; cur = None; last = 0
    for l in lines:
        if not l or WATER.search(l): continue
        toks = grid_tok.findall(l)
        if len(toks) >= 3:
            for n, a in toks:
                n = int(n)
                if 1 <= n <= nq and n not in g: g[n] = a
            continue
        m = re.match(r"^(\d{1,3})(?:\s*[、.,，．:：。”\"]+\s*|\s+|$)(?!\d)(.*)", l)
        if m and (int(m.group(1)) == last + 1 or (int(m.group(1)) == last + 2 and len(m.group(2)) > 8)):
            last = cur = int(m.group(1)); blocks[cur] = [m.group(2)]; continue
        if cur: blocks[cur].append(l)
    out = {}; nb = 0
    for i in range(1, nq + 1):
        ans = None; ana = None
        if i in blocks:
            ana = "\n".join(blocks[i]).strip()
            am = re.findall(r"答案\s*[为是]?\s*[：:]?\s*([A-D](?:\s*[A-D])*)", ana.replace(" ", ""))
            if am: ans = clean_ans(am[-1]); nb += 1
        if not ans: ans = g.get(i)
        out[i] = {"answer": ans, "analysis": ("[OCR识别，可能有错字] " + ana) if ana else None, "seg": None, "figs": []}
    return out, len(g), nb

# ---------- main ----------
def import_pair(c, qpath, apath, ocr_dir, log):
    name = os.path.basename(qpath)
    qdoc = fitz.open(qpath)
    subjective = "主观题" in name
    pid_row = c.execute("SELECT id FROM papers WHERE source_q=?", (name,)).fetchone()
    keep_pid = None; old_ids = {}
    if pid_row:  # re-import: keep paper id and question ids (so users' wrong book / history survive)
        keep_pid = pid_row[0]
        old_ids = {r[1]: r[0] for r in c.execute("SELECT id, num FROM questions WHERE paper_id=?", (keep_pid,))}
        for q_ in old_ids.values():
            c.execute("DELETE FROM options WHERE question_id=?", (q_,)); c.execute("DELETE FROM images WHERE question_id=?", (q_,))
        c.execute("DELETE FROM images WHERE material_id IN (SELECT id FROM materials WHERE paper_id=?)", (keep_pid,))
        c.execute("DELETE FROM questions WHERE paper_id=?", (keep_pid,)); c.execute("DELETE FROM materials WHERE paper_id=?", (keep_pid,))
        c.execute("DELETE FROM papers WHERE id=?", (keep_pid,))
    title = norm_name(name).replace("《", " 《")
    dm = re.match(r"(\d{4})年(\d{1,2})?月?(\d{1,2})?", name)
    date = "-".join(x for x in dm.groups() if x) if dm else ""
    c.execute("INSERT INTO papers(id, title, exam_date, source_q, source_a, kind) VALUES(?,?,?,?,?,?)",
              (keep_pid, title, date, name, os.path.basename(apath) if apath else None, "subjective" if subjective else "objective"))
    pid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    mdir = os.path.join(MEDIA, f"p{pid}")
    stat = {"paper": title, "file": name, "questions": 0, "with_answer": 0, "with_images": 0, "failures": [], "answer_source": None}

    def save_img(doc, pno, rect, fname):
        p = render(doc, pno, rect, os.path.join(mdir, fname), dpi=200, vpad=1 if "full" in fname else 3)
        return (os.path.relpath(p, MEDIA) + "#w=" + str(round(rect.width + 6))) if p else None

    # answers
    adoc = fitz.open(apath) if apath else None
    atext_len = len("".join(p.get_text() for p in adoc).strip()) if adoc else 0
    if subjective:
        qtext = "\n".join(p.get_text() for p in qdoc)
        qtext = "\n".join(l for l in qtext.splitlines() if not WATER.search(l))
        if adoc and atext_len > 200:
            atext = "\n".join(p.get_text() for p in adoc)
        else:
            f = os.path.join(ocr_dir, os.path.basename(apath) + ".txt") if apath else None
            atext = "[OCR识别]\n" + open(f).read() if f and os.path.exists(f) else ""
        atext = "\n".join(l for l in atext.splitlines() if not WATER.search(l))
        c.execute("INSERT INTO questions(id,paper_id,num,module,qtype,stem,answer,analysis,auto_grade) VALUES(?,?,?,?,?,?,?,?,0)",
                  (old_ids.get(1), pid, 1, "主观题", "subjective", qtext.strip(), None, atext.strip()))
        c.execute("UPDATE papers SET qcount=1, duration_min=150 WHERE id=?", (pid,))
        stat.update(questions=1, with_answer=1 if atext.strip() else 0, answer_source="text" if atext_len > 200 else "ocr", note="主观题，整卷展示，不自动判分")
        log.append(stat); return stat

    qs, mats, _ = parse_questions(qdoc)
    if adoc is not None and atext_len > 200:
        ans = parse_answers_text(adoc); stat["answer_source"] = "text"
    else:
        f = os.path.join(ocr_dir, os.path.basename(apath) + ".txt") if apath else None
        if f and os.path.exists(f):
            ans, ng, ns = parse_answers_ocr(open(f).read(), len(qs)); stat["answer_source"] = f"ocr(grid={ng},seq={ns})"
        else:
            ans = {}; stat["answer_source"] = "missing"
    mat_ids = {}
    for k, m in enumerate(mats):
        c.execute("INSERT INTO materials(paper_id,text) VALUES(?,?)", (pid, m["seg"].txt()))
        mid = c.execute("SELECT last_insert_rowid()").fetchone()[0]; mat_ids[id(m)] = mid
        o = 0
        if m["seg"].inline:
            for pno, band in sorted(m["seg"].bands.items()):
                p = save_img(qdoc, pno, band, f"m{k}_full{pno}.png")
                if p: c.execute("INSERT INTO images(material_id,role,path,ord) VALUES(?,?,?,?)", (mid, "material_full", p, o)); o += 1
        for j, (pno, r) in enumerate(m["seg"].figs):
            p = save_img(qdoc, pno, r, f"m{k}_{j}.png")
            if p: c.execute("INSERT INTO images(material_id,role,path,ord) VALUES(?,?,?,?)", (mid, "material", p, o)); o += 1
    for q in qs:
        n = q["num"]; flags = []
        a = ans.get(n) or {}
        answer = a.get("answer")
        opts = q["opts"]
        if len(opts) < 4: flags.append(f"options={len(opts)}")
        if not answer: flags.append("no_answer")
        elif answer not in ("".join(opts.keys()) + "ABCD"): pass
        qt = q["qtype"]
        if qt == "single" and answer and len(answer) > 1: qt = "multi"
        c.execute("INSERT INTO questions(id,paper_id,num,module,qtype,stem,material_id,answer,analysis,auto_grade,parse_flags) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (old_ids.get(n), pid, n, q["module"], qt, q["stem"].txt(), mat_ids.get(id(q["mat"])) if q["mat"] else None, answer, a.get("analysis"), 1 if answer else 0, ",".join(flags) or None))
        qid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        for lab, s in opts.items():
            c.execute("INSERT INTO options(question_id,label,text) VALUES(?,?,?)", (qid, lab, s.txt()))
        o = 0; has_img = False
        segs = [("stem_full", q["stem"])] + [(f"opt_full:{lab}", s) for lab, s in opts.items()]
        for role, s in segs:
            if s.inline:
                for pno, band in sorted(s.bands.items()):
                    p = save_img(qdoc, pno, band, f"q{n}_{role.replace(':','')}_{pno}.png")
                    if p: c.execute("INSERT INTO images(question_id,role,path,ord) VALUES(?,?,?,?)", (qid, role, p, o)); o += 1; has_img = True
        for j, (pno, r, role) in enumerate(q["figs"]):
            p = save_img(qdoc, pno, r, f"q{n}_{j}.png")
            if p: c.execute("INSERT INTO images(question_id,role,path,ord) VALUES(?,?,?,?)", (qid, role, p, o)); o += 1; has_img = True
        if a.get("seg") is not None and adoc is not None:
            s = a["seg"]
            if s.inline:
                for pno, band in sorted(s.bands.items()):
                    p = save_img(adoc, pno, band, f"a{n}_full{pno}.png")
                    if p: c.execute("INSERT INTO images(question_id,role,path,ord) VALUES(?,?,?,?)", (qid, "analysis_full", p, o)); o += 1
            for j, (pno, r) in enumerate(a["figs"]):
                p = save_img(adoc, pno, r, f"a{n}_{j}.png")
                if p: c.execute("INSERT INTO images(question_id,role,path,ord) VALUES(?,?,?,?)", (qid, "analysis", p, o)); o += 1
        if has_img or q["mat"]: stat["with_images"] += 1 if has_img else 0
        stat["questions"] += 1; stat["with_answer"] += 1 if answer else 0
        if flags: stat["failures"].append(f"{n}:{'/'.join(flags)}")
    nq = len(qs)
    c.execute("UPDATE papers SET qcount=?, duration_min=? WHERE id=?", (nq, 120 if nq <= 120 else 150, pid))
    stat["materials"] = len(mats)
    stat["modules"] = dict(collections.Counter(q["module"] for q in qs))
    extra = sorted(set(ans) - set(q["num"] for q in qs))
    if extra: stat["failures"].append(f"answers_without_question:{len(extra)}")
    log.append(stat); return stat

def pair_files(qdir, adir):
    qs = sorted(glob.glob(os.path.join(qdir, "*.pdf"))); As = {norm_name(a): a for a in glob.glob(os.path.join(adir, "*.pdf"))}
    return [(q, As.get(norm_name(q))) for q in qs]

def run(qdir, adir, ocr_dir, only=None):
    c = db.init(); log = []
    for q, a in pair_files(qdir, adir):
        if only and only not in q: continue
        try:
            s = import_pair(c, q, a, ocr_dir, log); c.commit()
            print(f"{s['questions']:4d} q  ans {s['with_answer']:4d}  img {s['with_images']:3d}  fail {len(s['failures']):3d}  [{s['answer_source']}] {s['paper']}", flush=True)
        except Exception as e:
            import traceback; traceback.print_exc(); c.rollback(); log.append({"file": q, "error": str(e)})
    c.execute("INSERT INTO import_log(report) VALUES(?)", (json.dumps(log, ensure_ascii=False),)); c.commit()
    return log

if __name__ == "__main__":
    a = sys.argv[1:]
    ocr = os.path.join(os.path.dirname(__file__), "..", "data", "ocr")
    if "--ocr-dir" in a: i = a.index("--ocr-dir"); ocr = a[i + 1]; del a[i:i + 2]
    only = None
    if "--only" in a: i = a.index("--only"); only = a[i + 1]; del a[i:i + 2]
    run(a[0], a[1], ocr, only)
