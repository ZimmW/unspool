# Unspool · 总裁速览

**[English](./README.en.md)** | 中文

把任意视频/播客链接,变成"不遗漏信息"的结构化笔记 —— 自动沉淀到本地(Obsidian)/ 飞书 / Notion。

## 它解决什么(为什么需要它)

长视频和播客是信息的富矿,却也是时间的黑洞:**必须线性听完、无法扫读、看完即忘**,知识随播放进度一起蒸发。

**Unspool 在「长视频/播客」与「知识复利」之间架起一座桥。** 它把动辄数小时的内容**重组**(不是压缩)成可扫描的密集分章节笔记,一条信息不丢(只删广告),并直接沉淀进你的知识库 —— 让**每一条看过的内容,都变成可检索、可追问、会增值的知识资产。**

- **速览**:3 小时的访谈几分钟扫完,结构清晰、信息完整
- **自动记笔记**:产出直接落到本地 / Obsidian / 飞书 / Notion,省去手敲整理
- **知识沉淀,处处可做**:无论本地 Markdown(Obsidian)、飞书文档还是 Notion,都带平台/时长/日期等属性,可筛选、可搜索、可反链 —— 越攒越厚,长成你的"第二大脑"
- **可对话的知识**:笔记落到飞书 / Notion 后,平台上的 agent 还能就其中知识点评论、问答、关联 —— 内容从"看完即弃"升级为能持续追问、彼此勾连的知识对象
- **跨平台统一**:YouTube / B站 / 抖音 / 小红书 / 播客,殊途同归成同一种结构化格式
- **团队杠杆**:一个人处理,全团队读;为时间稀缺、需广进信息的决策者而建

> 核心理念:**重组,不是压缩**。不挑要点、不写 TL;DR、不做主观评分,只把线性内容变成密集分章节的 bullet 笔记。

## 和传统 AI 总结有什么不同

| | 传统 AI 总结 | 总裁速览(Unspool) |
|---|---|---|
| 核心动作 | **压缩**——挑它认为的"要点" | **重组**——全量重排成可扫描结构 |
| 信息 | 主观筛选,大量细节丢失 | 不筛选(唯一例外:删广告) |
| 形态 | 一段话 / 几条 TL;DR | 分章节 + 时间戳 + 表格 + 嵌套 bullet |
| 主观介入 | 有:评分、提炼、"亮点" | 无:只有客观信息 |
| 能否替代原片 | 否,只能知道个大概 | 接近:细节都在,扫读即可 |
| 用完之后 | 一段文字,看完即弃 | 落到 Obsidian/飞书/Notion,可检索、可沉淀复利 |

**同一段访谈,两种产出:**

传统总结(几乎所有可执行细节都没了):

> 嘉宾回顾了公司的融资历程,比较了开源与闭源路线的优劣,并对 Scaling Law 的未来表示乐观。

总裁速览(节选,信息密度高、可扫读):

```
## 融资历程 [12:30-18:40]
- 2021 种子轮:红杉领投,$X
- 2023 A 轮:估值 $Y → 资金用于自建训练集群

## 开源 vs 闭源之争 [18:40-26:10]
| 维度 | 开源 | 闭源 |
|---|---|---|
| 能力 | 前沿落后 | 领先 |
| 成本 | 自建 infra | 按量付费、贵 |
| 控制 | 可私有部署 | 依赖厂商 |
```

## 支持的平台

| 平台 | 实现 | 备注 |
|---|---|---|
| YouTube | yt-dlp(字幕优先,无字幕走 ASR) | 最快 |
| Bilibili | **登录后取 AI 字幕免 ASR**;否则音频流 → ASR | 登录后最快 |
| 小红书 | yt-dlp 原生 → ASR | 慢:无音频流,需下完整视频 |
| 小宇宙 | 内置 adapter(抓单集音频)→ ASR | 很快,纯音频 |
| 抖音 / TikTok | Evil0ctal 解析器 + cookie → ASR | 需额外安装(见下) |
| 其他 yt-dlp 支持的 1800+ 站点 | yt-dlp | 视平台而定 |

## 首次设置

先看全貌,再按下面逐项配。**带 ★ 的是大多数人必做的三件事。**

| 项目 | 必需? | 干什么用 | 怎么做 |
|---|---|---|---|
| 系统依赖 | ★ 必需 | 下载音视频/字幕、转码 | `brew install ffmpeg yt-dlp` |
| Python 依赖 | ★ 必需 | 跑脚本 | `pip install -r requirements.txt` |
| LLM 模型 | ★ 必需 | **核心大脑**:把逐字稿重组成文档 | agent 里**默认免配**(用 agent 的模型);独立跑才填 `llm` |
| ASR API key | 处理**无字幕**内容时必需 | 把语音转成文字 | 填 `config.yaml` 的 `asr` |
| 浏览器登录 | 强烈建议 | 解锁需登录/反爬的内容 | 平时浏览器登录常用站即可 |
| 输出方式 | 至少选一种 | 文档存到哪 | 本地默认开;飞书/Notion 见下 |
| 抖音 vendor | 处理抖音才需 | 抖音反爬解析 | clone 一个 vendor |

### 1. 系统依赖 ★

```bash
# macOS
brew install ffmpeg yt-dlp
# Linux
sudo apt install ffmpeg && pipx install yt-dlp
```

`yt-dlp` 负责从 1800+ 站点下载音视频和字幕;`ffmpeg` 负责音频切片/转码(ASR 要用)。

### 2. Python 依赖 ★

```bash
pip install -r requirements.txt
```

### 3. 配置文件 ★

```bash
mkdir -p ~/.总裁速览
cp config.example.yaml ~/.总裁速览/config.yaml
```

下面 4、5、6 都是编辑这一个文件(它在你的家目录,不在本仓库里)。

### 4. LLM —— 默认就用 agent 的模型

这是整个 skill 的**大脑**:把逐字稿重组成密集分章节的结构化文档,**每条内容都要用,不可省**。

**跑在 agent(Claude Code / OpenClaw 等)里时,通常什么都不用配** —— 会自动复用 agent 自己的 Claude 模型(读环境变量 `ANTHROPIC_API_KEY`)。

只有当你想**单独指定**模型(比如换更便宜的 DeepSeek,或脱离 agent 独立跑)时,才填 `llm` 段:

```yaml
llm:
  provider: deepseek       # anthropic / deepseek / openai 兼容
  api_key: <你的 key>      # DeepSeek 申请:https://platform.deepseek.com
  model: deepseek-chat
```

> 成本:按 token 计费。DeepSeek 很便宜(一条长访谈通常几分到几毛)。

### 5. ASR API key —— 为什么"有条件"必需

ASR = 语音转文字。**只有当内容拿不到现成字幕时才需要它**把音频转成逐字稿:

- **用不到 ASR**:YouTube 有字幕的视频、B站登录后有 AI 字幕的视频 → 直接读字幕,免费又快
- **必须 ASR**:小红书、抖音、小宇宙、无字幕的播客/YouTube → 得听音频转文字

所以:**只要你会处理上面"必须 ASR"那类内容,就得配 ASR key。** 推荐几个,挑一个去申请:

| 服务 | 特点 | 申请地址 |
|---|---|---|
| **Groq**(最易上手) | 有免费额度、速度快 | https://console.groq.com/keys |
| **OpenAI** | 最稳、全球可用 | https://platform.openai.com/api-keys |
| **Gemini** | Google,有免费额度 | https://aistudio.google.com/apikey |
| **Qwen**(阿里) | Qwen3-ASR,中文强 | https://bailian.console.aliyun.com |
| **MiMo**(默认) | 小米,中文友好 | https://api.xiaomimimo.com |

拿到 key 填进 `config.yaml`。默认是 MiMo;**上手最简单是 Groq**:

```yaml
asr:
  provider: groq
  api_key: <你的 key>
  base_url: https://api.groq.com/openai/v1
  model: whisper-large-v3-turbo
```

> 成本:按**音频时长**计费,是长内容的主要开销。所以 skill 会优先找字幕版来省这笔钱(见「智能跨平台路由」)。

### 6. 输出方式 —— 至少选一种

文档生成后存到哪。三种可单选也可多开。简单说:**个人本地党 → 配 Obsidian;要协作/可检索的知识库 → 飞书或 Notion(两个都推荐,看你常驻哪个生态)。**

| 方式 | 适合 | 说明 |
|---|---|---|
| **本地 Markdown**(默认开) | 个人、想要可控的纯文件 | **推荐配 Obsidian**:把 path 指到 vault 即用,自带 frontmatter 可筛选/反链 |
| **飞书**(推荐) | 在飞书生态里协作 | 成飞书云文档,可分享/评论,团队知识沉淀 |
| **Notion**(推荐) | 个人或团队的可检索资料库 | 每篇入库带平台/时长/日期属性,可筛选搜索 |

本地默认就开,不用配。飞书 / Notion 的逐步设置见下方「[输出目标](#输出目标)」。

### 7. 浏览器登录(强烈建议)—— 为什么 & 怎么做

很多内容**藏在登录/反爬后面**:B站的 AI 字幕要登录才取得到、抖音必须带 cookie、部分会员/限定内容也要登录。

**你不用导出任何东西、不用填 cookie**。做法极简:**平时就用你日常的浏览器(Chrome 等)登录着 B站、抖音等常用站点**就行。skill 会在需要时**自动从浏览器读取 cookie**并缓存(macOS 首次可能弹一次钥匙串密码,之后走缓存)。

> 不登录会怎样?公开内容照常跑;但 B站会走 ASR(慢且花钱)、抖音可能直接失败。

### 8. 抖音/TikTok 额外安装(不处理抖音可跳过)

抖音/TikTok 反爬强,`yt-dlp` 搞不定,需 clone 一个社区解析器:

```bash
mkdir -p ~/.总裁速览/vendor
git clone https://github.com/Evil0ctal/Douyin_TikTok_Download_API.git \
    ~/.总裁速览/vendor/Douyin_TikTok_Download_API
cd ~/.总裁速览/vendor/Douyin_TikTok_Download_API && pip install -r requirements.txt
```

不装的话:**只有贴抖音链接才会报错**,其他平台不受影响。

**备选后端 JoeanAmier**(可选,Evil0ctal 失效时切换):clone `JoeanAmier/TikTokDownloader`
到 `~/.总裁速览/vendor/TikTokDownloader` 并装依赖,然后在 config 设 `douyin.backend: joeanamier`。

### 9. 先跑一条验证

建议**先用一条有字幕的短 YouTube** 验证链路(免 ASR,最快看到结果):

```bash
python -m scripts.run "https://www.youtube.com/watch?v=<某短视频>"
```

跑通后会在 `~/Documents/总裁速览/` 看到生成的 .md。再去试无字幕/其他平台的内容。

## 使用

```bash
python -m scripts.run "https://www.youtube.com/watch?v=xxx"
python -m scripts.run "https://www.bilibili.com/video/BVxxx/"
python -m scripts.run "https://www.xiaoyuzhoufm.com/episode/xxx"
python -m scripts.run "https://v.douyin.com/xxx/"
```

作为 Skill 安装到 Claude Code / OpenClaw 等 agent 后,粘贴链接即自动调用。详见 [SKILL.md](./SKILL.md)。

## cookie 机制

- **公开内容默认不带 cookie**(YouTube/小红书/B站/小宇宙)——先无 cookie 尝试,失败才回退
- **抖音必须 cookie**——自动从浏览器提取并缓存,避免每次跑都弹密码
- 配置见 `config.yaml` 的 `cookies` 段(`from_browser: chrome` 等)

## 智能跨平台路由(≥30 分钟内容)

作为 Skill 使用时,agent 收到链接会**先预检**(`python -m scripts.preflight <url>`):

- 时长 < 30 分钟,或已有字幕 → 直接处理
- **≥30 分钟且无字幕** → 自动搜 YouTube + Apple Podcasts + B站 找同款
  - 若找到更好的源(有字幕可免 ASR / 帮小红书逃 1GB 下载),列给用户选
  - 时长接近度排序(±20 分钟内),最终由用户确认是否同款

典型收益:小红书长视频(下 1GB + ASR)→ 命中 YouTube 同款字幕版 → 秒级免 ASR。
详见 [SKILL.md](./SKILL.md) 的两步编排。

## 输出目标

**本地 Markdown**(默认开):`~/Documents/总裁速览/`,文件名 `日期_[平台]_标题_时长.md`。
文档头含来源、时长、原链接、处理时间、运行时长、说话人说明(多人内容)。

> **想进 Obsidian**:把 `output.local.path` 指到你的 vault 文件夹即可。本地文件默认在顶端写
> YAML frontmatter(平台/时长/日期/原链接),Obsidian 的 **Properties / Dataview** 可据此筛选检索
> —— 等于在本地复刻 Notion 那个可查询库。不想要可设 `output.local.frontmatter: false`。

飞书和 Notion **都推荐**(看你团队/个人常驻哪个生态),可单开也可都开;真嵌套列表 / 真表格 / 高亮块都保真。**个人想要可控文件就用本地 + Obsidian。**

### 飞书(推荐)

1. 在[飞书开放平台](https://open.feishu.cn/)建一个**自建应用**,拿到 `app_id` / `app_secret`
2. 给应用开权限:**云文档**(创建/编辑文档)
3. 在 `config.yaml` 填:
   ```yaml
   output:
     feishu:
       enabled: true
       app_id: cli_xxx
       app_secret: xxx
       folder_token: ""          # 留空 = 放"我的空间"根目录
       tenant_domain: 你的租户    # 形如 abcd1234,用于拼最终 URL
   ```

### Notion(推荐——可累积成可检索的资料库)

每跑一条就**写入一个数据库**,带 `平台 / 时长(分) / 日期 / 原链接` 属性,可在 Notion 里筛选、排序、搜索。

1. 去 [my-integrations](https://www.notion.so/my-integrations) 建一个 **internal integration**(Authentication 选 **Access token**,不是 OAuth),拿到 `ntn_...` / `secret_...` token
2. 在 Notion 里新建一个**空白页面**当容器,右上 `•••` → **Connections** → 把刚建的 integration 加进去(否则它无权访问)
3. 在 `config.yaml` 填(`parent_page_id` 是那个页面 URL 末尾的 32 位字符):
   ```yaml
   output:
     notion:
       enabled: true
       token: ntn_xxx
       parent_page_id: <容器页面 id>   # 首次自动在其下建"总裁速览"数据库并缓存
       mode: database                  # database(推荐)| page
   ```
   也可跳过 `parent_page_id`、直接填已有的 `database_id`。

## ASR 说明(MiMo)

MiMo 的语音识别走 `mimo-v2-omni` 多模态模型(chat completions + 音频),不是标准
`/audio/transcriptions` 接口。长音频自动按 5 分钟切片并发转写。

可切换其他 provider(改 `config.yaml` 的 `asr.provider`):
- `mimo` / `gemini` → multimodal_chat 协议
- `openai` / `groq` / `qwen` → openai_transcriptions 协议(标准 Whisper 接口)

## 成本与隐私(请先了解)

- **会花钱的地方**:LLM(按 token,便宜)+ ASR(按音频时长,长内容的大头)。有字幕的内容只花 LLM 钱;无字幕长内容 ASR 是主要开销 —— 这也是 skill 优先找字幕版的原因。
- **内容会发给第三方 API**:逐字稿会发给你配置的 **LLM 厂商**、音频会发给 **ASR 厂商**做处理。介意的话选自己信任的 provider,或用自托管模型。
- **密钥/cookie 只在本地**:都存 `~/.总裁速览/`,不上传任何地方;`config.yaml`、cookie、缓存都已被 `.gitignore` 排除。
- **密钥轮换**:key/token 一旦在聊天、截图、协作中暴露过,**用一阵子后去对应平台重置一次**。
- **登录态**:skill 只读取浏览器里已有的 cookie 用于下载,不会改你的账号或代你操作。

## 项目结构

```
.
├── SKILL.md                    # Skill 入口(给 agent 的指令)
├── README.md / README.en.md    # 说明文档(中文 / English)
├── requirements.txt
├── config.example.yaml
└── scripts/
    ├── run.py                  # 主入口 + 平台路由
    ├── preflight.py            # 预检:30 分钟门槛 + 字幕检查 + 跨平台找同款
    ├── search.py               # 跨平台搜索(YouTube / Apple / B站)
    ├── bilibili.py             # B站 WBI 签名 + 搜索 + AI 字幕提取
    ├── config.py               # 配置加载
    ├── downloader.py           # yt-dlp 封装(probe/字幕/音频,cookie 回退)
    ├── cookies.py              # 浏览器 cookie 提取 + 缓存
    ├── transcript.py           # Transcript 结构 + VTT 解析
    ├── asr.py                  # ASR adapter(MiMo omni / OpenAI 兼容,并发+重试)
    ├── chapters.py             # 章节切分(原生质量检测 / AI 兜底)
    ├── summarizer.py           # LLM 文档生成(分段 + 电报式 prompt)
    ├── output_local.py         # 本地 Markdown(文件名截断)
    ├── output_feishu.py        # 飞书 docx + markdown→block 树(真·嵌套/真·表格)
    ├── output_notion.py        # Notion 数据库写入(真·嵌套/真·表格/真·callout + 属性)
    └── adapters/
        ├── douyin.py           # 抖音/TikTok(Evil0ctal 默认 / JoeanAmier 备选)
        ├── douyin_joeanamier.py # 抖音 JoeanAmier 后端(Web API)
        └── xiaoyuzhou.py       # 小宇宙(抓单集音频)
```

## 致谢

本项目站在这些开源项目的肩膀上:

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) —— 多平台音视频 / 字幕下载
- [FFmpeg](https://ffmpeg.org/) —— 音频切片 / 转码
- [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) —— 抖音 / TikTok 解析(默认后端)
- [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader) —— 抖音备选后端

> 本项目**不打包、不分发**上述项目的代码,由用户自行安装到本地 `vendor/`,各自遵循其原始 license。
> 抖音 / TikTok 反爬频繁变动,这两个 vendor 请保持最新(失效时 `git pull` 更新)。

## 已知限制

- **抖音/TikTok**:依赖 Evil0ctal 解析器,平台 anti-bot 升级时可能短暂失效;
  规划的兜底是 JoeanAmier / agent 浏览器手动下载(见 SKILL.md,尚未接线)
- **小红书**:无独立音频流,需下完整视频(1GB+ 常见),较慢
- **小宇宙**:目前只支持单集 `/episode/` 链接,不支持整档 `/podcast/`
- **MiMo ASR**:按音频时长计费,中文人名/专名偶有识别错误
- **说话人标注**:由 LLM 推断,可能不准确
- 微信公众号视频暂不支持
