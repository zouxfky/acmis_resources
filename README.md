# ACMIS

当前目录包含：

- `src/`：React + Vite 登录页
- `backend/app.py`：FastAPI + SQLite 登录接口
- `schema.md`：当前数据库结构草稿

## 前端启动

```bash
npm install
npm run dev
```

默认地址：

```bash
http://127.0.0.1:4173
```

## 后端启动

先安装依赖：

```bash
python3 -m pip install -r backend/requirements.txt
```

启动 API：

```bash
python3 -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

## 默认登录账号

首次启动后会自动初始化 SQLite 数据库 `backend/acmis.db`，并写入一个管理员账号：

```text
username: admin
password: ChangeMe123!
```

这只是启动用默认账号，后续应尽快修改。

## 已接入接口

- `POST /api/login`：登录并写入 HttpOnly 会话 Cookie
- `GET /api/session`：读取当前登录用户
- `POST /api/logout`：退出登录
- `POST /api/change-password`：登录态下修改密码，请求体为：

```json
{
  "current_password": "旧密码",
  "new_password": "新密码"
}
```
