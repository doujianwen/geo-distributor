# 健康检查使用说明（README_HEALTH_CHECK）

geo-distributor 本地演示环境健康检查（RA-11 告警钩子）现有**两个等价实现**，判据完全一致：

| 文件 | 环境 | 推荐度 |
|---|---|---|
| `health_check.ps1` | **Windows 原生 PowerShell（推荐）** | ⭐ 首选——Windows 计划任务直接调用 |
| `health_check.sh` | Git Bash / MSYS 兼容版本 | 备用——MSYS 环境使用 |

## 检查判据（两版一致）

- **C1** `/health` 返回 200 且 body 精确为 `{"status":"ok"}`
- **C2** `data/geo_distributor.db` 存在，`reports_projection` 表可读
- **C3** `PRAGMA quick_check` 返回 `ok`
- **C4** 唯一索引 `ux_reports_projection_ptv` 真实存在（RA-10 幂等守卫）
- **C5** `data/audit_log.db` 存在且 `audit_log` 行数 > 0
- **C6**（可选）经 Apache 反代 `/geo-api/health` 可达

任一失败 → 退出码 1 + `[FAIL]` 明细；全部通过 → 退出码 0 + `HEALTH_CHECK: PASS`。

## PowerShell（推荐）

```powershell
# 基本检查
powershell -ExecutionPolicy Bypass -File scripts\health_check.ps1

# 含 Apache 反代探针
powershell -ExecutionPolicy Bypass -File scripts\health_check.ps1 -WithApache
```

Python 查找顺序：`<repo>\.venv\Scripts\python.exe` → 系统 PATH `python`。

### Windows 计划任务接入

```powershell
schtasks /Create /TN "GEO-HealthCheck" /SC HOURLY /TR `
  "powershell -ExecutionPolicy Bypass -File E:\GEO项目\技术层\geo-distributor\scripts\health_check.ps1"
```

退出码即告警钩子：计划任务捕获非 0 退出后可触发外部告警
（如飞书 Webhook，参照 bookconv `FEISHU_WEBHOOK_URL` 模式）。

## Git Bash / MSYS（兼容说明）

```bash
bash scripts/health_check.sh
bash scripts/health_check.sh --with-apache
```

⚠️ `health_check.sh` 依赖 MSYS 的 `curl` 与 bash heredoc，**仅在 Git Bash/MSYS 下保证正确**；
在纯 Windows 原生环境（PowerShell、cmd、计划任务）下请使用 `health_check.ps1`。
2026-10-17 V2 终裁已双环境实测：两版判据一致、结论一致（见
`FINAL_RELEASE_CLOSURE_V2/03_DUAL_ENV_VALIDATION.md`）。

## 已知环境差异（非系统缺陷）

PowerShell 5.1 向 `python.exe` 传递**内嵌双引号的命令行参数**时会被 Win32 参数解析剥离
（`python -c "...'...'..."` 场景）。两版脚本均已规避：
ps1 采用临时脚本文件方式，sh 采用 heredoc 方式。若自行改造，请注意此差异。
