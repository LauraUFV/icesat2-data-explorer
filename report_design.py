from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path
from typing import Any, Callable


PALETTES = {
    "ATL03": ("#7454a1", "#f3eef9"),
    "ATL08": ("#4f8f32", "#eff7eb"),
    "ATL13": ("#197fa3", "#edf7fa"),
    "ATL24": ("#0f6688", "#edf6f9"),
    "MODEL_TIDE": ("#176e96", "#edf6fb"),
}

PLUGIN_DERIVED_FIELDS = {
    "height_ortho",
    "geoid_mean_tide",
    "atl03_cnf_name",
    "quality_name",
    "class_name",
    "tide_ocean_model_m",
    "tide_time_utc",
    "tide_valid",
    "tide_model",
    "tide_method",
}

POSITION_FIELDS = {
    "time", "time_ns", "latitude", "longitude", "x_atc", "y_atc",
}
ORBIT_FIELDS = {
    "spot", "cycle", "region", "rgt", "gt", "srcid", "ph_index",
    "index_ph", "segment_id_beg", "refid", "name",
}
DATABASE_FIELDS = {"fid", "geometry"}


def date_only(
    value: Any,
) -> str:
    if value is None:
        return "—"

    if hasattr(
        value,
        "date",
    ):
        try:
            return value.date().isoformat()
        except Exception:
            pass

    if hasattr(
        value,
        "isoformat",
    ):
        try:
            text = str(
                value.isoformat()
            )
        except Exception:
            text = str(value)
    else:
        text = str(value)

    match = re.search(
        r"\d{4}-\d{2}-\d{2}",
        text,
    )

    return (
        match.group(0)
        if match
        else text
    )


def date_range_text(
    start_value: Any,
    end_value: Any,
) -> str:
    return (
        date_only(start_value)
        + " to "
        + date_only(end_value)
    )


def value_text(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.8g}"
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return str(value)


def logo_data_uri() -> str:
    path = Path(__file__).resolve().parent / "icons" / "plugin.svg"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return "data:image/svg+xml;base64," + encoded


def palette(product: str) -> tuple[str, str]:
    return PALETTES.get(product.upper(), ("#146b8b", "#edf6f8"))


def report_css(accent: str, accent_soft: str) -> str:
    return f"""
    :root {{
        color-scheme: light;
        --ink: #24343f;
        --muted: #61717c;
        --line: #dce4e8;
        --panel: #f7f9fa;
        --accent: {accent};
        --accent-soft: {accent_soft};
        --ok: #2f7d3d;
        --ok-soft: #edf7ef;
        --warn: #9a6400;
        --warn-soft: #fff6dc;
        --info: #356b83;
        --info-soft: #edf5f8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
        margin: 0;
        color: var(--ink);
        background: #eef2f4;
        font-family: "Segoe UI", Arial, sans-serif;
        line-height: 1.48;
    }}
    .page {{ max-width: 1240px; margin: 24px auto; background: white; box-shadow: 0 8px 30px rgba(31,49,60,.10); }}
    header {{ padding: 30px 40px 24px; background: linear-gradient(135deg, var(--accent-soft), #fff 70%); border-bottom: 5px solid var(--accent); }}
    .brand {{ display: flex; align-items: center; gap: 16px; }}
    .brand img {{ width: 58px; height: 58px; }}
    h1 {{ margin: 0; font-size: 29px; line-height: 1.15; color: #173e50; }}
    .subtitle {{ margin: 5px 0 0; color: var(--muted); }}
    .author-card {{ margin-top: 20px; display: inline-block; padding: 10px 14px; border: 1px solid var(--line); border-radius: 8px; background: rgba(255,255,255,.82); }}
    .author-card strong {{ color: #173e50; }}
    main {{ padding: 28px 40px 48px; }}
    section {{ margin: 0 0 30px; }}
    h2 {{ margin: 0 0 13px; font-size: 20px; color: #173e50; border-bottom: 1px solid var(--line); padding-bottom: 7px; }}
    h3 {{ color: #234d60; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(175px, 1fr)); gap: 12px; margin: 0 0 28px; }}
    .metric {{ border: 1px solid var(--line); border-top: 4px solid var(--accent); border-radius: 8px; padding: 13px 14px; background: white; min-height: 88px; }}
    .metric-label {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .metric-value {{ display: block; margin-top: 6px; font-size: 19px; font-weight: 700; color: #173e50; overflow-wrap: anywhere; }}
    .notice {{ padding: 13px 15px; border-left: 4px solid var(--accent); background: var(--accent-soft); border-radius: 5px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; overflow-wrap: anywhere; }}
    th {{ background: var(--panel); font-weight: 650; color: #324c59; }}
    .key-value th {{ width: 28%; }}
    .table-scroll {{ overflow-x: auto; }}
    .field-table {{ min-width: 880px; table-layout: auto; }}
    .field-table th:nth-child(1) {{ min-width: 150px; }}
    .field-table th:nth-child(3) {{ min-width: 260px; }}
    .field-table th:nth-child(5) {{ min-width: 300px; }}
    .aoi-map {{ margin: 16px 0 0; }}
    .aoi-map img {{ display: block; width: 100%; max-height: 560px; object-fit: contain; border: 1px solid var(--line); border-radius: 8px; background: #f4f7f8; }}
    .aoi-map figcaption {{ margin-top: 7px; color: var(--muted); font-size: 12px; }}
    code, pre {{ font-family: Consolas, "Courier New", monospace; }}
    code {{ color: #174f68; }}
    pre {{ background: #14212a; color: #eff5f7; padding: 16px; border-radius: 7px; overflow-x: auto; white-space: pre-wrap; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; white-space: nowrap; }}
    .badge-source {{ background: var(--accent-soft); color: var(--accent); }}
    .badge-plugin {{ background: #eef7e9; color: #497e2f; }}
    .badge-db {{ background: #f1f2f4; color: #59636e; }}
    .status-pass {{ background: var(--ok-soft); color: var(--ok); }}
    .status-warning {{ background: var(--warn-soft); color: var(--warn); }}
    .status-info {{ background: var(--info-soft); color: var(--info); }}
    details {{ margin: 10px 0; border: 1px solid var(--line); border-radius: 7px; background: white; }}
    summary {{ cursor: pointer; padding: 11px 13px; font-weight: 700; color: #254e61; background: var(--panel); }}
    details > .details-body {{ padding: 12px 13px; }}
    .bar-track {{ width: 100%; height: 8px; background: #e9eef1; border-radius: 5px; overflow: hidden; }}
    .bar-fill {{ height: 100%; background: var(--accent); }}
    footer {{ border-top: 1px solid var(--line); padding: 20px 40px 28px; color: var(--muted); font-size: 12px; }}
    @page {{ size: A4 landscape; margin: 12mm; }}
    @media print {{
        body {{ background: white; }}
        .page {{ max-width: none; margin: 0; box-shadow: none; }}
        header {{ background: white; padding: 15px 18px; }}
        main {{ padding: 16px 18px; }}
        footer {{ padding: 14px 18px; }}
        section, .metric, details {{ break-inside: avoid; }}
        details > summary {{ display: none; }}
        details > .details-body {{ display: block; padding: 0; }}
        .field-table {{ min-width: 0; font-size: 8.5px; }}
        pre {{ color: black; background: #f2f2f2; border: 1px solid #ccc; }}
    }}
    """


def table_rows(items: list[tuple[str, Any]]) -> str:
    return "".join(
        "<tr><th>" + html.escape(str(label)) + "</th><td>" +
        html.escape(value_text(value)) + "</td></tr>"
        for label, value in items
    )


def summary_cards(items: list[tuple[str, Any]]) -> str:
    cards = []
    for label, value in items:
        cards.append(
            '<article class="metric"><span class="metric-label">'
            + html.escape(str(label))
            + '</span><span class="metric-value">'
            + html.escape(value_text(value))
            + '</span></article>'
        )
    return '<div class="summary-grid">' + "".join(cards) + '</div>'


def status_badge(status: str) -> str:
    key = status.lower()
    css = "status-pass" if key == "pass" else "status-warning" if key == "warning" else "status-info"
    return f'<span class="badge {css}">{html.escape(status)}</span>'


def quality_table(checks: list[tuple[str, Any, str, str]]) -> str:
    rows = []
    for check, result, status, note in checks:
        rows.append(
            "<tr><td>" + html.escape(str(check)) + "</td><td>" +
            html.escape(value_text(result)) + "</td><td>" + status_badge(status) +
            "</td><td>" + html.escape(str(note)) + "</td></tr>"
        )
    return ('<table><thead><tr><th>Check</th><th>Result</th><th>Status</th><th>Interpretation</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>')


def field_source(product: str, name: str, description: str) -> tuple[str, str]:
    if name in DATABASE_FIELDS:
        return "GeoPackage", "badge-db"
    if name in PLUGIN_DERIVED_FIELDS:
        return "Plugin-derived", "badge-plugin"
    if product == "MODEL_TIDE" and name.startswith("tide_"):
        return "Plugin / pyTMD", "badge-plugin"
    if "not mapped" in description.lower():
        return "Returned field", "badge-db"
    if name == "srcid":
        return "SlideRule", "badge-source"
    return "ICESat-2 / SlideRule", "badge-source"


def field_group(product: str, name: str) -> str:
    if name in DATABASE_FIELDS:
        return "Database and geometry"
    if name in PLUGIN_DERIVED_FIELDS:
        return "Plugin-derived attributes"
    if name in POSITION_FIELDS:
        return "Position and time"
    if name in ORBIT_FIELDS:
        return "Orbit and provenance"
    lowered = name.lower()
    if any(token in lowered for token in ("geoid", "tide", "dac", "free2mean")):
        return "Geophysical corrections"
    if any(token in lowered for token in ("quality", "confidence", "class", "flag", "invalid", "sigma", "cnf", "snowcover", "landcover")):
        return "Classification, uncertainty and quality"
    return "Scientific measurements"


def attribute_dictionary(
    product: str,
    field_schema: list[dict[str, Any]],
    null_counts: dict[str, int],
    resolver: Callable[[str, str], dict[str, str]],
) -> str:
    if not field_schema:
        return "<p>No attribute fields were reported.</p>"

    # NULL counts remain available for Quality assessment, but are
    # intentionally omitted from the Attribute dictionary.
    _ = null_counts

    groups: dict[str, list[str]] = {}

    for item in field_schema:
        name = str(
            item.get(
                "name",
                "",
            )
        )
        definition = resolver(
            product,
            name,
        )
        source, source_css = field_source(
            product,
            name,
            definition["description"],
        )
        row = (
            "<tr><td><code>"
            + html.escape(name)
            + "</code></td>"
            '<td><span class="badge '
            + source_css
            + '">'
            + html.escape(source)
            + "</span></td>"
            "<td>"
            + html.escape(
                definition["description"]
            )
            + "</td>"
            "<td>"
            + html.escape(
                definition["units"]
            )
            + "</td>"
            "<td>"
            + html.escape(
                definition["notes"]
            )
            + "</td></tr>"
        )
        groups.setdefault(
            field_group(
                product,
                name,
            ),
            [],
        ).append(
            row
        )

    order = [
        "Position and time",
        "Scientific measurements",
        "Geophysical corrections",
        "Classification, uncertainty and quality",
        "Orbit and provenance",
        "Plugin-derived attributes",
        "Database and geometry",
    ]
    blocks = []

    for group in order:
        rows = groups.get(
            group
        )

        if not rows:
            continue

        blocks.append(
            '<details open><summary>'
            + html.escape(group)
            + f' ({len(rows)} fields)</summary>'
            '<div class="details-body table-scroll">'
            '<table class="field-table"><thead><tr>'
            '<th>Field</th><th>Source</th><th>Description</th>'
            '<th>Units</th><th>Interpretation / notes</th>'
            '</tr></thead><tbody>'
            + "".join(rows)
            + "</tbody></table></div></details>"
        )

    return "".join(
        blocks
    )

