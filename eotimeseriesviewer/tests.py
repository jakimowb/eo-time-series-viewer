# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import json
import math
import os
import pathlib
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Match, Pattern, Tuple, Union

import numpy as np
from osgeo import gdal, osr

from eotimeseriesviewer import DIR_EXAMPLES
from eotimeseriesviewer.dateparser import DateTimePrecision, ImageDateUtils
from eotimeseriesviewer.main import EOTimeSeriesViewer
from eotimeseriesviewer.qgispluginsupport.qps.testing import start_app, TestCase, TestObjects as TObj
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, rasterLayerMapToPixel
from eotimeseriesviewer.sensors import SensorInstrument
from eotimeseriesviewer.temporalprofile.temporalprofile import LoadTemporalProfileTask, TemporalProfileUtils
from eotimeseriesviewer.timeseries.source import TimeSeriesSource
from eotimeseriesviewer.timeseries.timeseries import TimeSeries
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import edit, QgsApplication, QgsError, QgsFeature, QgsFields, QgsGeometry, QgsMapToPixel, QgsPointXY, \
    QgsRasterLayer, QgsVectorLayer

start_app = start_app

osr.UseExceptions()
gdal.UseExceptions()

DIR_LARGE_TIMESERIES = None

EOTSV_TIMESERIES_JSON = Path(os.environ.get('EOTSV_TIMESERIES_JSON', Path()))

FORCE_CUBE = os.environ.get('FORCE_CUBE')
FORCE_CUBE = Path(FORCE_CUBE).expanduser() if isinstance(FORCE_CUBE, str) and Path(
    FORCE_CUBE).expanduser().is_dir() else None
JSON_NDVI = [{"name": None,
              "x": [456616800.0, 460764000.0, 462146400.0, 486424800.0, 492559200.0, 520207200.0, 522972000.0,
                    523749600.0, 524354400.0, 552002400.0, 556149600.0, 583797600.0, 613605600.0, 614210400.0,
                    615592800.0, 616975200.0, 618357600.0, 620517600.0, 649548000.0, 651535200.0, 678492000.0,
                    678578400.0, 679183200.0, 680652000.0, 681343200.0, 682725600.0, 684712800.0, 708991200.0,
                    709596000.0, 712360800.0, 712447200.0, 713052000.0, 713138400.0, 715125600.0, 717285600.0,
                    739404000.0, 741391200.0, 742168800.0, 770421600.0, 773186400.0, 773964000.0, 775346400.0,
                    775951200.0, 803599200.0, 804376800.0, 805759200.0, 807141600.0, 809128800.0, 834012000.0,
                    868572000.0, 871336800.0, 875484000.0, 898380000.0, 902527200.0, 903132000.0, 906674400.0,
                    932162400.0, 933544800.0, 933631200.0, 936309600.0, 936396000.0, 937000800.0, 937087200.0,
                    937692000.0, 937778400.0, 960501600.0, 960588000.0, 961192800.0, 961279200.0, 966117600.0,
                    970178400.0, 994370400.0, 994456800.0, 995839200.0, 996444000.0, 997826400.0, 998517600.0,
                    1028239200.0, 1029621600.0, 1030399200.0, 1031781600.0, 1056578400.0, 1060034400.0, 1060120800.0,
                    1061503200.0, 1063490400.0, 1064872800.0, 1089151200.0, 1091138400.0, 1091916000.0, 1094594400.0,
                    1094680800.0, 1095372000.0, 1118786400.0, 1119477600.0, 1120946400.0, 1121637600.0, 1124316000.0,
                    1124402400.0, 1125784800.0, 1127080800.0, 1127167200.0, 1149890400.0, 1149976800.0, 1150581600.0,
                    1151359200.0, 1151964000.0, 1152050400.0, 1152741600.0, 1153346400.0, 1154124000.0, 1158184800.0,
                    1158271200.0, 1158876000.0, 1158962400.0, 1184536800.0, 1187906400.0, 1212876000.0, 1214172000.0,
                    1214863200.0, 1214949600.0, 1220479200.0, 1222466400.0, 1222552800.0, 1246744800.0, 1252274400.0,
                    1275688800.0, 1277762400.0, 1278453600.0, 1278540000.0, 1279231200.0, 1307570400.0, 1311717600.0,
                    1313791200.0, 1316469600.0, 1317247200.0, 1345586400.0, 1346191200.0, 1348956000.0, 1370383200.0,
                    1373148000.0, 1373839200.0, 1373925600.0, 1374530400.0, 1375308000.0, 1376604000.0, 1377295200.0,
                    1402178400.0, 1402264800.0, 1404338400.0, 1405634400.0, 1405720800.0, 1406412000.0, 1409781600.0,
                    1433973600.0, 1436047200.0, 1438812000.0, 1438898400.0, 1439503200.0, 1440194400.0, 1440280800.0,
                    1440885600.0, 1465077600.0, 1465164000.0, 1467151200.0, 1467842400.0, 1471989600.0, 1472076000.0,
                    1472680800.0, 1473458400.0, 1474149600.0, 1474754400.0, 1496268000.0, 1500328800.0, 1503871200.0,
                    1504476000.0, 1504562400.0, 1528668000.0, 1530741600.0, 1532901600.0, 1533506400.0, 1534888800.0,
                    1536357600.0, 1560463200.0, 1561240800.0, 1561845600.0, 1563314400.0, 1563919200.0, 1566684000.0,
                    1566770400.0, 1590962400.0, 1592949600.0, 1597096800.0, 1597874400.0, 1599861600.0, 1599948000.0,
                    1600639200.0, 1601330400.0, 1622757600.0, 1624053600.0, 1624744800.0, 1624831200.0, 1628892000.0,
                    1628978400.0, 1630965600.0, 1631052000.0, 1654293600.0, 1656194400.0, 1656540000.0, 1660082400.0,
                    1662069600.0, 1662069600.0, 1687730400.0, 1692482400.0, 1693864800.0, 1694296800.0, 1694642400.0,
                    1694728800.0, 1695160800.0],
              "y": [-0.0395655546935609, 0.05341800522973478, -0.11239495798319328, -0.2668371696504689,
                    -0.1951219512195122, -0.13603120429058996, 0.11088400613183444, -0.01229895931882687,
                    0.13605220228384993, -0.23051681706316654, 0.002785515320334262, -0.2281323877068558,
                    -0.09587449157466589, -0.22694174757281554, 0.025702331141661684, -0.1816809260191243,
                    -0.02421595871377531, -0.060064935064935064, -0.19979869149471566, -0.03571428571428571,
                    -0.2210636079249218, -0.09694793536804308, -0.20361509835194044, -0.2871157619359058,
                    -0.006933333333333333, -0.021728145528044467, -0.15993359158826784, 0.08362369337979095,
                    -0.05304518664047151, 0.06051873198847262, -0.044938719927371765, -0.059619450317124734,
                    -0.005573248407643312, -0.002380952380952381, 0.11285574092247301, -0.04671115347950429,
                    -0.10303030303030303, 0.03802588996763754, -0.2722222222222222, -0.09252669039145907,
                    -0.25975473801560756, -0.08803611738148984, -0.16621743036837378, -0.1738206544836379,
                    -0.2473944048272079, -0.005084082909659757, -0.06593406593406594, -0.08815612382234186,
                    -0.28004235044997355, -0.41700404858299595, -0.2134056185312962, -0.13144908030506955,
                    -0.19522388059701493, -0.3081834010446895, -0.13671481357070878, -0.1499452754469172,
                    -0.2171945701357466, -0.18190298507462688, -0.26256410256410256, -0.35528596187175043,
                    -0.3516819571865443, -0.36989498249708286, -0.3613543490951547, -0.08345120226308345,
                    -0.03903654485049834, -0.30265295073091497, -0.3128326434062685, -0.2567191844300278,
                    -0.22082191780821916, -0.12781954887218044, -0.33374766935985084, 0.06, -0.05445026178010471,
                    -0.1988338192419825, -0.15680954964731417, -0.36426332288401253, -0.09156844968268359,
                    -0.35626535626535627, -0.16213683223992503, -0.049773755656108594, -0.4530175706646295,
                    0.19792099792099793, -0.2870544090056285, -0.18062678062678061, -0.35311572700296734,
                    -0.3488372093023256, -0.4163288940359004, -0.299922898997687, -0.26272066458982346,
                    -0.3038086802480071, -0.589098532494759, -0.5635673624288425, -0.18666666666666668,
                    -0.36193029490616624, -0.5672043010752689, -0.43219264892268694, -0.014176663031624863,
                    -0.34937759336099583, -0.45297504798464494, -0.28486293206197855, -0.5177304964539007,
                    -0.6287625418060201, 0.01761252446183953, -0.36774193548387096, 0.05283605283605284,
                    -0.3777403035413153, -0.33067729083665337, -0.027502750275027504, 0.08281829419035847,
                    -0.10891089108910891, -0.21141975308641975, -0.29594477998274377, -0.23076923076923078,
                    -0.37840785169029445, -0.31771894093686354, 0.13862928348909656, 0.0950354609929078,
                    -0.08892355694227769, -0.2722298221614227, -0.28417818740399386, -0.31010452961672474,
                    -0.22828040742959857, -0.3179791976225854, -0.25114754098360653, -0.04945340968245705,
                    -0.2824631860776439, -0.3103448275862069, 0.15632754342431762, -0.55767397521449,
                    -0.5412844036697247, -0.40726933830382106, -0.3483927019982624, -0.2679200940070505,
                    -0.481555333998006, -0.10088331008833101, -0.17574396406513196, -0.34562951082598237,
                    -0.12363067292644757, -0.2756756756756757, -0.29965556831228474, -0.35881841876629017,
                    -0.3788235294117647, -0.020469296055916127, -0.706046511627907, -0.453168044077135,
                    -0.21460176991150443, -0.4291814946619217, -0.13696060037523453, -0.12049433573635428, -0.095,
                    0.07685352622061482, -0.7488789237668162, -0.2231404958677686, -0.30919623461259954,
                    -0.8656716417910447, -0.14285714285714285, -0.5111478117258464, -0.5305164319248826,
                    -0.3076474022183304, -0.40325497287522605, -0.6724667349027635, -0.14377768828030607,
                    -0.215007215007215, 0.24655436447166923, 0.21255153458543288, -0.012814428096820124,
                    -0.47763347763347763, -0.7093596059113301, -0.13674496644295303, -0.2817564035546262,
                    -0.32905982905982906, -0.35131490222521916, -0.4988235294117647, -0.7409493161705552,
                    -0.5922643029814666, -0.4879297732260424, -0.29961089494163423, -0.1958644457208501,
                    -0.3864734299516908, -0.6795201371036846, -0.8167487684729065, -0.3017057569296375,
                    -0.2055984555984556, -0.3503509891512444, -0.3724696356275304, -0.3958041958041958,
                    -0.43988684582743987, -0.6280087527352297, -0.347010550996483, -0.3333333333333333,
                    -0.7013945857260049, -0.6485867074102368, -0.4584415584415584, -0.7666948436179205,
                    -0.4129692832764505, -0.03945578231292517, -0.49157733537519144, -0.5059523809523809,
                    -0.6934306569343066, -0.40013271400132716, -0.75, 0.0136986301369863, -0.1941502773575391,
                    -0.33923705722070846, -0.09731543624161074, -0.7457044673539519, -0.37517053206002726,
                    -0.13002964845404488, -0.4274028629856851, -0.6304155614500442, -0.411214953271028,
                    -0.6299840510366826, -0.29515938606847697, -0.6234718826405868, -0.8105906313645621,
                    -0.41033434650455924, -0.6151419558359621, -0.45051194539249145, -0.16341114816579325],
              "dates": ["1984-06-21T00:00:00", "1984-08-08T00:00:00", "1984-08-24T00:00:00", "1985-06-01T00:00:00",
                        "1985-08-11T00:00:00", "1986-06-27T00:00:00", "1986-07-29T00:00:00", "1986-08-07T00:00:00",
                        "1986-08-14T00:00:00", "1987-06-30T00:00:00", "1987-08-17T00:00:00", "1988-07-02T00:00:00",
                        "1989-06-12T00:00:00", "1989-06-19T00:00:00", "1989-07-05T00:00:00", "1989-07-21T00:00:00",
                        "1989-08-06T00:00:00", "1989-08-31T00:00:00", "1990-08-02T00:00:00", "1990-08-25T00:00:00",
                        "1991-07-03T00:00:00", "1991-07-04T00:00:00", "1991-07-11T00:00:00", "1991-07-28T00:00:00",
                        "1991-08-05T00:00:00", "1991-08-21T00:00:00", "1991-09-13T00:00:00", "1992-06-20T00:00:00",
                        "1992-06-27T00:00:00", "1992-07-29T00:00:00", "1992-07-30T00:00:00", "1992-08-06T00:00:00",
                        "1992-08-07T00:00:00", "1992-08-30T00:00:00", "1992-09-24T00:00:00", "1993-06-07T00:00:00",
                        "1993-06-30T00:00:00", "1993-07-09T00:00:00", "1994-06-01T00:00:00", "1994-07-03T00:00:00",
                        "1994-07-12T00:00:00", "1994-07-28T00:00:00", "1994-08-04T00:00:00", "1995-06-20T00:00:00",
                        "1995-06-29T00:00:00", "1995-07-15T00:00:00", "1995-07-31T00:00:00", "1995-08-23T00:00:00",
                        "1996-06-06T00:00:00", "1997-07-11T00:00:00", "1997-08-12T00:00:00", "1997-09-29T00:00:00",
                        "1998-06-21T00:00:00", "1998-08-08T00:00:00", "1998-08-15T00:00:00", "1998-09-25T00:00:00",
                        "1999-07-17T00:00:00", "1999-08-02T00:00:00", "1999-08-03T00:00:00", "1999-09-03T00:00:00",
                        "1999-09-04T00:00:00", "1999-09-11T00:00:00", "1999-09-12T00:00:00", "1999-09-19T00:00:00",
                        "1999-09-20T00:00:00", "2000-06-09T00:00:00", "2000-06-10T00:00:00", "2000-06-17T00:00:00",
                        "2000-06-18T00:00:00", "2000-08-13T00:00:00", "2000-09-29T00:00:00", "2001-07-06T00:00:00",
                        "2001-07-07T00:00:00", "2001-07-23T00:00:00", "2001-07-30T00:00:00", "2001-08-15T00:00:00",
                        "2001-08-23T00:00:00", "2002-08-02T00:00:00", "2002-08-18T00:00:00", "2002-08-27T00:00:00",
                        "2002-09-12T00:00:00", "2003-06-26T00:00:00", "2003-08-05T00:00:00", "2003-08-06T00:00:00",
                        "2003-08-22T00:00:00", "2003-09-14T00:00:00", "2003-09-30T00:00:00", "2004-07-07T00:00:00",
                        "2004-07-30T00:00:00", "2004-08-08T00:00:00", "2004-09-08T00:00:00", "2004-09-09T00:00:00",
                        "2004-09-17T00:00:00", "2005-06-15T00:00:00", "2005-06-23T00:00:00", "2005-07-10T00:00:00",
                        "2005-07-18T00:00:00", "2005-08-18T00:00:00", "2005-08-19T00:00:00", "2005-09-04T00:00:00",
                        "2005-09-19T00:00:00", "2005-09-20T00:00:00", "2006-06-10T00:00:00", "2006-06-11T00:00:00",
                        "2006-06-18T00:00:00", "2006-06-27T00:00:00", "2006-07-04T00:00:00", "2006-07-05T00:00:00",
                        "2006-07-13T00:00:00", "2006-07-20T00:00:00", "2006-07-29T00:00:00", "2006-09-14T00:00:00",
                        "2006-09-15T00:00:00", "2006-09-22T00:00:00", "2006-09-23T00:00:00", "2007-07-16T00:00:00",
                        "2007-08-24T00:00:00", "2008-06-08T00:00:00", "2008-06-23T00:00:00", "2008-07-01T00:00:00",
                        "2008-07-02T00:00:00", "2008-09-04T00:00:00", "2008-09-27T00:00:00", "2008-09-28T00:00:00",
                        "2009-07-05T00:00:00", "2009-09-07T00:00:00", "2010-06-05T00:00:00", "2010-06-29T00:00:00",
                        "2010-07-07T00:00:00", "2010-07-08T00:00:00", "2010-07-16T00:00:00", "2011-06-09T00:00:00",
                        "2011-07-27T00:00:00", "2011-08-20T00:00:00", "2011-09-20T00:00:00", "2011-09-29T00:00:00",
                        "2012-08-22T00:00:00", "2012-08-29T00:00:00", "2012-09-30T00:00:00", "2013-06-05T00:00:00",
                        "2013-07-07T00:00:00", "2013-07-15T00:00:00", "2013-07-16T00:00:00", "2013-07-23T00:00:00",
                        "2013-08-01T00:00:00", "2013-08-16T00:00:00", "2013-08-24T00:00:00", "2014-06-08T00:00:00",
                        "2014-06-09T00:00:00", "2014-07-03T00:00:00", "2014-07-18T00:00:00", "2014-07-19T00:00:00",
                        "2014-07-27T00:00:00", "2014-09-04T00:00:00", "2015-06-11T00:00:00", "2015-07-05T00:00:00",
                        "2015-08-06T00:00:00", "2015-08-07T00:00:00", "2015-08-14T00:00:00", "2015-08-22T00:00:00",
                        "2015-08-23T00:00:00", "2015-08-30T00:00:00", "2016-06-05T00:00:00", "2016-06-06T00:00:00",
                        "2016-06-29T00:00:00", "2016-07-07T00:00:00", "2016-08-24T00:00:00", "2016-08-25T00:00:00",
                        "2016-09-01T00:00:00", "2016-09-10T00:00:00", "2016-09-18T00:00:00", "2016-09-25T00:00:00",
                        "2017-06-01T00:00:00", "2017-07-18T00:00:00", "2017-08-28T00:00:00", "2017-09-04T00:00:00",
                        "2017-09-05T00:00:00", "2018-06-11T00:00:00", "2018-07-05T00:00:00", "2018-07-30T00:00:00",
                        "2018-08-06T00:00:00", "2018-08-22T00:00:00", "2018-09-08T00:00:00", "2019-06-14T00:00:00",
                        "2019-06-23T00:00:00", "2019-06-30T00:00:00", "2019-07-17T00:00:00", "2019-07-24T00:00:00",
                        "2019-08-25T00:00:00", "2019-08-26T00:00:00", "2020-06-01T00:00:00", "2020-06-24T00:00:00",
                        "2020-08-11T00:00:00", "2020-08-20T00:00:00", "2020-09-12T00:00:00", "2020-09-13T00:00:00",
                        "2020-09-21T00:00:00", "2020-09-29T00:00:00", "2021-06-04T00:00:00", "2021-06-19T00:00:00",
                        "2021-06-27T00:00:00", "2021-06-28T00:00:00", "2021-08-14T00:00:00", "2021-08-15T00:00:00",
                        "2021-09-07T00:00:00", "2021-09-08T00:00:00", "2022-06-04T00:00:00", "2022-06-26T00:00:00",
                        "2022-06-30T00:00:00", "2022-08-10T00:00:00", "2022-09-02T00:00:00", "2022-09-02T00:00:00",
                        "2023-06-26T00:00:00", "2023-08-20T00:00:00", "2023-09-05T00:00:00", "2023-09-10T00:00:00",
                        "2023-09-14T00:00:00", "2023-09-15T00:00:00", "2023-09-20T00:00:00"]}]


def example_raster_files(pattern: Union[str, Pattern, Match] = '*.tif') -> List[str]:
    return list(file_search(DIR_EXAMPLES, pattern, recursive=True))


def createTimeSeries(self) -> TimeSeries:
    files = example_raster_files()
    TS = TimeSeries()
    self.assertIsInstance(TS, TimeSeries)
    TS.addSourceInputs(files)
    self.assertTrue(len(TS) > 0)
    return TS


class EOTSVTestCase(TestCase):

    @classmethod
    def tearDownClass(cls):
        cls.assertTrue(EOTimeSeriesViewer.instance() is None, 'EOTimeSeriesViewer instance was not closed')
        super().tearDownClass()

    @staticmethod
    def taskManagerProcessEvents() -> bool:
        tm = QgsApplication.taskManager()
        has_active_tasks = False
        while any(tm.activeTasks()):
            if not has_active_tasks:
                print('Wait for QgsTaskManager tasks to be finished...\r', flush=True)
                has_active_tasks = True
            QgsApplication.processEvents()
        print('\rfinished.', flush=True)
        return has_active_tasks

    def tearDown(self):
        self.taskManagerProcessEvents()
        self.assertTrue(EOTimeSeriesViewer.instance() is None)
        super().tearDown()

    @staticmethod
    def closeBlockingWidget():
        """
        Closes the active blocking (modal) widget
        """
        w = QgsApplication.instance().activeModalWidget()
        if isinstance(w, QWidget):
            print('Close blocking {} "{}"'.format(w.__class__.__name__, w.windowTitle()))
            w.close()

    @classmethod
    def exampleRasterFiles(cls) -> List[str]:
        return example_raster_files()


class TestObjects(TObj):
    """
    Creates objects to be used for testing. It is preferred to generate objects in-memory.
    """

    @staticmethod
    def generate_multi_sensor_profiles() -> List[Dict]:
        """
        Returns two multi-sensor profile values dictionaries
        :return: List[Dict]
        """

        dump = """[{"date": ["1984-08-24T00:00:00", "1985-06-01T00:00:00", "1985-08-11T00:00:00", "1986-06-27T00:00:00", "1986-07-29T00:00:00", "1987-06-30T00:00:00", "1987-08-17T00:00:00", "1988-07-02T00:00:00", "1988-07-11T00:00:00", "1988-08-28T00:00:00", "1989-06-12T00:00:00", "1989-06-19T00:00:00"], "sensor": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "sensor_ids": ["{\"nb\": 6, \"px_size_x\": 30.0, \"px_size_y\": 30.0, \"dt\": 3, \"wl\": [0.486, 0.57, 0.66, 0.838, 1.677, 2.217], \"wlu\": \"micrometers\", \"name\": null}"], "values": [[686.0, 1240.0, 1091.0, 3248.0, 2889.0, 1678.0], [1093.0, 1067.0, 1036.0, 1753.0, 1899.0, 1219.0], [446.0, 899.0, 620.0, 5779.0, 2009.0, 796.0], [503.0, 730.0, 512.0, 4277.0, 1704.0, 720.0], [445.0, 732.0, 668.0, 2169.0, 1787.0, 965.0], [494.0, 844.0, 568.0, 3688.0, 1420.0, 562.0], [1581.0, 1915.0, 2008.0, 3402.0, 3652.0, 2638.0], [347.0, 688.0, 365.0, 5759.0, 2178.0, 674.0], [734.0, 1011.0, 696.0, 4720.0, 2133.0, 842.0], [519.0, 748.0, 911.0, 1621.0, 2899.0, 2197.0], [405.0, 725.0, 484.0, 4276.0, 1566.0, 536.0], [279.0, 565.0, 377.0, 4009.0, 1658.0, 623.0]]}, {"date": ["1984-08-24T00:00:00", "1985-08-11T00:00:00", "1986-06-27T00:00:00", "1986-07-04T00:00:00", "1986-08-14T00:00:00", "1987-06-30T00:00:00", "1987-07-07T00:00:00", "1987-07-16T00:00:00", "1987-08-17T00:00:00", "1988-07-02T00:00:00", "1989-06-10T00:00:00", "1989-06-19T00:00:00"], "sensor": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "sensor_ids": ["{\"nb\": 6, \"px_size_x\": 30.0, \"px_size_y\": 30.0, \"dt\": 3, \"wl\": [0.486, 0.57, 0.66, 0.838, 1.677, 2.217], \"wlu\": \"micrometers\", \"name\": null}"], "values": [[660, 970, 1117, 1598, 1740, 1183], [625, 987, 1208, 1971, 2301, 1484], [448, 699, 504, 4463, 1491, 575], [515, 721, 585, 4450, 1519, 541], [896, 1378, 1676, 2716, 2954, 1731], [496, 935, 609, 4750, 1594, 567], [587, 1022, 790, 4773, 1963, 772], [2611, 2833, 2653, 5344, 3024, 1416], [1028, 1464, 1612, 2684, 2941, 1628], [527, 1105, 758, 4394, 1220, 506], [377, 559, 377, 4545, 1323, 445], [384, 562, 376, 4649, 1465, 511]]}]"""

        data = json.loads(dump)
        assert isinstance(data, list)
        for d in data:
            assert TemporalProfileUtils.isProfileDict(d)
        return data

    @staticmethod
    def generate_seasonal_ndvi_dates(start_year=1986, end_year=1990, count=100) -> Tuple[np.array, np.array]:
        if False:
            # Generate evenly spaced dates
            start_date = datetime(start_year, 1, 1)
            end_date = datetime(end_year, 12, 31)
            total_days = (end_date - start_date).days
            step = total_days / (count - 1)
            dates = [start_date + timedelta(days=int(i * step)) for i in range(count)]

            # Generate NDVI values with phenological pattern
            ndvi_values = []
            for date in dates:
                day_of_year = date.timetuple().tm_yday
                # Normalize day of year to range [0, 2π]
                angle = (2 * math.pi * day_of_year) / 365.25
                # Simulate NDVI: low in winter (~-0.2), high in summer (~1.0)
                ndvi = 0.6 * math.sin(angle - math.pi / 2) + 0.4  # Shift to range [-0.2, 1.0]
                ndvi_values.append(round(ndvi, 3))
        else:
            profile = JSON_NDVI[0]
            dates = [datetime.fromisoformat(d) for d in profile['dates']]
            ndvi_values = profile['y']
        return np.asarray(dates), np.asarray(ndvi_values)

    @staticmethod
    def createTemporalProfileDict() -> Dict[str, Any]:
        """
        Returns an exemplary temporal profile dictionary
        with a multi-sensor timeseries of 2 sensors.
        :return: dict
        """
        from example.Images import Img_2014_01_15_LC82270652014015LGN00_BOA
        from example.Images import re_2014_06_25

        tss1 = TimeSeriesSource.create(Img_2014_01_15_LC82270652014015LGN00_BOA)
        tss2 = TimeSeriesSource.create(re_2014_06_25)
        lyr1 = tss1.asRasterLayer()
        lyr2 = tss2.asRasterLayer()

        sensorIDs = []
        values = []
        sensors = []
        dates = []

        def addValues(lyr: QgsRasterLayer, datetime: str):
            sid = lyr.customProperty(SensorInstrument.PROPERTY_KEY)
            extent = lyr.extent()
            # random point within the extent
            x = np.random.uniform(extent.xMinimum(), extent.xMaximum())
            y = np.random.uniform(extent.yMinimum(), extent.yMaximum())
            point = QgsPointXY(x, y)
            val = TemporalProfileUtils.profileValues(lyr, point)
            values.append(val)
            if sid not in sensorIDs:
                sensorIDs.append(sid)
            sensors.append(sensorIDs.index(sid))
            dates.append(datetime)

            s = ""

        addValues(lyr1, '2024-01-01')
        addValues(lyr1, '2024-01-02')
        addValues(lyr2, '2024-01-03')
        addValues(lyr2, '2024-01-04')

        profileDict = {TemporalProfileUtils.SensorIDs: sensorIDs,
                       TemporalProfileUtils.Sensor: sensors,
                       TemporalProfileUtils.Date: dates,
                       TemporalProfileUtils.Values: values}
        assert TemporalProfileUtils.isProfileDict(profileDict)
        success, error = TemporalProfileUtils.verifyProfile(profileDict)
        assert success, error
        return profileDict

    @staticmethod
    def createTimeSeries(precision: DateTimePrecision = DateTimePrecision.Day) -> TimeSeries:

        TS = TimeSeries()
        TS.setDateTimePrecision(precision)
        # files = file_search(DIR_EXAMPLES, '*.tif', recursive=True)
        files = file_search(DIR_EXAMPLES / 'Images', '*.tif', recursive=True)
        TS.addSourceInputs(list(files), runAsync=False)
        assert len(TS) > 0
        return TS

    @staticmethod
    def createProfileLayer(timeseries: TimeSeries = None) -> QgsVectorLayer:

        if timeseries is None:
            timeseries = TestObjects.createTimeSeries()
        layer = TemporalProfileUtils.createProfileLayer()
        assert isinstance(layer, QgsVectorLayer)
        assert layer.isValid()

        tpFields = TemporalProfileUtils.temporalProfileFields(layer)
        assert isinstance(tpFields, QgsFields)
        assert tpFields.count() > 0

        sources = timeseries.sourceUris()
        l0 = QgsRasterLayer(sources[0])
        ns, nl = l0.width(), l0.height()
        m2p: QgsMapToPixel = rasterLayerMapToPixel(l0)
        points = [m2p.toMapCoordinates(0, 0),
                  m2p.toMapCoordinates(int(0.5 * ns), int(0.5 * nl)),
                  m2p.toMapCoordinates(ns - 1, nl - 1)]

        task = LoadTemporalProfileTask(sources, points, crs=l0.crs(), n_threads=os.cpu_count(),
                                       description='Load example temporal profiles')
        task.run_serial()

        new_features: List[QgsFeature] = list()
        for profile, point in zip(task.profiles(), task.profilePoints()):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(point.asWkt()))
            # profileJson = TemporalProfileUtils.profileJsonFromDict(profile)
            assert TemporalProfileUtils.verifyProfile(profile)
            f.setAttribute(tpFields[0].name(), profile)
            new_features.append(f)

        with edit(layer):
            if not layer.addFeatures(new_features):
                err = layer.error()
                if isinstance(err, QgsError):
                    raise err.message()

        layer.setDisplayExpression("format('Feature %1', $id)")
        return layer

    @staticmethod
    def createArtificialTimeSeries(n=100) -> List[str]:
        vsiDir = '/vsimem/tmp'
        d1 = np.datetime64('2000-01-01')
        print('Create in-memory test timeseries of length {}...'.format(n))
        files = example_raster_files()

        paths = []
        i = 0
        import itertools
        drv = gdal.GetDriverByName('GTiff')
        assert isinstance(drv, gdal.Driver)
        for file in itertools.cycle(files):
            if i >= n:
                break

            date = d1 + i
            path = os.path.join(vsiDir, 'file.{}.{}.tif'.format(i, date))
            dsDst = drv.CreateCopy(path, gdal.Open(file))
            assert isinstance(dsDst, gdal.Dataset)
            paths.append(path)

            i += 1

        print('Done!')

        return paths

    @staticmethod
    def exampleImagePaths() -> list:
        import example
        path = pathlib.Path(example.__file__).parent / 'Images'
        files = list(file_search(path, '*.tif', recursive=True))
        assert len(files) > 0
        return files

    @staticmethod
    def createTestImageSeries(n=1) -> list:
        assert n > 0

        datasets = []
        for i in range(n):
            ds = TestObjects.inMemoryImage()
            datasets.append(ds)
        return datasets

    @staticmethod
    def createMultiSourceTimeSeries(n_max: int = -1) -> list:

        # real files
        files = TestObjects.exampleImagePaths()

        if n_max > 0:
            n_max = min(n_max, len(files))
        else:
            n_max = len(files)

        movedFiles = []
        uid = uuid.uuid4()

        for i, pathSrc in enumerate(files[0: n_max]):
            bn = os.path.basename(pathSrc)

            dsSrc = gdal.Open(pathSrc)
            dtg = ImageDateUtils.datetime(pathSrc)
            dtg2 = dtg.addSecs(random.randint(60, 300)
                               )
            pathDst = f'/vsimem/{uid}_shifted_{i}.bsq'
            tops = gdal.TranslateOptions(format='ENVI')
            gdal.Translate(pathDst, dsSrc, options=tops)
            dsDst = gdal.Open(pathDst, gdal.GA_Update)
            assert isinstance(dsDst, gdal.Dataset)
            gt = list(dsSrc.GetGeoTransform())
            ns, nl = dsDst.RasterXSize, dsDst.RasterYSize
            gt[0] = gt[0] + 0.5 * ns * gt[1]
            gt[3] = gt[3] + abs(0.5 * nl * gt[5])
            dsDst.SetGeoTransform(gt)
            dsDst.SetMetadata(dsSrc.GetMetadata(''), '')

            dsDst.SetMetadataItem('ACQUISITIONDATETIME', dtg2.toString(Qt.ISODate), 'IMAGERY')
            dsDst.FlushCache()
            del dsDst
            dsDst = None
            dsDst = gdal.Open(pathDst)
            assert list(dsDst.GetGeoTransform()) == gt
            movedFiles.append(pathDst)

        final = []
        for f1, f2 in zip(files, movedFiles):
            final.append(f1)
            final.append(f2)
        return final
