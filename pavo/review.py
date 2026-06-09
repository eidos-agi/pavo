from __future__ import annotations

import json
import shlex
import shutil
from html.parser import HTMLParser
from html import escape
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AnchorReviewSheetResult:
    review_sheet_path: Path
    candidate_count: int
    pending_count: int


@dataclass(frozen=True)
class AnchorReviewCorrectionsResult:
    review_sheet_path: Path
    approved_count: int
    corrections: list[str]
    cli_args: list[str]


@dataclass(frozen=True)
class AnchorReviewPageResult:
    review_sheet_path: Path
    review_page_path: Path
    candidate_count: int
    pending_count: int


@dataclass(frozen=True)
class AnchorReviewImportResult:
    review_sheet_path: Path
    imported_sheet_path: Path
    candidate_count: int
    approved_count: int
    rejected_count: int
    pending_count: int
    human_reviewed: bool


@dataclass(frozen=True)
class AnchorReviewRerunCommandResult:
    review_sheet_path: Path
    manifest_path: Path
    approved_count: int
    command: list[str]
    shell_command: str


@dataclass(frozen=True)
class AnchorReviewPageVerificationResult:
    review_sheet_path: Path
    review_page_path: Path
    passed: bool
    candidate_count: int
    audio_count: int
    approve_count: int
    reject_count: int
    pending_button_count: int
    note_count: int
    export_button_present: bool
    reset_button_present: bool
    embedded_sheet_present: bool
    import_instruction_present: bool
    rerun_instruction_present: bool
    missing: list[str]

    def as_report(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "review_sheet": str(self.review_sheet_path),
            "review_page": str(self.review_page_path),
            "candidate_count": self.candidate_count,
            "audio_count": self.audio_count,
            "approve_count": self.approve_count,
            "reject_count": self.reject_count,
            "pending_button_count": self.pending_button_count,
            "note_count": self.note_count,
            "export_button_present": self.export_button_present,
            "reset_button_present": self.reset_button_present,
            "embedded_sheet_present": self.embedded_sheet_present,
            "import_instruction_present": self.import_instruction_present,
            "rerun_instruction_present": self.rerun_instruction_present,
            "missing": self.missing,
            "next_required_proof": "human reviewer must approve or reject every clip, then import the reviewed sheet",
        }


@dataclass(frozen=True)
class AnchorReviewBundleResult:
    review_sheet_path: Path
    bundle_dir: Path
    bundled_sheet_path: Path
    review_page_path: Path
    copied_clip_count: int
    missing_clip_count: int


@dataclass(frozen=True)
class AnchorReviewGateResult:
    review_sheet_path: Path
    passed: bool
    human_reviewed: bool
    approved_count: int
    rejected_count: int
    pending_count: int
    page_ready: bool
    bundle_ready: bool
    browser_verified: bool
    rerun_command_ready: bool
    blockers: list[str]
    next_action: str

    def as_report(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "review_sheet": str(self.review_sheet_path),
            "human_reviewed": self.human_reviewed,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "pending_count": self.pending_count,
            "page_ready": self.page_ready,
            "bundle_ready": self.bundle_ready,
            "browser_verified": self.browser_verified,
            "rerun_command_ready": self.rerun_command_ready,
            "blockers": self.blockers,
            "next_action": self.next_action,
        }


def create_anchor_review_sheet(
    clip_packet_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> AnchorReviewSheetResult:
    packet_path = Path(clip_packet_path)
    packet = json.loads(packet_path.read_text())
    sheet_path = Path(out_path) if out_path else packet_path.with_name(packet_path.stem.replace("-clips", "-sheet") + ".json")
    rows = []
    for clip in packet.get("clips", []):
        rows.append(
            {
                "index": clip.get("index"),
                "status": "pending",
                "approved": False,
                "target_speaker_label": packet.get("target_speaker_label"),
                "target_speaker_name": packet.get("target_speaker_name"),
                "start": clip.get("start"),
                "end": clip.get("end"),
                "duration": clip.get("duration"),
                "text": clip.get("text"),
                "confidence": clip.get("confidence"),
                "method": clip.get("method"),
                "clip_path": clip.get("clip_path"),
                "suggested_speaker_correction": clip.get("suggested_speaker_correction"),
                "reviewer_note": "",
            }
        )
    sheet = {
        "passed": False,
        "human_reviewed": False,
        "review_packet": packet.get("review_packet"),
        "clip_packet": str(packet_path),
        "target_speaker_label": packet.get("target_speaker_label"),
        "target_speaker_name": packet.get("target_speaker_name"),
        "candidate_count": len(rows),
        "pending_count": len(rows),
        "approved_count": 0,
        "rejected_count": 0,
        "rows": rows,
        "instructions": [
            "Listen to each clip_path.",
            "Set approved true and status approved only for clean target-speaker clips.",
            "Set status rejected for wrong-speaker, overlap-heavy, noisy, or uncertain clips.",
            "Run pavo review anchors corrections <review-sheet> to export --speaker-correction flags.",
        ],
    }
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_path.write_text(json.dumps(sheet, indent=2) + "\n")
    return AnchorReviewSheetResult(
        review_sheet_path=sheet_path,
        candidate_count=len(rows),
        pending_count=len(rows),
    )


def compile_anchor_review_corrections(review_sheet_path: Path | str) -> AnchorReviewCorrectionsResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    corrections = []
    for row in sheet.get("rows", []):
        if row.get("approved") is not True or row.get("status") != "approved":
            continue
        correction = row.get("suggested_speaker_correction")
        if not correction:
            correction = _speaker_correction(row.get("start"), row.get("end"), row.get("target_speaker_label"))
        if correction:
            corrections.append(correction)
    cli_args = [arg for correction in corrections for arg in ["--speaker-correction", correction]]
    return AnchorReviewCorrectionsResult(
        review_sheet_path=sheet_path,
        approved_count=len(corrections),
        corrections=corrections,
        cli_args=cli_args,
    )


def create_anchor_review_page(
    review_sheet_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> AnchorReviewPageResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    page_path = Path(out_path) if out_path else sheet_path.with_suffix(".html")
    rows = sheet.get("rows", [])
    pending = [row for row in rows if row.get("status") == "pending"]
    cards = "\n".join(_review_card(row) for row in rows)
    sheet_json = json.dumps(sheet).replace("</", "<\\/")
    download_name_json = json.dumps(sheet_path.name)
    title = f"Pavo Anchor Review - {sheet.get('target_speaker_name') or sheet.get('target_speaker_label') or 'Speaker'}"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17211c;
      background: #f7faf4;
    }}
    header {{
      padding: 28px 32px;
      background: #0d3b2e;
      color: #f9fff7;
    }}
    main {{
      max-width: 1040px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    .meta {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      color: #d7f5dd;
    }}
    .instructions {{
      margin: 0 0 18px;
      padding: 16px;
      border: 1px solid #bfd7c5;
      background: #ffffff;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      margin: 18px 0;
    }}
    button {{
      border: 1px solid #174835;
      border-radius: 6px;
      background: #174835;
      color: #ffffff;
      padding: 8px 12px;
      font: inherit;
      cursor: pointer;
    }}
    button.secondary {{
      background: #ffffff;
      color: #174835;
    }}
    button:focus-visible,
    textarea:focus-visible {{
      outline: 3px solid #8ed39a;
      outline-offset: 2px;
    }}
    article {{
      margin: 16px 0;
      padding: 18px;
      border: 1px solid #cfdfd1;
      border-radius: 8px;
      background: #ffffff;
    }}
    .row-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
      margin-bottom: 10px;
    }}
    h2 {{
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }}
    code {{
      background: #eef4ee;
      padding: 2px 5px;
      border-radius: 4px;
    }}
    audio {{
      width: 100%;
      margin: 10px 0;
    }}
    dl {{
      display: grid;
      grid-template-columns: 160px 1fr;
      gap: 8px 12px;
      margin: 12px 0 0;
    }}
    dt {{
      font-weight: 700;
      color: #315044;
    }}
    dd {{
      margin: 0;
      overflow-wrap: anywhere;
    }}
    .status {{
      font-weight: 700;
      color: #7a4e00;
    }}
    .review-controls {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin: 12px 0;
    }}
    textarea {{
      width: 100%;
      box-sizing: border-box;
      min-height: 70px;
      margin-top: 8px;
      padding: 8px;
      border: 1px solid #bfd7c5;
      border-radius: 6px;
      font: inherit;
    }}
    @media (max-width: 700px) {{
      header {{ padding: 22px 18px; }}
      main {{ padding: 16px; }}
      dl {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <div class="meta">
      <span>{len(rows)} candidate clips</span>
      <span>{len(pending)} pending</span>
      <span>sheet: {escape(str(sheet_path))}</span>
    </div>
  </header>
  <main>
    <section class="instructions">
      Listen for clean {escape(str(sheet.get('target_speaker_label') or 'target speaker'))} anchor clips.
      Approve only clean target-speaker clips. Reject uncertain, overlapping, noisy, or wrong-speaker clips.
      Export the reviewed JSON sheet, import it with
      <code>pavo review anchors import {escape(str(sheet_path))} ~/Downloads/{escape(sheet_path.name)}</code>,
      print the corrected decompose command with
      <code>pavo review anchors rerun-command {escape(str(sheet_path))} /path/to/pavo-decompose-manifest.json</code>,
      then rerun decomposition and regenerate the Plaud proof report.
    </section>
    <section class="actions">
      <button type="button" id="export-json">Export reviewed JSON</button>
      <button type="button" class="secondary" id="reset-review">Reset page decisions</button>
      <span id="review-count">{len(pending)} pending</span>
    </section>
    {cards}
  </main>
  <script type="application/json" id="review-sheet-data">{sheet_json}</script>
  <script>
    const originalSheet = JSON.parse(document.getElementById("review-sheet-data").textContent);
    const decisions = new Map(originalSheet.rows.map((row) => [String(row.index), {{
      status: row.status || "pending",
      approved: row.approved === true,
      reviewer_note: row.reviewer_note || ""
    }}]));

    function setDecision(index, status) {{
      const key = String(index);
      const current = decisions.get(key) || {{}};
      current.status = status;
      current.approved = status === "approved";
      decisions.set(key, current);
      const card = document.querySelector(`[data-review-index="${{key}}"]`);
      if (card) {{
        card.querySelector("[data-status]").textContent = status;
      }}
      updateCount();
    }}

    function setNote(index, note) {{
      const key = String(index);
      const current = decisions.get(key) || {{}};
      current.reviewer_note = note;
      decisions.set(key, current);
    }}

    function buildReviewedSheet() {{
      const rows = originalSheet.rows.map((row) => {{
        const decision = decisions.get(String(row.index)) || {{}};
        return {{
          ...row,
          status: decision.status || "pending",
          approved: decision.approved === true,
          reviewer_note: decision.reviewer_note || ""
        }};
      }});
      const approvedCount = rows.filter((row) => row.status === "approved" && row.approved === true).length;
      const rejectedCount = rows.filter((row) => row.status === "rejected").length;
      const pendingCount = rows.filter((row) => row.status === "pending").length;
      return {{
        ...originalSheet,
        passed: rows.length > 0 && approvedCount > 0 && pendingCount === 0,
        human_reviewed: rows.length > 0 && pendingCount === 0,
        approved_count: approvedCount,
        rejected_count: rejectedCount,
        pending_count: pendingCount,
        rows
      }};
    }}

    function updateCount() {{
      const reviewed = buildReviewedSheet();
      document.getElementById("review-count").textContent =
        `${{reviewed.approved_count}} approved, ${{reviewed.rejected_count}} rejected, ${{reviewed.pending_count}} pending`;
    }}

    document.querySelectorAll("[data-approve]").forEach((button) => {{
      button.addEventListener("click", () => setDecision(button.dataset.approve, "approved"));
    }});
    document.querySelectorAll("[data-reject]").forEach((button) => {{
      button.addEventListener("click", () => setDecision(button.dataset.reject, "rejected"));
    }});
    document.querySelectorAll("[data-pending]").forEach((button) => {{
      button.addEventListener("click", () => setDecision(button.dataset.pending, "pending"));
    }});
    document.querySelectorAll("[data-note]").forEach((note) => {{
      note.addEventListener("input", () => setNote(note.dataset.note, note.value));
    }});
    document.getElementById("export-json").addEventListener("click", () => {{
      const blob = new Blob([JSON.stringify(buildReviewedSheet(), null, 2) + "\\n"], {{ type: "application/json" }});
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = {download_name_json};
      link.click();
      URL.revokeObjectURL(link.href);
    }});
    document.getElementById("reset-review").addEventListener("click", () => {{
      decisions.clear();
      originalSheet.rows.forEach((row) => decisions.set(String(row.index), {{
        status: row.status || "pending",
        approved: row.approved === true,
        reviewer_note: row.reviewer_note || ""
      }}));
      document.querySelectorAll("[data-review-index]").forEach((card) => {{
        const index = card.dataset.reviewIndex;
        const decision = decisions.get(index);
        card.querySelector("[data-status]").textContent = decision.status;
        const note = card.querySelector("[data-note]");
        if (note) note.value = decision.reviewer_note;
      }});
      updateCount();
    }});
    updateCount();
  </script>
</body>
</html>
"""
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(html)
    return AnchorReviewPageResult(
        review_sheet_path=sheet_path,
        review_page_path=page_path,
        candidate_count=len(rows),
        pending_count=len(pending),
    )


def create_anchor_review_bundle(
    review_sheet_path: Path | str,
    *,
    out_dir: Path | str,
) -> AnchorReviewBundleResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    bundle_dir = Path(out_dir)
    clips_dir = bundle_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing = 0
    bundled_rows = []
    for row in sheet.get("rows", []):
        bundled = dict(row)
        source = Path(str(row.get("clip_path", ""))).expanduser()
        if source.exists():
            clip_name = _bundle_clip_name(row, source)
            target = clips_dir / clip_name
            shutil.copy2(source, target)
            bundled["source_clip_path"] = str(source)
            bundled["clip_path"] = f"clips/{clip_name}"
            copied += 1
        else:
            missing += 1
        bundled_rows.append(bundled)
    bundled_sheet = {
        **sheet,
        "source_review_sheet": str(sheet_path),
        "bundle_dir": str(bundle_dir),
        "copied_clip_count": copied,
        "missing_clip_count": missing,
        "rows": bundled_rows,
    }
    bundled_sheet_path = bundle_dir / sheet_path.name
    bundled_sheet_path.write_text(json.dumps(bundled_sheet, indent=2) + "\n")
    page_result = create_anchor_review_page(bundled_sheet_path, out_path=bundle_dir / "index.html")
    return AnchorReviewBundleResult(
        review_sheet_path=sheet_path,
        bundle_dir=bundle_dir,
        bundled_sheet_path=bundled_sheet_path,
        review_page_path=page_result.review_page_path,
        copied_clip_count=copied,
        missing_clip_count=missing,
    )


def import_anchor_review_sheet(
    original_sheet_path: Path | str,
    reviewed_export_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> AnchorReviewImportResult:
    original_path = Path(original_sheet_path)
    export_path = Path(reviewed_export_path)
    original = json.loads(original_path.read_text())
    reviewed = json.loads(export_path.read_text())
    original_rows = original.get("rows", [])
    reviewed_rows = reviewed.get("rows", [])
    if len(original_rows) != len(reviewed_rows):
        raise ValueError("reviewed export row count does not match original sheet")

    reviewed_by_index = {_row_key(row): row for row in reviewed_rows}
    imported_rows = []
    for original_row in original_rows:
        key = _row_key(original_row)
        if key not in reviewed_by_index:
            raise ValueError(f"reviewed export is missing row {key}")
        reviewed_row = reviewed_by_index[key]
        _validate_same_review_row(original_row, reviewed_row)
        imported_rows.append(_imported_review_row(original_row, reviewed_row))

    approved_count = sum(1 for row in imported_rows if row.get("status") == "approved" and row.get("approved") is True)
    rejected_count = sum(1 for row in imported_rows if row.get("status") == "rejected")
    pending_count = sum(1 for row in imported_rows if row.get("status") == "pending")
    imported = {
        **original,
        "passed": bool(imported_rows and approved_count and not pending_count),
        "human_reviewed": bool(imported_rows and not pending_count),
        "candidate_count": len(imported_rows),
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "pending_count": pending_count,
        "rows": imported_rows,
    }
    target_path = Path(out_path) if out_path else original_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(imported, indent=2) + "\n")
    return AnchorReviewImportResult(
        review_sheet_path=original_path,
        imported_sheet_path=target_path,
        candidate_count=len(imported_rows),
        approved_count=approved_count,
        rejected_count=rejected_count,
        pending_count=pending_count,
        human_reviewed=bool(imported_rows and not pending_count),
    )


def build_anchor_review_rerun_command(
    review_sheet_path: Path | str,
    pavo_decompose_manifest_path: Path | str,
    *,
    source_id: str | None = None,
) -> AnchorReviewRerunCommandResult:
    sheet_path = Path(review_sheet_path)
    manifest_path = Path(pavo_decompose_manifest_path)
    corrections = compile_anchor_review_corrections(sheet_path)
    if not corrections.corrections:
        raise ValueError("review sheet has no approved speaker corrections")
    manifest = json.loads(manifest_path.read_text())
    rerun_source_id = source_id or f"{manifest.get('source_id')}_reviewed"
    command = [
        "pavo",
        "audio",
        "decompose",
        str(manifest["audio_path"]),
        "--source-id",
        rerun_source_id,
    ]
    for engine in manifest.get("engines") or ["faster-whisper"]:
        command.extend(["--engine", str(engine)])
    if manifest.get("title"):
        command.extend(["--title", str(manifest["title"])])
    for term in manifest.get("context_terms") or []:
        command.extend(["--context-term", str(term)])
    if manifest.get("context_file"):
        command.extend(["--context-file", str(manifest["context_file"])])
    if manifest.get("num_speakers"):
        command.extend(["--num-speakers", str(manifest["num_speakers"])])
    for speaker in manifest.get("speakers") or []:
        command.extend(["--speaker", str(speaker)])
    command.extend(corrections.cli_args)
    command.extend(["--max-regions", str(manifest.get("max_regions", 3))])
    command.extend(["--padding", str(manifest.get("padding", 1.0))])
    command.extend(["--min-duration", str(manifest.get("min_duration", 1.0))])
    if manifest.get("include_rejected_stems"):
        command.append("--include-rejected-stems")
    return AnchorReviewRerunCommandResult(
        review_sheet_path=sheet_path,
        manifest_path=manifest_path,
        approved_count=corrections.approved_count,
        command=command,
        shell_command=shlex.join(command),
    )


def verify_anchor_review_page(
    review_sheet_path: Path | str,
    review_page_path: Path | str,
) -> AnchorReviewPageVerificationResult:
    sheet_path = Path(review_sheet_path)
    page_path = Path(review_page_path)
    sheet = json.loads(sheet_path.read_text())
    html = page_path.read_text()
    parser = _ReviewPageParser()
    parser.feed(html)
    candidate_count = len(sheet.get("rows", []))
    missing = []
    expected_counts = {
        "audio controls": parser.audio_count,
        "approve buttons": parser.approve_count,
        "reject buttons": parser.reject_count,
        "pending buttons": parser.pending_button_count,
        "reviewer note fields": parser.note_count,
    }
    for label, count in expected_counts.items():
        if count != candidate_count:
            missing.append(f"{label}: expected {candidate_count}, found {count}")
    embedded_sheet_present = False
    if parser.review_sheet_json:
        try:
            embedded = json.loads(parser.review_sheet_json)
            embedded_sheet_present = len(embedded.get("rows", [])) == candidate_count
        except json.JSONDecodeError:
            embedded_sheet_present = False
    checks = {
        "export button": parser.export_button_present,
        "reset button": parser.reset_button_present,
        "embedded sheet JSON": embedded_sheet_present,
        "import instruction": "pavo review anchors import" in html,
        "rerun instruction": "pavo review anchors rerun-command" in html,
    }
    for label, present in checks.items():
        if not present:
            missing.append(label)
    return AnchorReviewPageVerificationResult(
        review_sheet_path=sheet_path,
        review_page_path=page_path,
        passed=not missing,
        candidate_count=candidate_count,
        audio_count=parser.audio_count,
        approve_count=parser.approve_count,
        reject_count=parser.reject_count,
        pending_button_count=parser.pending_button_count,
        note_count=parser.note_count,
        export_button_present=parser.export_button_present,
        reset_button_present=parser.reset_button_present,
        embedded_sheet_present=embedded_sheet_present,
        import_instruction_present=checks["import instruction"],
        rerun_instruction_present=checks["rerun instruction"],
        missing=missing,
    )


def gate_anchor_review(
    review_sheet_path: Path | str,
    *,
    page_report_path: Path | str | None = None,
    bundle_manifest_path: Path | str | None = None,
    browser_report_path: Path | str | None = None,
    rerun_report_path: Path | str | None = None,
) -> AnchorReviewGateResult:
    sheet_path = Path(review_sheet_path)
    summary = summarize_anchor_review_sheet(sheet_path)
    page_report = _load_optional_json(page_report_path)
    bundle_manifest = _load_optional_json(bundle_manifest_path)
    browser_report = _load_optional_json(browser_report_path)
    rerun_report = _load_optional_json(rerun_report_path)
    page_ready = bool(page_report.get("passed"))
    bundle_ready = bool(bundle_manifest.get("passed"))
    browser_verified = bool(browser_report.get("passed"))
    rerun_command_ready = bool(rerun_report.get("rerun_command_ready"))
    blockers = []
    if not page_ready:
        blockers.append("anchor review page is not verified")
    if not bundle_ready:
        blockers.append("browser-safe anchor review bundle is not ready")
    if not browser_verified:
        blockers.append("anchor review bundle has not been browser-verified")
    if not summary["human_reviewed"]:
        blockers.append(f"{summary['pending_count']} review rows are still pending")
    if not summary["approved_count"]:
        blockers.append("no speaker-anchor clips are approved")
    if summary["human_reviewed"] and summary["approved_count"] and not rerun_command_ready:
        blockers.append("rerun command is not ready")
    passed = bool(
        page_ready
        and bundle_ready
        and browser_verified
        and summary["human_reviewed"]
        and summary["approved_count"]
        and rerun_command_ready
    )
    next_action = (
        "run the rerun command and regenerate Plaud decompose proof"
        if passed
        else "review the bundled clips, export JSON, import it, then run pavo review anchors rerun-command"
    )
    return AnchorReviewGateResult(
        review_sheet_path=sheet_path,
        passed=passed,
        human_reviewed=summary["human_reviewed"],
        approved_count=summary["approved_count"],
        rejected_count=summary["rejected_count"],
        pending_count=summary["pending_count"],
        page_ready=page_ready,
        bundle_ready=bundle_ready,
        browser_verified=browser_verified,
        rerun_command_ready=rerun_command_ready,
        blockers=blockers,
        next_action=next_action,
    )


def summarize_anchor_review_sheet(review_sheet_path: Path | str) -> dict[str, Any]:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    rows = sheet.get("rows", [])
    approved = [row for row in rows if row.get("approved") is True and row.get("status") == "approved"]
    rejected = [row for row in rows if row.get("status") == "rejected"]
    pending = [row for row in rows if row.get("status") == "pending"]
    return {
        "passed": bool(rows and approved and not pending),
        "human_reviewed": bool(rows and not pending),
        "review_sheet": str(sheet_path),
        "target_speaker_label": sheet.get("target_speaker_label"),
        "candidate_count": len(rows),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "pending_count": len(pending),
        "corrections": compile_anchor_review_corrections(sheet_path).corrections,
        "next_required_proof": "rerun Plaud decompose with exported --speaker-correction flags and produce accepted stems",
    }


def _speaker_correction(start: Any, end: Any, speaker_label: Any) -> str | None:
    if start is None or end is None or not speaker_label:
        return None
    return f"{_format_seconds(start)}-{_format_seconds(end)}={speaker_label}"


def _row_key(row: dict[str, Any]) -> str:
    return str(row.get("index"))


def _validate_same_review_row(original: dict[str, Any], reviewed: dict[str, Any]) -> None:
    immutable_keys = [
        "index",
        "target_speaker_label",
        "start",
        "end",
        "clip_path",
        "suggested_speaker_correction",
    ]
    for key in immutable_keys:
        if str(original.get(key)) != str(reviewed.get(key)):
            raise ValueError(f"reviewed export row {original.get('index')} changed immutable field {key}")


def _imported_review_row(original: dict[str, Any], reviewed: dict[str, Any]) -> dict[str, Any]:
    status = reviewed.get("status") or "pending"
    if status not in {"pending", "approved", "rejected"}:
        raise ValueError(f"reviewed export row {original.get('index')} has invalid status {status}")
    approved = status == "approved"
    if reviewed.get("approved") is True and status != "approved":
        raise ValueError(f"reviewed export row {original.get('index')} has approved true without approved status")
    row = dict(original)
    row["status"] = status
    row["approved"] = approved
    row["reviewer_note"] = str(reviewed.get("reviewer_note") or "")
    return row


def _review_card(row: dict[str, Any]) -> str:
    clip_path = row.get("clip_path")
    audio_src = _audio_src(clip_path)
    correction = row.get("suggested_speaker_correction") or _speaker_correction(
        row.get("start"), row.get("end"), row.get("target_speaker_label")
    )
    index = escape(str(row.get("index")))
    note = escape(str(row.get("reviewer_note") or ""))
    return f"""<article data-review-index="{index}">
  <div class="row-head">
    <h2>Clip {index}</h2>
    <span class="status" data-status>{escape(str(row.get('status') or 'pending'))}</span>
  </div>
  <audio controls preload="metadata" src="{escape(audio_src)}"></audio>
  <div class="review-controls">
    <button type="button" data-approve="{index}">Approve</button>
    <button type="button" class="secondary" data-reject="{index}">Reject</button>
    <button type="button" class="secondary" data-pending="{index}">Pending</button>
  </div>
  <textarea data-note="{index}" placeholder="Reviewer note">{note}</textarea>
  <dl>
    <dt>Time</dt><dd>{escape(str(row.get('start')))} - {escape(str(row.get('end')))} seconds</dd>
    <dt>Text</dt><dd>{escape(str(row.get('text') or ''))}</dd>
    <dt>Target</dt><dd>{escape(str(row.get('target_speaker_label') or ''))} / {escape(str(row.get('target_speaker_name') or ''))}</dd>
    <dt>Correction</dt><dd><code>{escape(str(correction or ''))}</code></dd>
    <dt>Clip path</dt><dd>{escape(str(clip_path or ''))}</dd>
  </dl>
</article>"""


def _audio_src(clip_path: Any) -> str:
    if not clip_path:
        return ""
    path = Path(str(clip_path)).expanduser()
    if path.is_absolute():
        return path.as_uri()
    return str(path)


def _load_optional_json(path: Path | str | None) -> dict[str, Any]:
    if path is None:
        return {}
    json_path = Path(path)
    return json.loads(json_path.read_text()) if json_path.exists() else {}


def _bundle_clip_name(row: dict[str, Any], source: Path) -> str:
    index = row.get("index")
    prefix = f"candidate-{int(index):02d}" if isinstance(index, int) else f"candidate-{index or 'unknown'}"
    return f"{prefix}{source.suffix or '.wav'}"


class _ReviewPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.audio_count = 0
        self.approve_count = 0
        self.reject_count = 0
        self.pending_button_count = 0
        self.note_count = 0
        self.export_button_present = False
        self.reset_button_present = False
        self._in_review_sheet_script = False
        self._review_sheet_chunks: list[str] = []

    @property
    def review_sheet_json(self) -> str:
        return "".join(self._review_sheet_chunks).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "audio":
            self.audio_count += 1
        if "data-approve" in attr:
            self.approve_count += 1
        if "data-reject" in attr:
            self.reject_count += 1
        if "data-pending" in attr:
            self.pending_button_count += 1
        if "data-note" in attr:
            self.note_count += 1
        if attr.get("id") == "export-json":
            self.export_button_present = True
        if attr.get("id") == "reset-review":
            self.reset_button_present = True
        if tag == "script" and attr.get("id") == "review-sheet-data":
            self._in_review_sheet_script = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_review_sheet_script = False

    def handle_data(self, data: str) -> None:
        if self._in_review_sheet_script:
            self._review_sheet_chunks.append(data)


def _format_seconds(value: Any) -> str:
    seconds = max(0, int(round(float(value))))
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    if hour:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"
