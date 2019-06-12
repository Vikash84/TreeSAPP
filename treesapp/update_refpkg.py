import os
import sys
import re
import logging
from .external_command_interface import launch_write_command
from . import wrapper


def align_ref_queries(args, new_ref_queries, update_tree):
    """
    Function queries the candidate set of proteins to be used for updating the tree against the reference set
    The output feeds into find_novel_refs. Necessary to determine whether there are interesting new proteins or
    just more of the same
    :param args: Command-line argument object from get_options and check_parser_arguments
    :param new_ref_queries:
    :param update_tree:
    :return: Path to tabular alignment file
    """
    alignments = update_tree.Output + "candidate_alignments.tsv"

    ref_fasta = os.sep.join([args.treesapp, "data",  "alignment_data",  update_tree.COG + ".fa"])
    db_prefix = update_tree.Output + os.sep + update_tree.COG
    # Make a temporary BLAST database to see what is novel
    # Needs a path to write the temporary unaligned FASTA file
    wrapper.generate_blast_database(args, ref_fasta, "prot", db_prefix)

    logging.info("Aligning the candidate sequences to the current reference sequences using blastp... ")

    align_cmd = [args.executables["blastp"]]
    align_cmd += ["-query", new_ref_queries]
    align_cmd += ["-db", db_prefix + ".fa"]
    align_cmd += ["-outfmt", str(6)]
    align_cmd += ["-out", alignments]
    align_cmd += ["-num_alignments", str(1)]

    launch_write_command(align_cmd)

    # Remove the temporary BLAST database
    db_suffixes = ['', ".phr", ".pin", ".psq"]
    for db_file in db_suffixes:
        if os.path.isfile(db_prefix + ".fa" + db_file):
            os.remove(db_prefix + ".fa" + db_file)

    logging.info("done.\n")

    return alignments


def find_novel_refs(ref_candidate_alignments, aa_dictionary, create_func_tree):
    new_refs = dict()
    try:
        alignments = open(ref_candidate_alignments, 'r')
    except IOError:
        raise IOError("Unable to open " + ref_candidate_alignments + " for reading! Exiting.")

    line = alignments.readline()
    while line:
        fields = line.split("\t")
        if float(fields[2]) <= create_func_tree.cluster_id:
            query = '>' + fields[0]
            new_refs[query] = aa_dictionary[query]
        else:
            pass
        line = alignments.readline()

    alignments.close()
    return new_refs


def write_dict_to_table(data_dict: dict, output_file: str, sep="\t"):
    data_strings = []
    for key in data_dict:
        values = data_dict[key]
        if type(values) is str:
            data_strings.append(sep.join([key, values]))
        elif type(values) is list:
            data_strings.append(sep.join([key, sep.join(values)]))
        else:
            logging.error("Unable to tabularize values of type '" + str(type(values)) + "'\n")
            sys.exit(5)
    try:
        handler = open(output_file, 'w')
    except IOError:
        logging.error("Unable to open file '" + output_file + "' for writing.\n")
        sys.exit(3)
    handler.write("\n".join(data_strings) + "\n")
    handler.close()

    return


def reformat_ref_seq_descriptions(original_header_map):
    reformatted_header_map = dict()
    for treesapp_id in original_header_map:
        try:
            organism_info, accession = original_header_map[treesapp_id].split(" | ")
            if organism_info and accession:
                reformatted_header_map[treesapp_id] = accession + " [" + organism_info + "]"
            else:
                reformatted_header_map[treesapp_id] = original_header_map[treesapp_id]
        except IndexError:
            reformatted_header_map[treesapp_id] = original_header_map[treesapp_id]
        # Remove the side-chevron character
        if reformatted_header_map[treesapp_id][0] == '>':
            reformatted_header_map[treesapp_id] = reformatted_header_map[treesapp_id][1:]
    return reformatted_header_map


def map_classified_seqs(ref_pkg_name, assignments, unmapped_seqs):
    classified_seq_lineage_map = dict()
    for lineage in assignments[ref_pkg_name]:
        # Map the classified sequence to the header in FASTA
        x = 0
        while x < len(unmapped_seqs):
            seq_name = unmapped_seqs[x]
            original_name = re.sub(r"\|{0}\|\d+_\d+$".format(ref_pkg_name), '', seq_name)
            if original_name in assignments[ref_pkg_name][lineage]:
                classified_seq_lineage_map[seq_name] = lineage
                unmapped_seqs.pop(x)
            else:
                x += 1
    # Ensure all the classified sequences were mapped to lineages
    if unmapped_seqs:
        logging.error("Unable to map all classified sequences in to a lineage. These are missing:\n" +
                      "\n".join(unmapped_seqs) + "\n")
        sys.exit(5)
    return classified_seq_lineage_map


def strip_assigment_pattern(seq_names: list, refpkg_name: str):
    """
    Strips the |RefPkg|start_stop pattern from the end of sequence names
    :param seq_names: A list of sequence names (headers) that were assigned using TreeSAPP
    :param refpkg_name: Name of the reference package that sequences were assigned to (e.g. McrA, nosZ)
    :return: Dictionary mapping the original headers to the new headers
    """
    return {seq_name: re.sub(r"\|{0}\|\d+_\d+$".format(refpkg_name), '', seq_name) for seq_name in seq_names}
