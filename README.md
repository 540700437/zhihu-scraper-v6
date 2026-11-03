# 知乎问答抓取器 v6

一个按工程化标准写的知乎问答抓取工具：**DOM 与 API 双通道抓取、按回答 ID 幂等入库、中断可续、六种格式流式导出**。

项目从"能跑通"迭代到"能维护"，目标不是抓一次数据，而是把一次性的爬虫脚本写成一个可以长期运行、页面改版后能低成本修复的小系统。

---

## 核心特性

| 特性 | 说明 |
| --- | --- |
| **双通道抓取** | 先用 DOM 滚动获取首屏与渲染后内容，再走官方 API 分页拉取全量；两个通道互相兜底 |
| **API 优先** | 结构化数据永远比解析 HTML 可靠，DOM 只作为 API 不可用时的回退路径 |
| **幂等写入** | `answer_id` 为主键，配合 `content_hash` 判重，反复抓取不会产生重复数据 |
| **断点续爬** | `scrape_progress` 表记录已抓取 offset，中断后从断点继续，不必重头再来 |
| **选择器热修** | 所有 DOM 定位集中在 `selectors.py`，并为每个字段维护候选选择器，页面改版只需改一处 |
| **流式导出** | Markdown / HTML / JSON / CSV / Excel / Parquet 六种格式，全部基于生成器，数据量大也不会撑爆内存 |
| **风控可控** | 随机延时、并发上限、指数退避重试、封禁策略（wait / notify / abort）均可配置 |

## 目录结构

```
zhihu_scraper_v6/
├── main.py             # 入口：命令行参数、抓取主流程、导出调度
├── config.py           # 全局配置（pydantic-settings，支持 .env 覆盖）
├── browser.py          # Playwright 浏览器与登录态管理
├── scroll_manager.py   # 无限滚动：到底判定、无变化阈值、超时保护
├── dom_parser.py       # DOM 解析：回答、作者、图片、代码块
├── api_client.py       # 官方 API 客户端：分页、并发、退避重试
├── selectors.py        # 候选选择器注册表 + 自动择优
├── models.py           # Question / Answer / Image 数据模型
├── database.py         # SQLite 持久层（WAL、外键、UPSERT、索引）
├── logger.py           # 日志
├── utils.py            # 工具函数（question_id 提取等）
└── exporters/          # 六种导出器，共享 BaseExporter
    ├── markdown.py  ├── html.py   ├── json_exporter.py
    ├── csv_exporter.py  ├── excel.py  └── parquet.py
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 2. 运行（首次会打开浏览器，需要手动登录知乎）
python -m zhihu_scraper_v6.main "https://www.zhihu.com/question/28966967"

# 3. 指定导出格式
python -m zhihu_scraper_v6.main <URL> --export md html json

# 4. 批量抓取（URL 一行一个，# 开头为注释）
python -m zhihu_scraper_v6.main --url-file urls.txt

# 5. 只用 API（不启动 DOM 抓取，速度更快）
python -m zhihu_scraper_v6.main <URL> --no-dom

# 6. 无头模式
python -m zhihu_scraper_v6.main <URL> --headless
```

> 登录态保存在 `~/zhihu_chrome_profile_v6`（Playwright 持久化用户目录），不需要在代码里写死任何 Cookie。

## 配置项（config.py）

| 分组 | 关键项 | 说明 |
| --- | --- | --- |
| 路径 | `db_path` / `export_dir` / `log_dir` | 一律以项目根目录为基准，不随启动目录变化 |
| API | `api_limit` / `api_concurrency` / `api_max_retry` | 每页条数、并发数、重试次数 |
| 滚动 | `scroll_max_rounds` / `scroll_no_change_threshold` | 最大滚动轮数、连续无新增即停止的阈值 |
| 风控 | `block_policy` | `wait` 等待 / `notify` 提醒 / `abort` 中止 |
| 存储 | `store_content_html` / `content_html_max_chars` | 是否保留原始 HTML、单条上限 |

所有配置都可以用 `.env` 覆盖，例如 `API_CONCURRENCY=3`。

## 导出产物

按 `exports/<question_id>/` 组织，每种格式独立目录：

```
exports/28966967/
├── markdown/   # 分页 Markdown，适合阅读与二次编辑
├── html/       # 分页静态 HTML，带目录，可直接浏览
├── json/       # 完整结构化数据，含图片与代码块
├── csv/        # 表格化字段
├── excel/      # 需 openpyxl
└── parquet/    # 需 pyarrow + pandas，适合数据分析
```

Excel 与 Parquet 为**可选依赖**：未安装时不会报错退出，只在日志中提示安装方式。

## 几个设计取舍

- **为什么 API 优先？** DOM 解析依赖页面结构，知乎改版频繁；API 返回的是结构化 JSON，字段稳定、可分页、可并发。
- **为什么用 SQLite + WAL？** 单机抓取场景不需要服务端数据库，WAL 模式让读写并发不互相阻塞，同时保持零部署。
- **为什么导出用生成器？** 一次性把十万条回答读进内存会直接 OOM，改成流式后导出内存占用与数据量解耦。
- **为什么保留原始 HTML？** 文本清洗规则会变，原文一旦丢了就再也补不回来。

## 免责声明

本项目仅用于**个人学习与爬虫技术研究**，请遵守知乎用户协议与 `robots.txt`，控制请求频率，不要用于商业用途、大规模采集或数据转售。仓库不包含任何抓取到的内容数据（数据库与导出目录已在 `.gitignore` 中排除）。

## License

MIT
