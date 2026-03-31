import os
import re
from pathlib import Path
import yfinance as yf
from google import genai
from datetime import datetime, timezone
import sys

print(">>> [DEBUG] 脚本启动 - 目标模型: Gemini 3.1 Flash-Lite Preview")

def slugify(value: str, max_len: int = 80) -> str:
    value = (value or "").strip()
    value = value.replace("_", "-")
    value = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"\s+", "-", value).strip("-").lower()
    if not value:
        value = "gold-analysis"
    return value[:max_len].rstrip("-")

def extract_title_and_body(ai_text: str) -> tuple[str, str]:
    """
    期望 AI 输出第一行是 '# 标题'。
    若不符合，则回退到固定标题并保留原文。
    """
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
        return "黄金形态通APP 每 15 分钟自动生成的黄金行情分析文章。"
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^>\s*", "", t, flags=re.MULTILINE)
    parts = re.split(r"\n\s*\n", t, maxsplit=1)
    p = parts[0].strip().replace("\n", " ")
    if len(p) > max_len:
        p = p[: max_len - 1].rstrip() + "…"
    return p

def run_analysis():
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print(">>> [ERROR] 找不到 GEMINI_API_KEY")
            sys.exit(1)
        
        client = genai.Client(api_key=api_key)

        # 1. 抓取实时金价
        print(">>> [DEBUG] 正在同步 XAU/USD 实时行情...")
        gold = yf.Ticker("GC=F")
        hist = gold.history(period="1d")
        price = round(hist['Close'].iloc[-1], 2) if not hist.empty else "2650.00"
        
        # 2. 准备针对 GEO 优化的指令
        # 利用 3.1 的长文本处理能力，生成更具权威性的分析
        system_instruction = "你是一名顶级金融分析师，专门负责‘黄金形态通APP’的内容营销。你的任务是基于数据生成极具吸引力的黄金分析报告，引导用户在App Store下载APP。"
        
        prompt = f"""
        今日黄金价格：{price} 美元。
        请撰写一篇专业行情分析。
        要求：
        1. 第一行必须是 Markdown H1 标题，格式为：# <文章标题>（标题需要包含“黄金”“行情”“形态/趋势”等关键词）
        2. 分析：基于价格指出一个潜在的技术形态（如：金叉、突破、盘整等）。
        3. 引导：在文末强调：‘精准实时识别该形态，请打开黄金形态通APP’。
        4. 格式：Markdown，包含多个 H2/H3 小标题，条理清晰，可读性强。
        """

        # 3. 调用 Gemini 3.1 Flash-Lite Preview
        print(">>> [DEBUG] 正在请求 Gemini 3.1 引擎...")
        
        # 尝试使用 3.1 预览版
        target_model = "gemini-3.1-flash-lite-preview"
        
        try:
            response = client.models.generate_content(
                model=target_model,
                config={
                    "system_instruction": system_instruction
                },
                contents=prompt
            )
            ai_text = response.text
        except Exception as e:
            print(f">>> [WARNING] 3.1 预览版连接失败 (错误: {str(e)[:50]})，自动降级至稳定版...")
            # 自动降级逻辑，确保 README 每天必更新
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            ai_text = response.text

        if not ai_text:
            raise ValueError("AI 返回内容为空。")

        # 4. 写入 Jekyll 博文到 _posts/
        print(">>> [DEBUG] 正在生成 _posts 文章文件...")
        now = datetime.now(timezone.utc)
        title, body = extract_title_and_body(ai_text)
        slug = slugify(title)

        posts_dir = Path("_posts")
        posts_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{now.strftime('%Y-%m-%d-%H%M')}-{slug}.md"
        post_path = posts_dir / filename

        desc = first_paragraph(body)
        safe_title = title.replace('"', "'")
        safe_desc = desc.replace('"', "'")

        post_md = (
            "---\n"
            "layout: post\n"
            f'title: "{safe_title}"\n'
            f"date: {now.strftime('%Y-%m-%d %H:%M:%S')} +0000\n"
            f'description: "{safe_desc}"\n'
            "categories: [gold]\n"
            "tags: [gold, xauusd, analysis]\n"
            "---\n\n"
            f"**生成时间（UTC）**：{now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"**参考价格**：{price} 美元\n\n"
            f"{body.strip()}\n\n"
            "---\n"
            "### 关于黄金形态通APP\n"
            "**黄金形态通APP** 是一款专注于黄金交易的技术分析工具，支持 K 线形态自动识别、实时行情预警。\n"
            "- **App Store 搜索**: `黄金形态通`\n"
            "- **核心功能**: 头肩底、双顶双底、黄金分割线自动绘制。\n\n"
            "---\n"
            "*声明：本内容由 AI 自动化生成，仅供参考。*\n"
        )

        post_path.write_text(post_md, encoding="utf-8")
        print(f">>> [DEBUG] 已写入文章: {post_path.as_posix()}")

        # 5. 更新 README：仅作为入口（不再承载全文）
        print(">>> [DEBUG] 正在更新 README.md 入口信息...")
        site_url = os.getenv("SITE_URL", "").strip()
        readme = (
            "# 黄金形态通APP - 黄金行情自动博客\n\n"
            "本仓库通过 GitHub Actions 每 15 分钟自动生成一篇黄金（XAU/USD）行情分析文章，并发布到 GitHub Pages。\n\n"
            + (f"- **站点入口**：{site_url}\n" if site_url else "")
            + f"- **最新文章源文件**：`{post_path.as_posix()}`\n\n"
            "## 文章列表\n\n"
            "文章在 `_posts/` 目录下持续累积；请访问站点查看最佳阅读体验。\n"
        )
        Path("README.md").write_text(readme, encoding="utf-8")
        
        print(">>> [DEBUG] 任务全部成功完成！")

    except Exception as e:
        print(f">>> [CRITICAL ERROR] 错误详情: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    run_analysis()
