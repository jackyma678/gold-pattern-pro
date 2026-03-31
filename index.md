---
layout: default
title: "最新文章"
description: "黄金形态通APP：每 15 分钟自动生成一篇黄金行情分析。"
---

## 最新文章

{% for post in site.posts limit: 30 %}
- [{{ post.title }}]({{ post.url | relative_url }})（{{ post.date | date: "%Y-%m-%d %H:%M UTC" }}）
{% endfor %}

## 订阅

- RSS：[`{{ "/feed.xml" | relative_url }}`]({{ "/feed.xml" | relative_url }})
