"""Shared IOP symbology. Importing this module never changes the Qt platform."""
from decimal import Decimal

from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsClassificationEqualInterval, QgsFillSymbol, QgsGradientColorRamp,
    QgsGradientStop, QgsGraduatedSymbolRenderer, QgsProperty, QgsRendererRange,
    QgsSymbolLayer,
)

DEFAULT_IOP_COLORS = ('#ff0000', '#ffffff', '#008000')


def color_ramp(colors, zero_position):
    low, zero, high = (QColor(color) for color in colors)
    return QgsGradientColorRamp(low, high, False, [QgsGradientStop(zero_position, zero)])


def fill_symbol(color, attribute, zero_color=None):
    symbol = QgsFillSymbol.createSimple({
        'color': color, 'outline_color': '#b3b3b3', 'outline_width': '0.025',
    })
    if zero_color is not None:
        expression = f"""CASE WHEN "{attribute}" = 0 THEN '{zero_color}' ELSE '{color}' END"""
        symbol.symbolLayer(0).setDataDefinedProperty(
            QgsSymbolLayer.PropertyFillColor, QgsProperty.fromExpression(expression))
    return symbol


def renderer(lower: Decimal, upper: Decimal, classes: int, attribute='iop', *, colors=DEFAULT_IOP_COLORS):
    """Equal intervals on a symmetric scale with a separate color for exactly zero."""
    if lower >= 0 or upper != -lower or classes < 2:
        raise ValueError('The diverging scale must be symmetric around zero')
    step = (upper - lower) / classes
    ramp = color_ramp(colors, 0.5)
    ranges = []
    for i in range(classes):
        start, end = lower + i * step, lower + (i + 1) * step
        color = ramp.color(i / (classes - 1)).name()
        symbol = fill_symbol(color, attribute, colors[1])
        ranges.append(QgsRendererRange(float(start), float(end), symbol,
                                       f'{start:+.3f} — {end:+.3f}'.replace('.', ',')))
    result = QgsGraduatedSymbolRenderer(attribute, ranges)
    result.setClassificationMethod(QgsClassificationEqualInterval())
    result.updateColorRamp(ramp)
    return result


def custom_renderer(lower: Decimal, upper: Decimal, attribute: str, *, colors=DEFAULT_IOP_COLORS):
    """Use ten classes on each side of zero; clip outside values in the display only."""
    if not Decimal('-1') <= lower < 0 < upper <= Decimal('1'):
        raise ValueError('Zakres musi spełniać −1 ≤ minimum < 0 < maksimum ≤ 1.')
    zero_position = float(-lower / (upper - lower))
    ramp = color_ramp(colors, zero_position)
    ranges = []
    for left, right, negative in ((lower, Decimal(0), True), (Decimal(0), upper, False)):
        step = (right - left) / 10
        for index in range(10):
            start, end = left + index * step, left + (index + 1) * step
            if negative:
                color_position = zero_position * index / 10
            else:
                color_position = zero_position + (1 - zero_position) * (index + 1) / 10
            color = ramp.color(color_position).name()
            zero_color = colors[1] if index == (9 if negative else 0) else None
            symbol = fill_symbol(color, attribute, zero_color)
            ranges.append(QgsRendererRange(float(start), float(end), symbol,
                                           f'{start:+.4f} — {end:+.4f}'.replace('.', ',')))
    result = QgsGraduatedSymbolRenderer(f'clamp({lower}, "{attribute}", {upper})', ranges)
    result.setSourceColorRamp(ramp)
    return result
