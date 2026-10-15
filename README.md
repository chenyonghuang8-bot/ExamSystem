# 题境 · 真题练习（MVP）

Web + 手机 PWA 的事业单位真题练习系统：章节闯关、自动判分 + 解析、错题回炉、限时整卷模考、每日进度与连练天数，以及 PDF 题库导入（文字解析 + 图形/公式裁图 + 扫描件 OCR）。

- 后端：FastAPI + SQLite（`backend/`）
- 前端：原生 JS 单页应用 + PWA（`frontend/`，无需构建），由后端直接托管
- 导入：PyMuPDF 解析试题/答案 PDF，tesseract `chi_sim` 识别扫描版答案

## 目录
```
backend/app.py        API（登录/练习/错题本/模考/管理导入）
backend/importer.py   题库导入（试题 PDF + 答案 PDF -> papers/questions/options/materials/images）
backend/ocr.py        单个 PDF OCR；backend/ocr_batch.py 批量 OCR（多进程）
backend/seed.py       创建测试账号
frontend/             页面、样式、PWA manifest、service worker
tests/e2e.py          Playwright 端到端测试 + 截图
data/                 运行数据（数据库 tijing.db、media/ 裁图、ocr/ 识别结果）—— 不入 git
```

## 本地运行（无 Docker）
```bash
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt            # OCR 另需系统安装 tesseract + chi_sim 语言包
# 1) 扫描版答案先 OCR（只处理没有文字层的 PDF）
OMP_THREAD_LIMIT=1 python backend/ocr_batch.py "<答案目录>" data/ocr
# 2) 导入题库（试题与答案按文件名自动配对；重复导入会原地更新，题目 id 不变）
python -m backend.importer "<试题目录>" "<答案目录>"
# 3) 测试账号
python -m backend.seed                     # admin / Tijing@2026（管理员）  test / test123456（普通）
# 4) 启动
uvicorn backend.app:app --host 0.0.0.0 --port 8000      # 或 ./run.sh（崩溃自动重启）
```
打开 http://localhost:8000 。之后也可以用管理员账号在「我的 → 题库管理」页面逐套上传 PDF 导入。

## 部署到 Mac Mini（推荐 Docker Compose）
1. 安装 Docker Desktop（或 OrbStack）。
2. 把整个 `tijing/` 目录拷到 Mac Mini（含 `data/` 即可直接带上已导入的题库和账号；不带则按下面重新导入）。
3. 启动：
   ```bash
   cd tijing
   docker compose up -d --build
   ```
4. 如需在容器里重新导入：把 PDF 放到 `import/试题` 与 `import/答案`，然后
   ```bash
   docker compose exec tijing python backend/ocr_batch.py /app/import/答案 /app/data/ocr
   docker compose exec tijing python -m backend.importer /app/import/试题 /app/import/答案
   docker compose exec tijing python -m backend.seed
   ```
5. 同一局域网访问：`http://<Mac Mini 的 IP>:8000`。手机上用 Safari/Chrome 打开后「添加到主屏幕」即为 App。
   外网访问可用 Tailscale（推荐，免公网 IP）或 Cloudflare Tunnel 指向 `localhost:8000`。
   PWA 的离线缓存/安装要求 HTTPS（localhost 除外），局域网 http 下仍可正常使用网页。

不想用 Docker：`brew install python tesseract tesseract-lang`，按「本地运行」执行，再用 launchd 常驻 `run.sh`。

## 数据模型
`papers`（试卷）→ `questions`（num、module 模块=章节、qtype: single/multi/tf/subjective、stem、answer、analysis、auto_grade、parse_flags）
→ `options`（A–D…，判断题可用 A=正确/B=错误）、`materials`（资料分析/阅读材料，多题共享）、`images`（role: stem / options / stem_full / opt_full:X / material / material_full / analysis / analysis_full）。
用户侧：`users`、`attempts`、`wrongbook`（错几次、已掌握、手动收藏）、`exams`（作答、截止时间、成绩报告）。
含公式的题干/选项会额外保存整段渲染图（`*_full`），前端优先显示图，避免公式丢失。

## 测试
```bash
python tests/e2e.py http://localhost:8000     # 登录→闯关一轮→错题入本→再练/掌握→模考交卷，截图存 screenshots/
```
