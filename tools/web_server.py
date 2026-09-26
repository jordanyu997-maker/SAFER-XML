#!/usr/bin/env python3
"""Local web demo for Android XML accessibility checking and repair.

The server intentionally reuses the existing detector, RAG search, and repair
script instead of duplicating the project logic. It is designed as a local
prototype; put it behind authentication, quotas, and sandboxing before exposing
it publicly.
"""
import csv
import io
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
JOBS_ROOT = ROOT / "reports" / "web_jobs"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
SYSTEM_NAME = "SAFER-XML"
DETECTOR_PROFILE = "expanded_v3"
RAG_TOP_K = 2
PROMPT_CONTRACT = "v2_1"
MODEL_DEFAULTS = {
    "deepseek": "deepseek-v4-pro",
    "openai": "gpt-5.6-sol",
    "anthropic": "claude-opus-4-8",
}
API_KEY_ENVIRONMENTS = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

ISSUE_DISPLAY_COPY = {
    "ANDROID_XML_BUTTON_MISSING_ACCESSIBLE_NAME": (
        "The button does not have an accessible name.",
        "Provide accurate visible text, contentDescription, hint, or an associated label.",
    ),
    "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME": (
        "The clickable view does not have an accessible name.",
        "Provide an accurate accessible name or expose an associated visible label.",
    ),
    "ANDROID_XML_CUSTOM_VIEW_REQUIRES_ACCESSIBILITY_REVIEW": (
        "The custom view requires an accessibility review.",
        "Verify its accessible name, role, state, actions, focus behavior, and runtime semantics.",
    ),
    "ANDROID_XML_EMAIL_AUTOFILL_MISSING": (
        "The email input does not declare an autofill hint.",
        "Add the appropriate autofillHints value when autofill is applicable.",
    ),
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING": (
        "The email input does not declare email input semantics.",
        "Use an email-compatible inputType while preserving the intended behavior.",
    ),
    "ANDROID_XML_HARDCODED_ACCESSIBLE_TEXT": (
        "Accessibility text is hard-coded in the layout.",
        "Move user-facing accessibility text to a string resource.",
    ),
    "ANDROID_XML_IMAGE_BUTTON_MISSING_ACCESSIBLE_NAME": (
        "The image button does not have an accessible name.",
        "Add a concise, resource-backed contentDescription that describes the action.",
    ),
    "ANDROID_XML_IMAGE_SEMANTICS_REQUIRES_REVIEW": (
        "The image semantics cannot be determined from XML alone.",
        "Confirm whether the image is meaningful or decorative before exposing or hiding it.",
    ),
    "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT": (
        "The input does not have an effective label or hint.",
        "Add a stable hint, a TextInputLayout hint, labelFor, or another valid accessible label.",
    ),
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT": (
        "The input label or hint is too weak to identify its purpose.",
        "Use a specific, persistent label or hint that clearly describes the expected input.",
    ),
    "ANDROID_XML_INTERACTIVE_HIDDEN_BY_PARENT": (
        "An interactive element is hidden from accessibility by an ancestor.",
        "Review the ancestor accessibility settings and expose the control when it must be operable.",
    ),
    "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY": (
        "An interactive element is hidden from the accessibility tree.",
        "Remove the conflicting accessibility setting or redesign the interaction semantics.",
    ),
    "ANDROID_XML_INTERACTIVE_IMAGE_MISSING_ACCESSIBLE_NAME": (
        "The interactive image does not have an accessible name.",
        "Provide a concise, resource-backed contentDescription that describes the action.",
    ),
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE": (
        "The interactive element is not accessibility-focusable.",
        "Restore appropriate focus behavior without removing the interaction.",
    ),
    "ANDROID_XML_LABELFOR_TARGET_MISSING": (
        "The labelFor reference does not resolve to a target view.",
        "Update labelFor to reference the correct input ID.",
    ),
    "ANDROID_XML_LABELFOR_TARGET_NOT_INPUT": (
        "The labelFor reference targets a view that is not an input.",
        "Associate the label with the intended editable or selectable control.",
    ),
    "ANDROID_XML_LOW_TEXT_CONTRAST": (
        "The text may not meet the required contrast ratio.",
        "Verify resolved colors and adjust foreground or background colors as needed.",
    ),
    "ANDROID_XML_MEANINGFUL_IMAGE_MISSING_DESCRIPTION": (
        "A meaningful image does not have a text alternative.",
        "Add an accurate, resource-backed contentDescription.",
    ),
    "ANDROID_XML_MISSING_ACCESSIBLE_NAME": (
        "The interactive control does not have an accessible name.",
        "Provide an accessible name appropriate to the control and its context.",
    ),
    "ANDROID_XML_NAME_AUTOFILL_MISSING": (
        "The name input does not declare an autofill hint.",
        "Add the appropriate name-related autofillHints value when autofill is applicable.",
    ),
    "ANDROID_XML_NON_SEMANTIC_CLICKABLE": (
        "A generic container is clickable without clear control semantics.",
        "Verify its role, accessible name, keyboard or focus behavior, and runtime action.",
    ),
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING": (
        "The numeric input does not declare numeric input semantics.",
        "Use an appropriate numeric inputType while preserving the intended value format.",
    ),
    "ANDROID_XML_PARSE_ERROR": (
        "The XML file could not be parsed.",
        "Correct the XML syntax before running accessibility checks.",
    ),
    "ANDROID_XML_PASSWORD_AUTOFILL_MISSING": (
        "The password input does not declare an autofill hint.",
        "Add the appropriate password-related autofillHints value when autofill is applicable.",
    ),
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING": (
        "The password input does not declare password input semantics.",
        "Use an appropriate password inputType while preserving the intended behavior.",
    ),
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING": (
        "The phone input does not declare phone input semantics.",
        "Use a phone-compatible inputType while preserving the intended behavior.",
    ),
    "ANDROID_XML_PROGRESS_MISSING_STATUS_LABEL": (
        "The progress indicator does not expose a useful status label.",
        "Provide accessible progress or status information appropriate to the runtime state.",
    ),
    "ANDROID_XML_REPEATED_GENERIC_LABEL": (
        "Multiple controls reuse a generic accessible label.",
        "Use distinct, purpose-specific labels for controls with different actions.",
    ),
    "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL": (
        "The stateful control does not have an accessible label.",
        "Associate a visible label or provide an accurate accessible name without duplicating its state.",
    ),
    "ANDROID_XML_TOUCH_TARGET_SIZE_REQUIRES_REVIEW": (
        "The effective touch target size requires manual review.",
        "Verify the rendered target size and any runtime TouchDelegate behavior.",
    ),
    "ANDROID_XML_TOUCH_TARGET_TOO_SMALL": (
        "The interactive element may have an undersized touch target.",
        "Increase the effective touch target while preserving the visual and interaction design.",
    ),
    "ANDROID_XML_UNNAMED_FOCUSABLE_CONTAINER": (
        "A focusable container does not have an accessible name.",
        "Provide meaningful semantics or remove unnecessary focusability after review.",
    ),
}

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "retrieval"))

from tools.evaluation.android_xml_a11y_check import build_report, scan  # noqa: E402
from tools.evaluation.collect_android_xml_package import collect  # noqa: E402
from tools.android_xml_rag_prompt_contract import neutral_issue_query  # noqa: E402
from tools.retrieval.search_documents import load_documents, search  # noqa: E402
from tools.retrieval.v2_hybrid import (  # noqa: E402
    HashedSubwordVectorBackend,
    retrieve_for_issues,
)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def response_issue(issue, res_dir: Path):
    row = dict(issue)
    code = row.get("code", "")
    display_message, display_fix_hint = ISSUE_DISPLAY_COPY.get(
        code,
        (
            code.removeprefix("ANDROID_XML_").replace("_", " ").capitalize() + ".",
            "Review the affected element and apply the appropriate Android accessibility semantics.",
        ),
    )
    row["display_message"] = display_message
    row["display_fix_hint"] = display_fix_hint
    file_value = row.get("file")
    if file_value:
        try:
            row["relative_file"] = Path(file_value).resolve().relative_to(
                res_dir.resolve()
            ).as_posix()
        except ValueError:
            row["relative_file"] = Path(file_value).name
    return row


def report_for_res(res_dir: Path):
    issues = scan([res_dir], detector_profile=DETECTOR_PROFILE)
    report = build_report(issues)
    report["issues"] = [response_issue(issue, res_dir) for issue in issues]
    report["detector_profile"] = DETECTOR_PROFILE
    report["actionable_error_count"] = actionable_error_count(report)
    report["review_required_count"] = sum(
        issue.get("requires_review", False)
        or issue.get("repairability", "xml_safe") != "xml_safe"
        for issue in report["issues"]
    )
    return report


def safe_extract_zip(archive_bytes: bytes, target: Path):
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        for member in archive.infolist():
            name = member.filename
            if not name or name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"The ZIP contains an unsafe path: {name}")
            if member.file_size > MAX_UPLOAD_BYTES:
                raise ValueError(f"A file in the ZIP exceeds the size limit: {name}")
        archive.extractall(target)


def ensure_single_xml_package(job_dir: Path, xml_text: str, filename: str):
    package_dir = job_dir / "original"
    layout_dir = package_dir / "res" / "layout"
    values_dir = package_dir / "res" / "values"
    layout_dir.mkdir(parents=True, exist_ok=True)
    values_dir.mkdir(parents=True, exist_ok=True)
    name = Path(filename or "upload.xml").stem or "upload"
    safe_name = "".join(char if char.isalnum() or char == "_" else "_" for char in name)
    (layout_dir / f"{safe_name}.xml").write_text(xml_text, encoding="utf-8")
    strings = values_dir / "strings.xml"
    if not strings.exists():
        strings.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n</resources>\n',
            encoding="utf-8",
        )
    return package_dir


def ensure_zip_package(job_dir: Path, archive_bytes: bytes):
    upload_dir = job_dir / "upload"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_extract_zip(archive_bytes, upload_dir)
    package_dir = job_dir / "original"
    collect(upload_dir, package_dir, force=True)
    return package_dir


def save_upload_package(job_dir: Path, fields):
    xml_text = fields.get("xml_text", "").strip()
    filename = fields.get("filename", "upload.xml")
    upload = fields.get("file")
    if upload:
        upload_name, upload_bytes = upload
        suffix = Path(upload_name).suffix.lower()
        if suffix == ".zip":
            return ensure_zip_package(job_dir, upload_bytes)
        if suffix == ".xml":
            return ensure_single_xml_package(
                job_dir,
                upload_bytes.decode("utf-8", errors="replace"),
                upload_name,
            )
        raise ValueError("Only .xml and .zip uploads are supported.")
    if not xml_text:
        raise ValueError("Paste XML or upload an .xml/.zip file.")
    return ensure_single_xml_package(job_dir, xml_text, filename)


def summarize_documents(query: str, limit: int):
    rows = []
    for score, document in search(query, limit=limit):
        content = document.get("content", {})
        source = document.get("source", {})
        rows.append({
            "score": score,
            "doc_id": document.get("doc_id"),
            "doc_type": document.get("doc_type"),
            "title_en": source.get("title_en", ""),
            "title_zh": source.get("title_zh", ""),
            "summary_en": content.get("summary_en", ""),
            "summary_zh": content.get("summary_zh", ""),
            "requirements_en": content.get("requirements_en", [])[:4],
            "requirements_zh": content.get("requirements_zh", [])[:4],
            "applies_to": document.get("tags", {}).get("applies_to", []),
        })
    return rows


def actionable_issues_from_report(report):
    if not isinstance(report, dict):
        return []
    return [
        issue
        for issue in report.get("issues", [])
        if issue.get("severity", issue.get("type", "error")) == "error"
        and issue.get("repairability", "xml_safe") == "xml_safe"
    ]


def summarize_v2_documents(report, limit=RAG_TOP_K):
    issues = actionable_issues_from_report(report)
    if not issues:
        return []
    results = retrieve_for_issues(
        issues,
        load_documents(),
        per_issue_limit=limit,
        prompt_limit=limit,
        direct_limit=2,
        candidate_limit=20,
        dense_backend=HashedSubwordVectorBackend(),
        lexical_weight=0.65,
        query_builder=neutral_issue_query,
    )
    rows = []
    for result in results:
        document = result["document"]
        content = document.get("content", {})
        source = document.get("source", {})
        rows.append({
            "doc_id": document.get("doc_id"),
            "doc_type": document.get("doc_type"),
            "title_en": source.get("title_en", ""),
            "title_zh": source.get("title_zh", ""),
            "summary_en": content.get("summary_en", ""),
            "summary_zh": content.get("summary_zh", ""),
            "requirements_en": content.get("requirements_en", [])[:4],
            "requirements_zh": content.get("requirements_zh", [])[:4],
            "issue_code": result.get("issue_code"),
            "reason": result.get("reason"),
            "lexical_score": result.get("lexical_score"),
            "dense_score": result.get("dense_score"),
            "hybrid_score": result.get("hybrid_score"),
            "metadata": result.get("metadata", {}),
        })
    return rows


def rag_query_from_report(report):
    parts = []
    for issue in report.get("issues", []):
        if issue.get("severity", issue.get("type")) != "error":
            continue
        parts.extend([
            issue.get("code", ""),
            issue.get("component", ""),
            issue.get("message", ""),
            issue.get("repair_query", ""),
        ])
    return " ".join(part for part in parts if part).strip() or "Android XML accessibility"


def rag_display_query_from_report(report):
    parts = []
    for issue in report.get("issues", []):
        if issue.get("severity", issue.get("type")) != "error":
            continue
        parts.extend([
            issue.get("code", ""),
            issue.get("component", ""),
            issue.get("repair_query", ""),
        ])
    return " ".join(part for part in parts if part).strip() or "Android XML accessibility"


def report_for_display(report, res_dir: Path):
    if not isinstance(report, dict):
        return report
    payload = dict(report)
    payload["issues"] = [
        response_issue(issue, res_dir)
        for issue in report.get("issues", [])
    ]
    return payload


def csv_rows(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def aggregate_summary(rows):
    def number(row, key):
        try:
            value = row.get(key, "")
            return float(value) if value not in {"", None} else 0.0
        except ValueError:
            return 0.0

    apps = len(rows)
    before = sum(number(row, "before_error_count") for row in rows)
    baseline_after = sum(number(row, "baseline_after_error_count") for row in rows)
    enhanced_after = sum(number(row, "enhanced_after_error_count") for row in rows)
    baseline_success = sum(1 for row in rows if row.get("baseline_after_error_count") == "0")
    enhanced_success = sum(1 for row in rows if row.get("enhanced_after_error_count") == "0")
    return {
        "app_count": apps,
        "before_error_count": int(before),
        "baseline_after_error_count": int(baseline_after),
        "enhanced_after_error_count": int(enhanced_after),
        "baseline_success_count": baseline_success,
        "enhanced_success_count": enhanced_success,
        "baseline_repair_rate": None if before == 0 else (before - baseline_after) / before,
        "enhanced_repair_rate": None if before == 0 else (before - enhanced_after) / before,
    }


def repair_attempt_count(run_state):
    if not isinstance(run_state, dict):
        return 0
    return sum(
        len(round_state.get("attempts", []))
        for round_state in run_state.get("rounds", [])
    )


def provider_api_configured(provider):
    environment = API_KEY_ENVIRONMENTS.get(provider)
    return bool(environment and os.environ.get(environment, "").strip())


def provider_statuses():
    return {
        provider: {
            "configured": provider_api_configured(provider),
            "model": model,
            "api_key_environment": API_KEY_ENVIRONMENTS[provider],
        }
        for provider, model in MODEL_DEFAULTS.items()
    }


def actionable_error_count(report):
    return len(actionable_issues_from_report(report))


def safe_job_id(value):
    value = str(value or "").strip()
    if not value or not value.isalnum():
        raise ValueError("Invalid job_id.")
    return value


def package_zip_bytes(package_dir: Path):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(package_dir).as_posix())
    return output.getvalue()


def repair_trace_summary(run_state):
    if not isinstance(run_state, dict):
        return {
            "accepted_rounds": 0,
            "rejected_attempts": 0,
            "stop_reason": None,
            "rounds": [],
        }
    rounds = []
    for round_state in run_state.get("rounds", []):
        attempts = round_state.get("attempts", [])
        rounds.append({
            "round": round_state.get("round"),
            "before_error_count": round_state.get("before_error_count"),
            "after_error_count": round_state.get("after_error_count"),
            "repairable_issue_count": round_state.get("repairable_issue_count"),
            "deferred_issue_count": round_state.get("deferred_issue_count"),
            "attempt_count": len(attempts),
            "accepted": any(item.get("status") == "accepted" for item in attempts),
            "rejected_count": sum(item.get("status") == "rejected" for item in attempts),
        })
    return {
        "accepted_rounds": sum(item["accepted"] for item in rounds),
        "rejected_attempts": sum(item["rejected_count"] for item in rounds),
        "stop_reason": run_state.get("stop_reason") or run_state.get("status"),
        "rounds": rounds,
    }


def retrieval_traces(package_dir: Path):
    report_dir = package_dir / "reports"
    rows = []
    for path in sorted(report_dir.glob("retrieval_trace_round_*.json")):
        payload = read_json(path, {})
        rows.append({
            "round": path.stem.rsplit("_", 1)[-1],
            "contract": payload.get("retrieval_contract_version"),
            "dense_backend": payload.get("dense_backend"),
            "knowledge_document_count": payload.get("knowledge_document_count", 0),
            "documents": payload.get("knowledge_documents", []),
        })
    return rows


def parse_multipart(handler):
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        length = int(handler.headers.get("Content-Length", "0"))
        body = handler.rfile.read(length)
        if "application/json" in content_type:
            return json.loads(body.decode("utf-8") or "{}")
        parsed = parse_qs(body.decode("utf-8"))
        return {key: values[-1] for key, values in parsed.items()}

    import cgi

    form = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
        },
    )
    fields = {}
    for key in form:
        item = form[key]
        if isinstance(item, list):
            item = item[-1]
        if item.filename:
            fields[key] = (item.filename, item.file.read(MAX_UPLOAD_BYTES + 1))
            if len(fields[key][1]) > MAX_UPLOAD_BYTES:
                raise ValueError("The uploaded file exceeds 12 MB.")
        else:
            fields[key] = item.value
    return fields


class Handler(BaseHTTPRequestHandler):
    server_version = "AndroidXMLA11yWeb/0.1"

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, message, status=HTTPStatus.BAD_REQUEST):
        self.send_json({"ok": False, "error": message}, status)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.send_json({
                "ok": True,
                "system_name": SYSTEM_NAME,
                "providers": provider_statuses(),
                "repair_backend": "tools/generate_android_xml_web.py",
                "detector_backend": "tools/evaluation/android_xml_a11y_check.py",
                "rag_backend": "knowledge/rag/knowledge_documents.json",
                "detector_profile": DETECTOR_PROFILE,
                "prompt_contract": PROMPT_CONTRACT,
                "retrieval_contract": "v4_structured_hybrid",
                "rag_top_k": RAG_TOP_K,
                "knowledge_document_count": len(load_documents()),
            })
            return
        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/download"):
            self.handle_download(parsed.path)
            return
        if parsed.path == "/api/experiments/summary":
            rows = csv_rows(ROOT / "experiments/android_xml/formal_experiment_app_summary.csv")
            self.send_json({"ok": True, "aggregate": aggregate_summary(rows), "rows": rows})
            return
        if parsed.path == "/api/experiments/records":
            rows = csv_rows(ROOT / "experiments/android_xml/formal_experiment_records.csv")
            self.send_json({"ok": True, "rows": rows})
            return
        if parsed.path == "/api/jobs":
            jobs = []
            if JOBS_ROOT.exists():
                for path in sorted(JOBS_ROOT.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
                    if path.is_dir():
                        meta = read_json(path / "job.json", {})
                        if meta:
                            jobs.append(meta)
            self.send_json({"ok": True, "jobs": jobs[:50]})
            return
        self.serve_static(parsed.path)

    def handle_download(self, path):
        parts = [part for part in path.split("/") if part]
        if len(parts) != 4 or parts[:2] != ["api", "jobs"] or parts[3] != "download":
            self.send_error_json("Invalid download URL.", HTTPStatus.NOT_FOUND)
            return
        try:
            job_id = safe_job_id(parts[2])
        except ValueError as exc:
            self.send_error_json(str(exc), HTTPStatus.BAD_REQUEST)
            return
        job_dir = JOBS_ROOT / job_id
        package_dir = job_dir / "proposed"
        if not package_dir.exists():
            self.send_error_json("The repaired resource package is not available.", HTTPStatus.NOT_FOUND)
            return
        data = package_zip_bytes(package_dir)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="safer-xml-{job_id}.zip"',
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            if self.path == "/api/check":
                self.handle_check()
            elif self.path == "/api/rag":
                self.handle_rag()
            elif self.path == "/api/repair":
                self.handle_repair()
            else:
                self.send_error_json("Unknown endpoint.", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_error_json(str(exc), HTTPStatus.BAD_REQUEST)

    def serve_static(self, path):
        if path in {"", "/"}:
            path = "/index.html"
        target = (WEB_ROOT / path.lstrip("/")).resolve()
        try:
            target.relative_to(WEB_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix == ".js":
            mime = "text/javascript"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def handle_check(self):
        fields = parse_multipart(self)
        job_id = uuid.uuid4().hex[:12]
        job_dir = JOBS_ROOT / job_id
        package_dir = save_upload_package(job_dir, fields)
        res_dir = package_dir / "res"
        report = report_for_res(res_dir)
        query = rag_query_from_report(report)
        display_query = rag_display_query_from_report(report)
        documents = summarize_v2_documents(report)
        meta = {
            "job_id": job_id,
            "status": "checked",
            "package_dir": str(package_dir.relative_to(ROOT)),
            "error_count": report["error_count"],
            "warning_count": report["warning_count"],
            "info_count": report["info_count"],
            "total_issue_count": report["total_issue_count"],
            "actionable_error_count": report["actionable_error_count"],
            "review_required_count": report["review_required_count"],
            "detector_profile": DETECTOR_PROFILE,
            "rag_top_k": RAG_TOP_K,
            "prompt_contract": PROMPT_CONTRACT,
        }
        write_json(job_dir / "original" / "reports" / "android_xml_a11y_report.json", report)
        write_json(job_dir / "job.json", meta)
        self.send_json({
            "ok": True,
            "job": meta,
            "report": report,
            "rag_query": query,
            "rag_display_query": display_query,
            "documents": documents,
            "pipeline": {
                "detector_profile": DETECTOR_PROFILE,
                "repairability_gate": "severity=error AND repairability=xml_safe",
                "retrieval_contract": "v4_structured_hybrid",
                "rag_top_k": RAG_TOP_K,
                "prompt_contract": PROMPT_CONTRACT,
            },
            "files": package_files(package_dir),
        })

    def handle_rag(self):
        fields = parse_multipart(self)
        query = fields.get("query", "").strip()
        if not query:
            raise ValueError("query must not be empty.")
        limit = int(fields.get("limit", 8) or 8)
        self.send_json({"ok": True, "documents": summarize_documents(query, limit)})

    def handle_repair(self):
        fields = parse_multipart(self)
        job_id = safe_job_id(fields.get("job_id", ""))
        job_dir = JOBS_ROOT / job_id
        original = job_dir / "original"
        if not original.exists():
            raise ValueError("The requested task was not found. Run the check again.")
        proposed = job_dir / "proposed"
        provider = fields.get("provider", "deepseek")
        if provider not in MODEL_DEFAULTS:
            raise ValueError("This interface supports DeepSeek, OpenAI, and Anthropic only.")
        model = fields.get("model", MODEL_DEFAULTS[provider]) or MODEL_DEFAULTS[provider]
        original_report = read_json(
            job_dir / "original" / "reports" / "android_xml_a11y_report.json",
            {},
        )
        if (
            actionable_error_count(original_report) > 0
            and not provider_api_configured(provider)
        ):
            meta = read_json(job_dir / "job.json", {})
            meta.update({
                "status": "repair_failed",
                "repair_returncode": 1,
                "final_error_count": original_report.get("error_count"),
                "model_calls": 0,
                "model_called": False,
            })
            write_json(job_dir / "job.json", meta)
            self.send_json({
                "ok": False,
                "error": (
                    f"{API_KEY_ENVIRONMENTS[provider]} is not configured. "
                    "The current XML contains automatically repairable errors, so the selected "
                    "provider must be configured before repair can run."
                ),
                "job": meta,
                "report": original_report,
                "repair_run": None,
                "files": package_files(original),
            }, HTTPStatus.BAD_REQUEST)
            return
        max_rounds = str(min(max(int(fields.get("max_rounds", 3) or 3), 1), 3))
        max_attempts = str(
            min(max(int(fields.get("max_model_attempts", 3) or 3), 1), 3)
        )
        cmd = [
            sys.executable,
            str(ROOT / "tools" / "generate_android_xml_web.py"),
            str(original),
            str(proposed),
            "--provider",
            provider,
            "--model",
            model,
            "--max-rounds",
            max_rounds,
            "--max-model-attempts",
            max_attempts,
            "--force",
        ]
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=600,
        )
        final_report_path = proposed / "reports" / "android_xml_a11y_report.json"
        run_path = proposed / "reports" / "repair_run.json"
        final_report = read_json(final_report_path, None)
        run_state = read_json(run_path, None)
        model_calls = repair_attempt_count(run_state)
        safety_report = read_json(
            proposed / "reports" / "android_xml_repair_safety_report.json",
            [],
        )
        trace = repair_trace_summary(run_state)
        meta = read_json(job_dir / "job.json", {})
        meta.update({
            "status": "repaired" if result.returncode == 0 else "repair_failed",
            "repair_returncode": result.returncode,
            "final_error_count": final_report.get("error_count") if final_report else None,
            "model_calls": model_calls,
            "model_called": model_calls > 0,
            "provider": provider,
            "model": model,
            "stop_reason": trace["stop_reason"],
            "accepted_rounds": trace["accepted_rounds"],
            "rejected_attempts": trace["rejected_attempts"],
            "safety_finding_count": len(safety_report),
        })
        write_json(job_dir / "job.json", meta)
        self.send_json({
            "ok": result.returncode == 0,
            "job": meta,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
            "report": report_for_display(final_report, proposed / "res") if final_report else None,
            "repair_run": run_state,
            "trace": trace,
            "retrieval_traces": retrieval_traces(proposed),
            "safety_report": safety_report,
            "original_files": package_files(original),
            "files": package_files(proposed) if proposed.exists() else [],
            "download_url": (
                f"/api/jobs/{job_id}/download" if proposed.exists() else None
            ),
        }, HTTPStatus.OK if result.returncode == 0 else HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def package_files(package_dir: Path):
    res_dir = package_dir / "res"
    if not res_dir.exists():
        return []
    rows = []
    for path in sorted(res_dir.rglob("*.xml")):
        rel = path.relative_to(package_dir).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        rows.append({"path": rel, "content": text})
    return rows


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run local Android XML accessibility web demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Android XML Accessibility Web Demo: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")


if __name__ == "__main__":
    main()
