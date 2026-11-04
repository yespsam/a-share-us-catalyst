# 九点猫研 CatDesk 9

每天 9 点，猫一眼市场机会。

每天早上 9 点生成一份“昨夜美股 -> 今日 A 股候选”的早报。它把美股主题涨跌、A 股历史次日表现、个股动量、新闻催化和风险提示合成一个评分，输出每个板块 5 只候选股。

> 输出是研究候选和风险提示，不是无条件买入指令。真实交易还需要结合账户风险承受能力、仓位、止损、流动性和当天开盘价格。

## 数据源

默认优先使用轻量直连接口，并保留 AkShare 作为显式备用：

- 美股日线：新浪单 ticker 静态日线，Yahoo chart 备用
- A 股实时行情：东方财富轻量 JSON
- A 股历史日线：东方财富轻量 JSON
- 个股新闻：东方财富新闻搜索 JSONP
- 宏观/政策新闻：东方财富 7x24 快讯，不够时再用同一搜索接口补「央行 / 证监会 / 汇金 / 产业政策」
- 涨停、跌停家数：东方财富涨停池、跌停池
- 指数成交额：东方财富指数，失败时用新浪指数
- 板块涨跌：东方财富板块列表，失败时用腾讯行业/概念榜
- 盘中候选池行情：东方财富批量行情，失败时用腾讯，再失败用新浪
- AkShare：默认不启用慢回退；需要诊断时加 `--allow-akshare-fallback`

外部接口会随上游网站变化而波动，所以工具内置了缓存和失败降级。宏观快讯大约缓存 30 分钟，盘口和板块大约缓存 12 分钟；接口失败时会读过期缓存，再失败就在报告里标明缺失，不用空数据冒充行情。第一次跑真实数据前先安装依赖。

## 快速开始

```bash
git clone https://github.com/yespsam/a-share-us-catalyst.git
cd a-share-us-catalyst
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python -m ashare_us_catalyst.cli --top 5
```

报告会写入：

```text
reports/YYYY-MM-DD-morning.md
reports/YYYY-MM-DD-morning.json
```

如果只是想检查格式和算法，不联网也可以跑样例数据：

```bash
PYTHONPATH=src python -m ashare_us_catalyst.cli --sample-data --top 5
```

## 每天 9 点自动运行

macOS 本地定时任务：

```bash
./scripts/install_launchd.sh
```

它会安装一个 `launchd` job，每个交易日早上 9 点执行 `scripts/run_report.sh`，把报告写入本机 `reports/`。日志在：

```text
logs/launchd.out.log
logs/launchd.err.log
```

## 交易日盘中异动

早报仍然是每天开盘前那一份。盘中可以另跑观察报告，内容包括：行业板块涨幅前几名和跌幅一侧、涨停/跌停家数、上证+深证成交额、候选池里的大幅波动或放量，以及最近十几个小时的政策快讯。

```bash
PYTHONPATH=src python -m ashare_us_catalyst.cli intraday
PYTHONPATH=src python -m ashare_us_catalyst.cli intraday --sample-data
```

等价写法是 `python -m ashare_us_catalyst.cli --intraday`。输出：

```text
reports/YYYY-MM-DD-intraday-HHMM.md
reports/YYYY-MM-DD-intraday-HHMM.json
reports/intraday-latest.json
```

`intraday-latest.json` 给本机脚本或网页轮询用。这些文件都在 `reports/`，不会提交到仓库。

交易日调度可以用仓库里的脚本。它只在上海时间周一至周五 09:35-11:30 和 13:05-14:55 真正拉数据，其他时间直接退出，所以可以挂到比较密的定时器上：

```bash
chmod +x scripts/run_intraday.sh
./scripts/run_intraday.sh
CATDESK_INTRADAY_FORCE=1 ./scripts/run_intraday.sh   # 收盘后也想看最后一次快照时
./scripts/install_intraday_launchd.sh               # macOS：每 30 分钟唤起，脚本自己判断是否在盘中
```

cron 示例：

```cron
35,5 9-11 * * 1-5 /path/to/a-share-us-catalyst/scripts/run_intraday.sh
5,35 13-14 * * 1-5 /path/to/a-share-us-catalyst/scripts/run_intraday.sh
```

盘中脚本不会自动发 Telegram，避免每半小时刷屏。需要推送时手动加 `--send-telegram`。

## 公网 Netlify 每天 9 点更新

公网网页是静态部署，必须重新构建 `dist/data/*.json` 并发布到 Netlify 才会更新。安装公网更新任务：

```bash
./scripts/install_public_launchd.sh
```

它会在每周一至周五 09:00 执行 `scripts/run_public_site_update.sh`，重新生成网页数据并运行：

```bash
npx netlify deploy --prod --dir=dist --functions=netlify/functions
```

这个任务依赖本机保持开机、联网，并且 Netlify CLI 已登录和链接到站点。日志在：

```text
logs/public-launchd.out.log
logs/public-launchd.err.log
```

## 网页版

```bash
./scripts/run_web.sh
```

打开：

```text
http://127.0.0.1:8765
```

网页包含：

- A 股早报：美股前夜主题 -> A 股板块和个股候选，并带上宏观/政策快讯和中国本地催化
- 盘中异动：板块涨幅、涨停家数、成交额、候选池波动和放量、政策快讯
- 美股优选：按质量、成长、估值、护城河、趋势和风险筛选美股候选
- 日韩市场：覆盖日本、韩国核心资产，保留汇率、政策、财报和跨境交易风险提示
- 高倍潜力：挖掘早期高弹性候选，结合产业空间、市值甜点、趋势初段、资金确认、新闻催化和风险闸门
- 回测证据：展示过去半年候选算法的历史表现
- 每日日报：网页内阅读完整早报文字版
- 报告历史：读取本地 `reports-web/`

美股“买入候选”是研究分层，不是保证收益或无条件买入指令。

## 公开仓库说明

本仓库只包含系统源码、网页、配置、测试和可公开的视觉资产。运行缓存、每日报告、Netlify 本地状态、渲染视频、个人声音样本和音频混音文件不会提交到 GitHub。

本工具仅以娱乐和公开资料整理为主，不构成投资建议，不代表确定收益。

## Telegram 推送

复制环境变量模板：

```bash
cp .env.example .env
```

填入：

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

然后：

```bash
PYTHONPATH=src python -m ashare_us_catalyst.cli --send-telegram
```

## 调整股票池

编辑 `config/themes.json`：

- `us_tickers`：昨夜美股信号股票，支持 `weight` 权重
- `candidates`：A 股候选池，工具会从里面按历史有效性、实时行情和新闻筛选 Top 5
- `logic`：板块映射逻辑，会进入报告
- `policy_keywords`：可选。宏观/政策标题如何映射到这个主题；留空时使用代码里的默认词表

编辑 `config/multibagger.json`：

- `us_universe`：早期高弹性美股候选池，包含阶段、赛道、市值档、成长、估值、护城河、催化和风险标签
- A 股高倍潜力候选默认复用 `config/themes.json` 中的 A 股股票池
- 每次公网更新会生成 `dist/data/multibagger.json`

## 评分口径

默认口径是 `china_local_v1`。正向权重合计 96%，风险另外扣分，因此中性输入下的总分中枢和旧口径接近。中国本地催化占 22 个点，从原来的美股信号、历史次日和动量里让出来。

| 因子 | 旧口径 | 中国本地催化 |
| --- | ---: | ---: |
| 美股主题信号 | 34% | 24% |
| 历史次日有效性 | 32% | 22% |
| 中国本地催化 | 0 | 22% |
| 个股动量 | 12% | 10% |
| 个股新闻 | 10% | 10% |
| 流动性 | 8% | 8% |
| 风险 | 另扣 | 另扣 |

中国本地催化从 50 分中性起算，只在读到数据时加减：

- 政策/宏观：标题映射到 `config/themes.json` 的 `policy_keywords`。没写关键词时用内置词表。降准、回购增持再贷款、汇金这类全市场政策会对所有主题给较小权重，券商权重大一些。收紧、减持新规、从严监管会降分，严重时再加风险扣分。超过 72 小时或报告日期之后的标题不计入。
- 涨停情绪：涨停家数相对大约 40 家的常态偏移，跌停家数扣分。开盘前如果当天涨停池还是空的，会改看最近一个有数据的交易日，并在报告里写明日期。
- 板块：主题对应的行业或概念板块涨跌，单日大约按 ±5% 封顶后计入。
- 个股资金面代理：量比、换手率、成交额。这是快照里的公开字段，不是北向资金推算。

某一项没读到就保持中性，不把缺失当成利好或利空。宏观、涨停和板块全部失败时，本次排序回退到旧口径，并在报告里写明。历史日期也不会拿今天的盘口去改写那天的分数。

`--legacy-weights` 强制使用旧权重。`--skip-macro` 只跳过政策快讯，盘口和板块仍会尝试。回测继续用旧权重，因为历史政策和涨停情绪无法逐日复原。

默认按板块输出 Top 5。每只股票包含：代码、名称、产业、市值、评分、历史胜率、利好逻辑和近期重大新闻。Buy、Outperform 和盘中异动标记都只是研究优先级，不是无条件买入或卖出指令。

早期高倍潜力模块额外关注：

- 市值甜点：偏好仍有重估空间但流动性可接受的中小市值区间
- 产业期权：AI、半导体、机器人、商业航天、量子、创新药、储能等高空间赛道
- 趋势初段：避免已经极度透支的后期标的，优先看启动确认和主升初段
- 资金确认：20 日趋势、60/120 日收益、换手率、量比和回撤位置
- 风险闸门：过热、ST/退市风险、负面新闻、估值过高、融资和商业化不确定性

## 常用命令

```bash
# 真实数据
PYTHONPATH=src python -m ashare_us_catalyst.cli --top 5

# 样例数据
PYTHONPATH=src python -m ashare_us_catalyst.cli --sample-data --top 5

# 只看前 4 个信号最强板块
PYTHONPATH=src python -m ashare_us_catalyst.cli --max-themes 4

# 不抓个股新闻，加快速度；宏观快讯仍会抓
PYTHONPATH=src python -m ashare_us_catalyst.cli --skip-news

# 不抓宏观/政策快讯
PYTHONPATH=src python -m ashare_us_catalyst.cli --skip-macro

# 回到旧的美股信号 + 历史次日 + 动量权重
PYTHONPATH=src python -m ashare_us_catalyst.cli --legacy-weights

# 盘中异动
PYTHONPATH=src python -m ashare_us_catalyst.cli intraday --sample-data

# 允许 AkShare 作为慢回退源
PYTHONPATH=src python -m ashare_us_catalyst.cli --allow-akshare-fallback

# 回看 500 天
PYTHONPATH=src python -m ashare_us_catalyst.cli --lookback-days 500
```
