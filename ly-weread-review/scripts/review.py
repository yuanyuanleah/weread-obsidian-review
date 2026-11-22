#!/usr/bin/env python3
"""Fetch WeRead reading summaries and write a private Obsidian dashboard."""
import argparse
import base64
import calendar
import hashlib
import json
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SHANGHAI = ZoneInfo("Asia/Shanghai")
GATEWAY = "https://i.weread.qq.com/api/agent/gateway"
THEMES = ("米棕暖调", "黛蓝雾灰", "抹茶奶油", "香芋紫", "砖红拿铁", "珊瑚奶油", "雾蓝银灰")
HEX = re.compile(r"#[0-9a-fA-F]{6}\Z")
OPEN = "<!-- weread-review:begin -->"
CLOSE = "<!-- weread-review:end -->"
REPORT_NAME = re.compile(r"(\d{4}(?:-\d{2})?) 微信读书(月度|年度)回顾\.md\Z")
INDEX_NAME = "00-阅读回顾.md"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 不让私人 API Key 随 HTTP 重定向发送。
        return None


def call_weread(api_name, **params):
    api_key = os.environ.get("WEREAD_API_KEY", "").strip()
    if not api_key:
        raise ValueError("当前运行环境未设置 WEREAD_API_KEY")
    version = os.environ.get("WEREAD_SKILL_VERSION", "1.0.6")
    body = {"api_name": api_name, "skill_version": version, **params}
    request = Request(GATEWAY, json.dumps(body, ensure_ascii=False).encode(), method="POST",
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=25) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise ValueError(f"微信读书 {api_name} 返回 HTTP {exc.code}") from None
    except (URLError, TimeoutError):
        raise ValueError(f"微信读书 {api_name} 连接失败或超时") from None
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError(f"微信读书 {api_name} 未返回可解析的数据") from None
    if not isinstance(result, dict):
        raise ValueError(f"微信读书 {api_name} 回包格式异常")
    code = result.get("errcode", 0)
    if code not in (0, "0", None):
        safe_code = code if re.fullmatch(r"-?\d{1,12}", str(code)) else "未知"
        raise ValueError(f"微信读书 {api_name} 返回错误码 {safe_code}")
    return result.get("data", result)


def period_bounds(period):
    if not isinstance(period, str) or not re.fullmatch(r"\d{4}(?:-\d{2})?", period):
        raise ValueError("周期使用 YYYY 或 YYYY-MM")
    year = int(period[:4])
    month = int(period[-2:]) if len(period) == 7 else 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1]) if len(period) == 7 else date(year, 12, 31)
    return start, end


def seconds(value):
    if type(value) is int and value >= 0:
        return value
    return None


def list_entries(value):
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def normalize(period, reply, as_of):
    first, last = period_bounds(period)
    if first > as_of:
        raise ValueError(f"{period} 尚未开始")
    if not isinstance(reply, dict) or not set(reply).intersection(
        ("totalReadTime", "readDays", "readTimes", "readStat", "readLongest", "preferCategory")
    ):
        raise ValueError(f"{period} 的微信读书回包没有可用统计字段")
    base_time = reply.get("baseTime")
    if base_time is not None and datetime.fromtimestamp(int(base_time), SHANGHAI).date() != first:
        raise ValueError(f"微信读书返回的周期与 {period} 不一致")
    monthly = len(period) == 7
    through = min(as_of, last)
    buckets = {}
    for stamp, value in (reply.get("readTimes") or {}).items():
        day = datetime.fromtimestamp(int(stamp), SHANGHAI).date()
        if first <= day <= through and seconds(value) is not None:
            buckets[day.isoformat() if monthly else day.strftime("%Y-%m")] = value
    summary = {entry.get("stat"): entry.get("counts") for entry in list_entries(reply.get("readStat"))}
    compare = reply.get("compare")
    totals = {
        "seconds": seconds(reply.get("totalReadTime")),
        "days": seconds(reply.get("readDays")),
        "daily_seconds": seconds(reply.get("dayAverageReadTime")),
        "read": summary.get("读过"),
        "finished": summary.get("读完"),
        "notes": summary.get("笔记"),
        "compare": round(compare * 100) if isinstance(compare, (int, float)) and not isinstance(compare, bool) else None,
    }
    ranking = []
    for entry in list_entries(reply.get("readLongest")):
        book = entry.get("book") or entry.get("albumInfo") or {}
        if isinstance(book, dict) and book.get("title"):
            ranking.append({"title": book["title"], "author": book.get("author", ""),
                            "seconds": seconds(entry.get("readTime"))})
    categories = [
        {"title": entry["categoryTitle"], "seconds": seconds(entry["readingTime"])}
        for entry in list_entries(reply.get("preferCategory"))
        if entry.get("categoryTitle") and (seconds(entry.get("readingTime")) or 0) > 0
    ]
    return {"period": period, "as_of": as_of.isoformat(), "through": through.isoformat(),
            "partial": as_of <= last, "totals": totals, "buckets": buckets,
            "ranking": ranking, "categories": categories}


def plain(value):
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def link_url(value):
    url = plain(value)
    if not url or any(char.isspace() or char in "<>" for char in url):
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme in ("https", "http") and parts.netloc and not parts.username:
        return url
    if parts.scheme == "weread" and parts.netloc:
        return url
    return ""


def confirmed_books(reply):
    books = {}
    for group in list_entries(reply.get("results")) if isinstance(reply, dict) else []:
        for entry in list_entries(group.get("books")):
            book = entry.get("bookInfo") or {}
            if not isinstance(book, dict) or not book.get("bookId") or not book.get("title") or book.get("soldout"):
                continue
            book_id = str(book["bookId"])
            books[book_id] = {
                "book_id": book_id, "title": book["title"], "author": book.get("author", ""),
                "description": book.get("intro", ""), "category": book.get("category", ""),
                "url": link_url(book.get("readerLink")) or link_url(book.get("deepLink")),
            }
    return list(books.values())


def plan_blocks(start, actions, has_books):
    if actions and (len(actions) != 4 or any(not plain(action) for action in actions)):
        raise ValueError("30 天计划需要四段非空的行动安排")
    if not actions:
        actions = [
            "选定一个阅读问题，先试读一本推荐书。写下两个想弄明白的小问题。" if has_books else "选定一个阅读问题，试读两本候选书，留下一本。写下两个想弄明白的小问题。",
            "安排三次各 20 分钟的阅读。记下两条能回答问题的观点和各自的例子。",
            "用书里的一条方法做一次小实验。记录做法、结果和意外之处。",
            "用 200 字复盘。记录一个还没解决的问题，决定继续读、换书或调整读法。",
        ]
    offsets = (0, 7, 14, 21, 30)
    return [{"start": (start + timedelta(days=offsets[index])).isoformat(),
             "end": (start + timedelta(days=offsets[index + 1] - 1)).isoformat(),
             "action": plain(action)} for index, action in enumerate(actions)]


def add_insights(review, insights, candidates, plan, plan_start):
    catalog = {entry["book_id"]: entry for entry in list_entries(candidates)}
    books = []
    for entry in list_entries(insights.get("books")):
        verified = catalog.get(str(entry.get("book_id")))
        if verified is None or not plain(entry.get("why")) or not plain(entry.get("start")):
            raise ValueError("每本推荐书都需要微信读书核实的 book_id、推荐理由和起读动作")
        if any(book["book_id"] == verified["book_id"] for book in books):
            raise ValueError(f"重复推荐了 {verified['title']}")
        books.append({key: verified.get(key, "") for key in ("book_id", "title", "author", "url")}
                     | {"why": plain(entry["why"]), "start": plain(entry["start"])})
    goal = plain(insights.get("goal"))
    patterns = [
        {"label": plain(entry["label"]), "evidence": plain(entry["evidence"])}
        for entry in list_entries(insights.get("patterns")) if plain(entry.get("label")) and plain(entry.get("evidence"))
    ]
    review.update({"goal": goal, "patterns": patterns, "books": books,
                   "plan": plan_blocks(plan_start, insights.get("plan_actions"), bool(books)) if plan else []})
    return review


def duration(value):
    if value is None:
        return "未返回"
    if 0 < value < 60:
        return f"{value} 秒"
    hours, minutes = divmod(value // 60, 60)
    return f"{hours} 小时 {minutes} 分" if hours else f"{minutes} 分钟"


def markdown(value):
    # 防止标题、书名和分析文本注入链接、HTML、属性或生成区边界。
    return re.sub(r"([\\`*_{}\[\]<>#|~!])", r"\\\1", plain(value))


def metrics(review):
    totals = review["totals"]
    result = [("阅读／收听总时长", duration(totals["seconds"])),
              ("有效阅读天数", f"{totals['days']} 天" if totals["days"] is not None else "未返回"),
              ("自然日均时长", duration(totals["daily_seconds"]))]
    result.extend((label, totals[key]) for label, key in (("读过", "read"), ("读完", "finished"), ("笔记", "notes"))
                  if totals[key] is not None)
    if totals["compare"] is not None:
        result.append(("日均时长较上期", f"{totals['compare']:+d}%"))
    return result


def report_text(review):
    period = review["period"]
    first, _ = period_bounds(period)
    scope = "本期进行中，" if review["partial"] else ""
    review["metrics"] = metrics(review)
    encoded = base64.b64encode(json.dumps(review, ensure_ascii=False).encode()).decode()
    lines = [OPEN, f"<!-- weread-review-payload:{encoded} -->", "## 阅读统计", "",
             f"{scope}覆盖 {first} 至 {review['through']}。来源为微信读书，按北京时间统计。", "",
             *[f"- {label}　{markdown(value)}" for label, value in review["metrics"]],
             "", "有效阅读天数按单日满 1 分钟计。", "",
             "## 阅读偏好", ""]
    categories = review["categories"]
    lines += [f"- {markdown(entry['title'])}　{duration(entry['seconds'])}" for entry in categories] or ["本期未返回可展示的偏好分类。"]
    lines += ["", "## 阅读与收听排行", ""]
    lines += [f"- {markdown(entry['title'])}{(' · ' + markdown(entry['author'])) if entry['author'] else ''}　{duration(entry['seconds'])}"
              for entry in review["ranking"]] or ["本期未返回排行条目。"]
    lines += ["", "## " + ("目标与待补主题" if review["goal"] else "阅读观察与探索方向"), ""]
    if review["goal"]:
        lines += [f"这次的阅读目标：{markdown(review['goal'])}", ""]
    lines += [f"- **{markdown(entry['label'])}**　{markdown(entry['evidence'])}" for entry in review["patterns"]] or ["目前没有足够依据给出进一步判断。"]
    lines += ["", "## 推荐阅读", ""]
    for entry in review["books"]:
        url = link_url(entry["url"])
        title = f"《{markdown(entry['title'])}》"
        if url:
            title = f"[{title}](<{url}>)"
        lines += [f"- {title} · {markdown(entry['author'])}", f"  - 为什么读：{markdown(entry['why'])}",
                  f"  - 从这里开始：{markdown(entry['start'])}"]
    if not review["books"]:
        lines.append("本期暂无核实后的推荐书目。")
    if review["plan"]:
        lines += ["", "## 未来 30 天计划", ""]
        lines += [f"- [ ] **{entry['start']} 至 {entry['end']}**　{markdown(entry['action'])}" for entry in review["plan"]]
    lines += ["", CLOSE]
    return "\n".join(lines)


def write_generated(path, header, block, tail=""):
    content = f"{header}\n\n{block}{tail}\n"
    if path.exists():
        old = path.read_text()
        if old.count(OPEN) != 1 or old.count(CLOSE) != 1 or old.index(CLOSE) < old.index(OPEN):
            raise ValueError(f"文件不属于本 Skill 的生成区，已保留：{path}")
        left, body = old.split(OPEN, 1)
        original, right = body.split(CLOSE, 1)
        checked = {line[6:] for line in original.splitlines() if line.startswith(("- [x] ", "- [X] "))}
        block = "\n".join(
            "- [x] " + line[6:] if line.startswith("- [ ] ") and line[6:] in checked else line
            for line in block.splitlines()
        )
        content = left + block + right
        if content == old:
            return
        if path.name != INDEX_NAME:
            archive = path.parent / "_历史版本"
            archive.mkdir(exist_ok=True)
            digest = hashlib.sha256(old.encode()).hexdigest()[:12]
            backup = archive / f"{path.stem} {digest}.md"
            if not backup.exists():
                write_note(backup, old)
    write_note(path, content)


def write_note(path, content):
    if path.is_symlink():
        raise ValueError(f"生成文件不能是符号链接：{path}")
    with NamedTemporaryFile(dir=path.parent, prefix=".weread-", encoding="utf-8", mode="w", delete=False) as file:
        try:
            file.write(content)
            file.close()
            Path(file.name).replace(path)
        finally:
            Path(file.name).unlink(missing_ok=True)


def destination(vault, folder):
    vault = vault.expanduser().resolve(strict=True)
    if not vault.is_dir() or not (vault / ".obsidian").is_dir():
        raise ValueError(f"请选择包含 .obsidian 的库目录：{vault}")
    relative = Path(folder)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("展示文件夹须为库内相对路径")
    target = vault / relative
    if not target.resolve().is_relative_to(vault):
        raise ValueError(f"展示文件夹指向 Obsidian 库外：{target}")
    for path in (target / INDEX_NAME, target / "_看板", target / "_看板" / "view.js", target / "_历史版本"):
        if path.is_symlink():
            raise ValueError(f"生成路径不能是符号链接：{path}")
    return target


def ensure_dashboard(target, theme=None):
    default = "米棕暖调"
    index_path = target / INDEX_NAME
    if theme is None and index_path.exists():
        prior = re.search(r"<!-- weread-theme:([^<>]+) -->", index_path.read_text())
        if prior:
            default = prior[1]
    theme = theme or default
    if theme not in THEMES and not HEX.fullmatch(theme):
        raise ValueError(f"未知配色：{theme}")
    target.mkdir(parents=True, exist_ok=True)
    view = target / "_看板" / "view.js"
    source = (ASSETS / "dashboard.js").read_text()
    if view.exists() and view.read_text() != source and not view.read_text().startswith("// weread-reading-review\n"):
        raise ValueError(f"展示组件已存在，已保留：{view}")
    files = sorted(
        (path for path in target.glob("*.md") if REPORT_NAME.fullmatch(path.name) and
         "<!-- weread-review-payload:" in path.read_text()),
        key=lambda path: REPORT_NAME.fullmatch(path.name)[1].ljust(7, "Z"), reverse=True,
    )
    links = "\n".join(f"- [[{path.stem}]]" for path in files) or "生成第一份月报或年报后，这里会出现报告。"
    block = "\n".join([OPEN, f"<!-- weread-theme:{theme} -->", "```dataviewjs",
                       'const folder = dv.current().file.folder;',
                       f'await dv.view([folder, "_看板"].filter(Boolean).join("/"), {{theme: {json.dumps(theme, ensure_ascii=False)}}});',
                       "```", "", "## 报告目录", "", links, "", CLOSE])
    write_generated(index_path, PRIVATE_HEADER + "\n\n# 微信读书回顾", block)
    view.parent.mkdir(exist_ok=True)
    if not view.exists() or view.read_text() != source:
        write_note(view, source)
    return index_path


PRIVATE_HEADER = "---\nprivacy: private\nallow_for_content: false\n---"


def load_json(path, default):
    return json.loads(path.read_text()) if path else default


def previous_review(path, period):
    if path.is_symlink():
        raise ValueError(f"生成文件不能是符号链接：{path}")
    if not path.exists():
        return {}
    match = re.search(r"<!-- weread-review-payload:([A-Za-z0-9+/=]+) -->", path.read_text())
    if match:
        report = json.loads(base64.b64decode(match[1]))
        if report["period"] == period:
            return report
    raise ValueError(f"报告同名但缺少匹配的生成数据，已保留：{path}")


def write_json(path, value):
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path:
        # 新建中间文件时仅当前用户可读写。
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(payload)
    else:
        print(payload, end="")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="读取某自然月或自然年的微信读书统计")
    fetch.add_argument("period")
    fetch.add_argument("--out", type=Path)
    search = sub.add_parser("search", help="核实微信读书书城的推荐候选")
    search.add_argument("keyword")
    search.add_argument("--context", required=True)
    search.add_argument("--out", type=Path)
    for name, description in (("render", "生成一期回顾并更新展示页"), ("dashboard", "搭建展示页或更改默认配色")):
        command = sub.add_parser(name, help=description)
        command.add_argument("--vault", type=Path, required=True)
        command.add_argument("--folder", default="微信读书回顾")
        command.add_argument("--theme")
        if name == "render":
            command.add_argument("--report", type=Path, required=True)
            command.add_argument("--insights", type=Path)
            command.add_argument("--catalog", type=Path)
            command.add_argument("--plan", action=argparse.BooleanOptionalAction, default=None)
            command.add_argument("--plan-start", type=date.fromisoformat)
    args = parser.parse_args()
    try:
        today = datetime.now(SHANGHAI).date()
        if args.command == "fetch":
            first, _ = period_bounds(args.period)
            if first > today:
                raise ValueError(f"{args.period} 尚未开始")
            mode = "monthly" if len(args.period) == 7 else "annually"
            base_time = int(datetime.combine(first, time(12), SHANGHAI).timestamp())
            write_json(args.out, normalize(args.period, call_weread("/readdata/detail", mode=mode, baseTime=base_time), today))
        elif args.command == "search":
            write_json(args.out, confirmed_books(call_weread("/store/search", keyword=args.keyword, scope=10, context=args.context)))
        else:
            target = destination(args.vault, args.folder)
            if args.theme is not None and args.theme not in THEMES and not HEX.fullmatch(args.theme):
                raise ValueError(f"未知配色：{args.theme}")
            if args.command == "render":
                review = load_json(args.report, None)
                period = review["period"]
                period_bounds(period)
                monthly = len(period) == 7
                title = period + (" 微信读书月度回顾" if monthly else " 微信读书年度回顾")
                path = target / f"{title}.md"
                prior = previous_review(path, period)
                prior_plan = prior.get("plan", [])
                prior_books = prior.get("books", [])
                insights = {key: prior[key] for key in ("goal", "patterns", "books") if key in prior}
                insights["plan_actions"] = [step["action"] for step in prior_plan]
                insights.update(load_json(args.insights, {}))
                catalog = prior_books + load_json(args.catalog, [])
                plan = args.plan if args.plan is not None else bool(prior_plan) if prior else monthly
                start = args.plan_start or (date.fromisoformat(prior_plan[0]["start"]) if prior_plan else today)
                add_insights(review, insights, catalog, plan, start)
                target.mkdir(parents=True, exist_ok=True)
                write_generated(path, f"{PRIVATE_HEADER}\n\n# {title}", report_text(review), "\n\n## 我的复盘\n")
                print(path)
            print(ensure_dashboard(target, args.theme))
    except (ValueError, OSError, KeyError, AttributeError, TypeError, OverflowError) as exc:
        parser.exit(1, f"微信读书回顾：{exc}\n")


if __name__ == "__main__":
    main()
