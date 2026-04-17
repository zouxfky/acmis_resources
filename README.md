# ACMIS

当前目录包含：

- `src/`：React + Vite 登录页
- `backend/app.py`：FastAPI + SQLite 登录接口
- `schema.md`：当前数据库结构草稿

## Windows 首次安装

推荐环境：

- Python `3.9+`
- Node.js `18+`
- PowerShell

首次安装依赖：

```powershell
cd C:\Users\Administrator\Desktop\acmis_resources
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r backend\requirements.txt
npm install
```

如果 PowerShell 提示脚本执行被限制，先执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Windows 后端启动

在 PowerShell 中执行：

```powershell
cd C:\Users\Administrator\Desktop\acmis_resources
.\.venv\Scripts\Activate.ps1
$env:ACMIS_SECRET_KEY="请替换成你自己的随机长字符串"
$env:ACMIS_ENV="development"
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

后端健康检查：

```powershell
curl.exe http://127.0.0.1:8000/api/health
```

正常返回：

```json
{"status":"ok"}
```

## Windows 前端启动

新开一个 PowerShell 窗口，执行：

```powershell
cd C:\Users\Administrator\Desktop\acmis_resources
npm run dev -- --host 0.0.0.0 --port 4173
```

前端访问地址：

```text
http://127.0.0.1:4173
```

前端响应检查：

```powershell
curl.exe -I http://127.0.0.1:4173
```

## Windows 局域网访问

如果要让其他机器访问当前 Windows 主机，需要额外放行端口：

```powershell
New-NetFirewallRule -DisplayName "ACMIS Backend 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000
New-NetFirewallRule -DisplayName "ACMIS Frontend 4173" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 4173
```

然后局域网访问：

```text
http://你的Windows机器IP:4173
```

## Linux 启动

如果是在 Linux 上运行，可使用：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm install
python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## 默认登录账号

首次启动后会自动初始化 SQLite 数据库 `backend/acmis.db`，并写入一个管理员账号：

```text
username: admin
password: acmis@admin
```

仅当 `users` 表为空时才会自动创建这名管理员。这个密码只用于首次启动，后续应尽快修改。

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
