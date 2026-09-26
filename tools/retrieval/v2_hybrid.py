"""Dependency-light V2 retrieval prototype with explicit dense-backend support."""
import hashlib
import math
import re
from collections import Counter
from urllib.parse import urlparse


WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_./:-]*|[0-9]+|[\u4e00-\u9fff]+")
ISSUE_CODE_RE = re.compile(r"ANDROID_XML_[A-Z0-9_]+")
ISSUE_CODE_PARENTS = {
    "ANDROID_XML_IMAGE_BUTTON_MISSING_ACCESSIBLE_NAME": {
        "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
    },
    "ANDROID_XML_BUTTON_MISSING_ACCESSIBLE_NAME": {
        "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
    },
    "ANDROID_XML_INTERACTIVE_IMAGE_MISSING_ACCESSIBLE_NAME": {
        "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
    },
    "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL": {
        "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
    },
    "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME": {
        "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
    },
    "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY": {
        "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE",
    },
}
ISSUE_DOCUMENT_ROUTES = {
    "ANDROID_XML_MISSING_ACCESSIBLE_NAME": (
        "android.fixmap.content-labeling",
        "android.rule.content-labels",
    ),
    "ANDROID_XML_IMAGE_BUTTON_MISSING_ACCESSIBLE_NAME": (
        "android.fixmap.content-labeling",
        "android.rule.content-labels",
    ),
    "ANDROID_XML_BUTTON_MISSING_ACCESSIBLE_NAME": (
        "android.fixmap.content-labeling",
        "android.rule.content-labels",
    ),
    "ANDROID_XML_INTERACTIVE_IMAGE_MISSING_ACCESSIBLE_NAME": (
        "android.fixmap.content-labeling",
        "android.rule.content-labels",
    ),
    "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME": (
        "android.fixmap.content-labeling",
        "android.rule.content-labels",
    ),
    "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT": (
        "android.rule.forms-errors",
        "android.fixcase.textfield-placeholder-only",
        "android.rule.content-labels",
    ),
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT": (
        "android.fixcase.xml-format-example-only-hint",
        "android.rule.forms-errors",
        "android.rule.content-labels",
    ),
    "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL": (
        "android.pattern.settings-controls",
        "android.rule.content-labels",
        "android.rule.forms-errors",
    ),
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE": (
        "android.fixcase.xml-standard-control-focusable-false",
        "android.rule.focus-navigation",
    ),
    "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY": (
        "android.rule.focus-navigation",
        "android.fixmap.implementation-focus-order",
    ),
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING": (
        "android.fixcase.xml-email-inputtype-missing",
        "android.rule.forms-errors",
    ),
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING": (
        "android.fixcase.xml-password-inputtype-missing",
        "android.rule.forms-errors",
    ),
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING": (
        "android.fixcase.xml-phone-inputtype-missing",
        "android.rule.forms-errors",
    ),
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING": (
        "android.fixcase.xml-number-inputtype-missing",
        "android.rule.forms-errors",
    ),
}
ISSUE_DOCUMENT_EXCLUSIONS = {
    "ANDROID_XML_MISSING_ACCESSIBLE_NAME": {
        "android.fixmap.clickable-view-accessibility",
    },
    "ANDROID_XML_IMAGE_BUTTON_MISSING_ACCESSIBLE_NAME": {
        "android.fixmap.clickable-view-accessibility",
    },
    "ANDROID_XML_BUTTON_MISSING_ACCESSIBLE_NAME": {
        "android.fixmap.clickable-view-accessibility",
    },
    "ANDROID_XML_INTERACTIVE_IMAGE_MISSING_ACCESSIBLE_NAME": {
        "android.fixmap.clickable-view-accessibility",
    },
    "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME": {
        "android.fixmap.clickable-view-accessibility",
        "android.rule.custom-views",
    },
    "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL": {
        "android.fixmap.clickable-view-accessibility",
    },
}


def tokenize(value):
    tokens = []
    for match in WORD_RE.findall(str(value).lower()):
        if any("\u4e00" <= char <= "\u9fff" for char in match):
            tokens.extend(match)
            tokens.extend(
                match[index:index + 2]
                for index in range(max(len(match) - 1, 0))
            )
        else:
            tokens.append(match)
            parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", match).split()
            tokens.extend(part.lower() for part in parts if part.lower() != match)
    return tokens


def direct_document_ids(issue):
    code = str(issue.get("code", "")).upper()
    ordered = [
        *ISSUE_DOCUMENT_ROUTES.get(code, ()),
        *issue.get("related_docs", ()),
    ]
    return list(dict.fromkeys(doc_id for doc_id in ordered if doc_id))


class HashedSubwordVectorBackend:
    """Deterministic local vector similarity without external model downloads."""

    backend_id = "hashed_subword_vector_v1"

    def __init__(self, dimensions=1024):
        if dimensions < 64:
            raise ValueError("Hashed vector dimensions must be at least 64")
        self.dimensions = dimensions

    def features(self, value):
        features = []
        for token in tokenize(value):
            normalized = token.casefold()
            if len(normalized) < 2:
                continue
            features.append(f"w:{normalized}")
            compact = re.sub(r"[^a-z0-9]", "", normalized)
            if 4 <= len(compact) <= 40:
                features.extend(
                    f"c3:{compact[index:index + 3]}"
                    for index in range(len(compact) - 2)
                )
        return features

    def vector(self, value):
        vector = [0.0] * self.dimensions
        for feature, count in Counter(self.features(value)).items():
            digest = hashlib.blake2b(
                feature.encode("utf-8"), digest_size=8
            ).digest()
            number = int.from_bytes(digest, "big")
            index = number % self.dimensions
            sign = -1.0 if number & 1 else 1.0
            vector[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    def score(self, query, texts):
        query_vector = self.vector(query)
        return [
            max(
                sum(left * right for left, right in zip(
                    query_vector,
                    self.vector(text),
                )),
                0.0,
            )
            for text in texts
        ]


def document_text(document):
    source = document.get("source", {})
    content = document.get("content", {})
    tags = document.get("tags", {})
    fields = [
        document.get("doc_id", ""),
        document.get("doc_type", ""),
        source.get("title_en", ""),
        source.get("title_zh", ""),
        content.get("summary_en", ""),
        content.get("summary_zh", ""),
        " ".join(content.get("requirements_en", [])),
        " ".join(content.get("requirements_zh", [])),
        " ".join(tags.get("keywords_en", [])),
        " ".join(tags.get("keywords_zh", [])),
        " ".join(tags.get("applies_to", [])),
        " ".join(tags.get("issue_codes", [])),
        document.get("retrieval", {}).get("search_text_mixed", ""),
    ]
    return " ".join(str(value) for value in fields if value)


def infer_metadata(document):
    doc_id = document.get("doc_id", "").lower()
    text = document_text(document).lower()
    source = document.get("source", {})
    urls = [
        source.get("understanding_url", ""),
        source.get("standard_url", ""),
    ]
    domains = {
        urlparse(url).netloc.lower()
        for url in urls
        if isinstance(url, str) and url.startswith(("http://", "https://"))
    }
    platforms = set()
    if doc_id.startswith("android.") or "android" in text or "talkback" in text:
        platforms.add("android")
    if doc_id.startswith("wcag"):
        platforms.add("cross_platform")
    if any(term in text for term in ("aria", "html", "dom", "web page")):
        platforms.add("web")
    if not platforms:
        platforms.add("unspecified")

    frameworks = set()
    if "compose" in text:
        frameworks.add("compose")
    if any(term in text for term in ("android xml", "android view", "edittext", "imageview")):
        frameworks.add("android_views")
    if any(term in text for term in ("aria", "html", "dom")):
        frameworks.add("web")
    if doc_id.startswith("wcag"):
        frameworks.add("cross_platform")
    if not frameworks:
        frameworks.add("unspecified")

    if domains.intersection({"developer.android.com", "developer.android.google.cn"}):
        authority = "official_android"
    elif domains.intersection({"w3.org", "www.w3.org"}):
        authority = "official_w3c"
    elif urls:
        authority = "external_or_local"
    else:
        authority = "local"
    return {
        "platforms": sorted(platforms),
        "frameworks": sorted(frameworks),
        "source_authority": authority,
    }


def eligible_for_android_xml(document):
    metadata = infer_metadata(document)
    platforms = set(metadata["platforms"])
    frameworks = set(metadata["frameworks"])
    if "android" not in platforms and "cross_platform" not in platforms:
        return False
    if frameworks == {"compose"}:
        return False
    if "web" in frameworks and not frameworks.intersection(
        {"android_views", "cross_platform"}
    ):
        return False
    return True


def issue_codes(value):
    return set(ISSUE_CODE_RE.findall(str(value).upper()))


def issue_code_family(code):
    normalized = str(code).upper()
    return {normalized, *ISSUE_CODE_PARENTS.get(normalized, set())}


def eligible_for_issue_query(document, query):
    query_codes = set().union(
        *(issue_code_family(code) for code in issue_codes(query))
    ) if issue_codes(query) else set()
    document_codes = {
        str(code).upper()
        for code in document.get("tags", {}).get("issue_codes", [])
        if code
    }
    return not query_codes or not document_codes or bool(
        query_codes.intersection(document_codes)
    )


def eligible_repair_candidate(document, query):
    if not eligible_for_android_xml(document):
        return False
    if not eligible_for_issue_query(document, query):
        return False
    doc_id = str(document.get("doc_id", ""))
    if doc_id.startswith("android.eval."):
        return False
    metadata = infer_metadata(document)
    if "android" not in metadata["platforms"]:
        return False
    return True


def repair_candidate_boost(document, query):
    doc_id = str(document.get("doc_id", ""))
    metadata = infer_metadata(document)
    query_families = set().union(
        *(issue_code_family(code) for code in issue_codes(query))
    ) if issue_codes(query) else set()
    document_codes = {
        str(code).upper()
        for code in document.get("tags", {}).get("issue_codes", [])
        if code
    }
    boost = 0.0
    routed_ids = {
        doc_id
        for code in issue_codes(query)
        for doc_id in ISSUE_DOCUMENT_ROUTES.get(code, ())
    }
    if doc_id in routed_ids:
        boost += 0.6
    if query_families & document_codes:
        boost += 0.5
    if doc_id.startswith(("android.fixcase.", "android.fixmap.")):
        boost += 0.25
    elif doc_id.startswith("android.rule."):
        boost += 0.15
    if metadata["source_authority"] == "official_android":
        boost += 0.1
    if "android_views" in metadata["frameworks"]:
        boost += 0.1
    return boost


class BM25Index:
    def __init__(self, documents, k1=1.5, b=0.75):
        self.documents = list(documents)
        self.k1 = k1
        self.b = b
        self.tokens = [tokenize(document_text(document)) for document in self.documents]
        self.lengths = [len(tokens) for tokens in self.tokens]
        self.average_length = (
            sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        )
        self.term_frequencies = [Counter(tokens) for tokens in self.tokens]
        document_frequencies = Counter()
        for tokens in self.tokens:
            document_frequencies.update(set(tokens))
        count = len(self.documents)
        self.idf = {
            token: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in document_frequencies.items()
        }

    def scores(self, query):
        query_tokens = tokenize(query)
        scores = []
        for frequencies, length in zip(self.term_frequencies, self.lengths):
            score = 0.0
            for token in query_tokens:
                frequency = frequencies.get(token, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1 - self.b
                    + self.b * length / (self.average_length or 1.0)
                )
                score += self.idf.get(token, 0.0) * (
                    frequency * (self.k1 + 1) / denominator
                )
            scores.append(score)
        return scores


def normalize_scores(values):
    if not values:
        return []
    maximum = max(values)
    if maximum <= 0:
        return [0.0 for _ in values]
    return [value / maximum for value in values]


def retrieve(
    query,
    documents,
    related_doc_ids=(),
    final_limit=3,
    direct_limit=2,
    candidate_limit=20,
    dense_backend=None,
    lexical_weight=0.65,
    excluded_doc_ids=(),
):
    if final_limit < 1 or direct_limit < 0 or candidate_limit < final_limit:
        raise ValueError("Invalid V2 retrieval limits")
    by_id = {document.get("doc_id"): document for document in documents}
    excluded_doc_ids = set(excluded_doc_ids)
    results = []
    seen = set()
    for doc_id in list(related_doc_ids)[:direct_limit]:
        document = by_id.get(doc_id)
        if not document or doc_id in seen or doc_id in excluded_doc_ids:
            continue
        seen.add(doc_id)
        results.append({
            "document": document,
            "doc_id": doc_id,
            "reason": "direct_issue_mapping",
            "lexical_score": None,
            "dense_score": None,
            "hybrid_score": 1.0,
            "metadata": infer_metadata(document),
        })
        if len(results) >= final_limit:
            return results

    candidates = [
        document
        for document in documents
        if document.get("doc_id") not in seen
        and document.get("doc_id") not in excluded_doc_ids
        and eligible_repair_candidate(document, query)
    ]
    index = BM25Index(candidates)
    lexical_raw = index.scores(query)
    lexical = normalize_scores(lexical_raw)
    if dense_backend is None:
        dense = [0.0 for _ in candidates]
        dense_available = False
    else:
        dense_raw = dense_backend.score(query, [document_text(item) for item in candidates])
        if len(dense_raw) != len(candidates):
            raise ValueError("Dense backend returned an invalid score count")
        dense = normalize_scores([float(value) for value in dense_raw])
        dense_available = True
    scored = []
    dense_weight = 1.0 - lexical_weight if dense_available else 0.0
    effective_lexical_weight = lexical_weight if dense_available else 1.0
    for document, lexical_score, dense_score in zip(candidates, lexical, dense):
        hybrid = (
            effective_lexical_weight * lexical_score
            + dense_weight * dense_score
        )
        hybrid *= 1.0 + repair_candidate_boost(document, query)
        if hybrid <= 0:
            continue
        scored.append((hybrid, lexical_score, dense_score, document))
    scored.sort(key=lambda item: (-item[0], item[3].get("doc_id", "")))
    for hybrid, lexical_score, dense_score, document in scored[:candidate_limit]:
        doc_id = document.get("doc_id")
        if doc_id in seen:
            continue
        seen.add(doc_id)
        results.append({
            "document": document,
            "doc_id": doc_id,
            "reason": "hybrid" if dense_available else "metadata_filtered_bm25",
            "lexical_score": lexical_score,
            "dense_score": dense_score if dense_available else None,
            "hybrid_score": hybrid,
            "metadata": infer_metadata(document),
        })
        if len(results) >= final_limit:
            break
    return results


def default_issue_query(issue):
    parts = [
        "Android XML accessibility repair",
        issue.get("code", ""),
        issue.get("component", "") or issue.get("element", ""),
        issue.get("message", ""),
        issue.get("repair_query", ""),
    ]
    return " ".join(str(part) for part in parts if part)


def retrieve_for_issues(
    issues,
    documents,
    per_issue_limit=3,
    prompt_limit=6,
    direct_limit=2,
    candidate_limit=20,
    dense_backend=None,
    lexical_weight=0.65,
    query_builder=None,
):
    """Retrieve compact evidence per issue, then deduplicate at prompt level.

    Results are merged rank-by-rank so an early issue cannot consume the entire
    prompt budget. Within the same rank, an explicitly issue-tagged document is
    preferred over general background guidance.
    """
    if per_issue_limit < 1 or prompt_limit < 1:
        raise ValueError("Invalid V2 issue or prompt retrieval limits")
    query_builder = query_builder or default_issue_query
    per_issue_results = []
    for issue_index, issue in enumerate(issues):
        issue_results = retrieve(
            query_builder(issue),
            documents,
            related_doc_ids=direct_document_ids(issue),
            final_limit=per_issue_limit,
            direct_limit=direct_limit,
            candidate_limit=candidate_limit,
            dense_backend=dense_backend,
            lexical_weight=lexical_weight,
            excluded_doc_ids=ISSUE_DOCUMENT_EXCLUSIONS.get(
                str(issue.get("code", "")).upper(),
                (),
            ),
        )
        per_issue_results.append([
            {
                **result,
                "issue_index": issue_index,
                "issue_code": issue.get("code"),
            }
            for result in issue_results
        ])

    merged = []
    seen = set()
    for rank in range(per_issue_limit):
        candidates = [
            results[rank]
            for results in per_issue_results
            if rank < len(results)
        ]
        candidates.sort(
            key=lambda result: (
                -int(
                    bool(issue_code_family(result.get("issue_code", "")) & {
                        str(code).upper()
                        for code in result["document"].get("tags", {}).get(
                            "issue_codes", []
                        )
                    })
                ),
                -float(result.get("hybrid_score") or 0.0),
                result.get("issue_index", 0),
                result.get("doc_id", ""),
            )
        )
        for result in candidates:
            doc_id = result["doc_id"]
            if doc_id in seen:
                continue
            seen.add(doc_id)
            merged.append(result)
            if len(merged) >= prompt_limit:
                return merged
    return merged
