"""创建测试账号: python -m backend.seed"""
from . import app as A
for un, pw, adm in [("admin", "Tijing@2026", 1), ("test", "test123456", 0)]:
    if not A.q1("SELECT id FROM users WHERE username=?", (un,)): A.create_user(un, pw, adm); print("created", un)
    else: print("exists", un)
