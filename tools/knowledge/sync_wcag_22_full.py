#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "knowledge" / "sources" / "wcag_rules.json"
INVENTORY_PATH = ROOT / "knowledge" / "sources" / "wcag_22_inventory.json"
WCAG_URL = "https://www.w3.org/TR/WCAG22/"
UNDERSTANDING_BASE = "https://www.w3.org/WAI/WCAG22/Understanding/"


PRINCIPLES = {
    "1": "Perceivable",
    "2": "Operable",
    "3": "Understandable",
    "4": "Robust",
}


AAA_DATA = {
    "1.2.6": {
        "name_zh": "手语（预录）",
        "applies_to": ["video", "media", "caption", "sign language"],
        "keywords": ["手语", "预录视频", "视频", "sign language", "video", "media"],
        "rule": "预录同步媒体应提供手语翻译。",
        "generation_constraints": ["为预录视频提供手语版本或手语轨道入口。", "播放器附近应清楚标明手语版本。", "不要只依赖字幕替代手语。"],
        "good_example": "<a href=\"lesson-sign-language.html\">观看手语版本</a>",
        "bad_example": "<video controls src=\"lesson.mp4\"></video>",
    },
    "1.2.7": {
        "name_zh": "扩展音频描述（预录）",
        "applies_to": ["video", "media", "audio description"],
        "keywords": ["扩展音频描述", "视频", "extended audio description", "video"],
        "rule": "当普通音频描述不足以表达视觉信息时，应提供扩展音频描述。",
        "generation_constraints": ["为复杂预录视频提供扩展音频描述版本。", "在播放器附近提供可发现的扩展描述入口。", "重要视觉信息不能只存在于画面中。"],
        "good_example": "<a href=\"demo-extended-audio-description.html\">播放扩展音频描述版本</a>",
        "bad_example": "<video controls src=\"demo.mp4\"></video>",
    },
    "1.2.8": {
        "name_zh": "媒体替代（预录）",
        "applies_to": ["video", "audio", "media", "transcript"],
        "keywords": ["媒体替代", "文字稿", "transcript", "media alternative"],
        "rule": "预录同步媒体应提供完整的媒体替代内容。",
        "generation_constraints": ["提供包含对话、重要声音和重要视觉信息的完整文字稿。", "文字稿链接应靠近媒体播放器。", "文字稿应可键盘访问。"],
        "good_example": "<video controls src=\"interview.mp4\"></video><a href=\"#transcript\">阅读完整文字稿</a>",
        "bad_example": "<video controls src=\"interview.mp4\"></video>",
    },
    "1.2.9": {
        "name_zh": "纯音频（直播）",
        "applies_to": ["audio", "live media", "transcript"],
        "keywords": ["直播音频", "实时文字", "live audio", "transcript"],
        "rule": "直播纯音频内容应提供等价的替代信息。",
        "generation_constraints": ["为直播音频提供实时文字、摘要或等价替代入口。", "替代内容入口应靠近播放器。", "不要让关键信息只存在于音频中。"],
        "good_example": "<audio controls src=\"live.mp3\"></audio><a href=\"live-transcript.html\">查看实时文字</a>",
        "bad_example": "<audio controls src=\"live.mp3\"></audio>",
    },
    "1.3.6": {
        "name_zh": "识别目的",
        "applies_to": ["icon", "button", "control", "landmark"],
        "keywords": ["目的", "图标目的", "控件目的", "identify purpose", "purpose", "icon"],
        "rule": "界面组件、图标和区域的目的应能被程序化识别。",
        "generation_constraints": ["对图标按钮和自定义控件提供稳定的可访问名称。", "使用语义元素和标准 ARIA 表达区域与控件目的。", "不要只用视觉图标表达功能。"],
        "good_example": "<button type=\"button\" aria-label=\"打开购物车\"><svg aria-hidden=\"true\"></svg></button>",
        "bad_example": "<div onclick=\"cart()\"><svg></svg></div>",
    },
    "1.4.6": {
        "name_zh": "增强对比度",
        "applies_to": ["text", "button", "link", "form"],
        "keywords": ["增强对比度", "颜色对比", "contrast enhanced", "contrast"],
        "rule": "文本对比度应达到更高的 AAA 标准。",
        "generation_constraints": ["普通文本对比度尽量达到 7:1。", "大文本对比度尽量达到 4.5:1。", "不要把浅色文字放在浅色背景上。"],
        "good_example": "<p style=\"color:#111;background:#fff\">重要说明</p>",
        "bad_example": "<p style=\"color:#aaa;background:#fff\">重要说明</p>",
    },
    "1.4.7": {
        "name_zh": "低背景音或无背景音",
        "applies_to": ["audio", "media"],
        "keywords": ["背景音", "音频", "background audio", "audio"],
        "rule": "语音音频中的背景声音应足够低、可关闭或不存在。",
        "generation_constraints": ["提供无背景音或低背景音版本。", "提供关闭背景音的控制。", "不要让背景音乐盖过语音内容。"],
        "good_example": "<button type=\"button\">关闭背景音乐</button>",
        "bad_example": "<audio autoplay src=\"speech-with-loud-music.mp3\"></audio>",
    },
    "1.4.8": {
        "name_zh": "视觉呈现",
        "applies_to": ["text", "article", "reading"],
        "keywords": ["视觉呈现", "行宽", "行距", "阅读", "visual presentation", "reading"],
        "rule": "大段文本应支持用户调整前景/背景、行宽、对齐和间距。",
        "generation_constraints": ["避免强制两端对齐的大段文本。", "正文行宽不要过长。", "允许用户切换高对比或舒适阅读样式。", "文本容器应能适应行距和字号变化。"],
        "good_example": "<main class=\"article\"><p>文章正文...</p><button type=\"button\">切换阅读模式</button></main>",
        "bad_example": "<p style=\"width:1200px;text-align:justify;line-height:1\">文章正文...</p>",
    },
    "1.4.9": {
        "name_zh": "文字图片（无例外）",
        "applies_to": ["image", "text", "logo"],
        "keywords": ["文字图片", "图片文字", "images of text"],
        "rule": "除纯装饰或必要情况外，不应使用文字图片。",
        "generation_constraints": ["优先使用真实文本和 CSS。", "不要把按钮文字、标题或正文做成图片。", "必要的文字图片应提供等价文本。"],
        "good_example": "<h1>年度报告</h1>",
        "bad_example": "<img src=\"title.png\" alt=\"年度报告\">",
    },
    "2.1.3": {
        "name_zh": "键盘（无例外）",
        "applies_to": ["keyboard", "widget", "canvas", "drag"],
        "keywords": ["键盘无例外", "键盘", "keyboard no exception"],
        "rule": "所有功能都应能通过键盘完成，不保留路径输入例外。",
        "generation_constraints": ["自定义组件必须提供完整键盘操作。", "拖拽、绘制、滑动等功能应提供键盘替代。", "不要让关键流程依赖鼠标轨迹。"],
        "good_example": "<button type=\"button\">上移</button><button type=\"button\">下移</button>",
        "bad_example": "<canvas onmousemove=\"draw(event)\"></canvas>",
    },
    "2.2.3": {
        "name_zh": "无时间限制",
        "applies_to": ["session", "form", "quiz", "checkout"],
        "keywords": ["无时间限制", "超时", "时间", "no timing", "timeout"],
        "rule": "内容和交互不应依赖时间限制。",
        "generation_constraints": ["避免给表单、测验或流程设置不可调整时间限制。", "如存在保存或安全需求，应提供保存草稿和继续机制。", "不要因为超时丢失用户输入。"],
        "good_example": "<button type=\"button\">保存草稿</button>",
        "bad_example": "<p>请在 60 秒内完成，否则清空表单。</p>",
    },
    "2.2.4": {
        "name_zh": "中断",
        "applies_to": ["modal", "toast", "notification"],
        "keywords": ["中断", "通知", "弹窗", "interruptions", "notification"],
        "rule": "中断应可推迟或关闭，紧急情况除外。",
        "generation_constraints": ["非紧急弹窗和通知应允许关闭、稍后提醒或静音。", "不要在用户输入时突然打断焦点。", "重要中断应有清楚文本说明。"],
        "good_example": "<button type=\"button\">稍后提醒</button><button type=\"button\">关闭通知</button>",
        "bad_example": "<div role=\"alertdialog\">广告</div>",
    },
    "2.2.5": {
        "name_zh": "重新认证",
        "applies_to": ["session", "authentication", "form"],
        "keywords": ["重新认证", "登录过期", "session", "reauthentication"],
        "rule": "重新认证后，用户应能继续之前的数据和流程。",
        "generation_constraints": ["会话过期重新登录后应恢复用户输入和当前位置。", "在超时前保存草稿。", "不要在重新认证后清空流程数据。"],
        "good_example": "<p role=\"status\">登录已恢复，表单内容已保留。</p>",
        "bad_example": "<p>登录过期，请重新填写所有内容。</p>",
    },
    "2.2.6": {
        "name_zh": "超时",
        "applies_to": ["session", "timeout", "form"],
        "keywords": ["超时", "数据丢失", "timeout", "session"],
        "rule": "用户应被告知可能导致数据丢失的非活动超时。",
        "generation_constraints": ["在会话或表单超时前明确提示用户。", "说明超时后哪些数据会丢失。", "提供延长、保存或恢复机制。"],
        "good_example": "<div role=\"alert\">会话将在 2 分钟后过期。<button>延长时间</button></div>",
        "bad_example": "<script>setTimeout(()=>location.reload(),60000)</script>",
    },
    "2.3.2": {
        "name_zh": "三次闪烁",
        "applies_to": ["animation", "video", "game"],
        "keywords": ["闪烁", "动画", "three flashes", "flashing"],
        "rule": "网页内容不应每秒闪烁超过三次。",
        "generation_constraints": ["避免快速闪烁动画。", "视频或动效应通过闪烁风险检查。", "提供关闭动画的控制。"],
        "good_example": "<button type=\"button\">关闭动画</button>",
        "bad_example": "<div class=\"flash\">警告</div>",
    },
    "2.3.3": {
        "name_zh": "交互触发的动画",
        "applies_to": ["animation", "transition", "motion"],
        "keywords": ["交互动画", "减少动态效果", "animation from interactions", "motion"],
        "rule": "交互触发的非必要动画应可禁用。",
        "generation_constraints": ["尊重 prefers-reduced-motion。", "提供关闭非必要动效的设置。", "不要让页面切换和控件反馈依赖强烈动画。"],
        "good_example": "@media (prefers-reduced-motion: reduce) { * { animation: none; transition: none; } }",
        "bad_example": ".panel { animation: spin 1s infinite; }",
    },
    "2.4.8": {
        "name_zh": "位置",
        "applies_to": ["navigation", "breadcrumb", "page"],
        "keywords": ["当前位置", "面包屑", "location", "breadcrumb"],
        "rule": "应提供用户在一组网页中的当前位置。",
        "generation_constraints": ["使用面包屑、当前导航状态或页面层级说明当前位置。", "当前项可使用 aria-current。", "不要只靠视觉高亮表达当前位置。"],
        "good_example": "<nav aria-label=\"面包屑\"><a href=\"/\">首页</a> <span aria-current=\"page\">设置</span></nav>",
        "bad_example": "<div class=\"active\">设置</div>",
    },
    "2.4.9": {
        "name_zh": "链接目的（仅链接）",
        "applies_to": ["link", "navigation", "card"],
        "keywords": ["链接目的", "链接文本", "link purpose"],
        "rule": "仅从链接文本本身就应能理解链接目的。",
        "generation_constraints": ["链接文本应自描述。", "避免多个链接都叫“更多”“点击这里”。", "卡片链接应包含对象名称。"],
        "good_example": "<a href=\"/orders/42\">查看订单 42 详情</a>",
        "bad_example": "<a href=\"/orders/42\">更多</a>",
    },
    "2.4.10": {
        "name_zh": "章节标题",
        "applies_to": ["heading", "article", "form", "page"],
        "keywords": ["章节标题", "标题", "section headings", "heading"],
        "rule": "内容章节应使用标题组织。",
        "generation_constraints": ["长页面、表单和设置页应使用清晰 heading 分区。", "标题文本应说明章节目的。", "不要只用加粗 div 充当标题。"],
        "good_example": "<section><h2>通知设置</h2></section>",
        "bad_example": "<div class=\"section-title\">通知设置</div>",
    },
    "2.4.12": {
        "name_zh": "焦点不被遮挡（增强）",
        "applies_to": ["focus", "sticky header", "modal"],
        "keywords": ["焦点遮挡", "固定头部", "focus not obscured"],
        "rule": "获得键盘焦点的组件不应被作者创建的内容遮挡。",
        "generation_constraints": ["处理 sticky header、cookie banner、浮层遮挡焦点的问题。", "滚动定位时预留 scroll-margin。", "不要让固定元素盖住当前焦点控件。"],
        "good_example": ":focus-visible { outline: 3px solid #005fcc; scroll-margin-block: 5rem; }",
        "bad_example": ".header{position:fixed;top:0;height:80px}",
    },
    "2.4.13": {
        "name_zh": "焦点外观",
        "applies_to": ["focus", "button", "link", "form"],
        "keywords": ["焦点外观", "焦点样式", "focus appearance"],
        "rule": "键盘焦点指示器应具有足够尺寸和对比度。",
        "generation_constraints": ["提供明显的 :focus-visible 样式。", "焦点指示器面积和对比度应足够。", "不要移除 outline 后只用轻微颜色变化替代。"],
        "good_example": ":focus-visible { outline: 3px solid #005fcc; outline-offset: 3px; }",
        "bad_example": ":focus { outline: none; color: #777; }",
    },
    "2.5.5": {
        "name_zh": "目标大小（增强）",
        "applies_to": ["button", "link", "touch", "target"],
        "keywords": ["目标大小", "触控", "target size", "touch"],
        "rule": "可点击目标应达到更大的 AAA 尺寸要求。",
        "generation_constraints": ["主要按钮和链接目标尽量达到 44x44 CSS 像素。", "相邻触控目标应保持足够间距。", "不要使用难以点击的小图标按钮。"],
        "good_example": "<button style=\"min-width:44px;min-height:44px\">保存</button>",
        "bad_example": "<button style=\"width:18px;height:18px\">x</button>",
    },
    "2.5.6": {
        "name_zh": "并发输入机制",
        "applies_to": ["touch", "keyboard", "mouse", "input"],
        "keywords": ["输入方式", "触控", "鼠标", "键盘", "concurrent input"],
        "rule": "内容不应限制用户使用可用的输入方式。",
        "generation_constraints": ["不要禁用键盘、鼠标、触控或辅助技术输入。", "响应式交互应同时支持点击、键盘和触控。", "不要假设用户只有一种输入设备。"],
        "good_example": "<button type=\"button\">打开菜单</button>",
        "bad_example": "<div ontouchstart=\"openMenu()\">菜单</div>",
    },
    "3.1.3": {
        "name_zh": "不常见词",
        "applies_to": ["content", "help", "glossary"],
        "keywords": ["不常见词", "术语", "词汇表", "unusual words", "glossary"],
        "rule": "不常见词、术语和习语应提供解释。",
        "generation_constraints": ["为专业术语提供解释、词汇表或内联说明。", "首次出现缩略或生僻术语时给出说明。", "帮助页面应链接到术语表。"],
        "good_example": "<dfn>ARIA</dfn><span>可访问富互联网应用规范。</span>",
        "bad_example": "<p>请配置复杂的 ARIA activedescendant。</p>",
    },
    "3.1.4": {
        "name_zh": "缩写",
        "applies_to": ["content", "abbr", "help"],
        "keywords": ["缩写", "abbr", "abbreviation"],
        "rule": "缩写应提供展开形式或解释。",
        "generation_constraints": ["首次出现缩写时使用 abbr title 或文本解释。", "不要假设所有用户理解缩写。", "重要流程中的缩写应避免歧义。"],
        "good_example": "<abbr title=\"Web Content Accessibility Guidelines\">WCAG</abbr>",
        "bad_example": "<span>WCAG</span>",
    },
    "3.1.5": {
        "name_zh": "阅读水平",
        "applies_to": ["content", "help", "article"],
        "keywords": ["阅读水平", "易读", "reading level", "plain language"],
        "rule": "复杂文本应提供更易读的补充内容。",
        "generation_constraints": ["用户说明和错误信息使用简明语言。", "复杂政策或帮助内容提供摘要。", "避免不必要的长句和术语。"],
        "good_example": "<p>简单说明：密码至少 12 位。</p>",
        "bad_example": "<p>凭证复杂度参数不符合既定认证策略。</p>",
    },
    "3.1.6": {
        "name_zh": "发音",
        "applies_to": ["content", "glossary", "help"],
        "keywords": ["发音", "读音", "pronunciation"],
        "rule": "如果词语发音影响理解，应提供发音信息。",
        "generation_constraints": ["对容易误读且影响理解的术语提供发音说明。", "术语表可包含读音。", "不要让关键说明依赖不明确读音。"],
        "good_example": "<ruby>重庆<rt>Chongqing</rt></ruby>",
        "bad_example": "<span>重庆</span>",
    },
    "3.2.5": {
        "name_zh": "按请求改变",
        "applies_to": ["form", "select", "navigation", "settings"],
        "keywords": ["按请求改变", "上下文变化", "change on request"],
        "rule": "上下文变化应只在用户请求时发生，或提供关闭机制。",
        "generation_constraints": ["重大页面跳转、提交或弹窗应由明确按钮触发。", "自动跳转或自动提交应提供关闭方式。", "筛选自动更新时不应造成上下文丢失。"],
        "good_example": "<select id=\"country\"></select><button type=\"button\">应用</button>",
        "bad_example": "<select onchange=\"location.href=this.value\"></select>",
    },
    "3.3.5": {
        "name_zh": "帮助",
        "applies_to": ["form", "help", "support"],
        "keywords": ["帮助", "说明", "help", "support"],
        "rule": "应提供上下文相关帮助。",
        "generation_constraints": ["复杂表单字段应提供帮助文本或示例。", "帮助入口应位置清晰且可键盘访问。", "错误信息应链接到相关帮助。"],
        "good_example": "<label for=\"tax\">税号</label><input id=\"tax\" aria-describedby=\"tax-help\"><p id=\"tax-help\">可在发票右上角找到。</p>",
        "bad_example": "<input placeholder=\"税号\">",
    },
    "3.3.6": {
        "name_zh": "错误预防（全部）",
        "applies_to": ["form", "checkout", "delete", "submit"],
        "keywords": ["错误预防", "确认", "撤销", "error prevention"],
        "rule": "所有提交都应提供可逆、检查或确认机制。",
        "generation_constraints": ["重要提交前提供检查页面或确认对话框。", "允许用户修改输入。", "破坏性操作提供撤销或二次确认。"],
        "good_example": "<button type=\"button\">检查后提交</button>",
        "bad_example": "<button onclick=\"deleteAccount()\">删除账户</button>",
    },
    "3.3.9": {
        "name_zh": "可访问认证（增强）",
        "applies_to": ["login", "authentication", "password"],
        "keywords": ["认证", "登录", "密码", "accessible authentication"],
        "rule": "认证流程不应要求认知功能测试，且不依赖物体识别或用户提供的内容。",
        "generation_constraints": ["支持密码管理器和复制粘贴。", "提供无需记忆谜题或识别图片的认证方式。", "验证码应有可访问替代。"],
        "good_example": "<input autocomplete=\"current-password\"><button type=\"button\">使用一次性链接登录</button>",
        "bad_example": "<p>请选择所有包含自行车的图片才能登录。</p>",
    },
}


def strip_tags(fragment):
    fragment = re.sub(r"<script[\s\S]*?</script>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<style[\s\S]*?</style>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<div class=\"header-wrapper\">[\s\S]*?</div>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<div class=\"doclinks\">[\s\S]*?</div>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<p class=\"conformance-level\">[\s\S]*?</p>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"</(p|li|dt|dd|blockquote|div|h[1-6])>", "\n", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<dt[^>]*>", "\n", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<dd[^>]*>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<li[^>]*>", "\n- ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(fragment)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_official_success_criteria():
    document = urlopen(WCAG_URL, timeout=30).read().decode("utf-8", "ignore")
    items = []
    pattern = re.compile(r"<section id=\"([^\"]+)\" class=\"guideline\">([\s\S]*?)</section>", re.IGNORECASE)
    for match in pattern.finditer(document):
        slug, body = match.group(1), match.group(2)
        heading = re.search(r"<h[34][^>]*>([\s\S]*?)</h[34]>", body, re.IGNORECASE)
        level = re.search(r"Level\s+(A{1,3})", body)
        if not heading or not level:
            continue
        heading_text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", heading.group(1)))).strip()
        name_match = re.match(r"Success Criterion\s+(\d+\.\d+\.\d+)\s+(.+)", heading_text)
        if not name_match:
            continue
        rule_id, name = name_match.group(1), name_match.group(2)
        if rule_id == "4.1.1":
            continue
        items.append({
            "id": rule_id,
            "name": name,
            "level": level.group(1),
            "slug": slug,
            "official_text_en": strip_tags(body),
        })
    return items


def sort_key(rule):
    return tuple(int(part) for part in rule["id"].split("."))


def make_examples(data):
    good = data.get("good_example", "<button type=\"button\">可访问控件</button>")
    bad = data.get("bad_example", "<div onclick=\"doThing()\">控件</div>")
    return (
        [{"title": "正确示例", "code": good, "why": "该示例将规则要求落实到可访问的 HTML/CSS/JS 结构中。"}],
        [{"title": "错误示例", "code": bad, "why": "该示例缺少必要的语义、文本说明、键盘支持或状态反馈。"}],
    )


def make_rule(item):
    data = AAA_DATA.get(item["id"], {})
    constraints = data.get("generation_constraints", [f"生成代码时应满足 WCAG {item['id']} {item['name']}。"])
    good_examples, bad_examples = make_examples(data)
    return {
        "id": item["id"],
        "name": item["name"],
        "name_zh": data.get("name_zh", item["name"]),
        "level": item["level"],
        "principle": PRINCIPLES[item["id"].split(".")[0]],
        "source": {
            "standard": "WCAG 2.2",
            "standard_url": f"{WCAG_URL}#{item['slug']}",
            "understanding_url": f"{UNDERSTANDING_BASE}{item['slug']}.html",
            "techniques_urls": [],
            "apg_urls": [],
        },
        "applies_to": data.get("applies_to", ["web content"]),
        "keywords": data.get("keywords", [item["name"].lower()]),
        "intent": f"帮助用户在使用与 {item['name']} 相关的内容时获得更高等级的无障碍体验。",
        "rule": data.get("rule", f"应满足 WCAG {item['id']} {item['name']} 的要求。"),
        "generation_constraints": constraints,
        "code_constraints": constraints,
        "good_examples": good_examples,
        "bad_examples": bad_examples,
        "detection": {
            "static_check": True,
            "axe_or_pa11y": True,
            "manual_check": True,
            "test_steps": ["使用自动检测工具检查可检测问题。", "使用键盘完成主要交互流程。", "必要时使用屏幕阅读器确认名称、角色、状态和提示信息。"],
        },
        "repair_suggestions": constraints,
        "prompt_snippet": f"生成代码时优先满足 WCAG {item['id']} {item['name']}：{data.get('rule', item['name'])}",
        "bad_example": bad_examples[0]["code"],
        "good_example": good_examples[0]["code"],
        "official_text_en": item["official_text_en"],
        "official_text_source_url": f"{WCAG_URL}#{item['slug']}",
    }


def main():
    existing_rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    official_items = parse_official_success_criteria()
    official_by_id = {item["id"]: item for item in official_items}
    rules_by_id = {rule["id"]: rule for rule in existing_rules}

    added = []
    updated = []
    for item in official_items:
        if item["id"] in rules_by_id:
            rule = rules_by_id[item["id"]]
            rule["name"] = item["name"]
            rule["level"] = item["level"]
            rule["principle"] = PRINCIPLES[item["id"].split(".")[0]]
            rule.setdefault("source", {})
            rule["source"]["standard"] = "WCAG 2.2"
            rule["source"]["standard_url"] = f"{WCAG_URL}#{item['slug']}"
            rule["source"]["understanding_url"] = f"{UNDERSTANDING_BASE}{item['slug']}.html"
            rule["official_text_en"] = item["official_text_en"]
            rule["official_text_source_url"] = f"{WCAG_URL}#{item['slug']}"
            updated.append(item["id"])
        else:
            rules_by_id[item["id"]] = make_rule(item)
            added.append(item["id"])

    rules = sorted(rules_by_id.values(), key=sort_key)
    inventory = [
        {
            "id": item["id"],
            "name": item["name"],
            "level": item["level"],
            "code_related": item["id"] not in {"3.1.3", "3.1.4", "3.1.5", "3.1.6"},
        }
        for item in sorted(official_items, key=sort_key)
        if item["id"] in official_by_id
    ]

    RULES_PATH.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    INVENTORY_PATH.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated {len(updated)} existing WCAG rules")
    print(f"added {len(added)} missing WCAG rules: {', '.join(added) if added else 'none'}")
    print(f"wrote {len(rules)} rules to {RULES_PATH}")
    print(f"wrote {len(inventory)} inventory items to {INVENTORY_PATH}")


if __name__ == "__main__":
    main()
