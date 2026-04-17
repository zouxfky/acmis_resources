# SSH 运行态监控说明

这份文档只说明当前项目里真正要落地的 SSH 采样方案，目标是把远端容器运行信息写回数据库的 3 张运行态表：

- `container_runtime_system`
- `container_runtime_gpus`
- `container_runtime_processes`

不写历史时序，不写宿主机侧复杂 agent，不写多余的兼容方案。当前就是：

- FastAPI 进程内后台线程
- 用 SSH 周期性采样
- 每 60 秒一轮
- 同时最多采 3 台
- 每台短连接，采完立即断开
- 只保留“当前最新快照”

---

## 1. 当前运行态表

### `container_runtime_system`

用途：

- 保存一台容器当前的 CPU / 内存汇总状态

对应字段：

- `container_id`
- `cpu_percent`
- `memory_used_g`
- `memory_total_g`
- `memory_percent`
- `updated_at`

特点：

- 一台容器只保留 1 条
- 每次采样直接覆盖

### `container_runtime_gpus`

用途：

- 保存一台容器下每张 GPU 的当前状态

对应字段：

- `container_id`
- `gpu_index`
- `memory_total_g`
- `memory_used_g`
- `memory_percent`
- `compute_percent`
- `updated_at`

特点：

- 一台容器多条，一张卡一条
- 每次采样按 `container_id` 删旧插新

### `container_runtime_processes`

用途：

- 保存当前正在占用 GPU 的进程快照

对应字段：

- `container_id`
- `user_id`
- `linux_username`
- `pid`
- `process_name`
- `updated_at`

特点：

- 只保留当前快照
- 每次采样按 `container_id` 删旧插新
- `user_id` 允许为空，因为 SSH 采到的是 Linux 用户，不一定总能映射到系统用户

---

## 2. 当前推荐采样命令

当前页面和后端采样实际需要这 4 步命令：

```bash
nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits
top -bn1 | head -n 5
lsof /dev/nvidia* 2>/dev/null | awk 'NR>1 {print $1, $2, $3}' | sort -u
pids=$(lsof /dev/nvidia* 2>/dev/null | awk 'NR>1 {print $2}' | sort -u | paste -sd, -) && [ -n "$pids" ] && ps -p "$pids" -o pid=,user=,args=
```

说明：

- 第 1 条拿 GPU 逐卡数据
- 第 2 条拿 CPU / 内存总览
- 第 3 条拿当前 GPU 占用进程、PID 和 Linux 用户
- 第 4 条用 PID 反查完整命令行

---

## 3. 三条命令分别采什么

### 3.1 GPU 逐卡信息

命令：

```bash
nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits
```

示例输出：

```text
0, NVIDIA A100-SXM4-40GB, 40960, 4367, 27
1, NVIDIA A100-SXM4-40GB, 40960, 0, 0
```

字段含义：

- `index`：GPU 编号
- `name`：GPU 型号
- `memory.total`：该卡总显存，单位 MB
- `memory.used`：该卡已用显存，单位 MB
- `utilization.gpu`：该卡计算利用率，单位 `%`

落库方式：

- `index` -> `gpu_index`
- `memory.total` -> 换算为 `memory_total_g`
- `memory.used` -> 换算为 `memory_used_g`
- `memory.used / memory.total * 100` -> `memory_percent`
- `utilization.gpu` -> `compute_percent`

注意：

- 这是按每张 GPU 一行返回
- 显存和利用率天然就是逐卡数据，不应该先写进 `containers`

### 3.2 CPU / 内存总览

命令：

```bash
top -bn1 | head -n 5
```

示例输出：

```text
top - 01:08:35 up 65 days, 11:28,  0 users,  load average: 36.23, 48.78, 65.42
Tasks:  98 total,   1 running,   7 sleeping,   0 stopped,  90 zombie
%Cpu(s): 12.0 us,  1.6 sy,  0.0 ni, 85.8 id,  0.5 wa,  0.0 hi,  0.1 si,  0.0 st
MiB Mem : 1031843.4 total, 512780.6 free, 119529.8 used, 399532.8 buff/cache
MiB Swap:      0.0 total,      0.0 free,      0.0 used. 887866.1 avail Mem
```

当前只取这两类：

- CPU 使用率
- 内存总量 / 已用量

解析建议：

- CPU：`100 - id`
- 内存：从 `MiB Mem` 行取 `total` 和 `used`

落库方式：

- CPU -> `cpu_percent`
- 内存总量换算为 `memory_total_g`
- 内存已用换算为 `memory_used_g`
- `used / total * 100` -> `memory_percent`

说明：

- `top` 给人工排查和程序解析都够用
- 当前不需要把 load average、zombie 等系统信息写表

### 3.3 GPU 占用进程、Linux 用户和完整命令

命令：

```bash
lsof /dev/nvidia* 2>/dev/null | awk 'NR>1 {print $1, $2, $3}' | sort -u
```

示例输出：

```text
python3 1742 root
tensorboard 1891 alice
```

字段含义：

- 第 1 列：进程名
- 第 2 列：容器内 PID
- 第 3 列：Linux 用户

这条命令的用途：

- 先定位“当前哪些 PID 正在打开 GPU 设备”
- 先得到容器内 PID 和 Linux 用户

但是它不够，因为：

- 第 1 列只是进程名，不是完整命令
- 我们最终需要完整命令行来展示，比如：
  - `python3 test.py --matrix-size 16000 --steps 1000 --hold-seconds 100`

所以必须再补一条 `ps`。

### 3.4 用 PID 反查完整命令

命令：

```bash
pids=$(lsof /dev/nvidia* 2>/dev/null | awk 'NR>1 {print $2}' | sort -u | paste -sd, -) && [ -n "$pids" ] && ps -p "$pids" -o pid=,user=,args=
```

示例输出：

```text
1742 root python3 test.py --matrix-size 16000 --steps 1000 --hold-seconds 100
1891 alice tensorboard --logdir /workspace/runs/exp-0421
```

字段含义：

- 第 1 列：PID
- 第 2 列：Linux 用户
- 第 3 列开始：完整命令行

最终落库方式：

- `pid`：以 `ps` 返回的 PID 为准
- `linux_username`：优先取 `ps` 的用户，和 `lsof` 不一致时以 `ps` 为准
- `process_name`：直接存完整命令行，也就是 `args`
- `user_id`：
  - 能映射就写入
  - 映射不了就写 `NULL`

说明：

- 原始 `lsof /dev/nvidia*` 输出会很长，因为一个进程会打开很多 FD
- 这里必须做 `awk + sort -u` 去重
- `lsof` 负责找“谁在占 GPU”
- `ps` 负责拿“完整命令是什么”
- 当前不强依赖 `nvidia-smi --query-compute-apps` 的 PID，因为在容器环境里 PID 视角可能不一致

---

## 4. 当前采用的 SSH 方案

当前确定采用：

- 方案 A：直接放在 FastAPI 进程里
- SSH 实现：`paramiko`
- 采样周期：每 60 秒
- 最大并发：同时最多采 3 台
- 连接策略：采样时建立一次 SSH，采完立即断开

原因：

- 当前只是分钟级采样，没有必要维持长连接
- 短连接更容易控制超时、失败重试和密码变更
- 最大并发设为 3，可以避免同时压太多 SSH 和 SQLite 写入

---

## 5. 运行方式

推荐方式：

- FastAPI 启动后创建一个后台线程
- 后台线程每 60 秒触发一轮采样
- 读取所有 `containers.status = 'active'` 的容器
- 使用线程池并发采样
- 每轮最多同时处理 3 台

主循环逻辑：

1. 读取所有 `active` 容器
2. 投递到 `ThreadPoolExecutor(max_workers=3)`
3. 每个 worker 采样一台容器
4. 每台容器采完就断开 SSH
5. 本轮结束后等待下一轮

注意：

- 不要为分钟级任务维护常驻 SSH 连接
- 不要让同一台容器在上一轮没结束时又被下一轮重复采样

---

## 6. 单台容器采样流程

对一台容器，固定就是下面这 7 步：

1. 读取 `host / ssh_port / root_password`
2. 用 `paramiko` 建立 SSH 连接
3. 执行 GPU 命令
4. 执行 `top` 命令
5. 执行 `lsof` 命令
6. 如果存在 GPU 占用 PID，再执行 `ps` 命令拿完整命令行
7. 解析命令输出
8. 写入数据库并关闭 SSH 连接

对应伪代码：

```python
def collect_container_runtime(container):
    ssh = connect_via_paramiko(container.host, container.ssh_port, "root", container.root_password)
    try:
        gpu_output = exec_command(ssh, GPU_COMMAND)
        system_output = exec_command(ssh, TOP_COMMAND)
        process_output = exec_command(ssh, LSOF_COMMAND)
        pid_list = parse_pid_list(process_output)
        process_detail_output = exec_command(ssh, build_ps_command(pid_list)) if pid_list else ""

        system_payload = parse_system_output(system_output)
        gpu_rows = parse_gpu_output(gpu_output)
        process_rows = parse_process_output(process_output, process_detail_output)

        save_runtime_snapshot(container.id, system_payload, gpu_rows, process_rows)
    finally:
        ssh.close()
```

---

## 7. 数据库写入方式

当前采用“最新快照”模型，不保留历史。

### 7.1 写 `container_runtime_system`

每台容器只保留 1 条：

- `cpu_percent`
- `memory_used_g`
- `memory_total_g`
- `memory_percent`
- `updated_at`

写入方式：

- 直接 `upsert`

### 7.2 写 `container_runtime_gpus`

每台容器保留一组逐卡快照。

写入方式：

1. `DELETE FROM container_runtime_gpus WHERE container_id = ?`
2. 批量插入当前所有 GPU 行

### 7.3 写 `container_runtime_processes`

每台容器保留一组当前 GPU 占用进程。

写入方式：

1. `DELETE FROM container_runtime_processes WHERE container_id = ?`
2. 批量插入当前进程

说明：

- 进程是瞬时数据，不做增量更新
- PID、用户、命令变化都直接反映在下一次全量替换里
- `process_name` 现在存的是完整命令行，不再只是短进程名

### 7.4 推荐事务流程

```sql
BEGIN;

UPSERT container_runtime_system ...;

DELETE FROM container_runtime_gpus
WHERE container_id = ?;

INSERT INTO container_runtime_gpus (...);

DELETE FROM container_runtime_processes
WHERE container_id = ?;

INSERT INTO container_runtime_processes (...);

COMMIT;
```

这样可以保证：

- CPU / 内存
- GPU 逐卡状态
- GPU 占用进程

三者在同一轮采样下是一致的。

---

## 8. 并发控制

当前建议：

- 用 `ThreadPoolExecutor(max_workers=3)`
- 多台容器之间并发
- 单台容器内部串行执行 3 条命令

原则：

- 不要同时对太多容器发 SSH
- 不要同一台容器重入采样
- 不要一边采样一边长事务占住 SQLite

建议做法：

- 先在内存里解析完命令输出
- 再开短事务写库

---

## 9. 超时与失败处理

建议参数：

- SSH 连接超时：`5` 秒
- 单条命令超时：`10` 秒
- 单台容器总超时：`20` 秒以内

失败时规则：

- 当前容器本轮标记失败
- 记录错误日志
- 不影响其他容器继续采样
- 下一轮继续重试

建议至少打这些日志：

- `container_id`
- `host`
- 采样开始时间
- 采样结束时间
- 是否成功
- 错误原因

---

## 10. 为什么当前不用长连接

当前不建议长连接，原因如下：

- 分钟级采样不需要常驻 SSH 会话
- 长连接更容易受网络抖动、空闲超时、服务端策略影响
- 后端重启或代码更新后，残留连接更难清理
- 短连接更适合现在这种简单、稳定优先的方案

一句话：

- 当前采样密度低
- 长连接没有收益，反而增加状态管理复杂度

---

## 11. 当前方案的边界

这套 SSH 采样方案当前能稳定拿到：

- 当前 CPU 使用率
- 当前内存总量 / 已用量 / 占比
- 当前每张 GPU 的显存和利用率
- 当前占用 GPU 的 Linux 用户
- 当前占用 GPU 的进程名和 PID

当前不能直接保证：

- 从 Linux 用户稳定反推出 ACMIS 业务用户
- `nvidia-smi` 看到的 PID 与容器内 `ps` 的 PID 一定一致
- 做历史趋势分析

如果后续要把 GPU 占用进程映射到 ACMIS 用户，至少要满足其中一个条件：

- 每个 ACMIS 用户在容器里都有独立 Linux 用户
- 平台侧记录“谁启动了哪个任务”
- 宿主机侧能提供 PID namespace 映射

---

## 12. 当前落地结论

当前项目里最合适的就是下面这套：

- FastAPI 进程内后台采样线程
- `paramiko` 短连接 SSH
- 每 60 秒一轮
- 同时最多采 3 台
- 每台固定执行 3 条命令
- 只写 3 张最新快照表
- 不保留历史，不做长连接

这套方案已经和当前数据库结构、前端展示需求、并发规模对齐，可以直接进入代码实现。
