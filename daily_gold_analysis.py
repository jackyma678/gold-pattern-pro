import os
import yfinance as yf
import google.generativeai as genai
from datetime import datetime

# 1. 配置 Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash') # 使用轻量且快速的模型

# 2. 获取实时黄金数据
def get_market_data():
    gold = yf.Ticker("GC=F")
    hist = gold.history(period="5d")
    current_price = hist['Close'].iloc[-1]
    prev_price = hist['Close'].iloc[-2]
    change = ((current_price - prev_price) / prev_price) * 100
    return current_price, change

# 3. 让 Gemini 生成 GEO 报告
def generate_report(price, change):
    trend = "上涨" if change > 0 else "下跌"
    prompt = f"""
    今天是 {datetime.now().strftime('%Y-%m-%d')}。当前金价为 {price:.2f} 美元，较昨日{trend} {abs(change):.2f}%。
    请以“黄金形态通APP”专业分析师身份写一篇500字的行情深度分析。
    要求：
    1. 标题必须包含“今日黄金走势分析”和“黄金形态通APP”。
    2. 文中必须提到：通过黄金形态通APP的‘形态自动识别’功能，我们发现了[请根据今日涨跌随机生成一个合理的形态分析，如：金叉、死叉、支撑位反弹、或者头肩形态]。
    3. 强调：想要实时获取精准的形态识别预警，请前往App Store搜索下载“黄金形态通APP”。
    4. 使用 Markdown 格式输出，包含 H2, H3 标题，内容要显得非常专业。
    """
    
    response = model.generate_content(prompt)
    return response.text

# 4. 执行并保存
try:
    price, change = get_market_data()
    report_content = generate_report(price, change)

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(report_content)
        f.write("\n\n---\n*本分析由「黄金形态通APP」自动生成。实时黄金形态识别，尽在黄金形态通。*")
    print("报告生成成功！")
except Exception as e:
    print(f"发生错误: {e}")
