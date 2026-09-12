"""generate the current aria zone a step-by-step project pipeline pdf"""
from argparse import ArgumentParser
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT.parent / "ARIA_Zone_A_Full_Project_Pipeline.pdf"

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 17 * mm
MARGIN_TOP = 18 * mm
MARGIN_BOTTOM = 16 * mm

NAVY = colors.HexColor("#12324A")
BLUE = colors.HexColor("#087EA4")
TEAL = colors.HexColor("#0B8F87")
PALE_TEAL = colors.HexColor("#E7F5F3")
PALE_BLUE = colors.HexColor("#EAF3F8")
PALE_AMBER = colors.HexColor("#FFF4D8")
AMBER = colors.HexColor("#A96300")
PALE_RED = colors.HexColor("#FBE9E7")
RED = colors.HexColor("#A63C32")
INK = colors.HexColor("#1F2D38")
MUTED = colors.HexColor("#5F6F79")
LINE = colors.HexColor("#CAD5DC")
SOFT = colors.HexColor("#F5F7F8")
WHITE = colors.white

STATUS = {
    "COMPLETE": (TEAL, WHITE),
    "PARTIAL": (AMBER, WHITE),
    "IN PROGRESS": (BLUE, WHITE),
    "NEXT": (AMBER, WHITE),
    "BLOCKED": (RED, WHITE),
    "LATER": (MUTED, WHITE),
}


styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="CoverKicker",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=BLUE,
        spaceAfter=5 * mm,
        alignment=TA_CENTER,
    )
)
styles.add(
    ParagraphStyle(
        name="CoverTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=29,
        leading=33,
        textColor=NAVY,
        alignment=TA_CENTER,
        spaceAfter=5 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=13,
        leading=18,
        textColor=MUTED,
        alignment=TA_CENTER,
        spaceAfter=9 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="SectionLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=10,
        textColor=BLUE,
        spaceAfter=1.5 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="PhaseTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=NAVY,
        spaceAfter=3 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="PhaseObjective",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10.2,
        leading=14,
        textColor=INK,
        spaceAfter=5 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="PartTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=15,
        textColor=NAVY,
        spaceAfter=1.5 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12.5,
        textColor=INK,
        spaceAfter=1.8 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="BodySmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
        textColor=INK,
    )
)
styles.add(
    ParagraphStyle(
        name="BulletCompact",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.7,
        leading=11.5,
        leftIndent=4 * mm,
        firstLineIndent=-2.5 * mm,
        bulletIndent=0,
        textColor=INK,
        spaceAfter=0.8 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="CodeBlock",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=7.4,
        leading=9.5,
        textColor=NAVY,
        backColor=SOFT,
        borderColor=LINE,
        borderWidth=0.5,
        borderPadding=5,
        spaceBefore=1.5 * mm,
        spaceAfter=2 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="Callout",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12.5,
        textColor=INK,
    )
)
styles.add(
    ParagraphStyle(
        name="TableHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=WHITE,
    )
)
styles.add(
    ParagraphStyle(
        name="TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.7,
        leading=10,
        textColor=INK,
    )
)
styles.add(
    ParagraphStyle(
        name="TableCellBold",
        parent=styles["TableCell"],
        fontName="Helvetica-Bold",
    )
)
styles.add(
    ParagraphStyle(
        name="StatusText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.2,
        leading=8,
        alignment=TA_CENTER,
        textColor=WHITE,
    )
)

def P(text, style="Body"):
    return Paragraph(text, styles[style])

def bullets(items):
    return [
        Paragraph(f"- {item}", styles["BulletCompact"])
        for item in items
    ]

def status_chip(status):
    background, foreground = STATUS[status]
    paragraph = Paragraph(
        status,
        ParagraphStyle(
            name=f"Status{status}",
            parent=styles["StatusText"],
            textColor=foreground,
        ),
    )
    table = Table([[paragraph]], colWidths=[25 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0, background),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table

def callout(title, text, tone="blue"):
    palette = {
        "blue": (PALE_BLUE, BLUE),
        "teal": (PALE_TEAL, TEAL),
        "amber": (PALE_AMBER, AMBER),
        "red": (PALE_RED, RED),
    }
    background, accent = palette[tone]
    content = Paragraph(
        f"<b>{title}</b><br/>{text}",
        styles["Callout"],
    )
    table = Table([[content]], colWidths=[PAGE_WIDTH - 2 * MARGIN_X])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
                ("BOX", (0, 0), (-1, -1), 0.4, accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table

def data_table(headers, rows, widths=None):
    data = [
        [Paragraph(value, styles["TableHead"]) for value in headers]
    ]
    for row in rows:
        data.append(
            [
                value if hasattr(value, "wrap") else Paragraph(
                    str(value), styles["TableCell"]
                )
                for value in row
            ]
        )
    table = Table(
        data,
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
            ]
        )
    )
    return table

def phase_header(number, title, objective, status):
    return [
        P(f"PHASE {number}", "SectionLabel"),
        P(title, "PhaseTitle"),
        Table(
            [[P(objective, "PhaseObjective"), status_chip(status)]],
            colWidths=[PAGE_WIDTH - 2 * MARGIN_X - 31 * mm, 31 * mm],
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ]
            ),
        ),
        Spacer(1, 2 * mm),
    ]

def part(number, title, status, actions, evidence=None, exit_rule=None):
    rows = [
        [
            P(f"{number} {title}", "PartTitle"),
            status_chip(status),
        ]
    ]
    title_table = Table(
        rows,
        colWidths=[PAGE_WIDTH - 2 * MARGIN_X - 31 * mm, 31 * mm],
    )
    title_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )
    content = [title_table, Spacer(1, 1 * mm)]
    content.extend(bullets(actions))
    if evidence:
        content.append(
            P(f"<b>Evidence:</b> {evidence}", "BodySmall")
        )
    if exit_rule:
        content.append(
            P(f"<b>Part complete when:</b> {exit_rule}", "BodySmall")
        )
    content.append(Spacer(1, 3 * mm))
    return KeepTogether(content)

def gate(text):
    return callout("PHASE GATE", text, "teal")

def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(
        MARGIN_X,
        PAGE_HEIGHT - 11 * mm,
        PAGE_WIDTH - MARGIN_X,
        PAGE_HEIGHT - 11 * mm,
    )
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(NAVY)
    canvas.drawString(
        MARGIN_X,
        PAGE_HEIGHT - 8.5 * mm,
        "ARIA - ZONE A STEP-BY-STEP DELIVERY PIPELINE",
    )
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(
        PAGE_WIDTH - MARGIN_X,
        PAGE_HEIGHT - 8.5 * mm,
        "Current baseline: 24 August 2026",
    )
    canvas.line(
        MARGIN_X,
        11 * mm,
        PAGE_WIDTH - MARGIN_X,
        11 * mm,
    )
    canvas.drawString(
        MARGIN_X,
        7.5 * mm,
        "Execution roadmap - active Zone A scope only",
    )
    canvas.drawRightString(
        PAGE_WIDTH - MARGIN_X,
        7.5 * mm,
        f"Page {doc.page}",
    )
    canvas.restoreState()

def cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_HEIGHT - 34 * mm, PAGE_WIDTH, 34 * mm, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, PAGE_WIDTH, 8 * mm, fill=1, stroke=0)
    canvas.restoreState()

def build_story():
    story = [
        Spacer(1, 28 * mm),
        P("CM3070 FINAL PROJECT", "CoverKicker"),
        P("ARIA Zone A<br/>Step-by-Step Delivery Pipeline", "CoverTitle"),
        P(
            "A phased progression from the current working prototype to "
            "a privacy-safe, evaluated final product",
            "CoverSubtitle",
        ),
        callout(
            "CURRENT CHECKPOINT",
            "The active Zone A deployment remains ESP-A1, ESP-A2 and the wireless "
            "DJI Camera A, with batamfast-v2 masking applied before all vision "
            "processing and display. The hardware, camera, privacy/CV, multimodal "
            "windowing and collection gates are complete. Phase 2 remains PARTIAL: "
            "ESP-A1 delivered 98.185% and ESP-A2 97.963% against the unchanged 98% "
            "target. The shortfall remains an explicit limitation. Participant "
            "collection is closed after nine retained sessions. Phase 10 produced "
            "26,114 audited rows and 1,847 episodes, with 24,046 rows in eight frozen "
            "development folds and 2,068 rows in an isolated external test. All 14 "
            "split checks pass. Phase 11 is complete. Camera A-only led development "
            "at 0.442791 macro F1; no sensor-only or early-fusion alternative beat it. "
            "The frozen Camera-only "
            "model was evaluated once on all 2,068 external rows: accuracy is 0.492263, "
            "balanced accuracy is 0.328030 and macro F1 is 0.348179. Reaching/Handling "
            "has only 19 rows and F1 is 0.000000, so reliable recognition of that class "
            "cannot be claimed. The development ablation, reliability, local model "
            "latency, privacy boundary and six synthetic missing-modality scenarios are "
            "recorded without post-result tuning. Phase 12.1 local inference is complete: "
            "offline/live preprocessing parity and the synthetic privacy boundary pass, "
            "while durable local JSONL delivery measured 5.720 ms p95. The full suite "
            "has 390 passes and three pre-existing frozen-hash failures. Recovering the "
            "exact historical v7 variants remains a final provenance action. Phase 12.2 "
            "privacy-aware dashboard integration is next.",
            "blue",
        ),
        Spacer(1, 4 * mm),
        data_table(
            ["Active component", "Locked configuration"],
            [
                ["ESP-A1", "Zone A; A_PIR_US_MIC; local UDP 4210"],
                ["ESP-A2", "Zone A; A_PIR_MIC; local UDP 4211; no ultrasonic"],
                ["Laptop receiver", "UDP 5005; accepts ESP-A1 and ESP-A2 only"],
                [
                    "camera_a",
                    "DJI Osmo Action 5 Pro; wireless RTMP ingest; local "
                    "video-only RTSP; 1920x1080 at 30 FPS",
                ],
                [
                    "Privacy",
                    "batamfast-v2 polygon exclusions; verified mask required before "
                    "detection, display, feature output or collection",
                ],
            ],
            widths=[42 * mm, 119 * mm],
        ),
        Spacer(1, 8 * mm),
        P(
            "Version 3.68 | 24 August 2026 | Active scope: Zone A only",
            "CoverSubtitle",
        ),
        PageBreak(),
        P("HOW TO USE THIS ROADMAP", "SectionLabel"),
        P("Progress through gates, not just tasks", "PhaseTitle"),
        P(
            "Each phase is divided into numbered parts. A part may be complete, "
            "in progress, next, blocked by a prerequisite, or deliberately "
            "scheduled for later. Participant collection is now closed; the earlier "
            "participant-facing gates are retained here as the historical audit trail.",
            "PhaseObjective",
        ),
        data_table(
            ["Status", "Meaning"],
            [
                [status_chip("COMPLETE"), "Implemented and supported by current evidence"],
                [status_chip("PARTIAL"), "Completed, but only part of the predefined acceptance criteria passed"],
                [status_chip("IN PROGRESS"), "Work exists but acceptance evidence is incomplete"],
                [status_chip("NEXT"), "Immediate executable work on the critical path"],
                [status_chip("BLOCKED"), "Cannot proceed until the stated prerequisite is met"],
                [status_chip("LATER"), "Valid downstream work after earlier gates"],
            ],
            widths=[36 * mm, 125 * mm],
        ),
        Spacer(1, 5 * mm),
        callout(
            "NON-NEGOTIABLE SCOPE",
            "Only consenting Counter Agents in Zone A are in scope. ESP-B, "
            "ESP-T, Zone B, Zone T, a second camera, Station Manager role "
            "attribution and cloud video are excluded from the active system.",
            "red",
        ),
        Spacer(1, 5 * mm),
        P("Critical path", "PartTitle"),
        data_table(
            ["Completed checkpoint", "Next", "Phase 12.1 gate", "Final-product path"],
            [
                [
                    "Phase 12.1 local inference service",
                    "Phase 12.2 privacy-aware dashboard",
                    "Complete with synthetic privacy and latency acceptance",
                    "Dataset -> baselines -> multimodal models -> dashboard -> "
                    "acceptance -> report",
                ]
            ],
            widths=[38 * mm, 42 * mm, 48 * mm, 33 * mm],
        ),
        Spacer(1, 5 * mm),
        P("Current evidence snapshot", "PartTitle"),
        data_table(
            ["Evidence", "Observed result", "Decision"],
            [
                [
                    "Unit suite",
                    "390 pass; three pre-existing frozen-hash failures",
                    "Phase 12.1 checks pass; historical drift remains separate",
                ],
                [
                    "Profile provenance",
                    "Retained manifests reference two historical v7 hashes; neither "
                    "matches the current v7 file",
                    "Recover and archive the exact variants; collection remains closed",
                ],
                [
                    "Camera-only diagnostic",
                    "1920x1080, 29.97 FPS, 1,820 frames, 0 reported drops",
                    "Short camera check passes",
                ],
                [
                    "60-second combined diagnostic",
                    "ESP-A1 60/60; ESP-A2 59/60; camera 1,799 frames/60.02 s; "
                    "one H264 track; no audio track",
                    "Short integration threshold passes",
                ],
                [
                    "Site mask",
                    "batamfast-v2; verified=true; was required for every retained "
                    "participant run",
                    "Phase 4 gate and Phase 7.4 recovery pass",
                ],
                [
                    "Phase 10 dataset",
                    "26,114 audited rows; 1,847 episodes; 24,046 development rows; "
                    "2,068 locked external-test rows",
                    "Phase 10 complete; all 14 split leakage checks pass",
                ],
                [
                    "Phase 11 evaluation",
                    "External macro F1 0.348179; balanced accuracy 0.328030; Reaching F1 0.000000 on 19 rows",
                    "Phase 11 complete; limitations retained and no post-result tuning",
                ],
            ],
            widths=[43 * mm, 78 * mm, 40 * mm],
        ),
        PageBreak(),
    ]

    story.extend(
        phase_header(
            "0",
            "Lock scope, governance and collection authority",
            "Make the active study boundary unambiguous before technical work "
            "can be mistaken for permission to collect participant data.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "0.1",
                "Freeze the active deployment scope",
                "COMPLETE",
                [
                    "Use only Zone A, ESP-A1, ESP-A2 and camera_a.",
                    "Retain retired nodes and cameras only as labelled historical evidence.",
                    "Use the Counter Agent activity set: Serving/Processing, "
                    "Idle/Waiting and Reaching/Handling.",
                    "Do not implement role attribution or biometric re-identification.",
                ],
                "AGENTS.md, README.md and active configuration files.",
                "Every active path and acceptance test excludes retired components.",
            ),
            part(
                "0.2",
                "Confirm the authoritative Ethics Pack Version 4.4 PDF",
                "COMPLETE",
                [
                    "Use outputs/pdf/ARIA Ethics Pack_v4_4.pdf as the authoritative current pack.",
                    "Retain Version 4.3 files as historical material, not as active sources.",
                    "Keep the pack-level cover and every running header at Version 4.4 and 4 August 2026.",
                    "Use expanded Part D for the three-class Counter Agent method and retired Station Manager role attribution.",
                ],
                "outputs/pdf/ARIA Ethics Pack_v4_4.pdf and docs/ethics/README.md.",
                "The authoritative PDF accurately describes the active Zone A-only deployment.",
            ),
            part(
                "0.3",
                "Generate and visually verify the Version 4.4 PDF",
                "COMPLETE",
                [
                    "Retain the authoritative participant-facing Version 4.4 PDF.",
                    "Render and visually inspect every page for clipping, stale version labels and formatting defects.",
                    "Confirm the PDF content and ethics README identify the same active scope before issue.",
                ],
                "outputs/pdf/ARIA Ethics Pack_v4_4.pdf plus rendered-page QA evidence.",
                "A visually verified, participant-facing Version 4.4 PDF exists.",
            ),
            part(
                "0.4",
                "Issue Version 4.4 and record the Part D amendment acknowledgement",
                "COMPLETE",
                [
                    "Issue only the visually verified Version 4.4 PDF.",
                    "Give the pack to every participating Counter Agent.",
                    "Record acknowledgement of amended Part D under approved secure controls.",
                ],
                "Issue and acknowledgement records stored outside the repository where identifiable.",
                "Every participating Counter Agent has received Version 4.4 and the required acknowledgement is recorded.",
            ),
            PageBreak(),
            P("PHASE 0 - CONTINUED", "SectionLabel"),
            P("Complete repository and data-handling controls", "PhaseTitle"),
            P(
                "Separate identifiable records from the working project and "
                "put reviewable guardrails around generated data, logs, media "
                "and final submission material.",
                "PhaseObjective",
            ),
            part(
                "0.5",
                "Move consent and acknowledgement records out of the project",
                "COMPLETE",
                [
                    "Keep consented participant PDFs in approved secure external storage.",
                    "Keep identifiable issue and acknowledgement evidence outside the repository.",
                    "Leave no participant-code key in the project folder.",
                ],
                "docs/ethics/consented is absent; secure external records are confirmed by the project owner.",
                "No identifiable consent or acknowledgement record remains in the project folder.",
            ),
            part(
                "0.6",
                "Create repository ignore and exclusion rules",
                "COMPLETE",
                [
                    "Review the new .gitignore rules for generated data, logs, consent records, media, keys, caches and model artefacts.",
                    "Confirm required README/.gitkeep files remain includable.",
                    "Treat ignore rules as a guardrail rather than proof that content is safe.",
                ],
                ".gitignore.",
                "The project owner reviews and marks the ignore policy approved.",
            ),
            part(
                "0.7",
                "Document Zone A data handling",
                "COMPLETE",
                [
                    "Review permitted data categories, approved locations and access separation.",
                    "Review camera/audio, session, incident, retention, Firebase and deletion controls.",
                    "Confirm the procedure matches the approved study and actual working environment.",
                ],
                "docs/privacy/data_handling.md.",
                "The project owner reviews and marks the data-handling procedure approved.",
            ),
            part(
                "0.8",
                "Reconcile current project and ethics status documents",
                "COMPLETE",
                [
                    "Update README.md with the completed ethics and short integration evidence.",
                    "Update docs/ethics/README.md with verified PDF issue and acknowledgement status.",
                    "Keep site-mask and live-acceptance blockers explicit.",
                ],
                "README.md and docs/ethics/README.md.",
                "Both status documents match the current Zone A evidence.",
            ),
            gate(
                "Phase 0 is complete: scope, ethics issue/acknowledgement, "
                "consent-record separation, ignore rules, data handling and "
                "status reconciliation are approved. Deployment credential "
                "replacement remains mandatory at the final-submission audit "
                "in Phase 14.3."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "1",
            "Finish the two-board hardware baseline",
            "Confirm that both physical Zone A nodes run the locked firmware, "
            "schema and wiring before site placement is calibrated.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "1.1",
                "ESP-A1 hardware and firmware",
                "COMPLETE",
                [
                    "Use firmware 1.1.1 with node_id ESP-A1 and sensor_config A_PIR_US_MIC.",
                    "Preserve PIR on D1, HC-SR04 TRIG on D5, ECHO on D6 through the voltage divider, and MAX4466 on A0.",
                    "Bind local UDP 4210 and send distance plus numerical-audio fields.",
                ],
                "Live packets from ESP-A1 and schema-validation tests.",
                "Packets are identifiable, valid and contain distance_cm/distance_valid.",
            ),
            part(
                "1.2",
                "ESP-A2 hardware and firmware",
                "COMPLETE",
                [
                    "Use firmware 1.1.1 with node_id ESP-A2 and sensor_config A_PIR_MIC.",
                    "Connect PIR and MAX4466 only; do not attach or emulate an ultrasonic sensor.",
                    "Bind local UDP 4211 and omit all distance fields.",
                ],
                "Live packets from ESP-A2 and asymmetric-schema tests.",
                "Packets are identifiable, valid and contain no distance fields.",
            ),
            part(
                "1.3",
                "Final physical placement and safety",
                "COMPLETE",
                [
                    "Mount A1 and A2 in distinct staff-side Zone A placements.",
                    "Record height, direction, power, cable route and intended coverage.",
                    "Keep wiring clear of public routes, liquids and moving equipment.",
                    "Confirm A1 ultrasonic aiming does not target customers or unstable surfaces.",
                ],
                "docs/calibration/results/2026-07-30_zone_a_placement_record.md; no identifiable photographs retained.",
                "Both placements are fixed, safe, repeatable and ready for sensor calibration.",
            ),
            gate(
                "ESP-A1 and ESP-A2 have correct firmware and wiring, and their "
                "final site positions are documented and physically safe."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "2",
            "Complete telemetry ingestion and sensor calibration",
            "Turn both boards into reliable, separately traceable numerical "
            "telemetry sources on the deployment network.",
            "PARTIAL",
        )
    )
    story.extend(
        [
            part(
                "2.1",
                "Validate the asymmetric telemetry schema",
                "COMPLETE",
                [
                    "Accept only ESP-A1 and ESP-A2 in Zone A.",
                    "Require schema_version, firmware_version, boot_id, sequence and numerical sensor fields.",
                    "Require ESP-A1 distance fields and reject them for ESP-A2.",
                ],
                "schemas/esp_packet.schema.json and unit tests.",
                "Malformed, retired-node and wrong-sensor packets fail closed.",
            ),
            part(
                "2.2",
                "Operate the UDP receiver and health monitor",
                "COMPLETE",
                [
                    "Listen on UDP 5005 and write separate ESP-A1/ESP-A2 logs plus a unified JSONL stream.",
                    "Detect stale nodes, gaps, restarts, duplicates and out-of-order packets independently.",
                    "Use laptop receive timestamps for cross-modal alignment.",
                ],
                "outputs/logs/udp_receiver.log, esp_a1.log and esp_a2.log; the completed mixed progression stream is retained under data/historical/telemetry_progression/.",
                "One node can fail without stopping the other.",
            ),
            part(
                "2.3",
                "Calibrate both site placements",
                "COMPLETE",
                [
                    "ESP-A1 intended PIR passed 5 / 5 and cross-placement passed with 0 / 5 unintended triggers.",
                    "ESP-A2 intended PIR passed 4 / 5 and cross-placement passed with 0 / 5 unintended triggers.",
                    "ESP-A1 ultrasonic reference points at 50 cm, 70 cm and 90 cm all passed.",
                    "Separate numerical-audio baselines and usable activity separation were accepted without raw audio.",
                ],
                "docs/calibration/results/2026-07-30_phase_2_3_trial_intervals.csv and docs/testing/results/2026-07-30_zone_a_phase_2_3_report.md.",
                "The generated Phase 2.3 calibration decision is PASS.",
            ),
            part(
                "2.4",
                "Run dual-node endurance and recovery - complete with accepted network limitation",
                "PARTIAL",
                [
                    "Only the ESP-A2 microcontroller node was replaced on 5 August after consistently poor earlier performance.",
                    "Completed the 6 August 90-minute rerun with both boards present; this is the current endurance evidence.",
                    "ESP-A1 passed: 5,302 / 5,400 packets (98.185%).",
                    "ESP-A2 improved to 5,290 / 5,400 packets (97.963%) but remained two packets short of the target.",
                    "The 2 August recovery trials remain supplemental evidence; ESP-A2's trial predates the replacement.",
                    "Camera A completed the same 5,400-second interval with no read failures; its longest-gap anomaly remains recorded.",
                    "Public Wi-Fi was uncontrolled and is accepted as an operational limitation without being claimed as the proven sole cause.",
                ],
                "docs/testing/results/2026-08-06_zone_a_phase_8_3_endurance_rerun.md, the historical 2 August Attempt 4 report and receiver JSONL/logs.",
                "Complete with partial acceptance: the latest endurance evidence is complete; ESP-A2's two-packet shortfall and the pre-replacement recovery limitation remain explicit.",
            ),
            gate(
                "Phase 2.3 calibration passed. Phase 2.4 is complete with "
                "partial acceptance; ESP-A1 passed the latest per-node delivery "
                "target, while ESP-A2 remained two packets short. The separate "
                "recovery trials passed on 2 August, before ESP-A2's 5 August "
                "microcontroller replacement. "
                "Phase 2 remains PARTIAL by design: the later Phase 8 GO accepts "
                "the reliability risk but does not convert either failed 98% result into a pass."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "3",
            "Commission the wireless DJI Camera A path",
            "Establish one stable, local, video-only 1080p stream without "
            "recording or exposing audio to ARIA.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "3.1",
                "Start the local MediaMTX bridge",
                "COMPLETE",
                [
                    "Run MediaMTX with config/mediamtx.local.yaml.",
                    "Accept DJI RTMP at ingest/camera_a on the site's uncontrolled public Wi-Fi network.",
                    "Use the localhost FFmpeg hook to copy H264 video and remove audio.",
                    "Expose only rtsp://127.0.0.1:8554/live/camera_a to ARIA; keep recording disabled.",
                ],
                "MediaMTX startup and path logs.",
                "The ARIA-facing stream advertises exactly one H264 video track and no audio.",
            ),
            P(
                "mediamtx config/mediamtx.local.yaml<br/>"
                "DJI publish: rtmp://LAPTOP_IP:1935/ingest/camera_a<br/>"
                "ARIA read: rtsp://127.0.0.1:8554/live/camera_a",
                "CodeBlock",
            ),
            part(
                "3.2",
                "Validate capture mode and short-run health",
                "COMPLETE",
                [
                    "Confirm camera_id camera_a and reject built-in, Continuity and second-camera sources.",
                    "Confirm 1920x1080 at approximately 30 FPS.",
                    "Measure successful frames, drops and stream availability.",
                ],
                "Camera-only result: 29.97 FPS, 1,820 frames and 0 reported drops.",
                "The short camera diagnostic passes at the locked mode.",
            ),
            part(
                "3.3",
                "Fix the final mount and framing",
                "COMPLETE",
                [
                    "Mount the DJI in its final stable position.",
                    "Aim at the staff-side Zone A area while minimising customer and sensitive surfaces.",
                    "Record mount position, height, direction and every later movement.",
                ],
                "docs/calibration/results/2026-07-30_camera_a_placement_record.md and config/masks.batamfast.yaml.",
                "The camera cannot move without triggering mask re-verification.",
            ),
            part(
                "3.4",
                "Run stream endurance and reconnect tests",
                "COMPLETE",
                [
                    "Completed 5,400 seconds at 29.969 measured FPS with 161,836 successful reads and no read failures.",
                    "Recorded the timing-inferred drop estimate, 267.167 ms longest gap and local frame-read latency with its interpretation limit.",
                    "Restored the video-only path automatically after a controlled DJI publisher interruption.",
                    "ESP-A1 and ESP-A2 each delivered 100% of expected packets during the endurance and reconnect evidence windows.",
                ],
                "docs/testing/results/2026-07-31_camera_a_phase_3_4.md and the linked JSON evidence.",
                "Phase 3.4 passes with the timing-estimator limitation explicitly recorded.",
            ),
            gate(
                "The fixed camera sustains a local 1920x1080/30 FPS video-only "
                "path and recovers cleanly while both ESP boards remain healthy."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "4",
            "Calibrate and accept the Zone A polygon privacy mask",
            "Make the only visible/processable camera output the approved "
            "staff-side view, with all customer and sensitive areas blacked out.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "4.1",
                "Implement polygon exclusions",
                "COMPLETE",
                [
                    "Retain backward-compatible rectangular base-region support.",
                    "Support multiple exclusion polygons through the excluded_polygons field in config/masks.batamfast.yaml.",
                    "Reject polygons with fewer than three points, zero area, invalid types or out-of-frame coordinates.",
                    "Apply exclusions before detection, tracking, pose or feature output.",
                ],
                "65 passing unit tests; draft wall-display and customer/right-counter polygons.",
                "The implementation was held verified=false until the completed Phase 4.4 live-site acceptance.",
            ),
            part(
                "4.2",
                "Add a safe draft-mask preview",
                "COMPLETE",
                [
                    "Use scripts/preview_privacy_mask.py.",
                    "Read only camera_a from the exact local RTSP path.",
                    "Display only masked output with polygon boundaries while allowing verified=false for calibration only.",
                    "Run no detection, write no frames and expose no unmasked preview.",
                    "Exit locally with q; use the existing live-site consent and exclusion procedure.",
                ],
                "Masked-only live-site demonstration completed; interactive editor and preview tests pass.",
                "The operator demonstrated local masked-only calibration without enabling participant-mode processing.",
            ),
            P(
                "PYTHONPATH=src python3 scripts/preview_privacy_mask.py "
                "--source rtsp://127.0.0.1:8554/live/camera_a "
                "--mask-config config/masks.batamfast.yaml",
                "CodeBlock",
            ),
            part(
                "4.3",
                "Perform on-site boundary calibration",
                "COMPLETE",
                [
                    "Clear the view of customers and non-participants before opening the calibration preview.",
                    "Adjust the wall-display and customer/right-counter polygon vertices against the final mounted feed.",
                    "Test ordinary staff movement at every retained boundary.",
                    "Exclude screens, payment areas, documents, reflective surfaces and all non-participants.",
                    "Preserve adequate shoulders, elbows, wrists and torso for pose features.",
                ],
                "docs/calibration/results/2026-07-31_camera_a_mask_calibration.md and the saved two-polygon mask.",
                "The operator accepted the retained view for boundary coverage and pose visibility.",
            ),
            part(
                "4.4",
                "Verify and fail closed",
                "COMPLETE",
                [
                    "Set verified=true only after final-position acceptance.",
                    "Update the camera mask status only after the same acceptance.",
                    "Reject absent, unverified, empty, wrong-resolution and wrong-camera masks.",
                    "Move the camera deliberately and confirm collection pauses until re-verification.",
                ],
                "docs/testing/privacy_failure_test.md, 38 focused passing tests and the completed live-site acceptance.",
                "Required configuration failures stop safely; deliberate movement remained blocked until final-position reverification.",
            ),
            gate(
                "A versioned, verified mask excludes all prohibited areas, "
                "retains adequate pose visibility and fails closed after any configuration or camera change."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "5",
            "Finish the privacy-first computer-vision pipeline",
            "Produce camera-local, pseudonymous skeletal and motion features "
            "from masked frames without retaining identities.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "5.1",
                "Enforce processing order",
                "COMPLETE",
                [
                    "Validate camera identity, resolution and verified mask.",
                    "Apply the mask before detector, tracker, pose estimator, display or feature writer.",
                    "Stop after sustained dropped frames rather than treating stale frames as current.",
                ],
                "src/aria/vision/pipeline.py and CV pipeline unit tests.",
                "No unmasked frame reaches downstream processing.",
            ),
            part(
                "5.2",
                "Complete detection and camera-local tracking",
                "COMPLETE",
                [
                    "Tune person detection for the downward Zone A view.",
                    "Maintain short-occlusion camera-local track IDs only.",
                    "Create a new ID after full exit/re-entry unless annotation later links segments for evaluation.",
                    "Measure ID switches, fragmentation and multiple-person behaviour.",
                ],
                "docs/testing/cv_pipeline_test.md and docs/testing/results/2026-08-01_phase_5_2_tracking_metrics.json: 14.283 FPS, 88.058 ms p95 frame age, zero read failures and accepted S1-S4 metrics.",
                "The evaluator passed with zero final ID switches, behaviour failures or collisions; initial fragmentation under heavier person-to-person occlusion remains recorded without biometric identity.",
            ),
            part(
                "5.3",
                "Complete pose and vision feature records",
                "COMPLETE",
                [
                    "Record frame timestamp, local track ID, bounding box and confidence.",
                    "Record keypoints, confidence/missingness and camera_id camera_a.",
                    "Add capture, detection, pose and total latency fields.",
                    "Add mask_config_version and explicit pose/frame availability.",
                ],
                "schemas/camera_track.schema.json, schema-valid JSONL writer and 112 passing unit tests.",
                "Feature records are versioned, privacy-safe and expose timing and availability for later windows.",
            ),
            part(
                "5.4",
                "Run live masked CV acceptance",
                "COMPLETE",
                [
                    "Run only after Phase 4 mask verification.",
                    "Test single and multiple consenting/controlled subjects.",
                    "Measure FPS, latency, drops, pose availability and track continuity.",
                ],
                "docs/testing/results/2026-07-31_camera_a_phase_5_4.md: "
                "120.108 seconds, 3,620 captured frames, zero read failures, "
                "6.969 effective FPS and 96.607% pose availability.",
                "The operator accepted the masked pipeline and its valid "
                "features, with close-overlap ID swaps, occasional duplicate "
                "IDs and approximately 7 FPS documented as limitations.",
            ),
            gate(
                "The live pipeline emits versioned, masked, camera-local skeletal "
                "features with measured latency and accepted tracking limitations. "
                "Phase 5 is complete."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "6",
            "Synchronise camera and sensors into multimodal windows",
            "Align Camera A features with ESP-A1/A2 without hiding jitter, "
            "missing packets or unavailable modalities.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "6.1",
                "Define the canonical time basis",
                "COMPLETE",
                [
                    "Use timezone-aware laptop receive/frame timestamps for alignment.",
                    "Keep ESP timestamp_ms only as uptime/diagnostic evidence.",
                    "Measure packet arrival jitter and frame timestamp consistency.",
                    "Record simultaneous non-research timing with Camera A, ESP-A1 and ESP-A2.",
                ],
                "1 August live run: 19.5-minute normal baseline, 585 windows; "
                "A1 55.940 ms and A2 68.731 ms mean absolute arrival jitter.",
                "Every active timestamp is timezone-aware SGT; naive and alternate-zone timestamps are rejected.",
            ),
            part(
                "6.2",
                "Create fixed multimodal windows",
                "COMPLETE",
                [
                    "Choose the initial window duration from observed activity timing.",
                    "Aggregate camera, A1 and A2 features separately before fusion.",
                    "Preserve packet/frame counts and availability per modality.",
                    "Exclude all lifecycle incident-linked window IDs during every accepted-session rebuild.",
                ],
                "Versioned feature_vector schema, deterministic window builder tests and 819 accepted windows after three incident exclusions.",
                "The same valid inputs and incident records rebuild the same 819 accepted windows.",
            ),
            part(
                "6.3",
                "Engineer fusion-ready features",
                "COMPLETE",
                [
                    "Include pose position/angles/movement summaries and confidence.",
                    "Include A1 PIR, distance validity/statistics and numerical-audio features.",
                    "Include A2 PIR and numerical-audio features with no synthetic distance.",
                    "Add cross-node agreement/contrast features only when calibrated and interpretable.",
                ],
                "Feature dictionary with units, ranges and missing-value rules.",
                "Every feature has a defined source and privacy justification.",
            ),
            part(
                "6.4",
                "Handle missing modalities explicitly",
                "COMPLETE",
                [
                    "Represent camera_available, pose_available, A1_available and A2_available.",
                    "Record missing packet/frame counts.",
                    "Never silently substitute zero for missing data.",
                ],
                "Missing-modality tests and window quality fields.",
                "Downstream models can distinguish missing data from real zero-valued observations.",
            ),
            gate(
                "Versioned windows align all available modalities reproducibly "
                "and expose timing quality and missingness explicitly."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "7",
            "Build safe session and collection tooling",
            "Turn the component pipeline into a controlled session lifecycle "
            "with preflight, pause, exclusion, stop and manifest evidence.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "7.1",
                "Define collection schemas",
                "COMPLETE",
                [
                    "Implement session manifest, annotation, prediction and incident schemas.",
                    "Version every schema and config reference.",
                    "Use pseudonymised participant IDs only.",
                ],
                "Historical Phase 7 schema versions remain immutable. Active formal "
                "sessions use session-manifest schema v8, annotation and prediction "
                "schemas v3, incident schema v5 and the role-neutral annotation protocol.",
                "All four versioned schemas reject invalid or incomplete records.",
            ),
            part(
                "7.2",
                "Implement preflight and start",
                "COMPLETE",
                [
                    "Verify consent/acknowledgement, camera identity/mode/mask/audio status, ESP identities/freshness and storage.",
                    "Create session_id and initial manifest before writers start.",
                    "Refuse startup on any privacy-critical failure.",
                ],
                "Fail-closed preflight adapters and CLI; SGT session IDs; atomic "
                "planned/running/aborted manifests; writer-order and returned-handle "
                "validation tests; 320 tests pass; on-site live preflight passed and "
                "a validated planned manifest was created before writers started.",
                "Software and on-site evidence confirm that a session cannot start "
                "unless every required control passes.",
            ),
            part(
                "7.3",
                "Implement pause, exclusion and clean stop",
                "COMPLETE",
                [
                    "Pause immediately for non-participant entry, camera movement, mask failure or equipment incident.",
                    "Mark affected intervals invalid and follow approved deletion procedures.",
                    "Close writers safely and record counts, gaps, files and incidents.",
                ],
                "Lifecycle controller, schema-valid incident records, persisted "
                "exclusion and recovery gates, version 3 manifest accounting and "
                "version 5 incident privacy rules; final summaries are writer-owned; "
                "duplicate incident IDs and output paths fail closed; 320 unit tests pass.",
                "No invalid interval is marked as usable participant data.",
            ),
            part(
                "7.4",
                "Run a non-research dry run",
                "COMPLETE",
                [
                    "Use a controlled empty/researcher-only scene after mask acceptance.",
                    "Exercise preflight, normal run, one-node loss, stream loss, privacy pause and clean stop.",
                    "Inspect all outputs for identities, prohibited media and inconsistent counts.",
                ],
                "Completed 27-minute dry-run manifest; three resolved incident records; "
                "counts, schemas, privacy scan and visual mask recovery verified.",
                "The whole session lifecycle behaves safely without participant data.",
            ),
            gate(
                "A non-research session completes end to end; deliberate failures "
                "produce the documented safe response and complete evidence."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "8",
            "Pass live-site acceptance before participant collection",
            "Combine ethics, placement, privacy, stability and operational "
            "controls into one explicit go/no-go decision.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "8.1",
                "Complete the live-site calibration record",
                "COMPLETE",
                [
                    "Consolidated the final A1/A2/camera placements and verified batamfast-v1 mask.",
                    "Recorded sensor calibration, packet and recovery statistics, and Camera A health.",
                    "Retained every failed target and the accepted ESP-A1/ESP-A2 public-network limitation without lowering or rewriting the result.",
                ],
                "docs/calibration/results/2026-08-02_phase_8_1_live_site_calibration.md.",
                "The dated consolidation record is complete and every component target has explicit evidence.",
            ),
            part(
                "8.2",
                "Complete privacy-failure and recovery tests",
                "COMPLETE",
                [
                    "Rejected absent, unverified, empty and out-of-bounds masks, wrong identity and wrong resolution.",
                    "Passed live stream-loss and mask-failure recovery with affected-window exclusion and privacy-critical deletion.",
                    "Required visual mask re-verification after movement or mask failure; no participant or raw-media evidence was retained.",
                ],
                "docs/testing/results/2026-08-02_phase_8_2_privacy_failure_recovery.md.",
                "Every tested privacy failure stops safely and recovery requires the correct verified state.",
            ),
            part(
                "8.3",
                "Complete the 90-minute combined acceptance run",
                "COMPLETE",
                [
                    "Completed both boards, Camera A, verified mask and health monitoring together for a 6 August 90-minute rerun.",
                    "Measured ESP-A1 at 98.185% and ESP-A2 at 97.963% against the unchanged 98% target.",
                    "Accepted ESP-A2's two-packet shortfall as a known operational limitation without rewriting it as a pass.",
                    "Recorded drops, longest gaps, restarts and camera performance; no participant data was collected.",
                ],
                "docs/testing/results/2026-08-06_zone_a_phase_8_3_endurance_rerun.md and linked evidence.",
                "The combined rerun is complete with partial acceptance; ESP-A2's delivery failure and the accepted operational limitation remain explicit.",
            ),
            part(
                "8.4",
                "Make the go/no-go collection decision",
                "COMPLETE",
                [
                    "Recorded the initial GO under Ethics Pack v4.3; Version 4.4 now "
                    "records the acknowledged three-class Part D amendment.",
                    "Confirmed valid site permission, pseudonymised IDs and consenting Counter Agents only.",
                    "Confirmed checklists, preflight, incident/exclusion records and deletion controls are ready.",
                    "Student Researcher recorded GO at 2026-08-02T16:44:13+08:00 without participant identities.",
                ],
                "docs/testing/results/2026-08-02_phase_8_4_go_decision.md.",
                "GO is recorded; each intended session must still pass its fresh preflight and checklist.",
            ),
            gate(
                "Phase 8 authorisation is complete. No participant-session writer "
                "starts unless that session's live preflight and checklist pass."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "9",
            "Run the approved pilot and participant sessions",
            "Collect only the minimum approved Zone A evidence needed for the "
            "research question, with immediate exclusions and traceable manifests.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "9.1",
                "Run one short approved pilot",
                "COMPLETE",
                [
                    "Completed approved pilot sessions with consenting Counter Agents during ordinary work and no recorded privacy incident.",
                    "Added lifecycle-owned localhost annotation controls with automatic SGT timestamps, two-second boundaries and missing-track closure.",
                    "Corrective recheck passed: all 9 schema-valid annotations matched their selected track in all 176 referenced windows.",
                    "Recorded 87.257% pose availability and retained the below-target ESP delivery as the accepted public-network limitation.",
                ],
                "docs/testing/results/2026-08-03_phase_9_1_pilot.md and completed pilot manifest zone_a_20260804T153952SGT_99e32732.",
                "Phase 9.1 is complete; the corrected workflow supports the approved method without identity inference or a collection-scope change.",
            ),
            part(
                "9.2",
                "Freeze collection settings",
                "COMPLETE",
                [
                    "Retained the completed first formal run under its historical "
                    "zone-a-collection-v3 profile without reinterpretation.",
                    "Accepted the persistent participant-card UI and consent-gated "
                    "in-session card addition, then froze the three-class method as "
                    "zone-a-collection-v5, accepted the split desktop layout as "
                    "zone-a-collection-v6, then froze polling-safe card controls as "
                    "zone-a-collection-v7.",
                    "Versioned the revised verified mask as batamfast-v2; active "
                    "manifests use schema version 8 and annotation/prediction records use version 3.",
                    "Formal live-session commands now reject changed CLI settings or hashed artifacts before preflight.",
                    "Recorded the accepted ESP delivery, pose-availability and local track-ID limitations without converting them into passes.",
                ],
                "config/collection.zone_a.v7.yaml, "
                "docs/data_collection/phase_9_3_v7_frozen_collection_settings.md and "
                "docs/testing/results/2026-08-05_phase_9_3_polling_safe_annotation_acceptance.md.",
                "Complete: formal sessions require one traceable, hash-recorded configuration; changes require a new version and affected recheck.",
            ),
            part(
                "9.3",
                "Run formal sessions",
                "COMPLETE",
                [
                    "Completed nine retained formal sessions between 4 and 10 August "
                    "2026: 8:00:20 wall-clock and 14:59:40 usable participant-labelled data.",
                    "Retained 26,990 usable two-second windows across nine pseudonymised "
                    "participants: 63.45% Serving/Processing, 31.66% Idle/Waiting and "
                    "4.89% Reaching/Handling.",
                    "Kept uncertainty, exclusions, the resolved first-run privacy incident, "
                    "ESP-A2 delivery and multi-person CV throughput explicit for later reporting.",
                    "Runs 3-7 retain v7 checksum 2efda050...; Runs 8-9 retain revised "
                    "v7 checksum 87758c7a... after wording-only artifact updates. Runtime settings were unchanged.",
                ],
                "Nine completed formal manifests, local pseudonymised session records, "
                "accepted UI evidence and the Version 4.4 ethics record.",
                "Complete: the revised eight-hour target is met and the retained "
                "collection is ready for Phase 10 reconstruction and audit.",
            ),
            gate(
                "Phase 9 is complete. Nine retained formal sessions provide a "
                "traceable Zone A collection for Phase 10 dataset reconstruction, "
                "privacy and quality audit, participant-level feature building and grouped splits."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "10",
            "Annotate, audit and freeze the dataset",
            "Create a reproducible model dataset without identity leakage, "
            "invalid intervals or hidden modality bias.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "10.1",
                "Apply the role-neutral annotation protocol",
                "COMPLETE",
                [
                    "Selected and approved nine completed formal sessions; excluded "
                    "pilots, dry runs, the aborted session and the no-annotation session.",
                    "Validated all 1,996 source annotations and produced 28,139 "
                    "participant-window records without rewriting source labels.",
                    "Mapped historical labels only in derived analysis and retained "
                    "uncertainty, exclusions and provenance.",
                    "Excluded selected-track absence and 461 conflicting track "
                    "assignments rather than inferring participant identity.",
                ],
                "Approved source inventory, normalised annotation windows, schema, "
                "normalisation report and acceptance evidence.",
                "Complete: 26,114 usable role-neutral windows are bounded, validated "
                "and traceable to approved source intervals.",
            ),
            part(
                "10.2",
                "Run data-quality and privacy audits",
                "COMPLETE",
                [
                    "Built 26,114 participant-specific feature rows across nine "
                    "pseudonymised participants and 1,847 activity episodes.",
                    "Reconciled 2,025 explicit exclusions and quantified camera, pose, "
                    "ESP-A1 and ESP-A2 availability without silent imputation.",
                    "Audited class balance by window and episode and retained the "
                    "minority Reaching/Handling limitation.",
                    "Found zero remaining schema, non-finite, track-scope, identity, "
                    "role, raw-media or retired-component failures.",
                ],
                "Participant-feature schema and builder, exclusion ledger, dataset "
                "card, build report and privacy/quality audit.",
                "Complete: every model input is schema-valid and no prohibited "
                "identifier or invalid interval remains.",
            ),
            part(
                "10.3",
                "Freeze external test and grouped development validation",
                "COMPLETE",
                [
                    "Locked 2,068 rows from the independent P0009-P0011 session "
                    "component for one final external test.",
                    "Assigned 24,046 development rows to eight fixed "
                    "leave-one-session-out validation folds.",
                    "Kept external participants, sessions, episodes and temporal "
                    "windows out of development; all 14 leakage checks pass.",
                    "Rebuilt the manifest and reports byte-identically and froze "
                    "their source and output hashes before model selection.",
                ],
                "Frozen split policy and schema, grouped split manifest, fold balance "
                "report, leakage audit and Phase 10.3 acceptance record.",
                "Complete: every row is assigned once, the external boundary is "
                "isolated and the grouped development folds rebuild deterministically.",
            ),
            gate(
                "Phase 10 is complete. The versioned dataset rebuilds "
                "deterministically, passes privacy and leakage audits and has a "
                "locked external test plus frozen development folds."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "11",
            "Train and evaluate baselines and fusion models",
            "Determine whether Camera A plus A1/A2 improves recognition over "
            "simpler baselines while preserving reproducibility and bounded claims.",
            "COMPLETE",
        )
    )
    story.extend(
        [
            part(
                "11.1",
                "Establish reproducible baselines",
                "COMPLETE",
                [
                    "Train majority, camera-only, A1-only and A1+A2 baselines.",
                    "Start with interpretable existing-dependency models such as Random Forest.",
                    "Tune only inside training/validation groups.",
                ],
                "Saved configs, seeds, metrics and model cards.",
                "Every final comparison has a reproducible baseline.",
            ),
            part(
                "11.2",
                "Train multimodal candidates",
                "COMPLETE",
                [
                    "Evaluated Camera+A1, Camera+A2 and Camera+A1+A2 with early feature fusion.",
                    "Reused the frozen eight development folds, seed and training-only preprocessing.",
                    "Retained Camera A-only because every fusion candidate had lower development macro F1.",
                ],
                "Frozen config, metrics, fitted models, model cards and acceptance record.",
                "The chosen model is justified by evidence, not complexity.",
            ),
            part(
                "11.3",
                "Run grouped evaluation and ablation",
                "COMPLETE",
                [
                    "Evaluated the frozen Camera-only model once on all 2,068 external rows.",
                    "Recorded per-class results, confusion matrix, reliability and local model latency.",
                    "Consolidated the frozen development ablation without evaluating alternatives externally.",
                    "Passed six synthetic missing-node/camera scenarios without stale prediction reuse.",
                ],
                "Frozen aggregate evaluation pack, ablation table and figure, reliability and latency metrics, privacy audit and missing-modality evidence.",
                "Complete: claims retain the isolated-component scope and the 19-row Reaching/Handling limitation.",
            ),
            gate(
                "A frozen model and evaluation pack support bounded conclusions "
                "about accuracy, modality contribution, reliability, privacy and latency."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "12",
            "Integrate live inference, dashboard and optional Firebase",
            "Present local predictions and health without turning the interface "
            "or cloud layer into an identity or video channel.",
            "IN PROGRESS",
        )
    )
    story.extend(
        [
            part(
                "12.1",
                "Build the local inference service",
                "COMPLETE",
                [
                    "Verified and loaded the frozen Camera-only model and versioned preprocessing contract.",
                    "Emitted schema-valid track activity, confidence and explicit unavailable states to idempotent local JSONL.",
                    "Passed offline/live parity, synthetic privacy and durable-delivery latency checks.",
                ],
                "Inference integration tests, privacy evidence and latency results.",
                "Complete: durable delivery p95 is 5.720 ms and output remains local and non-identifying.",
            ),
            part(
                "12.2",
                "Build the privacy-aware dashboard",
                "NEXT",
                [
                    "Show activity, confidence, camera FPS/mask status, A1/A2 freshness, packet loss and warnings.",
                    "Avoid video by default; if operator verification is required, show only the approved masked view.",
                    "Show uncertainty and exclusion state rather than presenting false certainty.",
                ],
                "Dashboard acceptance screenshots using synthetic/non-identifying data.",
                "The interface exposes health and privacy readiness without participant identity.",
            ),
            part(
                "12.3",
                "Keep Firebase optional and abstracted",
                "LATER",
                [
                    "Upload only explicitly approved abstracted features/predictions if required.",
                    "Never upload raw/masked video, raw audio, names or participant-code keys.",
                    "Test offline operation and retry/idempotency behaviour.",
                ],
                "Cloud-boundary tests and configuration documentation.",
                "The complete system works locally when Firebase is disabled.",
            ),
            gate(
                "The frozen model runs locally with visible health and uncertainty; "
                "optional cloud use remains abstracted and non-identifying."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "13",
            "Pass final end-to-end acceptance",
            "Demonstrate the complete product from sensors and masked camera "
            "through prediction, health, failure handling and clean shutdown. "
            "Implementation and the fail-closed evidence gate are ready; final "
            "live, stability and release evidence remain pending.",
            "PARTIAL",
        )
    )
    story.extend(
        [
            part(
                "13.1",
                "Run the final acceptance scenario",
                "PARTIAL",
                [
                    "Start from a clean boot and pass preflight.",
                    "Run Camera A, A1/A2, windows, model and dashboard together.",
                    "Verify multiple local tracks and selected ordinary activities.",
                    "Disconnect one node and confirm explicit degraded operation.",
                    "Trigger a privacy failure and confirm safe pause/stop.",
                    "Stop cleanly and validate manifests, counts and retained-data rules.",
                ],
                "Phase 13 contract, fail-closed assessor and privacy gate are implemented; final live report pending.",
                "Pending: every required normal and failure path has traceable final-build evidence.",
            ),
            part(
                "13.2",
                "Repeat session-length stability",
                "PARTIAL",
                [
                    "Measure FPS, packet loss, latency and storage.",
                    "Confirm no sustained degradation, unexplained gap or stale-state reuse.",
                ],
                "The 5,400-second duration and required metrics are frozen; final-build report pending.",
                "Pending: the final build remains stable for the full 5,400-second duration.",
            ),
            part(
                "13.3",
                "Freeze release artefacts",
                "PARTIAL",
                [
                    "Freeze code revision, configs, mask version, schemas, model and documentation.",
                    "Remove secrets, identities, prohibited media and unnecessary large artifacts.",
                    "Verify installation and demonstration on a clean environment.",
                ],
                "Artifact-hash and privacy checks are implemented; revisioned archive and clean-environment verification pending.",
                "Pending: a versioned clean-environment build matches the evaluated release.",
            ),
            gate(
                "Gate remains open until the traced final scenario, 5,400-second "
                "stability run and clean-environment release all pass."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        phase_header(
            "14",
            "Write, verify and submit the final project",
            "Turn the frozen implementation and evidence into an honest, "
            "traceable CM3070 report and demonstration package.",
            "LATER",
        )
    )
    story.extend(
        [
            part(
                "14.1",
                "Write the final report from frozen evidence",
                "LATER",
                [
                    "Document the scope change to Zone A and why retired zones/components remain historical.",
                    "Describe hardware, wireless camera transport, masking, timing, fusion, collection and evaluation.",
                    "Link every result claim to a generated table, figure or test record.",
                    "State privacy, sample-size, site, camera-angle and generalisation limitations.",
                ],
                "Complete report draft with traceable figures and tables.",
                "The report matches the final code, dataset and evaluation outputs.",
            ),
            part(
                "14.2",
                "Prepare a safe demonstration",
                "LATER",
                [
                    "Use synthetic or approved non-participant data as fallback.",
                    "Show pipeline health, masked processing and predictions without exposing identities.",
                    "Prepare a failure demonstration that proves privacy-safe stopping.",
                ],
                "Demonstration checklist and fallback package.",
                "The demo can run without prohibited or participant-identifying material.",
            ),
            part(
                "14.3",
                "Audit and submit",
                "LATER",
                [
                    "Run tests and rebuild all final artifacts.",
                    "Audit for credentials, identities, raw audio and prohibited video.",
                    "Verify every PDF/page, figure, link and archive on another environment.",
                    "Submit only the clean, frozen package.",
                ],
                "Final audit log and submission receipt.",
                "The submission is complete, reproducible, readable and privacy-safe.",
            ),
            gate(
                "The final report, code archive, evidence and demonstration agree "
                "on the active Zone A system and contain no prohibited material."
            ),
            PageBreak(),
        ]
    )

    story.extend(
        [
            P("APPENDIX A", "SectionLabel"),
            P("Phase 12.1 completion and next action", "PhaseTitle"),
            P(
                "Phase 12.1 is complete without changing the frozen model or evaluation "
                "contract. Continue with the privacy-aware dashboard path.",
                "PhaseObjective",
            ),
            data_table(
                ["Order", "Action", "Output"],
                [
                    [
                        "1",
                        "Complete: froze Camera A-only as the overall development choice and retained the Phase 11.2 fusion comparison.",
                        "Frozen model-selection pack",
                    ],
                    [
                        "2",
                        "Complete: ran the one-time external-test evaluation without changing the model, preprocessing or selection rules.",
                        "Locked external-test result",
                    ],
                    [
                        "3",
                        "Complete: reported classification, reliability, confusion matrix, privacy and local model latency results.",
                        "Grouped evaluation tables",
                    ],
                    [
                        "4",
                        "Complete: produced development ablation and passed all six synthetic missing-modality scenarios.",
                        "Phase 11.3 evaluation pack",
                    ],
                    [
                        "5",
                        "Complete: built and accepted the Phase 12.1 local inference service around the frozen Camera-only artifact and explicit unavailable state.",
                        "Versioned local inference service",
                    ],
                    [
                        "6",
                        "Next: build the Phase 12.2 privacy-aware dashboard from local predictions and health state.",
                        "Privacy-aware local dashboard",
                    ],
                ],
                widths=[16 * mm, 91 * mm, 54 * mm],
            ),
            Spacer(1, 6 * mm),
            callout(
                "CURRENT PROJECT GATE",
                "Phases 0, 1 and 3-11 are complete. Phase 2 remains PARTIAL because "
                "ESP-A2 finished two packets below the unchanged 98% delivery target; "
                "the limitation is retained. Participant collection is closed after "
                "nine retained sessions, and Phase 10 freezes 24,046 development rows "
                "plus 2,068 isolated external rows. Phase 11 is complete without "
                "post-result tuning: Camera A-only scored 0.442791 development macro F1 "
                "and 0.348179 external macro F1. Reaching/Handling scored 0.000000 on "
                "only 19 external rows and remains a strong limitation. The evaluation, "
                "ablation, reliability, local model latency, privacy and missing-modality "
                "evidence are recorded. Phase 12.1 local inference now passes frozen "
                "artifact, parity, degraded-mode, privacy and latency acceptance; durable "
                "delivery measured 5.720 ms p95. Recovering the exact historical v7 "
                "profile variants remains a provenance action. Phase 12.2 dashboard "
                "integration is next.",
                "teal",
            ),
            Spacer(1, 6 * mm),
            PageBreak(),
            P("Appendix B - authoritative active files", "PartTitle"),
            data_table(
                ["Area", "Files"],
                [
                    [
                        "Scope",
                        "AGENTS.md; README.md",
                    ],
                    [
                        "Firmware",
                        "firmware/esp_a/ESP_A_v1/ESP_A_v1.ino; "
                        "firmware/esp_a/ESP_A2_v1/ESP_A2_v1.ino",
                    ],
                    [
                        "Telemetry",
                        "schemas/esp_packet.schema.json; src/aria/ingestion/*; "
                        "docs/telemetry_schema.md",
                    ],
                    [
                        "Camera",
                        "config/cameras.batamfast.yaml; config/mediamtx.local.yaml; "
                        "scripts/test_cameras.py",
                    ],
                    [
                        "Privacy/CV",
                        "config/masks.batamfast.yaml; src/aria/cameras/privacy_mask.py; "
                        "src/aria/vision/*; config/bytetrack.zone_a.persistence.yaml; "
                        "docs/privacy/*; "
                        "docs/testing/results/2026-07-31_camera_a_phase_5_4.md",
                    ],
                    [
                        "Site/testing",
                        "docs/calibration/protocol.md; docs/calibration/results/*; "
                        "docs/testing/zone_a_integration_test.md; "
                        "docs/testing/wireless_camera_test.md; "
                        "docs/testing/live_site_acceptance_test.md",
                    ],
                    [
                        "Collection/dataset",
                        "config/collection.zone_a.v7.yaml; "
                        "config/phase_10_3_split_policy.json; "
                        "src/aria/collection/*; src/aria/dataset/*; "
                        "schemas/phase_10_*; docs/data_collection/*",
                    ],
                    [
                        "Modelling",
                        "config/phase_11_1_baselines.json; config/phase_11_2_multimodal.json; "
                        "config/phase_11_3_evaluation.json; src/aria/modeling/*; scripts/train_phase_11_1_baselines.py; "
                        "scripts/train_phase_11_2_multimodal.py; scripts/evaluate_phase_11_3.py; "
                        "scripts/generate_phase_11_3_ablation.py; scripts/test_phase_11_3_missing_modality.py; "
                        "outputs/evaluation/phase_11_3/*; docs/testing/results/2026-08-23_phase_11_3_external_evaluation.md",
                    ],
                    [
                        "Inference",
                        "config/phase_12_1_inference.json; src/aria/inference/*; "
                        "scripts/run_local_inference.py; scripts/accept_phase_12_1.py; "
                        "tests/unit/test_phase_12_1_inference_*; "
                        "docs/data_collection/phase_12_1_inference_contract.md; "
                        "docs/testing/results/2026-08-24_phase_12_1_local_inference_acceptance.md",
                    ],
                ],
                widths=[37 * mm, 124 * mm],
            ),
        ]
    )
    return story

def generate(output_path):
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    frame = Frame(
        MARGIN_X,
        MARGIN_BOTTOM,
        PAGE_WIDTH - 2 * MARGIN_X,
        PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        title="ARIA Zone A Step-by-Step Delivery Pipeline",
        author="ARIA Project",
        subject="CM3070 final-project execution roadmap",
        creator="ARIA project PDF generator",
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
    )
    doc.addPageTemplates(
        [
            PageTemplate(
                id="Cover",
                frames=[frame],
                onPage=cover_page,
                autoNextPageTemplate="Body",
            ),
            PageTemplate(
                id="Body",
                frames=[frame],
                onPage=header_footer,
            ),
        ]
    )
    doc.build(build_story())
    print(f"Generated {output_path}")

def main():
    parser = ArgumentParser(
        description="Generate the current ARIA Zone A phased pipeline PDF."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args()
    generate(args.output)

if __name__ == "__main__":
    main()
