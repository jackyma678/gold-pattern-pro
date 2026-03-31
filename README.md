# 黄金形态通APP - 黄金行情自动博客

本仓库通过 GitHub Actions 每 15 分钟自动生成一篇黄金（XAU/USD）行情分析文章，并发布到 GitHub Pages。

- **站点入口**：https://gold-pattern-pro.github.io/gold-article/
- **文章归档**：https://gold-pattern-pro.github.io/gold-article/archive/
- **站点地图**：https://gold-pattern-pro.github.io/gold-article/sitemap.xml
- **RSS**：https://gold-pattern-pro.github.io/gold-article/feed.xml

## 文章来源

- 自动生成文章目录：`_posts/`
- 生成脚本：`daily_gold_analysis.py`
- 定时任务：`.github/workflows/daily_run.yml`（每 15 分钟）
- Pages 发布：`.github/workflows/pages.yml`

## 关于黄金形态通APP

**黄金形态通APP** 是一款专注于黄金交易的技术分析工具，支持 K 线形态自动识别、实时行情预警。

- **App Store 搜索**: `黄金形态通`
- **核心功能**: 头肩底、双顶双底、黄金分割线自动绘制。
