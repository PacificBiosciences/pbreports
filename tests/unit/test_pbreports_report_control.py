import os
import logging
import json
import unittest
import tempfile
import shutil
import numpy as np
import os.path as op

from pbreports.report.control import to_report
from base_test_case import validate_report_complete, skip_if_data_dir_not_present

log = logging.getLogger(__name__)


def get_control_subreadset():
    ss = ('/pbi/dept/secondary/siv/testdata/SA3-Sequel/lambda/'
          '328/3280096/r54007_20171019_221349/1_A01/'
          'm54007_171019_222153.subreadset.xml')
    return ss


def get_empty_control_subreadset():
    ss = ('/pbi/dept/secondary/siv/testdata/SA3-Sequel/ecoli/'
          '318/3180211/r54019_20170314_001820/1_A01_empty_control/'
          'm54019_170314_003016.subreadset.xml')
    return ss


class TestControlRpt(unittest.TestCase):

    def setUp(self):
        self._output_dir = tempfile.mkdtemp(suffix="control")
        log.setLevel(logging.INFO)

    def tearDown(self):
        if op.exists(self._output_dir):
            shutil.rmtree(self._output_dir)

    @skip_if_data_dir_not_present
    def test_make_control_report(self):

        ss = get_control_subreadset()

        rpt = to_report(ss, self._output_dir)
        d = json.loads(rpt.to_json())

        self.assertEqual(8359, d['attributes'][0]['value'])
        self.assertEqual(26708, np.floor(d['attributes'][1]['value']))
        self.assertAlmostEqual(0.859876, d['attributes'][
                               2]['value'], delta=.0003)
        self.assertEqual(0.87, d['attributes'][3]['value'])

        self.assertTrue(os.path.exists(os.path.join(self._output_dir,
                                                    'concordance_plot.png')))
        self.assertTrue(os.path.exists(os.path.join(self._output_dir,
                                                    'concordance_plot_thumb.png')))
        self.assertTrue(os.path.exists(os.path.join(self._output_dir,
                                                    'readlength_plot.png')))
        self.assertTrue(os.path.exists(os.path.join(self._output_dir,
                                                    'readlength_plot_thumb.png')))
        validate_report_complete(self, rpt)

    @skip_if_data_dir_not_present
    def test_make_empty_control_report(self):

        ss = get_empty_control_subreadset()

        rpt = to_report(ss, self._output_dir)
        d = json.loads(rpt.to_json())

        self.assertEqual(0, d['attributes'][0]['value'])
        self.assertEqual(None, d['attributes'][1]['value'])
        self.assertEqual(None, d['attributes'][2]['value'])
        self.assertEqual(None, d['attributes'][3]['value'])

        self.assertTrue(os.path.exists(os.path.join(self._output_dir,
                                                    'concordance_plot.png')))
        self.assertTrue(os.path.exists(os.path.join(self._output_dir,
                                                    'concordance_plot_thumb.png')))
        self.assertTrue(os.path.exists(os.path.join(self._output_dir,
                                                    'readlength_plot.png')))
        self.assertTrue(os.path.exists(os.path.join(self._output_dir,
                                                    'readlength_plot_thumb.png')))
