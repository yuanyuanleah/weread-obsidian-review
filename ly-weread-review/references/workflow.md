# 数据与执行

## 官方连接

微信读书官方入口为 [WeRead Agent API Gateway](https://github.com/Tencent/WeChatReading/blob/main/skills/SKILL.md)。由用户在本机或调度环境安全配置 `WEREAD_API_KEY`。脚本从环境读取凭据，统计接口为 [`/readdata/detail`](https://github.com/Tencent/WeChatReading/blob/main/skills/readdata.md)，核实书目使用 [`/store/search`](https://github.com/Tencent/WeChatReading/blob/main/skills/search.md)。官方版本更新时核对文档与版本后，可由 `WEREAD_SKILL_VERSION` 覆盖请求版本。只在真实回顾已获授权时运行 `fetch` 或 `search`，凭据不得进入命令行参数、提示词、报告和自动化正文。

官方返回的总时长为秒，含阅读与收听。有效天数按单日满 60 秒计。日均时长取官方自然日口径。排行最多十项且有展示门槛，偏好分类也非完整明细。只在接口实际返回时展示各项数字。空值和缺少的分桶分别显示为未返回，零保留为零。当前周期注明抓取日，未来天数或月份留白。按明确请求核对上期时，另查同口径周期。当前未完成周期与完整周期的比较需写明可比范围。

推荐书目用核心主题或书名检索。按官方要求，`context` 带相关用户原始问题和最少必要背景。移除凭据和无关隐私。涉及私人叙述时，优先抽出获得授权的相关搜索请求，避免往书城发送私人笔记。返给用户的标题、作者和链接来自结果，不编目录。结果无条目/检索失败时如实说明，统计及可做的计划仍可完成。

## 渲染命令与输入

在本 Skill 目录执行。真实中间文件放在仅本用户可访问的临时目录，运行结束后按当前环境的保留规则处理。书目需要多次搜索时，按 `book_id` 合并已核实候选的 JSON 数组，再传入渲染。两个参数都可省略，适合只做统计或连接失败后保留已抓取部分。

```bash
python3 scripts/review.py fetch 2025-11 --out "$REVIEW_TMP/month.json"
python3 scripts/review.py search "观察与访谈" --context "用户相关原问题与本次检索的必要背景" --out "$REVIEW_TMP/books.json"
python3 scripts/review.py render --vault "<库路径>" --report "$REVIEW_TMP/month.json" --insights "$REVIEW_TMP/insights.json" --catalog "$REVIEW_TMP/books.json"
```

`insights.json` 的可选字段：

- `goal` 字符串，保留用户的实际阅读目标。未明确给目标时省略。
- `patterns` 数组，每项有 `label`、`evidence`。写明匹配的统计、与目标的关系及局限。
- `books` 数组，每项有 `book_id`、`why`、`start`。从 `--catalog` 核验标题、作者和链接。
- `plan_actions` 数组，恰好四个非空字符串，依次覆盖第 1–7、8–14、15–21、22–30 天。先试读，再提取观点，再做一次小实验，最后复盘。写明具体书、每周可用时间和验收产出。字段缺省时脚本使用通用计划。

用 `--plan` 强制附计划，用 `--no-plan` 去掉计划，用 `--plan-start YYYY-MM-DD` 指定起始日。更新同一期时，沿用本次未另行指定的阅读目标、推荐书和计划日期等选择。统计变化后复核阅读观察，传入更新后的 `patterns`。只换色时用 `dashboard --theme`。输出目录由 `--vault` 和可选 `--folder` 决定，须在所选库内。

## 交付检查

核查输出报告周期、部分周期提示、关键数字和计划边界。把手写内容留在「我的复盘」或生成区之外。重生成只更新明确标记的生成区，保留日期和行动相同的计划勾选、手写复盘及前一版本。已存在的未管理同名文件停下来保留。入口保留普通 Markdown 链接，看板由随 Skill 附带的 Dataview 组件负责，第三方插件可能因设备而异。定时运行对同一期使用同一路径。阅读报告、入口和历史版本为私密，不同步到公开库或用于公开创作，另有明确授权时按授权范围处理。
