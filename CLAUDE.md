# Scout

BoxProbe 客户侧 CLI。执行 Python 场景文件，录制 API 流量，生成回归对比报告。

**安装：** `pip install scout`（Forgejo Package Registry: `forge.boxprobe.com/core/-/packages/pypi/scout`）

## 代码结构

```
scout/
├── cli.py                  # Click CLI 入口
│                           #   scout run    — 正式执行（带 API 录制）
│                           #   scout verify — 调试验证（截图，不录制）
│                           #   scout diff   — 两次 run 的 API 回归对比
│                           #   scout runs   — 查看运行历史
├── config.py               # app.json 配置加载 + URL override
├── git.py                  # Git 信息读取（commit, branch）
├── index.py                # 运行索引（SQLite, .scout/index.db）
├── run_metadata.py         # 运行元数据构建
├── runner/
│   ├── executor.py         # Playwright 调度 + 批量执行
│   ├── scenario.py         # Scenario DSL（base_url, setup, test）
│   ├── page.py             # Page 抽象（导航、点击、输入、等待）
│   └── locator.py          # 元素定位（像素坐标 → Playwright locator）
├── collector/
│   ├── subprocess.py       # 录制代理子进程管理
│   ├── proxy.py            # hudsucker 代理 Python 包装
│   ├── control.py          # 代理控制 API（session start/stop）
│   └── db.py               # 录制数据库（SQLite: scenarios + api_records）
├── matcher/
│   ├── align.py            # API 记录配对（LCS 对齐）
│   ├── compare.py          # JSON 结构 + 值比对
│   ├── normalize.py        # URL 规范化（动态 ID 推断）
│   ├── diff_db.py          # Diff 结果数据库
│   └── diff_report.py      # HTML diff 报告生成
├── report/
│   ├── html.py             # 执行报告（HTML）
│   └── junit.py            # JUnit XML 报告
├── secrets/                # 凭证注入（pyrage 加密，待实现）
├── bridge/                 # Browser Bridge（CDP，待实现）
├── mcp/                    # MCP Server（AI Agent 集成，待实现）
└── server/                 # 待实现
```

## CLI 命令

```bash
# 正式执行：启动录制代理，录制 API 流量到 .scout/runs/<run_id>/record.db
scout run scenarios/auth/login-success
scout run scenarios/              # 目录递归查找 test.py

# 调试验证：截图模式，不启动录制代理
scout verify scenarios/auth/login-success --headed

# API 回归对比：两次 run 的录制数据做 diff
scout diff 20260424-153012-a1b2 20260425-101530-c3d4
scout diff <baseline_run_id> <target_run_id> --detail

# 查看历史
scout runs --app medusa-admin --env staging

# URL 覆盖（不同环境使用不同地址）
scout run scenarios/ --web-base-url http://localhost:9000 --api-base-url http://localhost:9000
```

## 数据流

```
scout run
  ├── 启动 hudsucker 录制代理（独立进程）
  ├── Playwright 浏览器 → 代理 → 目标应用
  ├── 每个 scenario 前后通知代理 start/stop session
  ├── API 流量 → .scout/runs/<run_id>/record.db
  ├── 执行结果 → .scout/runs/<run_id>/<scenario>/result.json
  ├── 报告 → .scout/runs/<run_id>/report.html + junit.xml
  └── 索引 → .scout/index.db

scout diff <baseline> <target>
  ├── 读取两个 run 的 record.db
  ├── 按 scenario 配对 → LCS 对齐 API 记录
  ├── 比对 status code + JSON 结构 + 值
  ├── 结果 → .scout/diffs/<baseline>_vs_<target>/diff.db
  └── 报告 → .scout/diffs/<baseline>_vs_<target>/report.html
```

## 场景文件格式（app.json + test.py）

```json
// app.json — 交付 repo 根目录
{
  "name": "medusa-admin",
  "web_base_url": "http://medusa-admin.boxprobe.com",
  "api_base_url": "http://medusa-admin.boxprobe.com",
  "app_version": "2.14.0",
  "viewport_width": 1280,
  "viewport_height": 900
}
```

```python
# scenarios/auth/login-success/test.py
from scout.runner.scenario import Scenario
from scout.runner.page import Page

scenario = Scenario(name="login-success", base_url="http://localhost:9000")

@scenario.setup
async def setup(page: Page):
    await page.goto("/app/login")

@scenario.test
async def test(page: Page):
    await page.fill("[name=email]", "admin@medusa-test.com")
    await page.fill("[name=password]", "supersecret")
    await page.click("button[type=submit]")
    await page.wait_for_url("**/orders")
```

## 发版流程

```bash
# 1. 修改 pyproject.toml 版本号
# 2. 提交推送
git add -A && git commit -m "feat: ..." && git push

# 3. 构建 + 发布到 Forgejo Package Registry
uv build
uv publish --publish-url http://forge.boxprobe.com/api/packages/core/pypi \
    --username __token__ --password <FORGEJO_TOKEN> dist/scout-<version>*

# Argus 重新部署时会自动拉取最新版本（pyproject.toml: scout>=0.1）
```

## 技术栈

| 层 | 选型 |
|----|------|
| CLI | Python + Click |
| 浏览器自动化 | Playwright (Python) |
| HTTP 客户端 | httpx |
| 录制代理 | hudsucker (Rust) — 独立二进制 |
| 数据存储 | SQLite（录制数据、diff 结果、运行索引） |
| 报告 | HTML + JUnit XML |
| Lint + 格式化 | ruff |
| 类型检查 | pyright |
| 测试 | pytest + pytest-asyncio + pytest-playwright |

## Python 环境管理

- Python >= 3.14
- 使用 uv，`pyproject.toml` + `.venv/`
- **所有 Python 命令必须用 `uv run`**，禁止裸 `python` / `pip`

## 语言与文档

- 文档使用中文
- 代码注释和 commit message 使用英文
