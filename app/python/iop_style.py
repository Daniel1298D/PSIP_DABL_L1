"""Shared IOP symbology. Importing this module never changes the Qt platform."""
from decimal import Decimal

from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsClassificationEqualInterval, QgsFillSymbol, QgsGradientColorRamp,
    QgsGradientStop, QgsGraduatedSymbolRenderer, QgsProperty, QgsRendererRange,
    QgsSymbolLayer,
)


def renderer(lower: Decimal, upper: Decimal, classes: int, attribute='iop'):
    """Equal intervals on a symmetric red/white/green scale; exactly zero is white."""
    if lower >= 0 or upper != -lower or classes < 2:
        raise ValueError('The diverging scale must be symmetric around zero')
    step = (upper - lower) / classes
    ramp = QgsGradientColorRamp(QColor('#ff0000'), QColor('#008000'), False,
                                [QgsGradientStop(0.5, QColor('#ffffff'))])
    ranges = []
    for i in range(classes):
        start, end = lower + i * step, lower + (i + 1) * step
        color = ramp.color(i / (classes - 1))
        symbol = QgsFillSymbol.createSimple({
            'color': color.name(), 'outline_color': '#b3b3b3', 'outline_width': '0.025',
        })
        expression = f'''CASE WHEN "{attribute}" = 0 THEN '#ffffff' ELSE '{color.name()}' END'''
        symbol.symbolLayer(0).setDataDefinedProperty(
            QgsSymbolLayer.PropertyFillColor, QgsProperty.fromExpression(expression))
        ranges.append(QgsRendererRange(float(start), float(end), symbol,
                                       f'{start:+.3f} — {end:+.3f}'.replace('.', ',')))
    result = QgsGraduatedSymbolRenderer(attribute, ranges)
    result.setClassificationMethod(QgsClassificationEqualInterval())
    result.updateColorRamp(ramp)
    return result


def custom_renderer(lower: Decimal, upper: Decimal, attribute: str):
    """Use ten classes on each side of zero; clip outside values in the display only."""
    if not Decimal('-1') <= lower < 0 < upper <= Decimal('1'):
        raise ValueError('Zakres musi spełniać −1 ≤ minimum < 0 < maksimum ≤ 1.')
    zero_position = float(-lower / (upper - lower))
    ramp = QgsGradientColorRamp(QColor('#ff0000'), QColor('#008000'), False,
                                [QgsGradientStop(zero_position, QColor('#ffffff'))])
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
            symbol = QgsFillSymbol.createSimple({
                'color': color, 'outline_color': '#b3b3b3', 'outline_width': '0.025',
            })
            if index == (9 if negative else 0):
                expression = f'''CASE WHEN "{attribute}" = 0 THEN '#ffffff' ELSE '{color}' END'''
                symbol.symbolLayer(0).setDataDefinedProperty(
                    QgsSymbolLayer.PropertyFillColor, QgsProperty.fromExpression(expression))
            ranges.append(QgsRendererRange(float(start), float(end), symbol,
                                           f'{start:+.4f} — {end:+.4f}'.replace('.', ',')))
    result = QgsGraduatedSymbolRenderer(f'clamp({lower}, "{attribute}", {upper})', ranges)
    result.setSourceColorRamp(ramp)
    return result
