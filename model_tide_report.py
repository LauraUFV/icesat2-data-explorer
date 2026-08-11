from __future__ import annotations

import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .field_definitions import (
    AUTHOR_LINE,
    REPORT_AUTHOR,
    REPORT_INSTITUTION,
    REPORT_ROLE,
    get_field_definition,
)
from .report_design import (
    attribute_dictionary,
    date_range_text,
    logo_data_uri,
    palette,
    quality_table,
    report_css,
    summary_cards,
    table_rows,
    value_text,
)


def _number(value: Any, decimals: int = 6) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(number):
        return "—"
    return f"{number:.{decimals}f}"


def _definition(product: str, name: str) -> dict[str, str]:
    definition = get_field_definition("MODEL_TIDE", name)
    if "not mapped" in definition["description"]:
        definition = get_field_definition("ATL24", name)
    return definition


def export_model_tide_report(output_path: str, data: dict[str, Any]) -> Path:
    output_file = Path(output_path).expanduser().resolve()
    report_path = output_file.with_name(output_file.stem + "_tide_report.html")
    total = int(data.get("total_records", 0) or 0)
    valid = int(data.get("valid_records", 0) or 0)
    invalid = int(data.get("invalid_records", 0) or 0)
    rate = 100.0 * valid / total if total else 0.0
    corrected = int(
        data.get(
            "corrected_depth_records",
            0,
        )
        or 0
    )
    accent, accent_soft = palette("MODEL_TIDE")
    logo = logo_data_uri()

    summary = summary_cards([
        ("Workflow", "ATL24 + model tide"),
        ("Total photons", total),
        ("Valid tide values", valid),
        ("Tide-corrected depths", corrected),
        ("Valid rate", f"{rate:.3f}%"),
        ("Tide model", data.get("model_id")),
        ("Interpolation", data.get("method")),
        (
            "Date range",
            date_range_text(
                data.get("first_time_utc"),
                data.get("last_time_utc"),
            ),
        ),
    ])
    provenance = [
        ("Plugin", "ICESat-2 Data Explorer"),
        ("Report generated (UTC)", datetime.now(timezone.utc).isoformat()),
        ("Source GeoPackage", data.get("source_path")),
        ("Source layer", data.get("source_layer")),
        ("Output GeoPackage", str(output_file)),
        ("Output layer", data.get("output_layer")),
        ("Original depth modified", False),
    ]
    model = [
        ("Tide engine", "pyTMD"),
        ("pyTMD version", data.get("pytmd_version")),
        ("Tide model", data.get("model_id")),
        ("Model distribution", data.get("model_distribution")),
        ("Model format", "NetCDF"),
        ("Interpolation", data.get("method")),
        ("Spatial extrapolation enabled", data.get("extrapolate")),
        ("Input CRS", "EPSG:4326"),
        ("Input time standard", "UTC datetime"),
        ("Output units", "m"),
        (
            "Corrected-depth field",
            "depth_tide_corrected_m",
        ),
        (
            "Corrected-depth formula",
            data.get(
                "corrected_depth_formula"
            )
            or "depth - tide_ocean_model_m",
        ),
    ]
    results = [
        ("Total ATL24 photons", total),
        ("Valid tide values", valid),
        ("Invalid/NULL tide values", invalid),
        ("Minimum tide (m)", _number(data.get("minimum_tide_m"))),
        ("Maximum tide (m)", _number(data.get("maximum_tide_m"))),
        ("Mean tide (m)", _number(data.get("mean_tide_m"))),
        ("Median tide (m)", _number(data.get("median_tide_m"))),
        (
            "Tide-corrected depth records",
            corrected,
        ),
        (
            "Minimum tide-corrected depth (m)",
            _number(
                data.get(
                    "minimum_corrected_depth_m"
                )
            ),
        ),
        (
            "Maximum tide-corrected depth (m)",
            _number(
                data.get(
                    "maximum_corrected_depth_m"
                )
            ),
        ),
        (
            "Mean tide-corrected depth (m)",
            _number(
                data.get(
                    "mean_corrected_depth_m"
                )
            ),
        ),
        ("First input time (UTC)", data.get("first_time_utc")),
        ("Last input time (UTC)", data.get("last_time_utc")),
    ]
    warnings = [str(v) for v in data.get("warnings", [])]
    warning_html = '<p>No warnings were reported.</p>' if not warnings else '<ul>' + ''.join('<li>' + html.escape(v) + '</li>' for v in warnings) + '</ul>'
    checks = [
        ("Source photons available", total, "Pass" if total > 0 else "Warning", "A non-empty source layer is required."),
        ("Finite model tide values", valid, "Pass" if valid > 0 else "Warning", "Only finite outputs are marked valid."),
        ("Invalid/NULL tide values", invalid, "Pass" if invalid == 0 else "Warning", "Invalid values remain NULL and are identified by tide_valid."),
        (
            "Tide-corrected depth values",
            corrected,
            "Pass" if corrected > 0 else "Warning",
            "A corrected value requires both a source depth and a finite model tide.",
        ),
        ("Original ATL24 depth preserved", True, "Pass", "The workflow writes a separate derived column without changing depth."),
    ]
    technical = json.dumps(data.get("engine_summary", {}), ensure_ascii=False, indent=2, default=str)

    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1"><title>ATL24 Model Tide Report</title>
    <style>{report_css(accent, accent_soft)}</style></head><body><div class="page">
    <header><div class="brand">{f'<img src="{logo}" alt="Plugin icon">' if logo else ''}<div><h1>ATL24 Model Tide Report</h1>
    <p class="subtitle">GOT4.10c prediction at ATL24 photon coordinates and UTC times.</p></div></div>
    <div class="author-card"><strong>{html.escape(REPORT_AUTHOR)}</strong><br>{html.escape(REPORT_ROLE)}<br>{html.escape(REPORT_INSTITUTION)}</div></header>
    <main>{summary}
    <section><h2>Executive summary</h2><div class="notice"><strong>{valid:,}</strong> of <strong>{total:,}</strong> ATL24 photons received a finite model tide value ({rate:.4f}%). A separate <code>depth_tide_corrected_m</code> value was created for <strong>{corrected:,}</strong> photons using <code>depth - tide_ocean_model_m</code>. The source <code>depth</code> field was not modified.</div></section>
    <section><h2>Data source and provenance</h2><table class="key-value">{table_rows(provenance)}</table></section>
    <section><h2>Model and processing</h2><table class="key-value">{table_rows(model)}</table></section>
    <section><h2>Results</h2><table class="key-value">{table_rows(results)}</table></section>
    <section><h2>Quality assessment</h2>{quality_table(checks)}</section>
    <section><h2>Vertical-reference note</h2><div class="notice"><code>tide_ocean_model_m</code> is a modeled astronomical tide elevation. The derived field is calculated as <code>depth_tide_corrected_m = depth - tide_ocean_model_m</code>, reducing the instantaneous depth toward the model mean tide level. It is not a chart-datum transformation.</div></section>
    <section><h2>Attribute dictionary</h2><p>The output retains the original ATL24 fields and adds model-tide fields identified as plugin-derived.</p>
    {attribute_dictionary('MODEL_TIDE', data.get('field_schema', []) or [], {}, _definition)}</section>
    <section><h2>Warnings</h2>{warning_html}</section>
    <section><h2>Scientific notes</h2><ul>
    <li>The modeled tide is evaluated for each photon longitude, latitude and UTC timestamp.</li>
    <li><code>depth_tide_corrected_m</code> is calculated only where both source depth and model tide are valid.</li>
    <li>No chart-datum transformation is applied.</li><li>Atmospheric pressure, wind setup, discharge and storm surge are not represented.</li>
    <li>The original ATL24 depth is preserved.</li></ul></section>
    <section><h2>Technical details</h2><details><summary>Engine and package summary</summary><div class="details-body"><pre>{html.escape(technical)}</pre></div></details></section>
    </main><footer>Prepared by {html.escape(AUTHOR_LINE)}. Automatically generated by ICESat-2 Data Explorer. This is a technical processing record and not an official institutional document of UFV or NASA.</footer>
    </div></body></html>'''
    report_path.write_text(document, encoding="utf-8")
    return report_path
