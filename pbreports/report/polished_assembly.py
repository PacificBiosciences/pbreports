#!/usr/bin/env python

"""Generate a report based on the polished assembly"""

from collections import OrderedDict
import logging
import csv
import os
import os.path as op
import sys

import numpy as np

from pbcommand.models.report import (Attribute, Report, Plot, PlotGroup,
                                     PbReportError)
from pbreports.report.report_spec import (MetaAttribute, MetaPlotGroup, MetaPlot,
                                          MetaColumn, MetaTable, MetaReport)
from pbcommand.common_options import add_debug_option
from pbcommand.models import FileTypes, get_pbparser
from pbcommand.cli import pbparser_runner
from pbcommand.utils import setup_log
from pbcore.io import FastqReader, GffReader

from pbreports.report.coverage import ContigCoverage
from pbreports.util import compute_n50

log = logging.getLogger(__name__)

__version__ = '0.4'

__all__ = ['make_polished_assembly_report', 'ContigInfo',
           'get_parser']

# Import Mapping MetaReport
_DIR_NAME = os.path.dirname(os.path.realpath(__file__))
SPEC_DIR = os.path.join(_DIR_NAME, 'specs/')
POLISHED_ASSEMBLY_SPEC = op.join(SPEC_DIR, 'polished_assembly.json')
meta_rpt = MetaReport.from_json(POLISHED_ASSEMBLY_SPEC)


class Constants(object):
    TOOL_ID = "pbreports.tasks.polished_assembly"
    A_N_CONTIGS = "polished_contigs"
    A_MAX_LEN = "max_contig_length"
    A_N50_LEN = "n_50_contig_length"
    A_SUM_LEN = "sum_contig_lengths"
    PG_COVERAGE = "coverage_based"
    P_COVERAGE = "cov_vs_qual"


def make_polished_assembly_report(report, gff, fastq, output_dir):
    """
    Entry to report.
    :param gff: (str) path to alignment_summary.gff
    :param fastq: (str) path to polished fastq file
    :param report: (str) report name
    create a polished assembly report.
    """
    log.info("Starting version {f} v{x}".format(
        x=__version__, f=os.path.basename(__file__)))

    log.debug("Loading {f}".format(f=fastq))
    contigs = _get_contigs(fastq)

    log.debug("Loading {f}".format(f=gff))
    _get_contig_coverage(gff, contigs)

    log.debug("Computing and creating plots")

    cvqp = _coverage_vs_quality_plot(contigs, output_dir)

    pgrp = PlotGroup(Constants.PG_COVERAGE,
                     thumbnail=cvqp.thumbnail,
                     plots=[cvqp])

    rep = Report(meta_rpt.id)
    rep.add_attribute(Attribute(Constants.A_N_CONTIGS, len(contigs)))
    read_lengths = [c.length for c in contigs.values()]
    read_lengths.sort()
    rep.add_attribute(_get_att_max_contig_length(read_lengths))
    rep.add_attribute(_get_att_n_50_contig_length(read_lengths))
    rep.add_attribute(_get_att_sum_contig_lengths(read_lengths))
    rep.add_plotgroup(pgrp)
    rep = meta_rpt.apply_view(rep)

    rep.write_json(os.path.join(output_dir, report))
    _write_coverage_vs_quality_csv(contigs, output_dir)

    return 0


def _get_contigs(fastq):
    """
    Digests the polished contigs into a dict of ContigInfo objects
    :param fastq: (str) path to polished fastq file
    :return: (dict) contig id -> ContigInfo object
    """
    contigs = {}
    fqr = FastqReader(fastq)
    for rec in fqr:
        # remove quiver/arrow appended string, otherwise we can't cross
        # reference the name in the gff
        cinf = ContigInfo(rec)
        contigs[cinf.name] = cinf

    return contigs


def _write_coverage_vs_quality_csv(contigs, output_dir):
    """
    Writes out the data supporting the coverage vs qv plot
    :param contigs: (dict) contig id -> ContigInfo object
    :param output_dir: (str) path to output directory
    :return: No return value
    """
    csv_path = os.path.join(output_dir, "polished_coverage_vs_quality.csv")
    with open(csv_path, "w") as fha:
        wrt = csv.writer(fha)
        wrt.writerow(["contig_id", "mean_coverage", "mean_qv"])
        for con in contigs.values():
            wrt.writerow([con.name, con.mean_coverage, con.mean_qv])


def _coverage_vs_quality_plot(contigs, output_dir):
    """
    Creates a scatter plot coverage vs quality plot for each contig in the
    polished assembly.  Each point represents one contig.
    :param contigs: (dict) contig id -> ContigInfo object
    :param output_dir: (str) path to output directory
    :return: (Plot) object that has already been saved as a PNG to output_dir
    """
    import pbreports.plot.helper as PH
    fig, axes = PH.get_fig_axes_lpr()
    axes = fig.add_subplot(111)
    axes.set_axisbelow(True)
    axes.set_ylabel(meta_rpt.get_meta_plotgroup(
        Constants.PG_COVERAGE).get_meta_plot(Constants.P_COVERAGE).ylabel)
    axes.set_xlabel(meta_rpt.get_meta_plotgroup(
        Constants.PG_COVERAGE).get_meta_plot(Constants.P_COVERAGE).xlabel)
    PH.set_tick_label_font_size(axes, 12, 12)
    PH.set_axis_label_font_size(axes, 16)

    x_vals = [x.mean_coverage for x in contigs.values()]
    y_vals = [x.mean_qv for x in contigs.values()]

    axes.set_xlim(0, max(x_vals) * 1.2)
    axes.set_ylim(0, max(y_vals) * 1.2)

    axes.scatter(x_vals, y_vals, s=12)

    png_path = os.path.join(output_dir, "polished_coverage_vs_quality.png")
    png, thumbpng = PH.save_figure_with_thumbnail(fig, png_path)

    return Plot(Constants.P_COVERAGE, os.path.basename(png),
                thumbnail=os.path.basename(thumbpng))


def _get_att_max_contig_length(read_lengths):
    """
    Return the last member of the sorted list. 0 if read_lengths is empty.
    :param read_lengths: sorted list
    :return: (int) The length of largest contig
    """
    val = 0
    l = len(read_lengths)
    if l == 0:
        val = 0
    else:
        val = read_lengths[l - 1]
    return Attribute(Constants.A_MAX_LEN, val)


def _get_att_sum_contig_lengths(read_lengths):
    """
    Return the last member of the sorted list. 0 if read_lengths is empty.
    :param read_lengths: sorted list
    """
    return Attribute(Constants.A_SUM_LEN, sum(read_lengths))


def _get_att_n_50_contig_length(read_lengths):
    """
    Get the n50 or 0 if n50 cannot be calculated
    :param read_lengths: sorted list
    """
    n50 = compute_n50(read_lengths)
    return Attribute(Constants.A_N50_LEN, int(n50))


def _validate_inputs(infile, desc="input file"):
    """
    Raise an Error if a required file is null or non-existent
    :param fasta_file: (str) path to fasta
    """
    if infile is None:
        raise PbReportError('%s cannot be None' % desc)
    if not os.path.exists(infile):
        raise IOError('{g} does not exist {d}'.format(g=infile, d=desc))


def _get_contig_coverage(alignment_summ_gff, contigs):
    """
    Modifies the passed contigs object to include coverage information.
    :param alignment_summ_gff: (str) path to alignment_summ_gff
    :param contigs: (dict) contig id -> ContigInfo object
    """
    reader = GffReader(alignment_summ_gff)
    for rec in reader:
        # Some contigs don't have any coverage, but make it into the gff file
        if rec.seqid in contigs:
            contigs[rec.seqid].add_coverage_data(rec)

    reader.close()


class ContigInfo(object):
    """Contains relevant contig information needed for plotting.  Contig id,
    length and averaged QV and average coverage depth.
    """

    def __init__(self, rec):
        """Constructs a new object with the given fastq record"""
        # strip quiver appendage from name
        if rec.name.endswith("|quiver"):
            self._name = rec.name[:rec.name.index('|quiver')]
        else:
            self._name = rec.name[:rec.name.index('|arrow')]
        self._qv = np.average(rec.quality)
        self._len = len(rec.sequence)
        self._cov = ContigCoverage(self._name)

    def __repr__(self):
        _d = dict(k=self.__class__.__name__, n=self.name, l=self.length)
        return "<{k} name:{n} length:{l} >".format(**_d)

    def add_coverage_data(self, gffrec):
        """Adds coverage information from a gff record"""
        self._cov.add_data(gffrec)

    @property
    def name(self):
        """Contig name (or ID)"""
        return self._name

    @property
    def mean_qv(self):
        """Mean QV value"""
        return self._qv

    @property
    def length(self):
        """Contig length"""
        return self._len

    @property
    def mean_coverage(self):
        """Mean coverage"""
        return self._cov.meanCoveragePerBase()


def args_runner(args):
    output_dir, report = os.path.split(args.polished_assembly_rpt)
    make_polished_assembly_report(report,
                                  args.aln_summary_gff,
                                  args.polished_assembly,
                                  output_dir)
    return 0


def resolved_tool_contract_runner(resolved_tool_contract):
    rtc = resolved_tool_contract
    make_polished_assembly_report(
        rtc.task.output_files[0],
        rtc.task.input_files[0],
        rtc.task.input_files[1],
        os.path.dirname(rtc.task.output_files[0]))
    return 0


def _add_options_to_parser(p):
    p.add_input_file_type(
        FileTypes.GFF,
        file_id="aln_summary_gff",
        name="Alignment Summary GFF",
        description="Alignment Summary GFF")
    p.add_input_file_type(
        FileTypes.FASTQ,
        file_id="polished_assembly",
        name="Polished Assembly FASTQ",
        description="Polished Assembly FASTQ")
    p.add_output_file_type(
        FileTypes.REPORT,
        file_id="polished_assembly_rpt",
        name="Polished Assembly Report",
        description="Polished Assembly Report",
        default_name="polished_assembly_report")


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
    driver_exe = ("python -m "
                  "pbreports.report.polished_assembly "
                  "--resolved-tool-contract ")
    p = get_pbparser(
        Constants.TOOL_ID,
        __version__,
        meta_rpt.title,
        __doc__,
        driver_exe)
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

# for 'python -m pbreports.report.polished_assembly ...'
if __name__ == "__main__":
    sys.exit(main())
