import math
import os
import re
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from difflib import SequenceMatcher

import httpx
import yfinance as yf
from google import genai

print(">>> [DEBUG] 脚本启动 - 目标模型: Gemini 3.1 Flash-Lite Preview")

RECENT_TITLES_LIMIT = 15
TITLE_SIMILARITY_ABORT = 0.88
TITLE_SIMILARITY_RETRY = 0.82

# (匹配词列表, slug 标签, 中文主题名用于 keywords / topics)
TOPIC_RULES: list[tuple[list[str], str, str]] = [
    (["非农", "NFP", "美国就业", "就业数据"], "topic-nfp", "非农数据"),
    (["美联储", "Fed", "加息", "降息", "鲍威尔", "FOMC"], "topic-fed", "美联储"),
    (["地缘", "中东", "战争", "冲突", "制裁"], "topic-geo", "地缘政治"),
    (["央行", "购金", "储备"], "topic-cbank", "央行购金"),
    (["通胀", "CPI", "PCE"], "topic-inflation", "通胀"),
    (["美元", "DXY", "美指"], "topic-dxy", "美元"),
    (["衰退", "违约", "债务危机", "风险资产"], "topic-risk", "风险偏好"),
    (["加息预期", "降息预期", "利率路径"], "topic-rates", "利率预期"),
]

def slugify(value: str, max_len: int = 80) -> str:
    value = (value or "").strip()
    value = value.replace("_", "-")
    value = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"\s+", "-", value).strip("-").lower()
    if not value:
        value = "gold-analysis"
    return value[:max_len].rstrip("-")

def extract_title_and_body(ai_text: str) -> tuple[str, str]:
    text = (ai_text or "").strip()
    if not text:
        return ("黄金形态通APP-实时行情研判", "")

    lines = text.splitlines()
    first = (lines[0] if lines else "").strip()
    if first.startswith("#"):
        title = first.lstrip("#").strip()
        body = "\n".join(lines[1:]).lstrip()
        return (title or "黄金形态通APP-实时行情研判", body)

    return ("黄金形态通APP-实时行情研判", text)

def first_paragraph(text: str, max_len: int = 160) -> str:
    t = (text or "").strip()
    if not t:
        return "黄金形态通APP 黄金（XAU/USD）行情分析文章摘要。"
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^>\s*", "", t, flags=re.MULTILINE)
    parts = re.split(r"\n\s*\n", t, maxsplit=1)
    p = parts[0].strip().replace("\n", " ")
    if len(p) > max_len:
        p = p[: max_len - 1].rstrip() + "…"
    return p

def social_blurb(description: str, max_len: int = 120) -> str:
    s = re.sub(r"\s+", " ", (description or "").strip())
    if len(s) > max_len:
        return s[: max_len - 1].rstrip() + "…"
    return s

def load_recent_titles(limit: int = RECENT_TITLES_LIMIT) -> list[str]:
    posts_dir = Path("_posts")
    if not posts_dir.is_dir():
        return []
    files = sorted(posts_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    titles: list[str] = []
    for p in files[:limit]:
        try:
            raw = p.read_text(encoding="utf-8")
            m = re.search(r'^title:\s*"(.*)"\s*$', raw, re.MULTILINE)
            if m:
                titles.append(m.group(1).strip())
                continue
            for line in raw.splitlines():
                if line.startswith("# "):
                    titles.append(line[2:].strip())
                    break
        except OSError:
            continue
    return titles

def max_title_similarity(new_title: str, past: list[str]) -> float:
    if not past or not new_title:
        return 0.0
    new_n = re.sub(r"\s+", "", new_title)
    best = 0.0
    for old in past:
        old_n = re.sub(r"\s+", "", old)
        if not old_n:
            continue
        best = max(best, SequenceMatcher(None, new_n, old_n).ratio())
    return best

def compute_volatility(gold: yf.Ticker) -> tuple[str, float, str]:
    try:
        hist = gold.history(period="5d")
        if hist is None or hist.empty or len(hist) < 2:
            return ("low", 0.0, "历史数据不足，按常态波动撰写即可。")
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        pct = (last - prev) / prev * 100.0 if prev else 0.0
        prev_for_range = prev if prev else last
        day_hi = float(hist["High"].iloc[-1])
        day_lo = float(hist["Low"].iloc[-1])
        intraday = (day_hi - day_lo) / prev_for_range * 100.0 if prev_for_range else 0.0
        mag = max(abs(pct), intraday * 0.45)
        if mag >= 1.2 or abs(pct) >= 0.9:
            return (
                "high",
                pct,
                f"波动偏高（较前收约 {pct:+.2f}%，日内振幅参考约 {intraday:.2f}%）。必须额外增加一个小节（自拟 H2 标题），聚焦「波动加剧时的观察要点与风险」，语气克制、不写收益承诺。",
            )
        if mag >= 0.45 or abs(pct) >= 0.35:
            return (
                "medium",
                pct,
                f"波动中等（较前收约 {pct:+.2f}%）。正文中需点明这一变化如何影响当前形态的判定，并列出 1～2 条具体观察要点。",
            )
        return (
            "low",
            pct,
            f"波动相对温和（较前收约 {pct:+.2f}%）。以结构与趋势为主，不渲染恐慌情绪。",
        )
    except Exception:
        return ("low", 0.0, "无法可靠计算波动，请按常规技术面展开。")

def detect_topics(full_text: str) -> tuple[list[str], list[str]]:
    """返回 (extra_tags slug, 中文主题列表)"""
    extra_tags: list[str] = []
    topics_zh: list[str] = []
    lower_blob = full_text.lower()
    for keys, slug, zh in TOPIC_RULES:
        hit = False
        for k in keys:
            if k.isascii():
                if k.lower() in lower_blob:
                    hit = True
                    break
            elif k in full_text:
                hit = True
                break
        if hit:
            if slug not in extra_tags:
                extra_tags.append(slug)
            if zh not in topics_zh:
                topics_zh.append(zh)
    return extra_tags, topics_zh

def build_prompt(price, vol_line: str, recent_titles: list[str]) -> str:
    block = ""
    if recent_titles:
        preview = "\n".join(f"- {t}" for t in recent_titles[:10])
        block = f"""
        近期已发布的标题（请勿只做少量词语替换；不要沿用相同立意与句式）：
{preview}
        """
    return f"""
        今日黄金价格：{price} 美元。
        {vol_line}
        {block}
        请撰写一篇专业行情分析。
        要求：
        1. 第一行必须是 Markdown H1 标题，格式为：# <文章标题>；标题长度约 20～40 个汉字，需含「黄金」「行情」及「形态」或「趋势」等词，风格类似专业财经媒体，避免空洞口号。
        2. 正文用 3～4 个小节展开，使用 H2/H3；建议分别从盘面形态、技术指标、风险提示、交易/观察思路等角度展开，避免只复读价格数字。
        3. 文末用一段话自然引导读者在 App Store 搜索并下载「黄金形态通APP」辅助识别形态；不得承诺收益、不得使用夸大或违规表述。
        4. 语气像写给实盘交易者的点评：有技术细节、有风险提示，条理清晰。
        """

def generate_ai_text(client: genai.Client, system_instruction: str, prompt: str) -> str:
    target_model = "gemini-3.1-flash-lite-preview"
    try:
        response = client.models.generate_content(
            model=target_model,
            config={"system_instruction": system_instruction},
            contents=prompt,
        )
        return (response.text or "").strip()
    except Exception as e:
        print(f">>> [WARNING] 3.1 预览版连接失败 (错误: {str(e)[:50]})，降级至稳定版...")
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        return (response.text or "").strip()

def write_health(ok: bool, message: str, post_relpath: str = "") -> None:
    automation = Path("automation")
    automation.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": ok,
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "message": message,
        "last_post": post_relpath,
    }
    (automation / "health.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    wh = os.getenv("NOTIFY_WEBHOOK_URL", "").strip()
    if wh and not ok:
        try:
            httpx.post(wh, json=payload, timeout=15.0)
        except Exception as exc:
            print(f">>> [WARNING] Webhook 通知失败: {exc}")

def write_social_snippet(
    site_url: str,
    title: str,
    description: str,
    price,
    post_path: Path,
    now: datetime,
    slug: str,
) -> None:
    social = Path("social")
    social.mkdir(parents=True, exist_ok=True)
    url_slug = f"{now.strftime('%H%M')}-{slug}"
    article_url = (
        f"{site_url.rstrip('/')}/posts/{now.year}/{now.month:02d}/{now.day:02d}/{url_slug}/"
    )
    text = (
        f"【分享草稿】\n"
        f"标题：{title}\n"
        f"金价参考：{price} 美元\n"
        f"摘要：{social_blurb(description)}\n"
        f"链接：{article_url}\n"
        f"源文件：{post_path.as_posix()}\n"
    )
    (social / "latest.txt").write_text(text, encoding="utf-8")

def yaml_quote(s: str) -> str:
    return (s or "").replace('"', "'")

def run_analysis():
    post_relpath = ""
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print(">>> [ERROR] 找不到 GEMINI_API_KEY")
            write_health(False, "缺少 GEMINI_API_KEY")
            sys.exit(1)

        client = genai.Client(api_key=api_key)
        system_instruction = (
            "你是一名顶级金融分析师，专门负责‘黄金形态通APP’的内容营销。"
            "你的任务是基于数据生成极具吸引力的黄金分析报告，引导用户在App Store下载APP。"
        )

        print(">>> [DEBUG] 正在同步 XAU/USD 实时行情...")
        gold = yf.Ticker("GC=F")
        hist = gold.history(period="1d")
        price = round(hist["Close"].iloc[-1], 2) if hist is not None and not hist.empty else "2650.00"

        vol_tier, vol_pct, vol_line = compute_volatility(gold)
        if isinstance(vol_pct, float) and math.isnan(vol_pct):
            vol_pct = 0.0
        print(f">>> [DEBUG] 波动档位: {vol_tier} ({vol_pct:+.2f}%)")

        recent_titles = load_recent_titles()
        prompt = build_prompt(price, vol_line, recent_titles)
        print(">>> [DEBUG] 正在请求 Gemini...")
        ai_text = generate_ai_text(client, system_instruction, prompt)
        if not ai_text:
            raise ValueError("AI 返回内容为空。")

        title, body = extract_title_and_body(ai_text)
        sim = max_title_similarity(title, recent_titles)
        if sim >= TITLE_SIMILARITY_RETRY:
            print(f">>> [WARNING] 标题相似度过高 ({sim:.2f})，尝试重写一次…")
            retry_prompt = (
                prompt
                + f"\n5. 上一版标题「{title}」与近期文章过于相似（相似度约 {sim:.0%}）。"
                  "请**全文重写**：标题必须更换立意与句式，可从跨周期、波动率、关键事件、仓位管理等不同角度切入。\n"
            )
            ai_text2 = generate_ai_text(client, system_instruction, retry_prompt)
            if ai_text2:
                title, body = extract_title_and_body(ai_text2)
                sim = max_title_similarity(title, recent_titles)
        if sim >= TITLE_SIMILARITY_ABORT:
            raise ValueError(f"标题与近期文章仍过于相似（{sim:.2f}），已中止以避免重复灌水。")

        print(">>> [DEBUG] 正在生成 _posts 文章文件...")
        now = datetime.now(timezone.utc)
        slug = slugify(title)
        posts_dir = Path("_posts")
        posts_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{now.strftime('%Y-%m-%d-%H%M')}-{slug}.md"
        post_path = posts_dir / filename
        post_relpath = post_path.as_posix()

        desc = first_paragraph(body)
        safe_title = yaml_quote(title)
        safe_desc = yaml_quote(desc)

        extra_tags, topics_zh = detect_topics(title + "\n" + body)
        base_tags = ["gold", "xauusd", "analysis", f"vol-{vol_tier}"]
        all_tags = base_tags + [t for t in extra_tags if t not in base_tags]
        tags_line = ", ".join(all_tags)

        keywords = ["黄金", "XAU/USD", "黄金行情", "技术分析", "形态识别", "金价"]
        for z in topics_zh:
            if z not in keywords:
                keywords.append(z)
        keywords_json = json.dumps(keywords, ensure_ascii=False)

        topics_yaml = "topics: []\n"
        if topics_zh:
            topics_yaml = "topics:\n" + "".join(f"  - {yaml_quote(z)}\n" for z in topics_zh)

        post_md = (
            "---\n"
            "layout: post\n"
            f'title: "{safe_title}"\n'
            f"date: {now.strftime('%Y-%m-%d %H:%M:%S')} +0000\n"
            f'description: "{safe_desc}"\n'
            f"lastmod: {now.strftime('%Y-%m-%d %H:%M:%S')} +0000\n"
            f"volatility_tier: {vol_tier}\n"
            f"price_change_hint: {round(vol_pct, 3)}\n"
            f"keywords: {keywords_json}\n"
            "categories: [gold]\n"
            f"tags: [{tags_line}]\n"
            f"{topics_yaml}"
            "---\n\n"
            f"**生成时间（UTC）**：{now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"**参考价格**：{price} 美元（波动参考：{vol_tier}，较前收约 {vol_pct:+.2f}%）\n\n"
            f"{body.strip()}\n\n"
            "---\n"
            "### 关于黄金形态通APP\n"
            "**黄金形态通APP** 是一款专注于黄金交易的技术分析工具，支持 K 线形态智能识别、实时行情预警。\n"
            "- **App Store 搜索**: `黄金形态通`\n"
            "- **核心功能**: AI行情分析，蜡烛图头肩底、双顶双底、黄金分割线智能绘制和识别。\n\n"
            "---\n"
            "*声明：本内容由 AI 辅助撰写，仅供参考。*\n"
        )

        post_path.write_text(post_md, encoding="utf-8")
        print(f">>> [DEBUG] 已写入文章: {post_relpath}")

        site_url = (
            os.getenv("SITE_URL", "").strip()
            or "https://gold-pattern-pro.github.io/gold-article/"
        )
        write_social_snippet(site_url, title, desc, price, post_path, now, slug)

        readme = (
            "# 黄金形态通APP - 黄金行情博客\n\n"
            "本仓库通过 GitHub 更新黄金（XAU/USD）行情分析，并发布到 GitHub Pages。\n\n"
            f"- **站点入口**：{site_url}\n"
            f"- **文章归档**：{site_url.rstrip('/')}/archive/\n"
            f"- **站点地图**：{site_url.rstrip('/')}/sitemap.xml\n"
            f"- **RSS**：{site_url.rstrip('/')}/feed.xml\n\n"
            "## 文章来源\n\n"
            f"- **最新文章**：`{post_relpath}`\n"
            "- **社交分享草稿**：`social/latest.txt`\n"
            "- **运行健康**：`automation/health.json`\n"
            "- 文章存放目录：`_posts/`\n"
            "- 生成脚本：`daily_gold_analysis.py`\n"
            "- 定时任务：`.github/workflows/daily_run.yml`\n"
            "- Pages 发布：`.github/workflows/pages.yml`\n\n"
            "## 关于黄金形态通APP\n\n"
            "**黄金形态通APP** 是一款专注于黄金交易的技术分析工具，支持 K 线形态智能识别、实时行情预警。\n\n"
            "- **App Store 搜索**: `黄金形态通`\n"
            "- **核心功能**: AI行情分析，蜡烛图头肩底、双顶双底、黄金分割线智能绘制和识别。\n"
        )
        Path("README.md").write_text(readme, encoding="utf-8")

        write_health(True, "ok", post_relpath)
        print(">>> [DEBUG] 任务全部成功完成！")

    except Exception as e:
        msg = str(e)
        print(f">>> [CRITICAL ERROR] 错误详情: {msg}")
        write_health(False, msg, post_relpath)
        sys.exit(1)


if __name__ == "__main__":
    run_analysis()
