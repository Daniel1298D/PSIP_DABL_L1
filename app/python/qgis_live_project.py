"""Create a QGIS project that reads the H3 results directly from env-test PostGIS."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsProject,
    QgsReferencedRectangle,
    QgsRendererRange,
    QgsVectorLayer,
)


def save_connection(profile_ini: Path, host: str, port: int, database: str, user: str, password: str) -> None:
    """Add an env-test connection to the existing GUI profile without changing local host."""
    settings = QSettings(str(profile_ini), QSettings.IniFormat)
    source = "PostgreSQL/connections/[PSIP] local host/"
    target = "PostgreSQL/connections/[PSIP] env-test/"
    for key in settings.allKeys():
        if key.startswith(source):
            settings.setValue(target + key[len(source):], settings.value(key))
    for name, value in {
        "host": host,
        "port": str(port),
        "database": database,
        "username": user,
        "password": password,
        "saveUsername": "true",
        "savePassword": "true",
    }.items():
        settings.setValue(target + name, value)
    settings.sync()
    assert settings.status() == QSettings.NoError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-ini", type=Path, required=True)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5434)
    parser.add_argument("--database", default="psip")
    parser.add_argument("--user", default="psip")
    args = parser.parse_args()
    password = os.environ["PGPASSWORD"]

    app = QgsApplication([], False)
    app.initQgis()
    crs = QgsCoordinateReferenceSystem("EPSG:3857")
    project = QgsProject.instance()
    project.setTitle("Warszawa — BDOT10K i H3 — PostgreSQL env-test")
    project.setCrs(crs)

    def db_layer(table: str, name: str, *, schema: str = "viz", srid: int = 3857) -> QgsVectorLayer:
        uri = (
            f"dbname='{args.database}' host={args.host} port={args.port} "
            f"user='{args.user}' password='{password}' sslmode=prefer "
            f"key='id' srid={srid} type=MultiPolygon table=\"{schema}\".\"{table}\" (geom) sql="
        )
        layer = QgsVectorLayer(uri, name, "postgres")
        if not layer.isValid():
            raise RuntimeError(f"Cannot open {schema}.{table} in PostgreSQL")
        if layer.crs().authid() != f"EPSG:{srid}":
            raise RuntimeError(f"Unexpected CRS for {schema}.{table}: {layer.crs().authid()}")
        return layer

    layers = {}
    colors = ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"]
    for resolution in (9, 8, 7):
        layer = db_layer(f"h3_{resolution}", f"H3 {resolution} — budynki [m²] — PostgreSQL")
        count = layer.featureCount()
        if count <= 0:
            raise RuntimeError(f"No features in PostgreSQL view viz.h3_{resolution}")
        values = sorted(float(feature["bubd_a"]) for feature in layer.getFeatures() if feature["bubd_a"] > 0)
        ranges = [
            QgsRendererRange(
                0, 0,
                QgsFillSymbol.createSimple({"color": "#f1f3f5", "outline_color": "#adb5bd", "outline_width": "0.08"}),
                "0 — brak budynków",
            )
        ]
        lower = 0.0
        for i, color in enumerate(colors):
            upper = values[min(len(values) - 1, int((i + 1) * len(values) / 5))]
            ranges.append(QgsRendererRange(
                lower, upper,
                QgsFillSymbol.createSimple({"color": color, "outline_color": "#57728a", "outline_width": "0.08"}),
                f"{lower:,.0f} – {upper:,.0f} m²",
            ))
            lower = upper
        layer.setRenderer(QgsGraduatedSymbolRenderer("bubd_a", ranges))
        for field in layer.fields():
            name = field.name()
            if name.endswith(("_a", "_l", "_p")):
                unit = {"a": "m²", "l": "m", "p": "liczba"}[name[-1]]
                label = {"bubd_a": "Budynki_A", "skdr_l": "Drogi_L"}.get(name, name.upper())
                layer.setFieldAlias(layer.fields().indexFromName(name), f"{label} [{unit}]")
        project.addMapLayer(layer)
        node = project.layerTreeRoot().findLayer(layer.id())
        node.setItemVisibilityChecked(resolution == 8)
        node.setExpanded(resolution == 8)
        layers[resolution] = layer

    boundary = db_layer("powiat", "Granica Warszawy — PostgreSQL", schema="grid", srid=2180)
    boundary.renderer().setSymbol(QgsFillSymbol.createSimple({
        "style": "no", "outline_color": "#d94841", "outline_width": "0.5"
    }))
    project.addMapLayer(boundary)
    extent = project.transformContext()
    from qgis.core import QgsCoordinateTransform
    extent = QgsCoordinateTransform(boundary.crs(), crs, extent).transformBoundingBox(boundary.extent())
    extent.scale(1.1)
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(extent, crs))
    project.setBackgroundColor(QColor("#ffffff"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    project.setFileName(str(args.output))
    if not project.write():
        raise RuntimeError(f"Cannot save project: {args.output}")
    save_connection(args.profile_ini, args.host, args.port, args.database, args.user, password)
    print(f"Saved live PostgreSQL QGIS project: {args.output}")
    print("Feature counts:", {resolution: layer.featureCount() for resolution, layer in layers.items()})


if __name__ == "__main__":
    main()
