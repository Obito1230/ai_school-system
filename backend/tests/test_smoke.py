"""冒烟测试：pytest -q backend/tests/test_smoke.py
覆盖：登录鉴权、工单创建→L1自动发布、L3拦截硬约束、复核队列通过、官方任务、看板。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 项目根入 path

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

client = TestClient(app)


def _login(username: str, password: str) -> str:
    r = client.post("/api/v1/users/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_login_and_auth_guard():
    token = _login("admin", "admin123")
    assert client.get("/api/v1/admin/dashboard",
                      headers={"Authorization": f"Bearer {token}"}).status_code == 200
    # 未登录 401
    assert client.get("/api/v1/admin/dashboard").status_code == 401
    # 学生访问管理接口 403
    stu = _login("stu01", "123456")
    assert client.get("/api/v1/admin/dashboard",
                      headers={"Authorization": f"Bearer {stu}"}).status_code == 403


def test_order_l1_auto_publish_flow():
    """学业答疑（无高风险命中）→ L1 自动发布 → 接单 → 完成 → 评价。"""
    stu = _login("stu01", "123456")
    h = {"Authorization": f"Bearer {stu}"}
    r = client.post("/api/v1/orders", headers=h,
                    json={"text": "我想请人明天下午在图书馆答疑辅导高数"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["blocked"] is False
    order = data["order"]
    assert order["status"] in ("published", "pending_manual_review")
    # 接单（另一个人）
    stu2 = _login("stu02", "123456")
    h2 = {"Authorization": f"Bearer {stu2}"}
    r2 = client.post(f"/api/v1/orders/{order['id']}/accept", headers=h2)
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "accepted"
    r3 = client.post(f"/api/v1/orders/{order['id']}/complete", headers=h2, json={})
    assert r3.json()["status"] == "completed"
    r4 = client.post(f"/api/v1/orders/{order['id']}/rate", headers=h, json={"score": 5, "comment": "很棒"})
    assert r4.json()["status"] == "evaluated"


def test_l3_blocked_hard_constraint():
    """搬运/维修 → L3 拦截：状态 blocked，不能接单（代码级硬约束）。"""
    stu = _login("stu01", "123456")
    h = {"Authorization": f"Bearer {stu}"}
    r = client.post("/api/v1/orders", headers=h, json={"text": "请帮我搬运行李到宿舍6号楼"})
    data = r.json()
    assert data["blocked"] is True
    order = data["order"]
    assert order["status"] == "blocked"
    # 拦截日志可查询
    admin = _login("admin", "admin123")
    logs = client.get("/api/v1/admin/audit-logs?action=l3_block",
                      headers={"Authorization": f"Bearer {admin}"}).json()
    assert any(l["target"] == order["work_order_no"] for l in logs["items"])
    # 广场不可见被拦截单
    plaza = client.get("/api/v1/orders", headers=h).json()
    assert all(i["id"] != order["id"] for i in plaza["items"])


def test_review_queue_approve():
    """L2 待复核 → 管理员通过 → 发布。"""
    stu = _login("stu01", "123456")
    h = {"Authorization": f"Bearer {stu}"}
    r = client.post("/api/v1/orders", headers=h, json={"text": "请人马上帮我取快递，特急"})
    order = r.json()["order"]
    admin = _login("admin", "admin123")
    ah = {"Authorization": f"Bearer {admin}"}
    r2 = client.post(f"/api/v1/admin/review-queue/{order['id']}/decide",
                     headers=ah, json={"decision": "approve", "opinion": "信息完整，同意发布"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "published"


def test_official_task_and_dashboard():
    admin = _login("admin", "admin123")
    ah = {"Authorization": f"Bearer {admin}"}
    r = client.post("/api/v1/admin/official-tasks", headers=ah,
                    json={"title": "校运会会务志愿者", "task_type": "讲座会务",
                          "location": "田径场", "time_slot": "周六全天"})
    assert r.status_code == 200
    d = client.get("/api/v1/admin/dashboard", headers=ah).json()
    assert d["total_orders"] >= 1
