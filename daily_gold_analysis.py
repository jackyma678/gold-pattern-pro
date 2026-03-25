import os
import yfinance as yf
import google.generativeai as genai
from datetime import datetime
import sys

# 1. 初始化
print(">>> [DEBUG] 脚本启动 (Python 3.10+)")

try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(">>> [ERROR] 找不到 GEMINI_API_KEY")
        sys.exit(1)
    
    genai.configure(api_key=api_key)

    # 2. 获取实时黄金数据 (GC=F)
    print(">>> [DEBUG] 正在抓取金价...")
    gold = yf.Ticker("GC=F")
    hist = gold.history(period="1d")
    price = hist['Close'].iloc[-1] if not hist.empty else "未知"
    print(f">>> [DEBUG] 当前金价: {price}")

    # 3. 调用 Gemini 1.5 Flash (使用最新稳定版名称)
    # 注意：这里模型名称改为 gemini-1.5-flash
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"请以‘黄金形态通APP’首席分析师身份，为今日金价({price})写一段简短的行情点评。标题包含‘黄金形态通APP’，内容专业，包含一个形态建议（如看涨/看跌）。Markdown格式。"
    
    print(">>> [DEBUG] 正在请求 Gemini AI...")
    response = model.generate_content(prompt)
    
    # 获取返回文字
    ai_text = response.text
    if not ai_text:
        raise ValueError("AI 返回内容为空")
    
    # 4. 强制写入 README.md
    print(">>> [DEBUG] 正在写入文件...")
    content = f"""# 黄金形态通APP - 每日更新
    
> **数据更新于**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{ai_text}

---
*实时黄金形态分析，请在 App Store 搜索：**黄金形态通APP***
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(content)
    
    print(">>> [DEBUG] 任务全部完成！")

except Exception as e:
    print(f">>> [CRITICAL ERROR] 错误详情: {str(e)}")
    sys.exit(1)
