from __future__ import annotations

import json
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
      Export the reviewed JSON sheet, replace the original sheet with it, then run
      <code>pavo review anchors corrections {escape(str(sheet_path))}</code>.
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


def _format_seconds(value: Any) -> str:
    seconds = max(0, int(round(float(value))))
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    if hour:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"
