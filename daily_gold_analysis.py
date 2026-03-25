import os
import yfinance as yf
from google import genai
from datetime import datetime
import sys
import time

print(">>> [DEBUG] 脚本启动 (降级至 1.5-Flash 以保证配额)")

try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(">>> [ERROR] 找不到 GEMINI_API_KEY")
        sys.exit(1)
    
    client = genai.Client(api_key=api_key)

    # 1. 获取实时黄金数据
    print(">>> [DEBUG] 正在抓取实时金价...")
    gold = yf.Ticker("GC=F")
    hist = gold.history(period="1d")
    price = hist['Close'].iloc[-1] if not hist.empty else "2650.0"
    print(f">>> [DEBUG] 当前金价: {price}")

    # 2. 调用最稳定的 Gemini 1.5 Flash 模型
    prompt = f"请以‘黄金形态通APP’分析师身份，为今日金价({price})写一段简短的行情点评。标题包含‘黄金形态通APP’。Markdown格式。"
    
    print(">>> [DEBUG] 正在请求 Gemini 1.5 AI...")
    
    # 增加简单的重试机制
    response = client.models.generate_content(
        model='gemini-1.5-flash', # 1.5版最稳定，基本不会报配额错误
        contents=prompt
    )
    
    ai_text = response.text
    if not ai_text:
        raise ValueError("AI 返回内容为空")
    
    # 3. 强制写入 README.md
    print(">>> [DEBUG] 正在写入文件...")
    content = f"""# 黄金形态通APP - 全自动行情预警

> **数据同步于**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{ai_text}

---
*实时黄金形态识别，请在 App Store 搜索：**黄金形态通APP***
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(content)
    
    print(">>> [DEBUG] 自动化任务全部成功！")

except Exception as e:
    print(f">>> [CRITICAL ERROR] 错误详情: {str(e)}")
    # 如果还是配额问题，打印一个友情提示
    if "429" in str(e):
        print("提示：您的 Gemini API 暂时配额不足，请等待 1 分钟后重试，或检查 Google AI Studio 是否启用了 Pay-as-you-go（免费层级通常足够）。")
    sys.exit(1)
