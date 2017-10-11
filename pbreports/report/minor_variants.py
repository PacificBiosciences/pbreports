
"""
Minor Variants Report
"""

import os
import os.path as op
import logging
import sys
import csv
import itertools
import json

import numpy as np

from pbcommand.models.report import Report, Table, Column
from pbcommand.models import FileTypes, get_pbparser
from pbcommand.cli import pbparser_runner
from pbcommand.utils import setup_log
from pbreports.io.specs import *

__version__ = '0.1.1'


class Constants(object):
    TOOL_ID = "pbreports.tasks.minor_variants_report"
    DRIVER_EXE = ("python -m pbreports.report.minor_variants "
                  "--resolved-tool-contract ")
    R_ID = "minor_variants"

    T_SAMPLES = "sample_table"
    C_SAMPLES_S = "barcode"
    C_COVERAGE_S = "coverage"
    C_VARIANTS_S = "variants"
    C_GENES_S = "genes"
    C_DRMS_S = "drms"
    C_HAPLOTYPES_S = "haplotypes"
    C_HAP_FREQ_S = "haplotype_frequency"
    SAMPLES_COL_IDS = [C_SAMPLES_S, C_COVERAGE_S, C_VARIANTS_S, C_GENES_S,
                       C_DRMS_S, C_HAPLOTYPES_S, C_HAP_FREQ_S]

    T_VARIANTS = "variant_table"
    C_SAMPLES_V = "barcode"
    C_POSITION_V = "position"
    C_REF_CODON_V = "ref_codon"
    C_VAR_CODON_V = "var_codon"
    C_VAR_FREQ_V = "var_freq"
    C_COVERAGE_V = "coverage"
    C_ORF_V = "orf"
    C_DRMS_V = "drms"
    C_HAPLOTYPES_V = "haplotypes"
    C_HAP_FREQ_V = "haplotype_frequencies"
    VARIANTS_COL_IDS = [C_SAMPLES_V, C_POSITION_V, C_REF_CODON_V, C_VAR_CODON_V, C_VAR_FREQ_V,
                        C_COVERAGE_V, C_ORF_V, C_DRMS_V, C_HAPLOTYPES_V, C_HAP_FREQ_V]


log = logging.getLogger(__name__)
spec = load_spec(Constants.R_ID)


def get_hap_vals(hap_hits, hap_vals, _type):
    """Returns list of haplotype name or frequency values
       for a given variant, using the boolean array and
       list of possible values"""
    haps = []
    for i, hap_hit in enumerate(hap_hits):
        if hap_hit:
            if _type is float:
                haps.append(100 * _type(hap_vals[i]))
            else:
                haps.append(_type(hap_vals[i]))
    return haps


def to_variant_table(juliet_summary):
    samples = []
    positions = []
    ref_codons = []
    sample_codons = []
    frequencies = []
    coverage = []
    genes = []
    drms = []
    haplotype_names = []
    haplotype_frequencies = []

    for sample_name, sample_details in juliet_summary.iteritems():
        _all_hap_names = []
        _all_hap_freqs = []
        for haplotype in sample_details['haplotypes']:
            _all_hap_names.append(haplotype['name'])
            _all_hap_freqs.append(haplotype['frequency'])
        for gene in sample_details['genes']:
            _genes = gene['name']
            for position in gene['variant_positions']:
                _coverage = position['coverage']
                _ref_codons = position['ref_codon']
                _position = position['ref_position']
                for aa in position['variant_amino_acids']:
                    for variant in aa['variant_codons']:
                        samples.append(str(sample_name))
                        positions.append(int(_position))
                        ref_codons.append(str(_ref_codons))
                        sample_codons.append(str(variant['codon']))
                        frequencies.append(100 * float(variant['frequency']))
                        coverage.append(int(_coverage))
                        genes.append(str(_genes))
                        drms.append([str(v)
                                     for v in variant['known_drm'].split(" + ")])
                        haplotype_names.append(get_hap_vals(
                            variant['haplotype_hit'], _all_hap_names, str))
                        haplotype_frequencies.append(get_hap_vals(
                            variant['haplotype_hit'], _all_hap_freqs, float))

    variant_table = [samples, positions, ref_codons, sample_codons, frequencies,
                     coverage, genes, drms, haplotype_names, haplotype_frequencies]

    return variant_table


def join_col(col):
    """Converts an array of arrays into an array of strings, using ';' as the sep."""
    joined_col = []
    for item in col:
        joined_col.append(";".join(map(str, item)))
    return joined_col


def write_variant_table(variant_table, file_name):
    header_row = []
    for c_id in Constants.VARIANTS_COL_IDS:
        header_row.append(spec.get_table_spec(
            Constants.T_VARIANTS).get_column_spec(c_id).header)
    variant_table_csv = variant_table[:]
    for i in [7, 8, 9]:
        variant_table_csv[i] = join_col(variant_table_csv[i])
    variant_table_csv_tr = zip(*variant_table_csv)
    with open(file_name, 'w') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header_row)
        [writer.writerow(r) for r in variant_table_csv_tr]


def _round(freqs):
    rounded = []
    for item in freqs:
        rounded.append("{0:.2f}".format(round(item, 2)))
    return rounded


def to_rpt_variant_table(variant_table):

    variant_table_r = variant_table[:]

    variant_table_r[9] = map(lambda x: _round(x), variant_table_r[9])

    for i in [7, 8, 9]:
        variant_table_r[i] = join_col(variant_table_r[i])

    columns = []
    for i, col_id in enumerate(Constants.VARIANTS_COL_IDS):
        columns.append(Column(col_id, values=variant_table_r[i]))

    variant_table_rpt = Table(Constants.T_VARIANTS, columns=columns)

    return variant_table_rpt


def my_agg(my_list, _func):
    """Performs the specified function on an array of arrays, 
       returning None in the case of a ValueError"""
    try:
        return _func([i for i in itertools.chain(*my_list)])
    except ValueError:
        # case for max of empty list
        return None


def aggregate_variant_table(variant_table):

    samples = []
    coverage = []
    variants = []
    genes = []
    drms = []
    haplotypes = []
    max_hap_freq = []

    for sample in set(variant_table[0]):
        indices = [i for i, x in enumerate(variant_table[0]) if x == sample]
        _coverage = [variant_table[5][i] for i in indices]
        _genes = [variant_table[6][i] for i in indices]
        _drms = [variant_table[7][i] for i in indices]
        _haplotypes = [variant_table[8][i] for i in indices]
        _max_hap_freq = [variant_table[9][i] for i in indices]

        samples.append(str(sample))
        coverage.append(int(np.median(_coverage)))
        variants.append(len(_coverage))
        genes.append(len(np.unique(_genes)))
        drms.append(len(my_agg(_drms, np.unique)))
        haplotypes.append(len(my_agg(_haplotypes, np.unique)))
        agg_max_hap_freq = my_agg(_max_hap_freq, max)
        if agg_max_hap_freq is not None:
            max_hap_freq.append(float(my_agg(_max_hap_freq, max)))
        else:
            max_hap_freq.append(None)

    sample_table = [samples, coverage, variants,
                    genes, drms, haplotypes, max_hap_freq]

    return sample_table


def to_sample_table(variant_table):

    sample_table = aggregate_variant_table(variant_table)

    columns = []
    for i, col_id in enumerate(Constants.SAMPLES_COL_IDS):
        columns.append(Column(col_id, values=sample_table[i]))

    sample_table_r = Table(Constants.T_SAMPLES, columns=columns)

    return sample_table_r


def to_report(juliet_summary_file, csv_file, output_dir):
    log.info("Starting {f} v{v}".format(f=os.path.basename(__file__),
                                        v=__version__))

    with open(juliet_summary_file) as f:
        juliet_summary = json.load(f)

    variant_table = to_variant_table(juliet_summary)
    write_variant_table(variant_table, csv_file)

    rpt_variant_table = to_rpt_variant_table(variant_table)
    sample_table = to_sample_table(variant_table)
    tables = [sample_table, rpt_variant_table]

    report = Report(Constants.R_ID, tables=tables)

    return spec.apply_view(report)


def _args_runner(args):
    output_dir = os.path.dirname(args.report)
    report = to_report(args.json, args.csv, output_dir)
    report.write_json(args.report)
    return 0


def _resolved_tool_contract_runner(rtc):
    output_dir = os.path.dirname(rtc.task.output_files[0])
    report = to_report(rtc.task.input_files[0],
                       rtc.task.output_files[1],
                       output_dir)
    report.write_json(rtc.task.output_files[0])
    return 0


def _add_options_to_parser(p):
    p.add_input_file_type(
        FileTypes.JSON,
        file_id="json",
        name="JSON",
        description="Juliet Summary JSON")
    p.add_output_file_type(FileTypes.REPORT, "report", spec.title,
                           description=("Filename of JSON output report. Should be name only, "
                                        "and will be written to output dir"),
                           default_name="report")
    p.add_output_file_type(FileTypes.CSV, "csv", "Per-Variant Table",
                           description=("Filename of CSV output table. Should be name only, "
                                        "and will be written to output dir"),
                           default_name="report")
    return p


def _get_parser():
    p = get_pbparser(
        Constants.TOOL_ID,
        __version__,
        "Minor Variants Report",
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
