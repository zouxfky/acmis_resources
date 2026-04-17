# ACMIS 基础表结构

当前确定的 10 张核心表如下。

说明：

- 当前文档按项目现状描述，不加外键约束
- `containers` 只存静态配置
- 运行态拆成系统状态、逐卡状态、进程快照三层
- 运行态表只保留当前快照，不存历史

## 1. 用户表 `users`

```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL UNIQUE,
    real_name VARCHAR(128) NULL,
    password_hash TEXT NOT NULL,
    role ENUM('admin', 'user') NOT NULL DEFAULT 'user',
    status ENUM('active', 'disabled') NOT NULL DEFAULT 'active',
    max_ssh_keys_per_user INT NOT NULL DEFAULT 12,
    max_join_keys_per_request INT NOT NULL DEFAULT 5,
    max_containers_per_user INT NOT NULL DEFAULT 6
);
```

字段说明：

- `id`：用户主键
- `username`：登录用户名，唯一
- `real_name`：用户姓名
- `password_hash`：密码哈希，不存明文
- `role`：角色，`admin` 或 `user`
- `status`：账户状态，`active` 或 `disabled`
- `max_ssh_keys_per_user`：该用户最多可保存多少把 SSH 公钥
- `max_join_keys_per_request`：该用户单次加入容器时最多可选多少把 SSH 公钥
- `max_containers_per_user`：该用户最多可加入多少台容器

## 2. SSH 公钥表 `ssh_public_keys`

```sql
CREATE TABLE ssh_public_keys (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    key_name VARCHAR(128) NOT NULL,
    fingerprint VARCHAR(128) NOT NULL UNIQUE,
    public_key TEXT NOT NULL
);
```

字段说明：

- `id`：公钥主键
- `key_name`：公钥名称
- `fingerprint`：公钥指纹，唯一
- `public_key`：完整 SSH 公钥内容

## 3. 用户与公钥关系表 `user_ssh_key_bindings`

```sql
CREATE TABLE user_ssh_key_bindings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    ssh_key_id BIGINT NOT NULL,
    CONSTRAINT uq_user_ssh_key UNIQUE (user_id, ssh_key_id)
);
```

字段说明：

- `id`：关系主键
- `user_id`：用户 ID
- `ssh_key_id`：公钥 ID
- `uq_user_ssh_key`：同一个用户不能重复绑定同一把公钥

## 4. 容器表 `containers`

```sql
CREATE TABLE containers (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(128) NOT NULL UNIQUE,
    host VARCHAR(255) NOT NULL,
    ssh_port INT NOT NULL DEFAULT 22,
    root_password VARCHAR(255) NOT NULL DEFAULT '',
    max_users INT NOT NULL DEFAULT 5,
    gpu_model VARCHAR(128) NOT NULL,
    gpu_memory VARCHAR(64) NOT NULL,
    gpu_count INT NOT NULL DEFAULT 1,
    cpu_cores INT NOT NULL DEFAULT 1,
    memory_size VARCHAR(64) NOT NULL,
    status ENUM('active', 'offline', 'disabled') NOT NULL DEFAULT 'active'
);
```

字段说明：

- `id`：容器主键
- `name`：容器名称，唯一
- `host`：SSH 主机地址
- `ssh_port`：SSH 端口
- `root_password`：root 登录密码，用于系统侧 SSH 采样
- `max_users`：该容器最多允许多少个用户加入
- `gpu_model`：GPU 型号，例如 `NVIDIA A100`
- `gpu_memory`：静态标称显存，例如 `40G`
- `gpu_count`：GPU 数量
- `cpu_cores`：CPU 核数
- `memory_size`：静态标称内存，例如 `512G`
- `status`：容器状态，`active`、`offline`、`disabled`

## 5. 容器系统运行状态表 `container_runtime_system`

```sql
CREATE TABLE container_runtime_system (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    container_id BIGINT NOT NULL UNIQUE,
    cpu_percent INT NOT NULL DEFAULT 0,
    memory_used_g DECIMAL(10,1) NOT NULL DEFAULT 0,
    memory_total_g DECIMAL(10,1) NOT NULL DEFAULT 0,
    memory_percent INT NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL
);
```

字段说明：

- `id`：系统运行状态主键
- `container_id`：所属容器 ID，一台容器只保留一条当前系统状态
- `cpu_percent`：当前 CPU 使用率，0-100
- `memory_used_g`：当前已用内存，单位 G
- `memory_total_g`：当前总内存，单位 G
- `memory_percent`：当前内存使用率，0-100
- `updated_at`：最近一次采样时间

## 6. 容器 GPU 运行状态表 `container_runtime_gpus`

```sql
CREATE TABLE container_runtime_gpus (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    container_id BIGINT NOT NULL,
    gpu_index INT NOT NULL,
    memory_total_g DECIMAL(10,1) NOT NULL DEFAULT 0,
    memory_used_g DECIMAL(10,1) NOT NULL DEFAULT 0,
    memory_percent INT NOT NULL DEFAULT 0,
    compute_percent INT NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_container_gpu UNIQUE (container_id, gpu_index)
);
```

字段说明：

- `id`：GPU 运行状态主键
- `container_id`：所属容器 ID
- `gpu_index`：GPU 编号，例如 0、1、2、3
- `memory_total_g`：该卡总显存，单位 G
- `memory_used_g`：该卡已用显存，单位 G
- `memory_percent`：该卡显存占比，0-100
- `compute_percent`：该卡计算利用率，0-100
- `updated_at`：最近一次采样时间
- `uq_container_gpu`：同一容器下，同一个 GPU 编号只能有一条记录

## 7. 容器 GPU 进程表 `container_runtime_processes`

```sql
CREATE TABLE container_runtime_processes (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    container_id BIGINT NOT NULL,
    user_id BIGINT NULL,
    linux_username VARCHAR(128) NOT NULL,
    pid BIGINT NOT NULL,
    process_name VARCHAR(255) NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_container_pid UNIQUE (container_id, pid)
);
```

字段说明：

- `id`：进程记录主键
- `container_id`：所属容器 ID
- `user_id`：对应的 ACMIS 用户 ID，可为空
- `linux_username`：容器内 Linux 用户名，例如 `root`、`alice`
- `pid`：容器内进程 PID
- `process_name`：进程名，例如 `python3`
- `updated_at`：最近一次采样时间
- `uq_container_pid`：同一容器下，同一个 PID 只保留一条记录

## 8. 公钥与容器关系表 `ssh_key_container_bindings`

```sql
CREATE TABLE ssh_key_container_bindings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ssh_key_id BIGINT NOT NULL,
    container_id BIGINT NOT NULL,
    CONSTRAINT uq_ssh_key_container UNIQUE (ssh_key_id, container_id)
);
```

字段说明：

- `id`：关系主键
- `ssh_key_id`：SSH 公钥 ID
- `container_id`：容器 ID
- `uq_ssh_key_container`：同一把公钥不能重复绑定同一台容器

## 9. 会话表 `user_sessions`

```sql
CREATE TABLE user_sessions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    session_token_hash VARCHAR(128) NOT NULL UNIQUE,
    csrf_token VARCHAR(128) NOT NULL,
    expires_at BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    last_seen_at DATETIME NOT NULL
);
```

字段说明：

- `id`：会话主键
- `user_id`：当前会话所属用户
- `session_token_hash`：浏览器 Cookie 对应的 session token 哈希值
- `csrf_token`：当前会话绑定的 CSRF token
- `expires_at`：会话过期时间戳
- `created_at`：会话创建时间
- `last_seen_at`：最近一次使用该会话的时间

## 10. 登录限流表 `login_rate_limits`

```sql
CREATE TABLE login_rate_limits (
    scope_key VARCHAR(128) PRIMARY KEY,
    failure_count INT NOT NULL DEFAULT 0,
    first_failed_at BIGINT NOT NULL DEFAULT 0,
    locked_until BIGINT NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL
);
```

字段说明：

- `scope_key`：限流作用域，例如 `ip:127.0.0.1` 或 `user:alice`
- `failure_count`：当前窗口内失败次数
- `first_failed_at`：本轮失败窗口起始时间戳
- `locked_until`：锁定截止时间戳，0 表示未锁定
- `updated_at`：最近一次更新该限流记录的时间
