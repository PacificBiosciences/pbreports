
from pprint import pformat
import tempfile
import unittest
import logging
import json
import os

from pbcore.util.Process import backticks
import pbcommand.testkit

import pbtestdata

from pbreports.report.barcode import run_to_report, iter_reads_by_barcode

from base_test_case import (validate_report_complete,
                            skip_if_data_dir_not_present)

log = logging.getLogger(__name__)


class TestToolContract(pbcommand.testkit.PbTestApp):
    DRIVER_BASE = "python -m pbreports.report.barcode"
    INPUT_FILES = [pbtestdata.get_file("barcoded-subreadset"),
                   pbtestdata.get_file("barcodeset")]


class TestBarcodeReportBasic(unittest.TestCase):

    def setUp(self):
        self.barcodes = pbtestdata.get_file("barcodeset")
        self.subreads = pbtestdata.get_file("barcoded-subreadset")

    def test_iter_reads_by_barcode(self):
        table = sorted(list(iter_reads_by_barcode(self.subreads, self.barcodes)), lambda a,b: cmp(b.nbases, a.nbases))
        self.assertEqual([r.label for r in table],
                         ["Not Barcoded", "lbc1--lbc1", "lbc3--lbc3"])
        self.assertEqual([r.nbases for r in table], [9791, 1436, 204])
        self.assertEqual([r.n_subreads for r in table], [1,1,1])

    @unittest.skip("Not implemented")
    def test_make_report(self):
        pass # TODO

    def test_run_to_report(self):
        report = run_to_report(self.subreads, self.barcodes)
        validate_report_complete(self, report)
        d = report.to_dict()
        self.assertIsNotNone(d)
        attr = {a.id:a.value for a in report.attributes}
        self.assertEqual(attr, {
            'mean_read_length': 820,
            'mean_longest_subread_legnth': 820,
            'min_reads': 1,
            'mean_reads': 1,
            'n_barcodes': 2,
            'max_reads': 1
        })
        self.assertEqual(report.tables[0].columns[0].values, [
                         'lbc1--lbc1', 'lbc3--lbc3', 'Not Barcoded'])
        self.assertEqual(report.tables[0].columns[1].values, [1, 1, 1])
        self.assertEqual(report.tables[0].columns[2].values, [1, 1, 1])
        self.assertEqual(report.tables[0].columns[3].values, [1436, 204, 9791])

    @skip_if_data_dir_not_present
    def test_large_dataset(self):
        SUBREADS = "/pbi/dept/secondary/siv/testdata/SA3-Sequel/phi29/315/3150101/r54008_20160219_002905/1_A01_tiny_barcoded/m54008_160219_003234.tiny.subreadset.xml"
        BARCODES = "/pbi/dept/secondary/siv/barcodes/Sequel_RSII_384_barcodes_v1/Sequel_RSII_384_barcodes_v1.barcodeset.xml"
        report = run_to_report(SUBREADS, BARCODES)
        validate_report_complete(self, report)
        d = report.to_dict()
        self.assertIsNotNone(d)
        attr = {a.id:a.value for a in report.attributes}
        self.assertEqual(attr, {
            'mean_read_length': 9322,
            'mean_longest_subread_legnth': 28314,
            'min_reads': 989,
            'mean_reads': 1065,
            'n_barcodes': 3,
            'max_reads': 1116
        })
        self.assertEqual(report.tables[0].columns[0].values,
                         ['bc1001--bc1001', 'bc1002--bc1002', 'bc1003--bc1003'])
        self.assertEqual(report.tables[0].columns[1].values, [1091, 1116, 989])
        self.assertEqual(report.tables[0].columns[2].values, [5370, 5053, 4710])
        self.assertEqual(report.tables[0].columns[3].values, [10306688, 10034254, 9452616])


class TestBarcodeIntegration(unittest.TestCase):

    def setUp(self):
        self.barcodes = pbtestdata.get_file("barcodeset")
        self.subreads = pbtestdata.get_file("barcoded-subreadset")
        self.ccs = False

    def test_integration(self):
        exe = "barcode_report"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        json_report_file_name = temp_file.name
        temp_file.close()
        cmd = "{e} --debug {b} {ba} {r}".format(e=exe,
                                                b=self.subreads,
                                                ba=self.barcodes,
                                                r=json_report_file_name)
        log.info("Running cmd {c}".format(c=cmd))
        output, rcode, emsg = backticks(cmd)
        if rcode != 0:
            log.error(output)
            log.error(emsg)
        self.assertEqual(0, rcode)
        with open(json_report_file_name, 'r') as f:
            s = json.load(f)
        self.assertIsNotNone(s)
        log.info(pformat(s))
        # cleanup
        os.remove(json_report_file_name)
