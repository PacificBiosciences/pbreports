
"""
Generates:
 - Filter ReadLength histograms with SDF (with thumbnails)
 - Filter ReadScore Histogram with SDF (with thumbnails)
 - Table of total bases, # of reads, mean readlengh, mean
   readscore
"""
import os
import logging
import sys

import numpy as np
from pbcommand.utils import setup_log

from pbreports.plot.helper import (get_fig_axes_lpr,
                                   save_figure_with_thumbnail, get_green)

from pbcommand.models import TaskTypes, FileTypes, get_pbparser
from pbcommand.cli import pbparser_runner
from pbcommand.common_options import add_debug_option

from pbreports.model.model import (Report, Table, Column, Plot,
                                   PlotGroup)
from pbcore.io import DataSet

__version__ = '0.1.0'

class Constants(object):
    TOOL_ID = "pbreports.tasks.filter_stats_report_xml"
    DRIVER_EXE = ("python -m pbreports.report.filter_stats_xml "
                  "--resolved-tool-contract ")


log = logging.getLogger(__name__)

def _total_from_bins(bins, min_val, bin_width):
    _min = min_val
    _wid = bin_width
    bin_means = [_min + (_wid * i) + _wid/2 for i in range(len(bins))]
    bin_totals = [count * mean for count, mean in zip(bins, bin_means)]
    return sum(bin_totals)

def to_report(stats_xml, output_dir, dpi=72):
    """Main point of entry

    :type stats_xml: str
    :type output_dir: str
    :type dpi: int

    :rtype: Report
    """
    log.info("Analyzing XML {f}".format(f=stats_xml))
    # stats_xml should be a dataset:
    dset = DataSet(stats_xml)
    # but if it isn't, no problem:
    if not dset.metadata.summaryStats:
        dset.loadStats(stats_xml)

    # Build the stats table:
    nbases = 0
    nreads = 0
    n50 = 0
    readscoretotal = 0
    readscorenumber = 0

    # if a merge failed there may be more than one dist:
    for rlendist in dset.metadata.summaryStats.readLenDists:
        nbases += _total_from_bins(rlendist.bins,
                                   rlendist.minBinValue,
                                   rlendist.binWidth)
        nreads += sum(rlendist.bins)

    for rqualdist in dset.metadata.summaryStats.readQualDists:
        readscoretotal += _total_from_bins(rqualdist.bins,
                                           rqualdist.minBinValue,
                                           rqualdist.binWidth)
        readscorenumber += sum(rqualdist.bins)

    row_names = ["Polymerase Read Bases",
                 "Polymerase Reads",
                 "Polymerase Read N50",
                 "Polymerase Read Length",
                 "Polymerase Read Quality"]
    _pre_filter = [np.round(nbases, decimals=2),
                   nreads,
                   n50,
                   np.round(nbases/nreads, decimals=2),
                   np.round(readscoretotal/readscorenumber, decimals=2)]

    plots = []

    # ReadLen distribution to barplot:
    for i, rlendist in enumerate(dset.metadata.summaryStats.readLenDists):
        len_fig, len_axes = get_fig_axes_lpr()
        len_axes.bar(rlendist.labels, rlendist.bins,
                     color=get_green(0), edgecolor=get_green(0),
                     width=(rlendist.binWidth * 0.75))
        len_axes.set_xlabel('Read Length')
        len_axes.set_ylabel('Reads')
        png_fn = os.path.join(output_dir, "readLenDist{i}.png".format(i=i))
        png_base, thumbnail_base = save_figure_with_thumbnail(len_fig, png_fn,
                                                              dpi=dpi)

        plots.append(Plot("filter_len_xml_plot_{i}".format(i=i),
                          os.path.relpath(png_base),
                          thumbnail=os.path.relpath(thumbnail_base)))

    plot_groups = [PlotGroup("filter_len_xml_plot_group",
                             title="Polymerase Read Length",
                             plots=plots,
                             thumbnail=os.path.relpath(thumbnail_base))]

    plots = []

    # ReadQual distribution to barplot:
    for i, rqualdist in enumerate(dset.metadata.summaryStats.readQualDists):
        qual_fig, qual_axes = get_fig_axes_lpr()
        qual_axes.bar(rqualdist.labels, rqualdist.bins,
                      color=get_green(0), edgecolor=get_green(0),
                      width=(rqualdist.binWidth * 0.75))
        qual_axes.set_xlabel('Read Quality')
        qual_axes.set_ylabel('Reads')

        png_fn = os.path.join(output_dir, "readQualDist{i}.png".format(i=i))
        png_base, thumbnail_base = save_figure_with_thumbnail(qual_fig, png_fn,
                                                              dpi=dpi)

        plots.append(Plot("filter_qual_xml_plot_{i}".format(i=i),
                          os.path.relpath(png_base),
                          thumbnail=os.path.relpath(thumbnail_base)))

    plot_groups.append(PlotGroup("filter_qual_xml_plot_group",
                                 title="Polymerase Read Quality",
                                 plots=plots))

    # build the report:
    columns = [Column("filter_names_column", header="Metrics",
                      values=row_names)]
    columns.append(Column("filter_stats_column", header="Values",
                          values=_pre_filter))

    tables = [Table("filter_xml_table", "Filtering Statistics", columns)]

    report = Report("filtering_stats_xml_report",
                    title="Filtering stats XML report",
                    tables=tables,
                    attributes=None,
                    plotgroups=plot_groups)

    return report


def args_runner(args):
    log.info("Starting {f} v{v}".format(f=os.path.basename(__file__),
                                        v=__version__))
    output_dir = os.path.dirname(args.report)
    report = to_report(args.subread_set, output_dir)
    report.write_json(args.report)
    return 0

def resolved_tool_contract_runner(resolved_tool_contract):
    rtc = resolved_tool_contract
    log.info("Starting {f} v{v}".format(f=os.path.basename(__file__),
                                        v=__version__))
    output_dir = os.path.dirname(rtc.task.output_files[0])
    report = to_report(rtc.task.input_files[0], output_dir)
    report.write_json(rtc.task.output_files[0])
    return 0

def _add_options_to_parser(p):
    p.add_input_file_type(
        FileTypes.DS_SUBREADS,
        file_id="subread_set",
        name="SubreadSet",
        description="SubreadSet")
    p.add_output_file_type(
        FileTypes.REPORT, "report", "JSON report",
        description=("Filename of JSON output report. Should be name only, "
                     "and will be written to output dir"),
        default_name="report.json")

def add_options_to_parser(p):
    """
    API function for extending main pbreport arg parser (independently of
    tool contract interface).
    """
    p_wrap = _get_parser_core()
    p_wrap.arg_parser.parser = p
    p.description = __doc__
    add_debug_option(p)
    _add_options_to_parser(p_wrap)
    p.set_defaults(func=args_runner)
    return p

def _get_parser_core():
    p = get_pbparser(
        Constants.TOOL_ID,
        __version__,
        "Filtering Statistics XML Report",
        __doc__,
        Constants.DRIVER_EXE,
        is_distributed=True)
    return p

def get_parser():
    p = _get_parser_core()
    _add_options_to_parser(p)
    return p

def main(argv=sys.argv):
    mp = get_parser()
    return pbparser_runner(argv[1:],
                           mp,
                           args_runner,
                           resolved_tool_contract_runner,
                           log,
                           setup_log)


# for 'python -m pbreports.report.sat ...'
if __name__ == "__main__":
    sys.exit(main())
