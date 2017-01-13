
import sys

from pbreports.report import coverage as coverage_base
from pbreports.io.specs import load_spec

class Constants(object):
    TOOL_ID = "pbreports.tasks.coverage_report_hgap"

class HgapCoverageReport(coverage_base.CoverageReport):
    TOOL_ID = Constants.TOOL_ID
    DRIVER_EXE = "python -m pbreports.report.coverage_hgap --resolved-tool-contract "
    spec = load_spec("coverage_hgap")

def main(argv=sys.argv[1:]):
    return coverage_base.main(argv, HgapCoverageReport)

if __name__ == "__main__":
    sys.exit(main())
