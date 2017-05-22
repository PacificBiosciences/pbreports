#!/usr/bin/env python

"""
Generates a table showing consensus stats and a report showing variants plots
for the top 25 contigs of the supplied reference.
"""

import logging
import hashlib
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pbcommand.models.report import (Table, Column, Attribute, Report,
                                     PlotGroup, Plot, PbReportError)
from pbcommand.models import FileTypes, get_pbparser
from pbcommand.cli import pbparser_runner
from pbcommand.utils import setup_log
from pbcore.io import GffReader, ReferenceSet

from pbreports.util import (openReference, average_or_none,
                            get_top_contigs_from_ref_entry)
import pbreports.plot.helper as PH
from pbreports.io.specs import *

log = logging.getLogger(__name__)

__version__ = '0.1'


class Constants(object):
    TOOL_ID = "pbreports.tasks.variants_report"
    DRIVER_EXE = "python -m pbreports.report.variants --resolved-tool-contract "
    R_ID = "variants"
    MAX_CONTIGS_ID = "pbreports.task_options.max_contigs"
    MAX_CONTIGS_DEFAULT = 25
    MEAN_CONTIG_LENGTH = "mean_contig_length"
    MEAN_BASES_CALLED = "weighted_mean_bases_called"
    MEAN_CONCORDANCE = "weighted_mean_concordance"
    MEAN_COVERAGE = "weighted_mean_coverage"
    LONGEST_CONTIG = "longest_contig_name"
    T_STATS = "consensus_table"
    C_CONTIG_NAME = "contig_name"
    C_CONTIG_LEN = "contig_len"
    C_BASES_CALLED = "bases_called"
    C_CONCORDANCE = "concordance"
    C_COVERAGE = "coverage"
    PG_VARIANTS = "variants_plots"
    P_VARIANTS = "variants_plot"

LENGTH, GAPS, ERR, COV = 0, 1, 2, 3

spec = load_spec(Constants.R_ID)


def make_variants_report(aln_summ_gff, variants_gff, reference, max_contigs_to_plot, report, output_dir, dpi=72, dumpdata=True):
    """
    Entry to report.
    :param aln_summ_gff: (str) path to alignment_summary.gff
    :param variants_gff: (str) path to variants_gff
    :param reference: (str) path to reference_dir
    :param max_contigs_to_plot: (int) max number of contigs to plot
    """
    _validate_inputs([('aln_summ_gff', aln_summ_gff),
                      ('variants_gff', variants_gff),
                      ('reference', reference)])

    # reference entry & top contings
    ref = openReference(reference)
    top_contigs = get_top_contigs_from_ref_entry(ref, max_contigs_to_plot)

    # extract gff data from files
    ref_data, contig_variants = _extract_alignment_summ_data(
        aln_summ_gff, top_contigs)
    _append_variants_gff_data(ref_data, variants_gff)

    # make report objects
    table, atts = _get_consensus_table_and_attributes(ref_data, ref)
    plotgroup = _create_variants_plot_grp(
        top_contigs, contig_variants, output_dir)

    rpt = Report(Constants.R_ID,
                 plotgroups=[plotgroup],
                 attributes=atts,
                 tables=[table],
                 dataset_uuids=(ReferenceSet(reference).uuid,))

    rpt = spec.apply_view(rpt)
    rpt.write_json(os.path.join(output_dir, report))
    return rpt


def _validate_inputs(files):
    """
    Raise an Error if a required file is null or non-existent
    :param files: list of tuples, first element of tuple is input name second is value
    """
    for f in files:
        if f[1] is None:
            raise PbReportError('{f} cannot be None'.format(f=f[0]))
        if not os.path.exists(f[1]):
            raise IOError('{f} does not exist'.format(f=f[1]))


def _extract_alignment_summ_data(aln_summ_gff, contigs):
    """
    :param aln_summ_gff: (str) path to alignment_summary.gff
    :param contigs: (list) top contigs from reference
    :returns: 2 dictionaries containing data extracted from alignment_summary.gff
    """

    def _get_name(id_):
        for c in contigs:
            if c.id == id_:
                return c.name

    contig_ids = [c.id for c in contigs]

    ref_data = {}
    var_map = {}

    log.info("Reading GFF data from {f}".format(f=aln_summ_gff))

    reader = GffReader(aln_summ_gff)
    for rec in reader:
        seqid = rec.seqid.split()[0]
        if seqid not in contig_ids:
            continue

        # first data set
        ref_data.setdefault(seqid, [0, 0, 0, 0])
        ref_data[seqid][LENGTH] = max(rec.end, ref_data[seqid][LENGTH])
        numGaps, lenGaps = rec.attributes["gaps"].split(",")
        ref_data[seqid][GAPS] += int(lenGaps)
        ref_data[seqid][COV] += float( rec.attributes["cov2"].split(",")[0] ) * \
            (rec.end - rec.start + 1)

        # second data set
        contig_var = None
        try:
            contig_var = var_map[seqid]
        except KeyError:
            contig_var = ContigVariants(seqid, _get_name(seqid))
            var_map[seqid] = contig_var

        contig_var.add_data(rec)

    reader.close()

    return ref_data, var_map


def _create_variants_plot_grp(top_contigs, var_map, output_dir):
    """
    Returns io.model.PlotGroup object
    Create the plotGroup element that contains variants plots of the top contigs.
    :param top_contigs: (list of Contig objects) sorted by contig size
    :param var_map: (dict string:ContigVariants) mapping of contig.header to ContigVariants object
    :param output_dir: (string) where to write images
    """
    plots = []
    thumbnail = None
    legend = None
    idx = 0
    for tc in top_contigs:
        if not tc.header in var_map:
            # no coverage of this contig
            continue
        ctg_var = var_map[tc.header]
        bars = _create_bars(ctg_var)
        if legend is None:
            legend = _get_legend_file(bars, output_dir)

        fig, ax = _create_contig_fig_ax(bars, _get_x_labels(ctg_var))

        fname = os.path.join(output_dir, ctg_var.file_name)
        if thumbnail is None:
            imgfiles = PH.save_figure_with_thumbnail(fig, fname)
            thumbnail = os.path.basename(imgfiles[1])
        else:
            fig.savefig(fname)

        id_ = 'coverage_variants_{i}'.format(i=str(idx))
        caption = "Observed variants across {c}".format(c=ctg_var.name)
        plot = Plot(id_, os.path.basename(fname),
                    title=caption, caption=caption)
        plots.append(plot)
        idx += 1
        plt.close(fig)

    plot_group = PlotGroup(Constants.PG_VARIANTS,
                           thumbnail=thumbnail,
                           legend=legend,
                           plots=plots)
    return plot_group


def _get_x_labels(ctg_var):
    return np.array([l[0] for l in ctg_var.variants])


def _get_legend_file(bars, output_dir):
    """
    Get the legend basename
    :param bars: iterable pbreports.plot.helper.Bar
    :param output_dir: Where to write file
    :return (string) filename
    """
    fig = PH.get_bar_plot_legend_fig(bars)
    fname = 'variants_plot_legend.png'
    fig.savefig(os.path.join(output_dir, fname), dpi=60)
    plt.close(fig)
    return fname


def _create_bars(contig_variants):
    """
    :param contig_variants: (ContigVariants)
    :returns: tuple of pbreports.plot.helper.Bar objects
    """

    dataIns = np.array([l[1] for l in contig_variants.variants])
    dataDels = np.array([l[2] for l in contig_variants.variants])
    dataSnv = np.array([l[3] for l in contig_variants.variants])

    insBarModel = PH.Bar(dataIns, 'Insertions', color=PH.get_blue(3))
    delBarModel = PH.Bar(dataDels, 'Deletions', color=PH.get_green(3))
    snvBarModel = PH.Bar(dataSnv, 'Substitutions', color=PH.get_orange())

    return (insBarModel, delBarModel, snvBarModel)


def _create_contig_fig_ax(bars, xlabels):
    """
    Returns a fig,ax plot for this contig
    :param contig_variants: (ContigVariants) 
    """
    fig, ax = PH.get_fig_axes_lpr()
    xlabel = get_plot_xlabel(spec, Constants.PG_VARIANTS, Constants.P_VARIANTS)
    ylabel = get_plot_ylabel(spec, Constants.PG_VARIANTS, Constants.P_VARIANTS)
    PH.apply_bar_data(ax, bars, xlabels, (xlabel, ylabel))
    return fig, ax


def _append_variants_gff_data(ref_data, variants_gff):
    """
    Adds data from variants gff to the ref_data dict
    :param ref_data: (dict) dict of data pulled from alignment_summary.gff
    :param variants_gff: (str) path to variants_gff

    :type variants_gff: str
    """
    reader = GffReader(variants_gff)
    for record in reader:
        err_len = record.end - record.start + 1
        seqid = record.seqid.split()[0]
        if seqid in ref_data:
            ref_data[seqid][ERR] += err_len
        else:
            # the variants might not be present in the top 25 contigs,
            # so we can just raise a warning in the log.
            msg = "Unable to find {r} in {f}".format(
                r=seqid, f=variants_gff)
            log.warn(msg)

    reader.close()


def _get_consensus_table_and_attributes(ref_data, reference_entry):
    """
    Get a tuple: Table and list of Attributes
    :param ref_data: (dict) dict of data pulled from alignment_summary.gff
    :param reference_entry: reference entry
    :return: tuple (Table, [Attributes])
    """
    ordered_ids = _ref_ids_ordered_by_len(ref_data)

    sum_lengths = 0.0
    mean_bases_called = 0.0
    mean_concord = None
    mean_coverage = 0.0

    columns = []
    columns.append(Column(Constants.C_CONTIG_NAME))
    columns.append(Column(Constants.C_CONTIG_LEN))
    columns.append(Column(Constants.C_BASES_CALLED))
    columns.append(Column(Constants.C_CONCORDANCE))
    columns.append(Column(Constants.C_COVERAGE))
    table = Table(Constants.T_STATS, columns=columns)

    for seqid in ordered_ids:
        contig = reference_entry.get_contig(seqid)

        length = float(ref_data[seqid][LENGTH])
        gaps = float(ref_data[seqid][GAPS])
        errors = float(ref_data[seqid][ERR])
        cov = float(ref_data[seqid][COV])

        sum_lengths += length
        bases_called = 1.0 - gaps / length
        mean_bases_called += bases_called * length

        concord = None
        if length != gaps:

            log.info('length {f}'.format(f=length))
            log.info('gaps {f}'.format(f=gaps))
            log.info('errors {f}'.format(f=errors))

            concord = 1.0 - errors / (length - gaps)
            if mean_concord is None:
                mean_concord = concord * length
            else:
                mean_concord += concord * length

        coverage = cov / length
        mean_coverage += coverage * length

        # table shows values for each contig
        table.add_data_by_column_id(Constants.C_CONTIG_NAME, contig.name)
        table.add_data_by_column_id(Constants.C_CONTIG_LEN, length)
        table.add_data_by_column_id(Constants.C_BASES_CALLED, bases_called)
        table.add_data_by_column_id(Constants.C_CONCORDANCE, concord)
        table.add_data_by_column_id(Constants.C_COVERAGE, coverage)

    mean_contig_length = 0.0
    mean_contig_length = average_or_none(sum_lengths, len(ordered_ids), 0.0)
    mean_bases_called = average_or_none(mean_bases_called, sum_lengths, 0.0)
    mean_coverage = average_or_none(mean_coverage, sum_lengths, 0.0)
    if mean_concord is not None:
        mean_concord = mean_concord / sum_lengths

    attributes = []
    if mean_concord is not None:
        attributes.append(Attribute(Constants.MEAN_CONCORDANCE, mean_concord))
    else:
        attributes.append(Attribute(Constants.MEAN_CONCORDANCE, 0.0))
    attributes.append(
        Attribute(Constants.MEAN_CONTIG_LENGTH, mean_contig_length))
    if len(ordered_ids) > 0:
        attributes.append(Attribute(Constants.LONGEST_CONTIG, ordered_ids[0]))
    else:
        attributes.append(Attribute(Constants.LONGEST_CONTIG, "NA"))
    attributes.append(
        Attribute(Constants.MEAN_BASES_CALLED, mean_bases_called))
    attributes.append(Attribute(Constants.MEAN_COVERAGE, mean_coverage))

    return table, attributes


def _ref_ids_ordered_by_len(ref_data):
    """
    Returns a list of seq id strings, ordered by the length of the sequence
    :param ref_data: (dict) dict of data pulled from alignment_summary.gff
    "return: list
    """
    ordered_tuples = []
    for ref in ref_data.keys():
        ordered_tuples.append((ref, ref_data[ref][LENGTH]))
    ordered_tuples = sorted(
        ordered_tuples, key=lambda tup: tup[1], reverse=True)
    return [i[0] for i in ordered_tuples]


class ContigVariants(object):

    def __init__(self, seqId, name=None):
        """Encapsulates variant info relevant to one chart"""
        self.seqid = seqId

        self.name = seqId if name is None else name

        self.variants = []

        # seqId is the fasta header, which could be long and have spaces and/or symbols that are
        # not good to use in filename.
        m = hashlib.md5()
        m.update(seqId)

        self.file_name = "variants_plot_%s%s" % (m.hexdigest(), ".png")

    def add_data(self, gff3Record):
        """Append x,y data from this record to the contig graph"""

        atts = gff3Record.attributes
        startPos = int(gff3Record.start)
        inse = int(atts['ins'])
        de1e = int(atts['del'])
        snv = int(atts['sub'])

        self.variants.append((startPos, inse, de1e, snv))


def _args_runner(args):
    rpt = make_variants_report(args.aln_summ_gff, args.variants_gff, args.reference, args.maxContigs,
                               args.report, os.path.dirname(args.report))
    log.info(rpt)
    return 0


def _resolved_tool_contract_runner(rtc):
    rpt = make_variants_report(
        aln_summ_gff=rtc.task.input_files[1],
        variants_gff=rtc.task.input_files[2],
        reference=rtc.task.input_files[0],
        max_contigs_to_plot=rtc.task.options[Constants.MAX_CONTIGS_ID],
        report=rtc.task.output_files[0],
        output_dir=os.path.dirname(rtc.task.output_files[0]))
    log.info(rpt)
    return 0


def _add_options_to_parser(p):
    p.add_output_file_type(FileTypes.REPORT, "report", "Variants Report",
                           description="Summary of variant calling",
                           default_name="variants_report")
    p.add_input_file_type(FileTypes.DS_REF,
                          file_id="reference",
                          name="Reference dataset",
                          description="ReferenceSet or FASTA")
    p.add_input_file_type(FileTypes.GFF,
                          file_id="aln_summ_gff",
                          name="Alignment summary GFF",
                          description="Alignment summary GFF")
    p.add_input_file_type(FileTypes.GFF,
                          file_id="variants_gff",
                          name="Variants GFF",
                          description="Variants GFF")
    p.add_int(Constants.MAX_CONTIGS_ID, "maxContigs",
              default=Constants.MAX_CONTIGS_DEFAULT,
              name="Maximum contigs",
              description="Maximum number of contigs to plot. Defaults to 25.")
    return p


def _get_parser():
    p = get_pbparser(
        Constants.TOOL_ID,
        __version__,
        spec.title,
        __doc__,
        Constants.DRIVER_EXE,
        is_distributed=True)
    return _add_options_to_parser(p)


def main(argv=sys.argv):
    return pbparser_runner(argv[1:],
                           _get_parser(),
                           _args_runner,
                           _resolved_tool_contract_runner,
                           log,
                           setup_log)

if __name__ == "__main__":
    sys.exit(main())
