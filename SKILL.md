---
name: 总裁速览
description: Unspool(总裁速览)—— 把任意视频/音频链接(YouTube、Bilibili、抖音、TikTok、小红书、小宇宙、Apple Podcasts 等)转成"不遗漏信息"的结构化笔记,沉淀到本地(Obsidian)/ 飞书 / Notion。使用场景:用户在对话框中粘贴或分享一个视频/播客 URL,希望快速拿到可扫描的全量结构化笔记。
---

# Unspool · 总裁速览

把视频/音频内容从"必须线性听完"重组为"可扫描结构化阅读"。**核心动作是重组,不是压缩** —— 不挑要点、不写 TL;DR、不做主观判断,只把线性内容变成密集分章节的 bullet 笔记。

**意义**:在「长视频/播客」与「知识复利」之间架一座桥。速览长内容 + 自动记笔记(沉淀到本地 Obsidian / 飞书 / Notion,均带平台·时长·日期属性,可筛选检索反链)+ 可对话的知识(平台上的 agent 能就知识点问答、关联)——让看过的内容变成可检索、可追问、会增值的知识资产。详见 README。

## 何时触发

- 用户输入一个视频/音频 URL(youtube.com、bilibili.com、douyin.com、xiaohongshu.com、xiaoyuzhoufm.com 等)
- 用户明确说"总结这个视频/播客""帮我看一下这个链接""转成文档"
- 用户分享了一个含媒体链接的消息

## 何时不触发

- URL 是文章/网页(非视频音频)
- 用户只想要简短摘要 / TL;DR(本 Skill 反其道而行,输出全量结构化)

## 使用方法(两步:先预检,再处理)

### 第一步:预检(决定用哪个源)

收到链接后,**先**跑预检:

```bash
python -m scripts.preflight "<URL>"
```

看输出的 `DECISION:` 行:

- **`DECISION: DIRECT(...)`** → 直接进第二步,处理原链接
- **`DECISION: CHOOSE(...)`** → 脚本在 `ALTERNATIVES:` 下列出了更好的替代源(同款视频在更快/有字幕的平台)。**把这些候选用自然语言呈现给用户**(平台 / 时长 / 是否有字幕 / 是否可能是全集),让用户选一个编号,或选 0 用原链接。
  - 例:"你发的小红书视频需下载完整视频较慢。我在 YouTube 找到了同一个视频(时长一致、**有字幕,可秒出且省钱**)。用哪个?
    1. YouTube 228min 有字幕 [链接]
    0. 还是用原小红书链接"

### 第二步:处理(用用户选定的 URL)

```bash
python -m scripts.run "<选定的 URL>"
```

可选 `--config /path/to/config.yaml`(默认读 `~/.总裁速览/config.yaml`)。

**预检的判断规则**(脚本已实现,你只管看 DECISION):
- 时长 < 30 分钟 → DIRECT(短内容不值得找替代)
- 有字幕(YouTube 字幕 / B站登录后 AI 字幕)→ DIRECT(能免 ASR)
- ≥30 分钟无字幕 → 搜 YouTube + Apple + B站 同款;只有"确实更好"的候选才会列出让你选
  - "确实更好" = 时长差 ≤ 20 分钟,且(候选有字幕 / 原平台是小红书·抖音这类痛点源)
  - 都不满足 → 仍判 DIRECT,用原链接

工作目录在本 Skill 包根目录。如未配置,引导用户参考 `README.md`。

**前提**:建议用户在本机浏览器登录常用网站(B站/抖音等),cookie 自动复用。

## 各平台处理路径(自动路由)

脚本会根据 URL 自动选择路径,**你(agent)通常不用管**:

| 平台 | 路径 | 说明 |
|---|---|---|
| YouTube | yt-dlp 字幕优先,无字幕走 ASR | 最快 |
| Bilibili | 登录后取 AI 字幕(免 ASR);否则音频流 → ASR | 登录后最快 |
| 小红书 | yt-dlp 原生 → ASR | 慢(需下完整视频,无音频流)|
| 小宇宙 | 自写 adapter(抓单集音频)→ ASR | 很快,纯音频 |
| 抖音 / TikTok | Evil0ctal adapter(见下方兜底链)→ ASR | 需 vendor + cookie |

## 抖音/TikTok 的三级兜底链

抖音/TikTok 有强 anti-bot,纯 HTTP 工具会随版本失效。处理顺序:

1. **Evil0ctal adapter(默认,已实现)**
   - 脚本自动调用 `~/.总裁速览/vendor/Douyin_TikTok_Download_API`(Python 直接 import)
   - cookie 自动从浏览器提取并缓存(首次可能弹一次系统密码,之后走缓存)
   - 大多数情况这一步就成功

2. **JoeanAmier/TikTokDownloader(备选,已实现)**
   - 日活维护的项目;若 Evil0ctal 失效,在 config 里改 `douyin.backend: joeanamier` 即可切换
   - 实现方式:本地起它的 Web API server(端口 5555)→ POST /douyin/detail → 拿视频直链
   - 需要安装到 `~/.总裁速览/vendor/TikTokDownloader`(见 README)

3. **Agent 用浏览器兜底(最终手段,未实现 —— 需要时由你 agent 临场处理)**
   - 若上面两级都失败,**你(agent)可以用自带的 browser 工具**去第三方解析站
     (如 snaptik、ssstik、aitoolwang 等)手动下载视频文件
   - 然后把文件交给本 Skill 处理(当前 `--file` 入口尚未实现,需要时再加)
   - 这一级不需要预先测试或接线,纯属应急路径

**当前状态**:抖音/TikTok 默认走第 1 级(Evil0ctal),可配置切到第 2 级(JoeanAmier)。
若都失败,先确认对应 vendor 已安装(见 README)。

## cookie 说明

- YouTube / 小红书 / B站 / 小宇宙的公开内容**默认不带 cookie**(先无 cookie 尝试,失败才回退)
- 抖音必须带 cookie(自动从 Chrome 提取并缓存到 `~/.总裁速览/cache/`)
- 用户首次跑抖音可能被 macOS 要一次钥匙串密码,之后 12 小时内走缓存不再要

## 返回给用户的内容

**仅**转发脚本 stdout 输出(一行完成提示 + 文件路径 + 标题·时长)。**不要**在回复里嵌入文档正文、要点摘录、章节预览 —— 所有内容都在文档里。

## 错误处理

| 现象 | 应对 |
|---|---|
| 配置文件不存在 | 引导用户参考 README 创建 `~/.总裁速览/config.yaml` |
| 抖音解析失败 | 确认 vendor 已装;提示用户在 Chrome 登录/访问过 douyin.com |
| 视频无法访问 | 提示链接可能已删除/私有/需付费 |
| ASR 余额不足(402)| 提示用户 MiMo 账户充值 |
| 飞书 API 失败 | 本地文件已保存,告诉用户本地路径 |

## 输出原则(产品哲学)

**绝对不要**修改 `scripts/summarizer.py` 中的 `SYSTEM_PROMPT`,除非用户明确要求调整产品哲学。该 prompt 是产品差异化核心:不筛选、不修辞、不主观评分、电报式密集分章节。
