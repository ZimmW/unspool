# 排障与平台细节(L3:出错或需要平台细节时才读)

本文件是 SKILL.md 的延伸,日常触发不需要读。仅当处理失败、行为异常,
或你需要了解某平台的具体路径时,再读这里。

## 各平台处理路径(自动路由)

脚本会根据 URL 自动选择路径,agent 通常不用管:

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

3. **Agent 用浏览器兜底(最终手段,未实现 —— 需要时由 agent 临场处理)**
   - 若上面两级都失败,agent 可以用自带的 browser 工具去第三方解析站
     (如 snaptik、ssstik、aitoolwang 等)手动下载视频文件
   - 然后把文件交给本 Skill 处理(当前 `--file` 入口尚未实现,需要时再加)
   - 这一级不需要预先测试或接线,纯属应急路径

**当前状态**:默认走第 1 级(Evil0ctal),可配置切到第 2 级(JoeanAmier)。
若都失败,先确认对应 vendor 已安装(见 README)。

## cookie 说明

- YouTube / 小红书 / B站 / 小宇宙的公开内容**默认不带 cookie**(先无 cookie 尝试,失败才回退)
- 抖音必须带 cookie(自动从 Chrome 提取并缓存到 `~/.总裁速览/cache/`)
- 用户首次跑抖音可能被 macOS 要一次钥匙串密码,之后走缓存不再要

## 错误处理

| 现象 | 应对 |
|---|---|
| 配置文件不存在 | 引导用户参考 README 创建 `~/.总裁速览/config.yaml` |
| 抖音解析失败 | 确认 vendor 已装;提示用户在 Chrome 登录/访问过 douyin.com |
| 视频无法访问 | 提示链接可能已删除/私有/需付费 |
| ASR 余额不足(402)| 提示用户给 ASR 账户(默认 MiMo)充值 |
| ASR 大段漏转(文档有 [⚠ 缺口] 标记) | 偶发可重跑;频繁出现建议换专职 ASR(config 改 `asr.provider: groq` 或 `qwen`,见 README) |
| 飞书 API 失败 | 本地文件已保存,告诉用户本地路径 |
| 飞书/Notion 上传失败 | 本地文件总是先落盘,路径在 stdout 里 |
