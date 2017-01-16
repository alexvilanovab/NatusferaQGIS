# -*- coding: utf-8 -*-
def classFactory(iface):
    from .natusfera_qgis import NatusferaQGIS
    return NatusferaQGIS(iface)
