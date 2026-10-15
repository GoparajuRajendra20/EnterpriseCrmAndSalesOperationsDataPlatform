"""Create a packaged, data-backed Tableau workbook with eight analytical sheets."""

import csv
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as E


def main():
    """Build a workbook snapshot from the current curated report files."""
    project_directory = Path(__file__).resolve().parents[1]
    output_directory = project_directory / "tableau"
    packaged_data = output_directory / "Data"
    packaged_data.mkdir(exist_ok=True)
    views = [
        ("Campaign Revenue", "marketing", "channel", "net_revenue"),
        ("Campaign Conversion", "marketing", "channel", "conversion_rate"),
        (
            "Partner Commission Variance",
            "compensation",
            "partner_id",
            "commission_variance",
        ),
        ("Sales Quota Attainment", "rep_compensation", "rep_id", "quota_attainment"),
        ("Customer Satisfaction", "customer_experience", "region", "average_csat"),
        ("Customer SLA Breaches", "customer_experience", "region", "sla_breaches"),
        ("CRM Regional Pipeline", "crm", "region", "leads"),
        (
            "Budget Allocation Scenario",
            "budget_allocation",
            "channel",
            "proposed_budget",
        ),
    ]
    root = E.Element(
        "workbook",
        {
            "source-platform": "mac",
            "version": "18.1",
            "original-version": "18.1",
            "xmlns:user": "http://www.tableausoftware.com/xml/user",
        },
    )
    datasources = E.SubElement(root, "datasources")
    schemas = {}
    for name in dict.fromkeys(v[1] for v in views):
        source = project_directory / "data/curated" / (name + ".csv")
        if not source.exists():
            raise SystemExit("Missing " + str(source) + "; export reports first")
        shutil.copyfile(source, packaged_data / source.name)
        with source.open() as source_file:
            reader = csv.DictReader(source_file)
            rows = list(reader)
            fields = reader.fieldnames
        datasource = E.SubElement(
            datasources,
            "datasource",
            {
                "caption": name.replace("_", " ").title(),
                "inline": "true",
                "name": name,
                "version": "18.1",
            },
        )
        connection = E.SubElement(
            datasource,
            "connection",
            {
                "class": "textscan",
                "directory": "Data",
                "filename": source.name,
                "password": "",
                "server": "",
                "textscan-character-set": "UTF-8",
                "textscan-col-separator": ",",
                "textscan-tab-separator": "0",
            },
        )
        E.SubElement(
            connection,
            "relation",
            {"name": name, "table": "[" + source.name + "]", "type": "table"},
        )
        schema = {}
        for field in fields:
            numeric = True
            try:
                for row in rows:
                    if row[field] != "":
                        float(row[field])
            except ValueError:
                numeric = False
            dimension = field.endswith("_id") or not numeric or field == "month"
            attrs = {
                "datatype": "string" if dimension else "real",
                "name": "[" + field + "]",
                "role": "dimension" if dimension else "measure",
                "type": "nominal" if dimension else "quantitative",
            }
            E.SubElement(datasource, "column", attrs)
            schema[field] = attrs
        schemas[name] = schema
    worksheets = E.SubElement(root, "worksheets")
    for title, datasource, dim, measure in views:
        worksheet = E.SubElement(worksheets, "worksheet", {"name": title})
        table = E.SubElement(worksheet, "table")
        view = E.SubElement(table, "view")
        sources = E.SubElement(view, "datasources")
        E.SubElement(
            sources,
            "datasource",
            {"caption": datasource.replace("_", " ").title(), "name": datasource},
        )
        dependencies = E.SubElement(
            view, "datasource-dependencies", {"datasource": datasource}
        )
        for field, deriv, kind in [
            (dim, "None", "nominal"),
            (
                measure,
                (
                    "Avg"
                    if measure
                    in ["quota_attainment", "conversion_rate", "average_csat"]
                    else "Sum"
                ),
                "quantitative",
            ),
        ]:
            E.SubElement(dependencies, "column", schemas[datasource][field])
            E.SubElement(
                dependencies,
                "column-instance",
                {
                    "column": "[" + field + "]",
                    "derivation": deriv,
                    "name": "["
                    + ("none" if deriv == "None" else deriv.lower())
                    + ":"
                    + field
                    + ":"
                    + ("nk" if kind == "nominal" else "qk")
                    + "]",
                    "pivot": "key",
                    "type": kind,
                },
            )
        E.SubElement(view, "aggregation", {"value": "true"})
        E.SubElement(table, "style")
        panes = E.SubElement(table, "panes")
        pane = E.SubElement(panes, "pane")
        pane_view = E.SubElement(pane, "view")
        E.SubElement(pane_view, "breakdown", {"value": "auto"})
        E.SubElement(pane, "mark", {"class": "Bar"})
        E.SubElement(table, "rows").text = f"[{datasource}].[none:{dim}:nk]"
        agg = (
            "avg"
            if measure in ["quota_attainment", "conversion_rate", "average_csat"]
            else "sum"
        )
        E.SubElement(table, "cols").text = f"[{datasource}].[{agg}:{measure}:qk]"
    dashboards = E.SubElement(root, "dashboards")
    dashboard = E.SubElement(
        dashboards, "dashboard", {"name": "Revenue Operations Overview"}
    )
    E.SubElement(dashboard, "style")
    E.SubElement(
        dashboard,
        "size",
        {
            "maxheight": "1100",
            "maxwidth": "1400",
            "minheight": "1100",
            "minwidth": "1400",
        },
    )
    zones = E.SubElement(dashboard, "zones")
    for i, (title, *_) in enumerate(views):
        E.SubElement(
            zones,
            "zone",
            {
                "h": "25000",
                "id": str(i + 1),
                "name": title,
                "type-v2": "viz",
                "w": "50000",
                "x": str((i % 2) * 50000),
                "y": str((i // 2) * 25000),
            },
        )
    windows = E.SubElement(root, "windows")
    for title, *_ in views:
        E.SubElement(windows, "window", {"class": "worksheet", "name": title})
    E.SubElement(
        windows, "window", {"class": "dashboard", "name": "Revenue Operations Overview"}
    )
    E.indent(root)
    E.ElementTree(root).write(
        output_directory / "PartnerRevenue.twb", encoding="utf-8", xml_declaration=True
    )
    with zipfile.ZipFile(
        output_directory / "PartnerRevenue.twbx", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        archive.write(output_directory / "PartnerRevenue.twb", "PartnerRevenue.twb")
        for source_file in packaged_data.glob("*.csv"):
            archive.write(source_file, "Data/" + source_file.name)
    print("Created", output_directory / "PartnerRevenue.twbx")


if __name__ == "__main__":
    main()
