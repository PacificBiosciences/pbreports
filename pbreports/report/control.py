
import os
import logging
import sys
import functools

from pbcommand.models.report import Report, Plot, PlotGroup, Attribute
from pbcommand.cli import pbparser_runner
from pbcommand.utils import setup_log
from pbcore.io import SubreadSet

from pbreports.plot.helper import (get_fig_axes_lpr, get_green,
                                   save_figure_with_thumbnail)
from pbreports.model import InvalidStatsError
from pbreports.io.specs import *
from pbreports.util import (_cont_dist_shaper, dist_shaper,
                            get_subreads_report_parser,
                            arg_runner_subreads_report,
                            rtc_runner_subreads_report)

__version__ = '0.1.0'


class Constants(object):
    TOOL_ID = "pbreports.tasks.control_report"
    DRIVER_EXE = ("python -m pbreports.report.control "
                  "--resolved-tool-contract ")
    R_ID = "control"
    A_NREADS = "reads_n"
    A_READLENGTH_MEAN = "readlength_mean"
    A_CONCORDANCE_MEAN = "concordance_mean"
    A_CONCORDANCE_MODE = "concordance_mode"

    P_READLENGTH = "readlength_plot"
    PG_READLENGTH = "readlength_plotgroup"
    P_CONCORDANCE = "concordance_plot"
    PG_CONCORDANCE = "concordance_plotgroup"


log = logging.getLogger(__name__)
spec = load_spec(Constants.R_ID)


def to_nreads(readlen_dist):
    nreads = readlen_dist.sampleSize
    attribute = Attribute(Constants.A_NREADS, nreads)
    return attribute


def to_readlength_mean(readlen_dist):
    readlength_mean = int(readlen_dist.sampleMean)
    attribute = Attribute(Constants.A_READLENGTH_MEAN, readlength_mean)
    return attribute


def to_concordance_mean(readqual_dist):
    concordance_mean = readqual_dist.sampleMean
    attribute = Attribute(Constants.A_CONCORDANCE_MEAN, concordance_mean)
    return attribute


def to_concordance_mode(readqual_dist):
    #    concordance_mode = readqual_dist.sampleMode
    concordance_mode = None
    attribute = Attribute(Constants.A_CONCORDANCE_MODE, concordance_mode)
    return attribute


def to_attributes(readlen_dist, readqual_dist):
    attributes = []
    attributes.append(to_nreads(readlen_dist))
    attributes.append(to_readlength_mean(readlen_dist))
    attributes.append(to_concordance_mean(readqual_dist))
    attributes.append(to_concordance_mode(readqual_dist))
    return attributes


def reshape(readlen_dist, edges, heights):
    lenDistShaper = functools.partial(_cont_dist_shaper, dist_shaper(
        [(heights, edges)], nbins=40, trim_excess=False))
    readlen_dist = lenDistShaper(readlen_dist)
    nbins = readlen_dist.numBins
    bin_counts = readlen_dist['BinCounts']
    heights = readlen_dist.bins
    bin_width = readlen_dist.binWidth
    edges = [float(bn) * bin_width for bn in xrange(nbins)]
    return edges, heights, bin_width


def to_readlen_plotgroup(readlen_dist, output_dir):
    plot_name = get_plot_title(
        spec, Constants.PG_READLENGTH, Constants.P_READLENGTH)
    x_label = get_plot_xlabel(
        spec, Constants.PG_READLENGTH, Constants.P_READLENGTH)
    y_label = get_plot_ylabel(
        spec, Constants.PG_READLENGTH, Constants.P_READLENGTH)
    nbins = readlen_dist.numBins
    bin_counts = readlen_dist['BinCounts']
    heights = readlen_dist.bins
    bin_width = readlen_dist.binWidth
    edges = [float(bn) * bin_width for bn in xrange(nbins)]
    edges, heights, bin_width = reshape(readlen_dist, edges, heights)
    fig, ax = get_fig_axes_lpr()
    ax.bar(edges, heights, color=get_green(0),
           edgecolor=get_green(0), width=(bin_width * 0.75))
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    png_fn = os.path.join(
        output_dir, "{p}.png".format(p=Constants.P_READLENGTH))
    png_base, thumbnail_base = save_figure_with_thumbnail(fig, png_fn, dpi=72)
    readlen_plot = Plot(Constants.P_READLENGTH,
                        os.path.relpath(png_base, output_dir),
                        title=plot_name, caption=plot_name,
                        thumbnail=os.path.relpath(thumbnail_base, output_dir))
    plot_groups = [PlotGroup(Constants.PG_READLENGTH, plots=[readlen_plot])]
    return plot_groups


def to_concordance_plotgroup(readqual_dist, output_dir):
    plot_name = get_plot_title(
        spec, Constants.PG_CONCORDANCE, Constants.P_CONCORDANCE)
    x_label = get_plot_xlabel(
        spec, Constants.PG_CONCORDANCE, Constants.P_CONCORDANCE)
    y_label = get_plot_ylabel(
        spec, Constants.PG_CONCORDANCE, Constants.P_CONCORDANCE)
    nbins = readqual_dist.numBins
    bin_counts = readqual_dist['BinCounts']
    heights = readqual_dist.bins
    edges = [float(bn) / float(nbins) for bn in xrange(nbins)]
    bin_width = readqual_dist.binWidth
    fig, ax = get_fig_axes_lpr()
    ax.bar(edges, heights, color=get_green(0),
           edgecolor=get_green(0), width=(bin_width * 0.75))
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    png_fn = os.path.join(
        output_dir, "{p}.png".format(p=Constants.P_CONCORDANCE))
    png_base, thumbnail_base = save_figure_with_thumbnail(fig, png_fn, dpi=72)
    concordance_plot = Plot(Constants.P_CONCORDANCE,
                            os.path.relpath(png_base, output_dir),
                            title=plot_name, caption=plot_name,
                            thumbnail=os.path.relpath(thumbnail_base, output_dir))
    plot_groups = [PlotGroup(Constants.PG_CONCORDANCE,
                             plots=[concordance_plot])]
    return plot_groups


def to_plotgroups(readlen_dist, readqual_dist, output_dir):
    plotgroups = []
    plotgroups.extend(to_readlen_plotgroup(readlen_dist, output_dir))
    plotgroups.extend(to_concordance_plotgroup(readqual_dist, output_dir))
    return plotgroups


def to_report(stats_xml, output_dir):
    log.info("Starting {f} v{v}".format(f=os.path.basename(__file__),
                                        v=__version__))
    log.info("Analyzing XML {f}".format(f=stats_xml))
    dset = SubreadSet(stats_xml)
    dset.loadStats()
    if stats_xml.endswith(".sts.xml"):
        dset.loadStats(stats_xml)
    return to_report_impl(dset, output_dir)


def to_report_impl(dset, output_dir):
    if not dset.metadata.summaryStats.controlReadLenDist:
        raise InvalidStatsError("Control Read Length Distribution not found")
    if not dset.metadata.summaryStats.controlReadQualDist:
        raise InvalidStatsError("Control Read Quality Distribution not found")

    readlen_dist = dset.metadata.summaryStats.controlReadLenDist
    readqual_dist = dset.metadata.summaryStats.controlReadQualDist

    attributes = to_attributes(readlen_dist, readqual_dist)
    plotgroups = to_plotgroups(readlen_dist, readqual_dist, output_dir)

    report = Report(Constants.R_ID, attributes=attributes,
                    plotgroups=plotgroups)

    return spec.apply_view(report)


resolved_tool_contract_runner = functools.partial(rtc_runner_subreads_report,
                                                  to_report)
args_runner = functools.partial(arg_runner_subreads_report, to_report)


def main(argv=sys.argv):
    mp = get_subreads_report_parser(Constants.TOOL_ID, __version__, spec.title,
                                    __doc__, Constants.DRIVER_EXE)
    return pbparser_runner(argv[1:],
                           mp,
                           args_runner,
                           resolved_tool_contract_runner,
                           log,
                           setup_log)


if __name__ == "__main__":
    sys.exit(main())
