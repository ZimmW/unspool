"""调用 Claude 把 transcript + 章节信息转成最终 Markdown 文档。"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

from .chapters import Chapter
from .transcript import Transcript


def _fmt_elapsed(seconds: float) -> str:
    """运行时长格式化,如 '3 分 12 秒' / '45 秒'。"""
    s = int(round(seconds))
    m, s = divmod(s, 60)
    if m:
        return f"{m} 分 {s} 秒"
    return f"{s} 秒"


SYSTEM_PROMPT = """你是一个内容结构化助手。你的任务是把一份视频/音频的 transcript 转换成一份"不遗漏任何信息点"的结构化文档。

## 核心原则(必须严格遵守)

1. **不筛选信息**:transcript 中所有有意义的陈述都必须进入文档。包括:事实、观点、数据、例子、提及的人/事/物、反问、补充、分歧。不要决定哪些"不重要"。

2. **不修辞包装**:绝对不要写 TL;DR、核心摘要、金句精选、值得听的理由、关键收获、要点回顾这类内容。文档里只有客观信息,没有引导性文字。

3. **清理无信息内容**:语气词、口头禅、寒暄客套、明显重复、节目预告应被清理。如果某段几乎全是这类内容,标"(略)"或不出现。

4. **广告必须直接删除**(不写"略"、不留痕迹):凡是出现"赞助""sponsor""优惠码""折扣码""限时优惠""promo code""brought to you by""本期/本节目由 X 提供"等广告标志,或出现品牌+购买引导组合的整段内容,**完全不要进入文档**,直接跳过,就像这段从未存在。

**严禁出现以下 meta 标记**:
- "(略)" / "(此处省略)"
- "(广告)" / "(广告插播)" / "(广告内容已删除)"
- "此处为广告" / "已跳过广告" / 任何形式说明"我删除了什么"的注释
- 章节中的广告时段也不要在 bullet 里提及该时间范围被删

判断标准:如果一段内容主要目的是推销第三方产品/服务,而非传递主播或嘉宾的观点,即为广告。如果整个章节全是广告,直接让这个章节的 bullets 为空(只留章节标题即可),不要任何说明文字。

5. **保留原始论证结构**:如果嘉宾用一个故事说明观点,用嵌套 bullet 保留这个"观点 + 故事"的结构,不要拆散。

6. **去对话化:只写信息,不写对话框架**。访谈节目中,主持人提问通常没有独立信息价值,真正的信息在嘉宾的回答里。
   - ❌ 不要写:"主持人提问 X""主持人问到 X""主持人介绍嘉宾 X""主持人转向 X 话题""嘉宾回答..."这类对话动作描述
   - ❌ 不要写:"嘉宾认为 X""嘉宾指出 X""嘉宾分享了 X"——直接陈述 X 即可,不要套主语
   - ✅ 正确做法:把问题里包含的事实/观点直接合并进回答的信息点;如果问题本身就是没有信息的引导句(如"那你是怎么做的呢"),整个跳过
   - ✅ 例外:**当说话人之间存在真正的分歧或互相补充时**,这是有信息的——用"X 认为...""Y 反驳..."保留双方观点
   - ✅ 例外:多人讨论中,**意见归属本身是信息**(谁说的很重要),才需要标说话人

简言之:文档读起来应该像一份事实/观点清单,而不是访谈实录。读者不需要知道这话是谁问的、节目怎么推进的、嘉宾被介绍了什么——只需要知道**讲了什么**。

## 文档骨架

```
# [视频标题]

**来源**:[平台] · [作者] · [节目名]
**时长**:XX 分 XX 秒
**原链接**:[URL]
**处理时间**:[时间]
**说话人说明**:说话人标注由 AI 推断,可能不准确(仅多说话人内容显示)

---

## [章节 1 标题] [HH:MM-HH:MM]

- 信息点
- 信息点
  - 子信息点
- 信息点

## [章节 2 标题] [HH:MM-HH:MM]
...
```

## 具体规则

- **章节标题**:有原生章节直接用;无则你来切分,标题不超过 15 字,描述性而非营销性
- **时间戳**:每个章节标题后必有时间戳,bullet 上不加时间戳
- **嵌套**:最多 2 层,仅用于"观点+论据""问题+回答""主张+补充"
- **说话人**:默认不标说话人,直接陈述信息。仅当出现观点分歧/相互补充/不同立场对照时,才标"X 认为..."。主持人开场介绍、衔接性提问一律不要标注归属。
- **bullet 颗粒度**:每个 bullet 一个独立信息单位,颗粒度保持一致

- **能合并就合并**:相邻 bullet 如果是同一论点的不同侧面、同一对象的不同属性、或前后承接的事实链,合并成一条。判断标准:如果两条 bullet 单独看都不完整、必须连读才有意义,就该合并。**不要为了凑数量而拆分**,一个完整想法占一条即可。

- **言语极简(电报式)**:bullet 是笔记,不是讲稿。

  **结构符号优先**(替代连接词):
  - `→` 表演变/因果/推导:`6 个月 → 1 个月 → 1 天` `工程加速 + 模型迭代 → 交付周期缩短`
  - `:` 引出定义/属性:`Kat:Cloud Code PM`
  - `+` 表并列累加,`|` 或 `/` 表选项
  - `vs` 表对比:`AI 前 vs AI 后`
  - 能用符号就别用"从...到...""导致""以及""并且"

  **名词短语化**:
  - 完整主谓宾改名词短语:"Boris 是技术负责人" → "Boris:技术负责人"
  - 角色介绍用冒号:"Kat Wu 为 Cloud Code 团队 PM" → "Kat:Cloud Code PM"
  - bullet 末尾不要加句号(疑问句保留问号)

  **删冗余主语和修饰**:
  - 同章节内反复出现的主语省略:"Anthropic 希望消除..." 在 Anthropic 章节里直接 "刻意消除..."
  - 删:"非常/特别/其实/可以说/值得注意的是/我觉得/一般来说/在我看来"
  - 删啰嗦句式:"以...的方式""通过...来...""为了...而..." 直接动词+宾语

  **删解释性插入语**(后面常是同义复述):
  - 删 "(即...)""(也就是...)""换言之""换句话说""说白了"
  - 同义重复只保留一处:"显著大幅"→"显著","快速迅速"→"快速","工程效率大幅提升"→"工程加速"

  **保留原文术语,不强行中译**:
  - `Cloud Code`、`research preview`、`dogfood`、`AGI`、`PM`、`PRD` 等原文保留
  - 中英混排是技术内容的自然形态,不要造"云代码""研究预览""内部试吃"这种生造词

  **括号语义复述删掉,数字/补充保留**:
  - "产品愿景设定者(设定 3-6 个月和 AGI 版本的产品方向)" → "产品愿景:3-6 个月 / AGI 版方向"
  - "心灵融合(约 80% 一致)" 数字保留;"工作方式类似心灵融合"完全可以省成"心灵融合"

  **长度上限(硬约束)**:
  - 顶层 bullet ≤ 40 字
  - 子 bullet ≤ 60 字
  - 超长就拆分,或者改写删水分。**宁可粗暴截断也不要堆砌**

  **目标**:同样的信息量,字数比对话原话压缩 60-70%。读起来像 X / Twitter 笔记,不像散文。

- **选对展现形式(核心:让读者"不读字"就能完成他要做的动作)**

  每段信息先想一步:读者拿它要做什么?形式服务那个动作,而不是套模板。

  | 读者要做的动作 | 信息的"形状" | 用什么 |
  |---|---|---|
  | 横向比较(A/B 在某维度差在哪) | 多对象共享一组属性 | 表格 |
  | 顺着核对一一对应 | A↔B 映射,≥3 对 | 两列表格 |
  | 理解怎么演变/推导出来 | 因果·转化·推导 | 箭头串 → |
  | 照着做 / 记顺序 / 看排名 | 有先后的序列 | 有序列表 `1. 2. 3.` |
  | 看主干挂着哪些细节 | 主从层级 | 嵌套 bullet |
  | 停下来记住这一句 | 一句定义/原话/结论 | 强调块 `>` |
  | 只是知道有哪些 | 无结构罗列 | bullet |

  **表格**——唯一理由是"对齐以便比较"。读者不会想比较,就别用表格(是负担)。
  - ✅ N 对象 × M 维度(M≥2):产品 × 适用场景/限制;多模型 × 多指标;AI 前 vs 后 × 多维度
  - ✅ ≥3 个一一对应映射,做成两列:产品→制造商、术语→解释、年份→事件、数据点序列
  - ❌ 单个对象的多个属性 → 没有"另一个对象"可比 → 用嵌套 bullet,**绝不要写成 `维度 | 内容` / `维度 | 数据` 这种伪表格**
  - ❌ 2×2 象限 / 矩阵 → 飞书表格画不好 → 改用 bullet 把四个格子说清
  - 表格示例:
    ```
    | 产品 | 适用场景 | 限制 |
    |---|---|---|
    | Claude Code | 一次性编码 + 最新功能 | 仅 CLI |
    | Desktop | 前端、非技术用户、全局概览 | 限本地 |
    | Cowork | 非代码输出(slides、文档) | - |
    ```

  **有序列表 `1. 2. 3.`**——只在"有先后"时用:步骤、流程、排名、时间顺序。并列无先后用普通 bullet。

  **强调块(行首 `> `)**——把一章里"最该停下来的一句"拎出来,**每章最多一个,可以没有**:
  - 嘉宾的关键**原话**(直接引语,是信息不是金句)
  - 一句**核心定义**或**反直觉结论**
  - ❌ 禁止用它放小编总结、评价、"值得注意"这类引导语(违反不修辞原则)

  **箭头串 →**——因果/转化/演变/推导,别套表格也别套步骤。单点类比"X 像 Y"用句式。

## Before / After 示范

❌ "Anthropic 希望消除一切阻碍产品交付的因素,许多产品功能的交付周期已从6个月缩短到1个月,有时甚至缩短到1天"
✅ "刻意消除一切发布阻碍,交付周期:6 个月 → 1 个月,极端 1 天"

❌ "Kat Wu 为 Cloud Code 团队 PM;Boris Cherny 是技术负责人和产品愿景设定者(设定 3-6 个月和 AGI 版本的产品方向)"
✅ "Kat:Cloud Code PM | Boris:技术负责人 + 产品愿景(3-6 个月 / AGI 版方向)"

❌ "AI 时代前,技术变化慢,产品规划周期为 6-12 个月,代码开发成本高,PM 大量精力用于协调跨团队排期以互相解耦"
✅ "AI 前:技术变化慢,规划周期 6-12 个月,代码成本高 → PM 主要协调跨团队排期"

❌ "LLM 极度通用,带来大量模糊性(为谁构建、解决什么问题、首要用例是什么)"
✅ "LLM 极通用 → 模糊性大:目标用户?核心问题?首要用例?"

## 输出前自检(表格最容易漏,重点过一遍)

逐章回看:**只要某章出现「2 个以上对象 × 2 个以上维度」的对比,就改成表格**,不要留成并列 bullet —— 这是最常漏的。典型场景:开源 vs 闭源、多模型/多公司/多方案并列、某事物前后(演变)在多个维度上的差异。
**护栏**:没有这种对比结构的章节保持 bullet,**不要为凑表格硬造**;单对象多属性、2×2 象限同样不做表。(即:有对比就别漏,没对比就别造。)

最常漏的转换,照这个做:
❌ 并列 bullet(该合并对比):
- 开源:社区迭代快、可私有部署;但前沿能力落后、需自建 infra
- 闭源:能力领先、开箱即用;但贵、依赖厂商、不可控
✅ 改表格(一眼对比):
| 维度 | 开源 | 闭源 |
|---|---|---|
| 能力 | 前沿落后 | 领先 |
| 成本 | 自建 infra | 按量付费、贵 |
| 控制 | 可私有部署 | 依赖厂商 |
| 生态 | 社区迭代快 | 开箱即用 |

## 输出

直接输出 Markdown 文档,不要任何前后说明,不要 ```markdown 包裹。
"""


def _fmt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _fmt_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h} 时 {m} 分 {s} 秒"
    return f"{m} 分 {s} 秒"


class _LLM:
    """统一 LLM 接口,封装 anthropic / OpenAI 兼容两种调用。"""

    def __init__(self, llm_cfg: dict[str, Any]):
        self.provider = llm_cfg.get("provider", "anthropic")
        self.model = llm_cfg.get("model")
        self.api_key = llm_cfg.get("api_key")
        if not self.api_key:
            raise RuntimeError(
                "未配置 LLM。请在 config.yaml 的 llm.api_key 填入密钥,"
                "或设置 ANTHROPIC_API_KEY 环境变量(agent 环境通常已有,"
                "此时本 skill 默认复用 agent 的 Claude 模型)。")
        self.base_url = llm_cfg.get("base_url")
        self._client = None

    def _build(self):
        if self._client is not None:
            return self._client
        if self.provider == "anthropic":
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key)
            self.model = self.model or "claude-sonnet-4-5"
        else:
            from openai import OpenAI
            base = self.base_url or _default_base_url(self.provider)
            self._client = OpenAI(api_key=self.api_key, base_url=base)
            self.model = self.model or _default_model(self.provider)
        return self._client

    def complete(self, system: str, user: str, max_tokens: int) -> str:
        client = self._build()
        if self.provider == "anthropic":
            resp = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            for block in resp.content:
                if getattr(block, "type", None) == "text":
                    return block.text
            return ""
        # OpenAI 兼容(DeepSeek、OpenAI、Groq 等)
        resp = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


def _default_base_url(provider: str) -> str | None:
    return {
        "deepseek": "https://api.deepseek.com/v1",
        "openai": None,  # 用 openai SDK 默认
        "groq": "https://api.groq.com/openai/v1",
    }.get(provider)


def _default_model(provider: str) -> str:
    return {
        "deepseek": "deepseek-chat",
        "openai": "gpt-4o",
        "groq": "llama-3.3-70b-versatile",
    }.get(provider, "gpt-4o")


def build_doc(
    *,
    transcript: Transcript,
    title: str,
    platform: str,
    uploader: str,
    url: str,
    duration: int,
    chapters: list[Chapter] | None,
    llm_cfg: dict[str, Any],
    per_chapter_threshold_minutes: int = 60,
    start_time: float | None = None,
) -> str:
    """生成最终文档。长内容按章节分批生成。

    start_time: process 起始的 time.time(),用于在文档头记录"运行时长"。
    """
    llm = _LLM(llm_cfg)

    # 先生成正文(这是耗时大头),再算运行时长,保证时长涵盖文档生成
    if chapters:
        body = _generate_per_chapter(llm, transcript, chapters)
    else:
        body = _generate_per_segment(llm, transcript, duration)
    body = _strip_generated_header(body)

    elapsed = (time.time() - start_time) if start_time else None
    header = _build_header(
        title=title, platform=platform, uploader=uploader,
        url=url, duration=duration, multi_speaker=transcript.has_speakers,
        processing_seconds=elapsed,
    )

    return f"{header}\n\n---\n\n{body.strip()}\n"


def _strip_generated_header(body: str) -> str:
    """删除 LLM 自作主张生成的文档头(`# 标题` + metadata + `---`),
    只保留从第一个 `## 章节` 开始的内容。"""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("## "):
            return "\n".join(lines[i:])
    return body  # 没找到任何 `## 章节`,原样返回


def _doc_title(title: str, max_chars: int = 50) -> str:
    """文档 # 标题:抖音/小红书的 title 常是几百字文案,这里取第一句并限长。"""
    t = title.strip()
    for sep in ["\n", "。", "！", "？", "!", "?", ";", "；"]:
        if sep in t:
            t = t.split(sep, 1)[0]
            break
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_chars:
        t = t[:max_chars].rstrip() + "…"
    return t


def _build_header(*, title: str, platform: str, uploader: str, url: str,
                  duration: int, multi_speaker: bool,
                  processing_seconds: float | None = None) -> str:
    source = f"{platform} · {uploader}" if uploader else platform
    lines = [
        f"# {_doc_title(title)}",
        "",
        f"**来源**:{source}",
        f"**时长**:{_fmt_duration(duration)}",
        f"**原链接**:{url}",
        f"**处理时间**:{datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    if processing_seconds is not None:
        lines.append(f"**运行时长**:{_fmt_elapsed(processing_seconds)}")
    if multi_speaker:
        lines.append("**说话人说明**:说话人标注由 AI 推断,可能不准确")
    return "\n".join(lines)


def _chapter_hint(chapters: list[Chapter] | None) -> str:
    if not chapters:
        return "(无原生章节,请你基于内容自行切分章节)"
    lines = ["原生章节(请直接采用这些标题和时间范围):"]
    for c in chapters:
        lines.append(f"- [{_fmt_ts(c.start)}-{_fmt_ts(c.end)}] {c.title}")
    return "\n".join(lines)


def _generate_single(llm: _LLM, transcript: Transcript,
                     chapters: list[Chapter] | None) -> str:
    user_msg = (
        f"{_chapter_hint(chapters)}\n\n"
        f"## Transcript\n\n{transcript.to_prompt_text()}\n\n"
        f"## 任务\n\n按系统提示生成文档正文(从第一个 `## 章节` 开始,"
        f"不要重复文档头部 metadata)。"
    )
    return llm.complete(SYSTEM_PROMPT, user_msg, max_tokens=8000)


def _generate_per_segment(llm: _LLM, transcript: Transcript, duration: int) -> str:
    """长内容无显式章节:按时间段切片,每段独立 inline 切章节(v1 风格)。

    每段约 50-60 分钟,保证 LLM 单次输出 8K token 不会被截断。
    各段保持 v1 的"LLM 边读边切章节"特性。
    """
    # 目标每段 30 分钟 —— 唯一目的是不撞 DeepSeek 8K output cap。
    # LLM 在每段内自由 inline 切章节。短视频 ≤ 30min 自动归为 1 段。
    target_segment_min = 30
    n_segments = max(1, round(duration / 60 / target_segment_min))
    segment_seconds = duration / n_segments

    print(f"      [per-segment] {n_segments} 段, 每段 ~{segment_seconds/60:.0f} 分钟",
          flush=True)

    parts: list[str] = []
    for i in range(n_segments):
        start = i * segment_seconds
        end = (i + 1) * segment_seconds if i < n_segments - 1 else duration
        segs = [s for s in transcript.segments
                if s.start >= start and s.start < end]
        if not segs:
            continue
        sub_text = "\n".join(
            f"[{_fmt_ts(s.start)}]{(' ' + s.speaker + ':') if s.speaker else ''} {s.text}"
            for s in segs
        )
        # 关键 prompt:告诉 LLM 这是第 i+1/N 段,自己切章节,时间戳要严格在段范围内
        user_msg = (
            f"这是一段长 transcript 的第 {i+1}/{n_segments} 段,"
            f"时间范围:{_fmt_ts(start)}-{_fmt_ts(end)}。\n\n"
            f"## Transcript\n\n{sub_text}\n\n"
            f"## 任务\n\n"
            f"按系统提示生成本段的文档正文。要求:\n"
            f"- 自行切分本段内的章节(按主题边界,标题 ≤15 字)\n"
            f"- 每个章节的时间戳必须严格落在本段范围 [{_fmt_ts(start)}-{_fmt_ts(end)}] 内\n"
            f"- 不要输出文档头部 metadata,直接从第一个 `## 章节` 开始\n"
            f"- 不要在段首加任何引言,不要总结、不要预告下一段\n"
        )
        print(f"      [segment {i+1}/{n_segments}] {_fmt_ts(start)}-{_fmt_ts(end)} "
              f"({len(segs)} 段)", flush=True)
        parts.append(llm.complete(SYSTEM_PROMPT, user_msg, max_tokens=8000).strip())

    return "\n\n".join(parts)


def _generate_per_chapter(llm: _LLM, transcript: Transcript,
                          chapters: list[Chapter]) -> str:
    """长内容:每个章节单独调一次,最后拼接。"""
    out_parts: list[str] = []
    for ch in chapters:
        segs = [s for s in transcript.segments
                if s.start >= ch.start and s.start < ch.end]
        if not segs:
            continue
        sub_text = "\n".join(
            f"[{_fmt_ts(s.start)}]{(' ' + s.speaker + ':') if s.speaker else ''} {s.text}"
            for s in segs
        )
        user_msg = (
            f"本章节标题:{ch.title}\n"
            f"时间范围:{_fmt_ts(ch.start)}-{_fmt_ts(ch.end)}\n\n"
            f"## Transcript(仅本章节)\n\n{sub_text}\n\n"
            f"## 任务\n\n仅输出本章节一段,格式:\n"
            f"`## {ch.title} [{_fmt_ts(ch.start)}-{_fmt_ts(ch.end)}]`\n"
            f"后跟 bullets。不要输出其他章节,不要输出文档头部。"
        )
        out_parts.append(llm.complete(SYSTEM_PROMPT, user_msg, max_tokens=8000).strip())
    return "\n\n".join(out_parts)
