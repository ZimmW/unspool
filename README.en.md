# Unspool

English | **[中文](./README.md)**

Turn any video/podcast link into structured, **lossless** notes — automatically deposited into a local file (Obsidian), Lark (Feishu), or Notion.

## What it's for (why you'd want it)

Long videos and podcasts are rich ore — and time sinks: you **must listen linearly, can't skim, and forget it the moment you finish**, the knowledge evaporating with the playback bar.

**Unspool is the bridge between long-form audio/video and compounding knowledge.** It **restructures** hours of content (it does *not* compress) into scannable, densely-chaptered notes — losing nothing (only ads removed) — and deposits them straight into your knowledge base, so **everything you watch becomes a searchable, queryable, appreciating knowledge asset.**

- **Skim anything**: a 3-hour interview in minutes — clear structure, complete information
- **Notes taken for you**: output lands in a local file / Obsidian / Lark / Notion — no manual transcribing
- **Knowledge precipitation, anywhere**: local Markdown (Obsidian), Lark docs, or Notion — all carry platform/duration/date properties you can filter, search, and backlink; the more you add, the richer your "second brain"
- **Knowledge you can talk to**: once in Lark / Notion, an agent there can comment on points, answer questions, and link them — content goes from "watch once and forget" to an interconnected knowledge object you keep interrogating
- **One format across platforms**: YouTube / Bilibili / Douyin / Xiaohongshu / podcasts all converge into the same structured shape
- **Team leverage**: one person processes, the whole team reads — built for time-poor decision-makers

> Core principle: **restructure, don't compress.** No cherry-picking, no TL;DR, no subjective scoring — just turn linear content into dense, chaptered bullet notes.

## Supported platforms

| Platform | How | Notes |
|---|---|---|
| YouTube | yt-dlp (subtitles first, ASR if none) | fastest |
| Bilibili | **AI subtitles when logged in (skip ASR)**; else audio → ASR | fastest when logged in |
| Xiaohongshu | yt-dlp native → ASR | slow: no audio-only stream, downloads full video |
| Xiaoyuzhou | built-in adapter (grabs episode audio) → ASR | fast, audio-only |
| Douyin / TikTok | Evil0ctal parser + cookie → ASR | extra install (see below) |
| 1800+ other yt-dlp sites | yt-dlp | varies |

## First-time setup

See the whole picture first, then configure each item. **The three ★ items are what most people must do.**

| Item | Required? | What it's for | How |
|---|---|---|---|
| System deps | ★ required | download A/V & subtitles, transcode | `brew install ffmpeg yt-dlp` |
| Python deps | ★ required | run the scripts | `pip install -r requirements.txt` |
| LLM model | ★ required | **the brain**: restructures transcript into the doc | **free in an agent** (uses the agent's model); only fill `llm` if running standalone |
| ASR API key | required for **subtitle-less** content | speech → text | fill `asr` in `config.yaml` |
| Browser login | strongly recommended | unlock login-gated / anti-bot content | just stay logged in on your everyday browser |
| Output target | pick at least one | where docs go | local is on by default; Lark/Notion below |
| Douyin vendor | only for Douyin | Douyin anti-bot parsing | clone one vendor |

### 1. System dependencies ★

```bash
# macOS
brew install ffmpeg yt-dlp
# Linux
sudo apt install ffmpeg && pipx install yt-dlp
```

`yt-dlp` downloads audio/video and subtitles from 1800+ sites; `ffmpeg` slices/transcodes audio (needed for ASR).

### 2. Python dependencies ★

```bash
pip install -r requirements.txt
```

### 3. Config file ★

```bash
mkdir -p ~/.总裁速览
cp config.example.yaml ~/.总裁速览/config.yaml
```

Steps 4–6 all edit this one file (it lives in your home dir, not in this repo).

### 4. LLM — defaults to the agent's model

This is the **brain**: it restructures the transcript into the densely-chaptered doc, used on **every** piece of content.

**Running inside an agent (Claude Code / OpenClaw, etc.), you usually configure nothing** — it reuses the agent's own Claude model (via the `ANTHROPIC_API_KEY` env var).

Only fill the `llm` section if you want to **pin a specific model** (e.g. cheaper DeepSeek, or running standalone):

```yaml
llm:
  provider: deepseek       # anthropic / deepseek / openai-compatible
  api_key: <your key>      # DeepSeek: https://platform.deepseek.com
  model: deepseek-chat
```

> Cost: billed per token. DeepSeek is very cheap (a long interview is typically pennies).

### 5. ASR API key — why it's "conditionally" required

ASR = speech-to-text. **You only need it when content has no ready-made subtitles:**

- **No ASR needed**: YouTube videos with captions, Bilibili videos with AI subtitles (logged in) → read subtitles directly, free and fast
- **ASR required**: Xiaohongshu, Douyin, Xiaoyuzhou, podcasts/YouTube without captions → must transcribe the audio

So: **if you'll process the "ASR required" kind of content, you need an ASR key.** Pick one and sign up:

| Service | Notes | Sign up |
|---|---|---|
| **Groq** (easiest) | free tier, very fast | https://console.groq.com/keys |
| **OpenAI** | most reliable, global | https://platform.openai.com/api-keys |
| **Gemini** | Google, free tier | https://aistudio.google.com/apikey |
| **Qwen** (Alibaba) | Qwen3-ASR, strong on Chinese | https://bailian.console.aliyun.com |
| **MiMo** (default) | Xiaomi, good for Chinese | https://api.xiaomimimo.com |

Put the key in `config.yaml`. Default is MiMo; **easiest to start with is Groq**:

```yaml
asr:
  provider: groq
  api_key: <your key>
  base_url: https://api.groq.com/openai/v1
  model: whisper-large-v3-turbo
```

> Cost: billed by **audio duration** — the main cost for long content. That's why the skill prefers a subtitled source to save it (see "Smart cross-platform routing").

### 6. Output target — pick at least one

Where the generated doc goes. Choose one or enable several. In short: **solo & local-first → pair with Obsidian; want collaboration / a searchable base → Lark or Notion (both recommended, pick whichever ecosystem you live in).**

| Target | Best for | Notes |
|---|---|---|
| **Local Markdown** (on by default) | solo, want plain controllable files | **pair with Obsidian**: point `path` at a vault; ships with filterable/backlinkable frontmatter |
| **Lark (Feishu)** (recommended) | collaborating in the Lark ecosystem | becomes a Lark cloud doc, shareable/commentable, team knowledge base |
| **Notion** (recommended) | a searchable library, solo or team | each run becomes a DB row with platform/duration/date props, filterable & searchable |

Local is on by default. Step-by-step Lark / Notion setup is in "[Output targets](#output-targets)" below.

### 7. Browser login (strongly recommended) — why & how

A lot of content is **behind login / anti-bot**: Bilibili AI subtitles require login, Douyin requires cookies, some member-only content needs login too.

**You don't export anything or paste cookies.** It's trivial: **just stay logged in to Bilibili, Douyin, etc. on your everyday browser (Chrome, etc.).** The skill **reads cookies straight from your browser** when needed and caches them (macOS may prompt for the keychain once, then it's cached).

> What if you don't log in? Public content still works; but Bilibili falls back to ASR (slow + costs money) and Douyin may fail outright.

### 8. Douyin/TikTok extra install (skip if you don't do Douyin)

Douyin/TikTok have strong anti-bot that `yt-dlp` can't handle, so clone a community parser:

```bash
mkdir -p ~/.总裁速览/vendor
git clone https://github.com/Evil0ctal/Douyin_TikTok_Download_API.git \
    ~/.总裁速览/vendor/Douyin_TikTok_Download_API
cd ~/.总裁速览/vendor/Douyin_TikTok_Download_API && pip install -r requirements.txt
```

Without it: **only Douyin links will error**; other platforms are unaffected.

**Fallback backend JoeanAmier** (optional, switch to it if Evil0ctal breaks): clone `JoeanAmier/TikTokDownloader`
into `~/.总裁速览/vendor/TikTokDownloader`, install deps, then set `douyin.backend: joeanamier`.

### 9. Run one to verify

Verify the pipeline with **a short subtitled YouTube video first** (no ASR, fastest result):

```bash
python -m scripts.run "https://www.youtube.com/watch?v=<a short video>"
```

The `.md` shows up in `~/Documents/总裁速览/`. Then try subtitle-less / other platforms.

## Usage

```bash
python -m scripts.run "https://www.youtube.com/watch?v=xxx"
python -m scripts.run "https://www.bilibili.com/video/BVxxx/"
python -m scripts.run "https://www.xiaoyuzhoufm.com/episode/xxx"
python -m scripts.run "https://v.douyin.com/xxx/"
```

Once installed as a Skill into an agent (Claude Code / OpenClaw, etc.), just paste a link and it triggers automatically. See [SKILL.md](./SKILL.md).

## Cookie mechanism

- **Public content carries no cookie by default** (YouTube/Xiaohongshu/Bilibili/Xiaoyuzhou) — tries without first, falls back only on failure
- **Douyin always needs cookies** — auto-extracted from the browser and cached, so you're not prompted every run
- Configured via the `cookies` section in `config.yaml` (`from_browser: chrome`, etc.)

## Smart cross-platform routing (≥30 min content)

When used as a Skill, the agent **pre-flights** every link first (`python -m scripts.preflight <url>`):

- < 30 minutes, or already has subtitles → process directly
- **≥30 minutes and no subtitles** → search YouTube + Apple Podcasts + Bilibili for the same content
  - if a better source is found (subtitled to skip ASR / saves Xiaohongshu a 1GB download), it's listed for you to choose
  - sorted by duration proximity (within ±20 min); you confirm it's the same content

Typical win: a long Xiaohongshu video (1GB download + ASR) → matched to the same video on YouTube with subtitles → instant, no ASR.

## Output targets

**Local Markdown** (on by default): `~/Documents/总裁速览/`, filename `date_[platform]_title_duration.md`.
The header carries source, duration, original link, processing time, runtime, and a speaker note (multi-speaker content).

> **Using Obsidian?** Point `output.local.path` at a folder inside your vault. Local files get YAML
> frontmatter at the top (platform/duration/date/source URL) by default, so Obsidian's **Properties /
> Dataview** can filter and search them — a local equivalent of the Notion database. Disable with
> `output.local.frontmatter: false`.

Lark and Notion are **both recommended** (pick the ecosystem you live in), single or combined; nested lists / real tables / callouts are all preserved. **For solo, controllable files, use local + Obsidian.**

### Lark (Feishu) (recommended)

1. Create a **custom app** on the [Lark Open Platform](https://open.feishu.cn/) and get `app_id` / `app_secret`
2. Grant the app permission: **Docs** (create/edit documents)
3. Fill `config.yaml`:
   ```yaml
   output:
     feishu:
       enabled: true
       app_id: cli_xxx
       app_secret: xxx
       folder_token: ""          # empty = root of "My Space"
       tenant_domain: your-tenant # like abcd1234, used to build the final URL
   ```

### Notion (recommended — builds a searchable library)

Each run **writes a row into a database** with `platform / duration(min) / date / source URL` properties you can filter, sort, and search in Notion.

1. Create an **internal integration** at [my-integrations](https://www.notion.so/my-integrations) (Authentication: choose **Access token**, not OAuth), get the `ntn_...` / `secret_...` token
2. Create a **blank page** in Notion as the container, top-right `•••` → **Connections** → add the integration you just made (otherwise it can't access anything)
3. Fill `config.yaml` (`parent_page_id` is the 32-char string at the end of that page's URL):
   ```yaml
   output:
     notion:
       enabled: true
       token: ntn_xxx
       parent_page_id: <container page id>   # auto-creates & caches a "总裁速览" database under it
       mode: database                        # database (recommended) | page
   ```
   You can also skip `parent_page_id` and pass an existing `database_id` directly.

## ASR note (MiMo)

MiMo's speech recognition runs through the `mimo-v2-omni` multimodal model (chat completions + audio), not the standard `/audio/transcriptions` endpoint. Long audio is auto-sliced into 5-minute chunks and transcribed concurrently.

Switch provider via `config.yaml`'s `asr.provider`:
- `mimo` / `gemini` → multimodal_chat protocol
- `openai` / `groq` / `qwen` → openai_transcriptions protocol (standard Whisper API)

## Cost & privacy (please read first)

- **Where the money goes**: LLM (per token, cheap) + ASR (per audio minute, the bulk for long content). Subtitled content only costs LLM; subtitle-less long content is dominated by ASR — which is why the skill prefers subtitled sources.
- **Content is sent to third-party APIs**: transcripts go to your configured **LLM provider**, audio to your **ASR provider**. If that matters to you, pick providers you trust or self-host.
- **Keys/cookies stay local**: all under `~/.总裁速览/`, never uploaded; `config.yaml`, cookies, and cache are all excluded by `.gitignore`.
- **Rotate keys**: if a key/token has ever been exposed (chat, screenshot, sharing), reset it on the provider after a while.
- **Login state**: the skill only reads existing browser cookies for downloading — it never changes your accounts or acts on your behalf.

## Project layout

```
.
├── SKILL.md                    # Skill entry (instructions for the agent)
├── README.md / README.en.md    # docs (中文 / English)
├── requirements.txt
├── config.example.yaml
└── scripts/
    ├── run.py                  # main entry + platform routing
    ├── preflight.py            # preflight: 30-min gate + subtitle check + same-content search
    ├── search.py               # cross-platform search (YouTube / Apple / Bilibili)
    ├── bilibili.py             # Bilibili WBI signing + search + AI subtitle extraction
    ├── config.py               # config loading
    ├── downloader.py           # yt-dlp wrapper (probe/subtitle/audio, cookie fallback)
    ├── cookies.py              # browser cookie extraction + cache
    ├── transcript.py           # Transcript structure + VTT parsing
    ├── asr.py                  # ASR adapter (MiMo omni / OpenAI-compatible, concurrent + retry)
    ├── chapters.py             # chapter splitting (native-quality check / AI fallback)
    ├── summarizer.py           # LLM doc generation (segmented + telegraphic prompt)
    ├── output_local.py         # local Markdown (filename truncation)
    ├── output_feishu.py        # Lark docx + markdown→block tree (real nesting / real tables)
    ├── output_notion.py        # Notion database write (real nesting/tables/callouts + properties)
    └── adapters/
        ├── douyin.py           # Douyin/TikTok (Evil0ctal default / JoeanAmier fallback)
        ├── douyin_joeanamier.py # Douyin JoeanAmier backend (Web API)
        └── xiaoyuzhou.py       # Xiaoyuzhou (grabs episode audio)
```

## Acknowledgements

This project stands on the shoulders of these open-source projects:

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — multi-platform audio/video & subtitle download
- [FFmpeg](https://ffmpeg.org/) — audio slicing / transcoding
- [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) — Douyin/TikTok parsing (default backend)
- [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader) — Douyin fallback backend

> This project **does not bundle or redistribute** their code — you install them into a local `vendor/` yourself, each under its own license.
> Douyin/TikTok anti-bot changes often, so keep these vendors up to date (`git pull` if they break).

## Known limitations

- **Douyin/TikTok**: relies on the Evil0ctal parser; may briefly break when the platform upgrades anti-bot. Planned fallbacks are JoeanAmier / agent browser manual download (see SKILL.md, not yet wired).
- **Xiaohongshu**: no separate audio stream, must download the full video (often 1GB+), slow.
- **Xiaoyuzhou**: currently only single-episode `/episode/` links, not whole-podcast `/podcast/`.
- **MiMo ASR**: billed by audio duration; occasional errors on Chinese names/jargon.
- **Speaker labels**: inferred by the LLM, may be inaccurate.
- WeChat Official Account videos are not yet supported.
