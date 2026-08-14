from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .field_definitions import (
    AUTHOR_LINE,
    REPORT_AUTHOR,
    REPORT_INSTITUTION,
    REPORT_ROLE,
    get_field_definition,
    get_value_label,
)
from .report_design import (
    attribute_dictionary,
    date_only,
    date_range_text,
    logo_data_uri,
    palette,
    quality_table,
    report_css,
    summary_cards,
    table_rows,
    value_text,
)


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # nosec B110
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # nosec B110
            pass
    return str(value)


def _statistics_table(statistics: dict[str, Any]) -> str:
    rows = []
    for field_name, values in statistics.items():
        if not isinstance(values, dict):
            continue
        rows.append(
            "<tr><td><code>" + html.escape(str(field_name)) + "</code></td>"
            "<td>" + html.escape(value_text(values.get("valid_count", 0))) + "</td>"
            "<td>" + html.escape(value_text(values.get("minimum"))) + "</td>"
            "<td>" + html.escape(value_text(values.get("maximum"))) + "</td>"
            "<td>" + html.escape(value_text(values.get("mean"))) + "</td>"
            "<td>" + html.escape(value_text(values.get("median"))) + "</td></tr>"
        )
    if not rows:
        return "<p>No product statistics were reported.</p>"
    return ('<div class="table-scroll"><table><thead><tr><th>Field</th><th>Valid</th>'
            '<th>Minimum</th><th>Maximum</th><th>Mean</th><th>Median</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


def _classification_table(product: str, category_counts: dict[str, Any]) -> str:
    rows = []
    for field_name, values in category_counts.items():
        if not isinstance(values, dict) or not values:
            continue
        maximum = max(int(v) for v in values.values()) or 1
        def sort_key(item):
            try:
                return (0, int(item[0]))
            except (TypeError, ValueError):
                return (1, str(item[0]))
        for code, count in sorted(values.items(), key=sort_key):
            label = get_value_label(product, field_name, code) or "See source documentation"
            width = min(100.0, 100.0 * int(count) / maximum)
            rows.append(
                "<tr><td><code>" + html.escape(str(field_name)) + "</code></td>"
                "<td>" + html.escape(str(code)) + "</td><td>" + html.escape(label) + "</td>"
                "<td>" + html.escape(value_text(count)) + "</td>"
                f'<td><div class="bar-track"><div class="bar-fill" style="width:{width:.2f}%"></div></div></td></tr>'
            )
    if not rows:
        return ""
    return ('<section><h2>Classification summary</h2><div class="table-scroll"><table>'
            '<thead><tr><th>Field</th><th>Code</th><th>Meaning</th><th>Count</th><th>Relative count</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div></section>')


def _vertical_reference(product: str) -> str:
    if product == "ATL03":
        return '''<section><h2>Vertical reference and geophysical fields</h2>
        <div class="notice"><strong>Calculated orthometric photon height</strong><br>
        <code>height_ortho = height − geoid</code>, using the ATL03 EGM2008 tide-free geoid.
        The original <code>height</code> is preserved. <code>tide_ocean</code> is stored separately and is not applied.</div>
        <table class="key-value"><tr><th>Ellipsoidal photon height</th><td><code>height</code></td></tr>
        <tr><th>Tide-free geoid</th><td><code>geoid</code></td></tr>
        <tr><th>Orthometric photon height</th><td><code>height_ortho</code></td></tr>
        <tr><th>Mean-tide geoid</th><td><code>geoid_mean_tide = geoid + geoid_free2mean</code></td></tr>
        <tr><th>Ocean tide</th><td><code>tide_ocean</code> — preserved, not applied</td></tr></table></section>'''
    if product == "ATL13":
        return '''<section><h2>Vertical reference</h2><div class="notice">
        <code>ht_ortho</code> is the orthometric water-surface height and <code>ht_water_surf</code>
        is the ellipsoidal water-surface height. <code>water_depth</code> is available only where a bottom was detected.</div></section>'''
    if product == "ATL24":
        return '''<section><h2>Vertical and depth reference</h2><div class="notice">
        The original ATL24 <code>depth</code>, <code>ellipse_h</code>, <code>ortho_h</code> and
        <code>surface_h</code> attributes are preserved. No model tide is applied during product acquisition.</div></section>'''
    return ""


def _quality_checks(product: str, data: dict[str, Any], null_counts: dict[str, int], warnings: list[str]):
    total = int(data.get("record_count", 0) or 0)
    visible = int(data.get("visible_count", 0) or 0)
    checks = [
        ("Output contains records", total, "Pass" if total > 0 else "Warning", "A non-empty output is expected."),
        ("Visible records after local filters", visible, "Pass" if visible > 0 else "Warning", "Local filters can hide records without deleting them."),
        ("Processing warnings", len(warnings), "Pass" if not warnings else "Warning", "Review the warnings section when present."),
    ]
    required = {"ATL03": "height", "ATL08": "h_te_median", "ATL13": "ht_ortho", "ATL24": "depth"}.get(product)
    for field in ("longitude", "latitude", "time_ns", required):
        if not field:
            continue
        missing = null_counts.get(field)
        if missing is None:
            checks.append((f"NULL values in {field}", "Not evaluated", "Info", "The task did not report a NULL count for this field."))
        else:
            checks.append((f"NULL values in {field}", missing, "Pass" if int(missing) == 0 else "Warning", "Missing values can limit spatial or scientific analysis."))
    return checks


def export_processing_report(output_path: str, report_data: dict[str, Any]) -> Path:
    output_file = Path(output_path).expanduser().resolve()
    report_path = output_file.with_name(output_file.stem + "_report.html")
    generated_at = datetime.now(timezone.utc).isoformat()
    product = str(report_data.get("product", "ICESat-2"))
    title = f"{product} Processing Report"
    accent, accent_soft = palette(product)

    field_schema = report_data.get("field_schema", []) or [
        {"name": str(name), "type": "—"} for name in report_data.get("returned_fields", [])
    ]
    null_counts = report_data.get("null_counts", {}) or {}
    warnings = [str(item) for item in report_data.get("warnings", [])]
    notes = [str(item) for item in report_data.get("scientific_notes", [])]
    stats = report_data.get("product_statistics", {}) or {}
    categories = report_data.get("category_counts", {}) or {}

    summary = summary_cards([
        ("Product", product),
        ("Stored records", report_data.get("record_count")),
        ("Visible records", report_data.get("visible_count")),
        (
            "Date range",
            date_range_text(
                report_data.get("start_date"),
                report_data.get("end_date"),
            ),
        ),
        ("Output layer", report_data.get("layer_name")),
        ("CRS", report_data.get("crs")),
    ])

    provenance = [
        ("Plugin", report_data.get("plugin_name")),
        ("Plugin version", report_data.get("plugin_version")),
        ("QGIS version", report_data.get("qgis_version")),
        ("Product version context", report_data.get("product_version_context")),
        ("Data source", report_data.get("data_source")),
        ("SlideRule endpoint", report_data.get("sliderule_endpoint")),
        ("Processing status", report_data.get("status", "Completed")),
        ("Report generated (UTC)", generated_at),
        ("Output GeoPackage", str(output_file)),
    ]
    request = [
        (
            "Start date",
            date_only(
                report_data.get("start_date")
            ),
        ),
        (
            "End date",
            date_only(
                report_data.get("end_date")
            ),
        ),
        (
            "Area of interest",
            report_data.get("area_type")
            or "Polygon used in the SlideRule request",
        ),
        ("Display field", report_data.get("display_field")),
        ("Local display filter", report_data.get("subset_string")),
        ("Server-side filters", report_data.get("server_filters")),
    ]

    aoi_map_data_uri = report_data.get(
        "aoi_map_data_uri"
    )
    aoi_map_caption = report_data.get(
        "aoi_map_caption"
    )

    if aoi_map_data_uri:
        aoi_map_html = (
            '<figure class="aoi-map"><img src="'
            + html.escape(
                str(aoi_map_data_uri),
                quote=True,
            )
            + '" alt="Area of interest overview">'
            + (
                "<figcaption>"
                + html.escape(
                    str(aoi_map_caption)
                )
                + "</figcaption>"
                if aoi_map_caption
                else ""
            )
            + "</figure>"
        )
    else:
        aoi_map_html = (
            '<div class="notice">'
            "The area-of-interest map was not available. "
            "The request geometry remains recorded in Technical details."
            "</div>"
        )

    index_html = ""
    if report_data.get("index_ph_status") is not None:
        index_html = '<section><h2>ATL03 linkage readiness</h2><table class="key-value">' + table_rows([
            ("index_ph returned", report_data.get("index_ph_status")),
            ("Purpose", "Trace an ATL24 record to the source ATL03 photon together with source and beam identifiers."),
        ]) + '</table></section>'

    stats_html = ('<section><h2>Product statistics</h2>' + _statistics_table(stats) + '</section>') if stats else ""
    classification_html = _classification_table(product, categories)
    notes_html = '<ul>' + ''.join('<li>' + html.escape(note) + '</li>' for note in notes) + '</ul>' if notes else '<p>No additional scientific notes.</p>'
    warning_html = '<p>No warnings were reported.</p>' if not warnings else '<ul>' + ''.join('<li>' + html.escape(w) + '</li>' for w in warnings) + '</ul>'
    request_parameters = json.dumps(report_data.get("request_parameters", {}), ensure_ascii=False, indent=2, default=_json_default)
    batch_processing_html = ""
    if product == "ATL03" and report_data.get("processing_strategy"):
        beam_split_resources = report_data.get(
            "beam_split_resources", []
        ) or []
        batch_rows = [
            ("Processing strategy", report_data.get("processing_strategy")),
            ("Resource discovery", report_data.get("resource_discovery")),
            ("Granules discovered", report_data.get("granules_discovered")),
            ("Granules processed", report_data.get("granules_processed")),
            ("Granules with photons", report_data.get("granules_with_data")),
            ("Granules without photons", report_data.get("granules_without_data")),
            ("Automatic retries", report_data.get("retry_count")),
            ("Granules split by beam", len(beam_split_resources)),
        ]
        statistics_note = report_data.get("statistics_note")
        statistics_note_html = (
            '<div class="notice">'
            + html.escape(str(statistics_note))
            + "</div>"
            if statistics_note
            else ""
        )
        batch_processing_html = (
            "<section><h2>Large-request processing</h2>"
            '<table class="key-value">'
            + table_rows(batch_rows)
            + "</table>"
            + statistics_note_html
            + "</section>"
        )

    logo = logo_data_uri()

    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>
    <style>{report_css(accent, accent_soft)}</style></head><body><div class="page">
    <header><div class="brand">{f'<img src="{logo}" alt="Plugin icon">' if logo else ''}<div>
    <h1>{html.escape(title)}</h1><p class="subtitle">Reproducible acquisition, processing and attribute documentation.</p></div></div>
    <div class="author-card"><strong>{html.escape(REPORT_AUTHOR)}</strong><br>{html.escape(REPORT_ROLE)}<br>{html.escape(REPORT_INSTITUTION)}</div></header>
    <main>{summary}
    <section><h2>Executive summary</h2><div class="notice">The output contains <strong>{html.escape(value_text(report_data.get('record_count')))}</strong> stored {html.escape(product)} records. The original scientific fields are preserved; plugin-derived attributes are identified separately in the attribute dictionary.</div></section>
    <section><h2>Data source and provenance</h2><table class="key-value">{table_rows(provenance)}</table></section>
    <section><h2>Request and visualization</h2>
    <table class="key-value">{table_rows(request)}</table>
    {aoi_map_html}</section>
    {_vertical_reference(product)}{batch_processing_html}{index_html}{stats_html}{classification_html}
    <section><h2>Quality assessment</h2>{quality_table(_quality_checks(product, report_data, null_counts, warnings))}</section>
    <section><h2>Attribute dictionary</h2><p>Fields are grouped by purpose. The source badge distinguishes ICESat-2/SlideRule attributes from values calculated by the plugin and database fields.</p>
    {attribute_dictionary(product, field_schema, null_counts, get_field_definition)}</section>
    <section><h2>Warnings</h2>{warning_html}</section>
    <section><h2>Scientific notes</h2>{notes_html}</section>
    <section><h2>Technical details</h2>
    <details><summary>Area-of-interest geometry (WKT)</summary>
    <div class="details-body"><pre>{html.escape(value_text(report_data.get("polygon_wkt")))}</pre></div></details>
    <details><summary>Complete SlideRule request parameters</summary>
    <div class="details-body"><pre>{html.escape(request_parameters)}</pre></div></details></section>
    </main><footer>Prepared by {html.escape(AUTHOR_LINE)}. Automatically generated by ICESat-2 Data Explorer. This is a technical processing record and not an official institutional document of UFV or NASA.</footer>
    </div></body></html>'''
    report_path.write_text(document, encoding="utf-8")
    return report_path
