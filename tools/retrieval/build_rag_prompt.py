#!/usr/bin/env python3
import argparse

from search_documents import search


def format_document(document):
    source = document["source"]
    content = document["content"]
    requirements_en = "\n".join(f"- {item}" for item in content.get("requirements_en", [])[:5])
    requirements_zh = "\n".join(f"- {item}" for item in content.get("requirements_zh", [])[:5])
    repairs_zh = "\n".join(f"- {item}" for item in content.get("repair_suggestions_zh", [])[:3])
    official_text = content.get("official_text_en", "")
    good = content.get("good_examples", [])
    bad = content.get("bad_examples", [])
    good_text = good[0]["code"] if good else "N/A"
    bad_text = bad[0]["code"] if bad else "N/A"
    url = source.get("understanding_url") or source.get("standard_url") or "local"

    return f"""[{document['doc_type']}] {source['title_en']} / {source['title_zh']}
Source: {url}
Official WCAG text:
{official_text or "N/A"}
English summary: {content['summary_en']}
中文摘要：{content['summary_zh']}
English requirements:
{requirements_en}
中文生成约束：
{requirements_zh}
Bad example:
{bad_text}
Good example:
{good_text}
中文修复建议：
{repairs_zh}
"""


def infer_platform(user_request):
    request = user_request.lower()
    android_terms = [
        "android",
        "安卓",
        "compose",
        "kotlin",
        "xml",
        "view",
        "recyclerview",
        "lazycolumn",
        "talkback",
        "switch access",
        "accessibilitychecks",
        "espresso",
    ]
    if any(term in request for term in android_terms):
        return "android"
    return "web"


def build_prompt(user_request, limit=8):
    results = search(user_request, limit)
    docs_text = "\n\n".join(format_document(document) for _, document in results)
    if not docs_text:
        docs_text = "No relevant documents were retrieved. Still follow WCAG 2.2 AA accessibility best practices."

    platform = infer_platform(user_request)
    if platform == "android":
        role = "You are an accessibility-focused Android code generation and repair assistant."
        generation_target = (
            "Generate or repair Android Kotlin/Jetpack Compose/View/XML code as appropriate for the user request. "
            "Follow Android accessibility guidance, platform semantics, and WCAG-derived principles."
        )
        output_format = (
            "1. Complete Android code or patch-style code\n"
            "2. Android accessibility rules satisfied\n"
            "3. Manual and automated checks still recommended"
        )
    else:
        role = "You are an accessibility-focused frontend code generation assistant."
        generation_target = (
            "Generate HTML, CSS, and JavaScript that satisfies WCAG 2.2 AA by default. "
            "If AAA guidance appears, treat it as an enhancement rather than a mandatory requirement."
        )
        output_format = (
            "1. Complete code\n"
            "2. Accessibility rules satisfied\n"
            "3. Manual checks still recommended"
        )

    return f"""{role}

Use the retrieved bilingual accessibility knowledge below as authoritative context.
{generation_target}

Retrieved knowledge:

{docs_text}

User request:
{user_request}

Output format:
{output_format}
"""


def main():
    parser = argparse.ArgumentParser(description="Build a RAG prompt from bilingual knowledge documents.")
    parser.add_argument("request", help="User request, for example: 生成一个登录表单")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    print(build_prompt(args.request, args.limit))


if __name__ == "__main__":
    main()
