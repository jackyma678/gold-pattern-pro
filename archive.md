---
layout: default
title: "文章归档"
description: "黄金形态通APP：全部历史文章归档。"
permalink: /archive/
---

## 文章归档

{% assign sorted_posts = site.posts | sort: "date" | reverse %}

共 **{{ sorted_posts.size }}** 篇。

<ul class="archive-list">
{% for post in sorted_posts %}
  <li>
    <a href="{{ post.url | relative_url }}">{{ post.title }}</a>
    <span class="archive-meta">（{{ post.date | date: "%Y-%m-%d %H:%M UTC" }}）</span>
  </li>
{% endfor %}
</ul>
