#!/usr/bin/env python3

__author__ = "Connor Morgan-Lang"
__maintainer__ = "Connor Morgan-Lang"
__license__ = "GPL"
__version__ = "0.0.2"

try:
    import argparse
    import sys
    import os
    import re
    import traceback
    import subprocess
    import Bio
    from Bio import Entrez
    from time import gmtime, strftime
    from urllib import error
    from treesapp import os_type, is_exe, which, format_read_fasta
except ImportError:
    sys.stderr.write("Could not load some user defined module functions:\n")
    sys.stderr.write(str(traceback.print_exc(10)))
    sys.exit(3)


class ReferenceSequence:
    def __init__(self):
        self.accession = ""
        self.description = ""
        self.organism = ""
        self.lineage = ""
        self.short_id = ""
        self.sequence = ""
        self.locus = ""

    def get_info(self):
        info_string = ""
        info_string += "accession = " + self.accession + ", " + "mltree_id = " + self.short_id + "\n"
        info_string += "description = " + self.description + ", " + "locus = " + self.locus + "\n"
        info_string += "organism = " + self.organism + "\n"
        info_string += "lineage = " + self.lineage + "\n"
        sys.stdout.write(info_string)
        sys.stdout.flush()


def get_arguments():
    parser = argparse.ArgumentParser(add_help=False)
    required_args = parser.add_argument_group("Required arguments")
    required_args.add_argument("-i", "--fasta_input",
                               help="FASTA file that will be used to create reference data for TreeSAPP",
                               required=True)
    required_args.add_argument("-c", "--code_name",
                               help="Unique name to be used by TreeSAPP internally. NOTE: Must be <=6 characters.\n"
                                    "(Refer to first column of 'cog_list.txt' under the '#functional cogs' section)",
                               required=True)
    required_args.add_argument("-p", "--identity",
                               help="The percent identity which the input sequences were clustered",
                               required=True,
                               type=str)

    optopt = parser.add_argument_group("Optional options")
    optopt.add_argument("-u", "--uc",
                        help="The USEARCH cluster format file produced from clustering reference sequences",
                        required=False,
                        default=None)
    optopt.add_argument('-l', '--min_seq_length',
                        help='Minimal sequence length [DEFAULT = 50]',
                        required=False,
                        default=50,
                        type=int)
    optopt.add_argument('-a', '--multiple_alignment',
                        help='The FASTA input is also the multiple alignment file to be used. '
                             'In this workflow, alignment with MUSCLE is skipped and this file is used instead.',
                        action="store_true",
                        default=False)
    optopt.add_argument('-m', '--molecule',
                        help='the type of input sequences (prot = Protein [DEFAULT]; dna = Nucleotide; rrna = rRNA)',
                        default='prot',
                        choices=['prot', 'dna', 'rrna'])
    optopt.add_argument('-r', "--rfam_cm",
                        help="The covariance model of the RNA family being packaged. REQUIRED if molecule is rRNA!",
                        default=None)
    optopt.add_argument("-b", "--bootstraps",
                        help="The number of bootstrap replicates RAxML should perform [ DEFAULT = autoMR ]",
                        required=False,
                        default="autoMR")
    optopt.add_argument("-T", "--num_threads",
                        help="The number of threads for RAxML to use [ DEFAULT = 4 ]",
                        required=False,
                        default=str(4),
                        type=str)
    optopt.add_argument("-h", "--help",
                        action="help",
                        help="show this help message and exit")
    miscellaneous_opts = parser.add_argument_group("Miscellaneous options")
    miscellaneous_opts.add_argument('--overwrite', action='store_true', default=False,
                                    help='overwrites previously processed output folders')
    miscellaneous_opts.add_argument('-v', '--verbose', action='store_true', default=False,
                                    help='Prints a more verbose runtime log')

    args = parser.parse_args()
    args.mltreemap = os.path.abspath(os.path.dirname(os.path.realpath(__file__))) + os.sep
    final_output_folder = "TreeSAPP_files_%s" % args.code_name
    args.output = final_output_folder

    if len(args.code_name) > 6:
        sys.stderr.write("ERROR: code_name must be <= 6 characters!\n")
        sys.stderr.flush()
        sys.exit(-1)

    if args.rfam_cm is None and args.molecule == "rrna":
        sys.stderr.write("ERROR: Covariance model file must be provided for rRNA data!\n")
        sys.exit(-2)

    return args


def find_executables(args):
    """
    Finds the executables in a user's path to alleviate the requirement of a sub_binaries directory
    :param args: command-line arguments objects
    :return: exec_paths beings the absolute path to each executable
    """
    exec_paths = dict()
    dependencies = ["raxmlHPC", "makeblastdb", "muscle", "hmmbuild", "cmbuild", "cmalign"]

    if os_type() == "linux":
        args.executables = args.mltreemap + "sub_binaries" + os.sep + "ubuntu"
    if os_type() == "mac":
        args.executables = args.mltreemap + "sub_binaries" + os.sep + "mac"
    elif os_type() == "win" or os_type() is None:
        sys.exit("ERROR: Unsupported OS")

    for dep in dependencies:
        if is_exe(args.executables + os.sep + dep):
            exec_paths[dep] = str(args.executables + os.sep + dep)
        # For rpkm and potentially other executables that are compiled ad hoc
        elif is_exe(args.mltreemap + "sub_binaries" + os.sep + dep):
            exec_paths[dep] = str(args.mltreemap + "sub_binaries" + os.sep + dep)
        elif which(dep):
            exec_paths[dep] = which(dep)
        else:
            sys.stderr.write("Could not find a valid executable for " + dep + ". ")
            sys.exit("Bailing out.")

    args.executables = exec_paths
    return args


def read_phylip(phylip_input):
    header_dict = dict()
    alignment_dict = dict()
    x = 0

    try:
        phylip = open(phylip_input, 'r')
    except IOError:
        raise IOError("ERROR: Unable to open the Phylip file (" + phylip_input + ") provided for reading!")

    line = phylip.readline()
    try:
        num_sequences, aln_length = line.strip().split(' ')
        num_sequences = int(num_sequences)
        aln_length = int(aln_length)
    except ValueError:
        raise AssertionError("ERROR: Phylip file is not formatted correctly!\n"
                             "Header line does not contain 2 space-separated fields "
                             "(number of sequences and alignment length). Exiting now.\n")
    line = phylip.readline()
    while line:
        line = line.strip()
        if len(line.split()) == 2:
            # This is the introduction set: header, sequence
            header, sequence = line.split()
            header_dict[x] = header
            alignment_dict[x] = sequence
            x += 1
        elif 60 >= len(line) >= 1:
            alignment_dict[x] += line
            x += 1
        elif line == "":
            # Reset accumulator on blank lines
            x = 0
        else:
            sys.exit(line + "\nERROR: Unexpected line in Phylip file.")

        line = phylip.readline()

        if x > num_sequences:
            sys.stderr.write("\nERROR:\n"
                             "Accumulator has exceeded the number of sequences in the file (according to header)!\n")
            sys.exit()

    # Check that the alignment length matches that in the header line
    x = 0
    while x < num_sequences-1:
        if len(alignment_dict[x]) != aln_length:
            sys.stderr.write("\nERROR:\n" + header_dict[x] +
                             " sequence length exceeds the stated multiple alignment length (according to header)!\n")
            sys.stderr.write("sequence length = " + str(len(alignment_dict[x])) +
                             ", alignment length = " + str(aln_length) + "\n")
            sys.exit()
        else:
            pass
        x += 1

    phylip.close()
    return header_dict, alignment_dict


def write_mfa(header_dict, alignment_dict, fasta_output):
    fasta_string = ""

    for entry in header_dict:
        fasta_string += '>' + header_dict[entry] + "\n"
        fasta_string += alignment_dict[entry] + "\n"

    try:
        fasta = open(fasta_output, 'w')
    except IOError:
        raise IOError("ERROR: Unable to open the FASTA file (" + fasta_output + ") provided for writing!")
    fasta.write(fasta_string)
    fasta.close()

    return


def get_headers(fasta_file):
    original_headers = list()
    try:
        fasta = open(fasta_file, 'r')
    except IOError:
        raise IOError("ERROR: Unable to open the FASTA file (" + fasta_file + ") provided for reading!")
    line = fasta.readline()
    while line:
        line = line.strip()
        if line[0] == '>':
            original_headers.append(line[1:])
        else:
            pass
        line = fasta.readline()

    fasta.close()
    return original_headers


def phylip_to_mfa(phylip_input, fasta_output, header_map):
    header_dict, alignment_dict = read_phylip(phylip_input)
    original_headers = get_headers(header_map)
    x = 0
    while x < len(header_dict.keys()):
        changed = False
        for header in original_headers:
            if re.search("^" + re.escape(str(header_dict[x])), header):
                header_dict[x] = header
                changed = True
        if changed is False:
            sys.exit("ERROR: unable to find " + str(header_dict[x]) + " in " + header_map)
        x += 1
    write_mfa(header_dict, alignment_dict, fasta_output)


def generate_cm_data(args):
    """
    Using the input unaligned FASTA file:
     1. align the sequences using cmalign against a reference Rfam covariance model to generate a Stockholm file
     2. use the Stockholm file (with secondary structure annotated) to build a covariance model
     3. align the sequences using cmalign against a reference Rfam covariance model to generate an aligned fasta (AFA)
    :param args:
    :return:
    """

    sys.stdout.write("Running cmalign to build Stockholm file with secondary structure annotations... ")
    sys.stdout.flush()

    cmalign_base = [args.executables["cmalign"],
                    "--mxsize", str(3084),
                    "--informat", "FASTA",
                    "--cpu", str(args.num_threads)]
    # First, generate the stockholm file
    cmalign_sto = cmalign_base + ["-o", args.code_name + ".sto"]
    cmalign_sto += [args.rfam_cm, args.fasta_input]

    stdout, cmalign_pro_returncode = launch_write_command(cmalign_sto)

    if cmalign_pro_returncode != 0:
        sys.stderr.write("ERROR: cmalign did not complete successfully for:\n")
        sys.stderr.write(' '.join(cmalign_sto) + "\n")
        sys.exit()

    sys.stdout.write("done.\n")
    sys.stdout.write("Running cmbuild... ")
    sys.stdout.flush()

    # Build the CM
    cmbuild_command = [args.executables["cmbuild"]]
    cmbuild_command += ["-n", args.code_name]
    cmbuild_command += [args.code_name + ".cm", args.code_name + ".sto"]

    stdout, cmbuild_pro_returncode = launch_write_command(cmbuild_command)

    if cmbuild_pro_returncode != 0:
        sys.stderr.write("ERROR: cmbuild did not complete successfully for:\n")
        sys.stderr.write(' '.join(cmbuild_command) + "\n")
        sys.exit()
    os.rename(args.code_name + ".cm", args.output + os.sep + args.code_name + ".cm")
    os.remove(args.code_name + ".sto")

    sys.stdout.write("done.\n")
    sys.stdout.write("Running cmalign to build MSA... ")
    sys.stdout.flush()

    # Generate the aligned FASTA file which will be used to build the BLAST database and tree with RAxML
    aligned_fasta = ""
    cmalign_afa = cmalign_base + ["--outformat", "Phylip"]
    cmalign_afa += ["-o", args.code_name + ".phy"]
    cmalign_afa += [args.rfam_cm, args.fasta_input]

    stdout, cmalign_pro_returncode = launch_write_command(cmalign_afa)

    if cmalign_pro_returncode != 0:
        sys.stderr.write("ERROR: cmalign did not complete successfully for:\n")
        sys.stderr.write(' '.join(cmalign_afa) + "\n")
        sys.exit()

    # Convert the Phylip file to an aligned FASTA file for downstream use
    phylip_to_mfa(args.code_name + ".phy", args.code_name + ".mfa", args.fasta_input)

    sys.stdout.write("done.\n")
    sys.stdout.flush()

    return aligned_fasta


def launch_write_command(cmd_list, collect_all=True):
    """
    Wrapper function for opening subprocesses through subprocess.Popen()
    :param cmd_list: A list of strings forming a complete command call
    :param collect_all: A flag determining whether stdout and stderr are returned 
    via stdout or just stderr is returned leaving stdout to be written to the screen
    :return: A string with stdout and/or stderr text and the returncode of the executable
    """
    stdout = ""
    if collect_all:
        proc = subprocess.Popen(' '.join(cmd_list),
                                shell=True,
                                preexec_fn=os.setsid,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        stdout = proc.communicate()[0].decode("utf-8")
    else:
        proc = subprocess.Popen(' '.join(cmd_list),
                                shell=True,
                                preexec_fn=os.setsid)
        proc.wait()
    return stdout, proc.returncode


def create_new_fasta(out_fasta, ref_seq_dict, dashes=False):
    """
    Writes a new FASTA file using a dictionary of ReferenceSequence class objects
    :param out_fasta: Name of the FASTA file to write to
    :param ref_seq_dict: Dictionary containing ReferenceSequence objects, numbers are keys
    :param dashes: Flag indicating whether hyphens should be retained from sequences
    :return:
    """
    out_fasta_handle = open(out_fasta, "w")
    num_seqs_written = 0

    for mltree_id in sorted(ref_seq_dict, key=int):
        ref_seq = ref_seq_dict[mltree_id]
        if dashes is False:
            sequence = re.sub('[-.]', '', ref_seq.sequence)
        else:
            # sequence = re.sub('\.', '', ref_seq.sequence)
            sequence = ref_seq.sequence
        out_fasta_handle.write(">" + ref_seq.short_id + "\n" + sequence + "\n")
        num_seqs_written += 1

    out_fasta_handle.close()

    if num_seqs_written == 0:
        sys.stderr.write("ERROR: No sequences written to " + out_fasta + ".\n")
        sys.stderr.write("The headers in your input file are probably not accommodated in the regex patterns used. "
                         "Function responsible: get_header_format. Please make an issue on the GitHub page.\n")
        sys.stderr.flush()
        sys.exit(5)

    return


def read_uc(uc_file):
    """
    Function to read a USEARCH cluster (.uc) file
    :param uc_file: Path to a .uc file produced by USEARCH
    :return: Dictionary where keys are representative cluster headers and the values are headers of identical sequences
    """
    cluster_dict = dict()
    try:
        uc = open(uc_file, 'r')
    except IOError:
        raise IOError("Unable to open " + uc_file + " for reading! Exiting...")

    line = uc.readline()
    # Find all clusters with multiple identical sequences
    while line:
        cluster_type, _, length, identity, _, _, _, cigar, header, representative = line.strip().split("\t")
        if cluster_type != "C":
            try:
                identity = float(identity)
            except ValueError:
                identity = "*"
            if cluster_type == "S":
                cluster_dict['>' + header] = list()
            if cluster_type == "H" and identity == 100.0 and cigar == '=':
                cluster_dict['>' + representative].append('>' + header)
        line = uc.readline()
    return cluster_dict


def present_cluster_rep_options(cluster_dict):
    """
    Present the headers of identical sequences to user for them to decide on representative header
    :param cluster_dict: dictionary from read_uc(uc_file)
    :return:
    """
    swappers = dict()
    candidates = dict()

    for rep in cluster_dict:
        candidates.clear()
        subs = cluster_dict[rep]
        if len(subs) >= 1:
            sys.stderr.write("Found multiple identical sequences in cluster file:\n")
            candidates[str(1)] = rep
            acc = 2
            for candidate in subs:
                candidates[str(acc)] = candidate
                acc += 1
            for num in sorted(candidates.keys(), key=int):
                sys.stderr.write(num + ". " + candidates[num] + "\n")
            sys.stderr.flush()
            best = input("Number of the best representative? ")
            # Useful for testing - no need to pick which sequence name is best!
            # best = str(1)
            while best not in candidates.keys():
                best = input("Invalid number. Number of the best representative? ")
            if best != str(1):
                swappers[rep] = candidates[best]

    return swappers


def reformat_headers(header_dict):
    """
    Imitate format_read_fasta header name reformatting
    :param header_dict: Dictionary of old header : new header key : value pairs
    :return:
    """
    swappers = dict()

    def reformat_string(string):
        if len(string) > 110:
            string = string[0:110]
        string = re.sub("\[|\]|\(|\)", '', string)
        string = re.sub("\s|;|,", '_', string)
        return string

    for old, new in header_dict.items():
        swappers[reformat_string(old)] = reformat_string(new)
    return swappers


def remove_dashes_from_msa(fasta_in, fasta_out):
    dashed_fasta = open(fasta_in, 'r')
    fasta = open(fasta_out, 'w')
    sequence = ""

    line = dashed_fasta.readline()
    while line:
        if line[0] == '>':
            if sequence:
                fasta.write(sequence + "\n")
                sequence = ""
            fasta.write(line)
        else:
            sequence += re.sub('[-.]', '', line.strip())
        line = dashed_fasta.readline()
    fasta.write(sequence + "\n")
    dashed_fasta.close()
    fasta.close()
    return


def get_header_format(header, code_name):
    """
    Used to decipher which formatting style was used: NCBI, FunGenes, or other
    :param header: A sequences header from a FASTA file
    :param code_name:
    :return:
    """
    # The regular expressions with the accession and organism name grouped
    # Protein databases:
    gi_re = re.compile(">gi\|(\d+)\|[a-z]+\|\w.+\|(.*)$")
    gi_prepend_proper_re = re.compile(">gi\|([0-9]+)\|[a-z]+\|[_A-Z0-9.]+\|.*\[(.*)\]$")
    gi_prepend_mess_re = re.compile(">gi\|([0-9]+)\|pir\|\|(.*)$")
    dbj_re = re.compile(">dbj\|(.*)\|.*\[(.*)\]")
    emb_re = re.compile(">emb\|(.*)\|.*\[(.*)\]")
    gb_re = re.compile(">gb\|(.*)\|.*\[(.*)\]")
    ref_re = re.compile(">ref\|(.*)\|.*\[(.*)\]")
    pdb_re = re.compile(">pdb\|(.*)\|(.*)$")
    pir_re = re.compile(">pir\|\|(\w+).* - (.*)$")
    sp_re = re.compile(">sp\|(.*)\|.*Full=(.*); AltName:.*$")
    fungene_re = re.compile("^>([A-Z0-9.]+)[_]+coded_by=(.+)[_]+organism=(.+)[_]+definition=(.+)$")

    # Nucleotide databases:
    mltree_re = re.compile("^>(\d+)_" + re.escape(code_name))
    silva_arb_re = re.compile("^>([A-Z0-9]+)\.([0-9]+)\.([0-9]+)_(.*)$")
    refseq_re = re.compile("^>([A-Z]+_[0-9]+\.[0-9])_(.*)$")
    nr_re = re.compile("^>([A-Z0-9]+\.[0-9])_(.*)$")

    header_format_regexi = [dbj_re, emb_re, gb_re, pdb_re, pir_re, ref_re, sp_re, fungene_re, mltree_re,
                            gi_prepend_proper_re, gi_prepend_mess_re, gi_re, silva_arb_re, refseq_re, nr_re]
    header_format_dbs = ["dbj", "emb", "gb", "pdb", "pir", "ref", "sp", "fungene",
                         "mltree", "gi_proper", "gi_mess", "gi_re", "silva", "refseq", "nr"]

    if len(header_format_dbs) != len(header_format_regexi):
        raise AssertionError("ERROR: len(header_format_dbs) != len(header_format_regexi)\n")
    i = 0
    while i < len(header_format_regexi):
        regex = header_format_regexi[i]
        if regex.match(header):
            return regex, header_format_dbs[i]
        i += 1

    return None, None


def get_sequence_info(code_name, fasta_dict, fasta_replace_dict, swappers=None):
    """
    This function is used to find the accession ID and description of each sequence from the FASTA file
    :param code_name: code_name from the command-line parameters
    :param fasta_dict: a dictionary with headers as keys and sequences as values (returned by format_read_fasta)
    :param fasta_replace_dict:
    :param swappers: Either the dictionary containing representative clusters (keys) and their constituents (values)
    :return: fasta_replace_dict with a complete ReferenceSequence() value for every mltree_id key
    """

    sys.stdout.write("Extracting information from headers for formatting purposes... ")
    sys.stdout.flush()
    fungene_gi_bad = re.compile("^>[0-9]+\s+coded_by=.+,organism=.+,definition=.+$")
    mltree_id_accumulator = 1
    swapped_headers = []
    if len(fasta_replace_dict.keys()) > 0:
        for mltree_id in fasta_replace_dict:
            ref_seq = fasta_replace_dict[mltree_id]
            ref_seq.short_id = mltree_id + '_' + code_name
            tmp_ref_def = re.sub('[)(\[\]]', '', ref_seq.description)  # Remove parentheses for comparisons
            # This `swappers` is actually cluster_dict
            # keys are representative headers, values are list of headers with identical sequences
            for header in swappers.keys():
                tmp_header = re.sub('[)(\[\]]', '', header)  # Remove parentheses for comparisons
                # Need to check both keys and values since it is unknown whether the rep was selected or not
                if re.search(ref_seq.accession, header):
                    if re.search(tmp_ref_def, tmp_header):
                        ref_seq.sequence = fasta_dict[header]
                if len(swappers[header]) > 0:
                    for constituent in swappers[header]:
                        if re.search(tmp_ref_def, constituent) and re.search(ref_seq.accession, constituent):
                            ref_seq.sequence = fasta_dict[header]

            if not ref_seq.sequence:
                sys.exit("Unable to find header for " + ref_seq.accession)

    else:  # if fasta_replace_dict needs to be populated, this is a new run
        for header in fasta_dict.keys():
            if fungene_gi_bad.match(header):
                sys.stderr.write("\nWARNING: Input sequences use 'GIs' which are obsolete and may be non-unique. "
                                 "For everyone's sanity, please download sequences with the `accno` instead.\n")
                sys.exit()
            mltree_id = str(mltree_id_accumulator)
            ref_seq = ReferenceSequence()
            ref_seq.sequence = fasta_dict[header]
            if swappers and header in swappers.keys():
                header = swappers[header]
                swapped_headers.append(header)
            header_format_re, header_db = get_header_format(header, code_name)
            if header_format_re is None:
                raise AssertionError("Unable to parse header: " + header)
            sequence_info = header_format_re.match(header)
            if sequence_info:
                if len(sequence_info.groups()) == 2:
                    ref_seq.accession = sequence_info.group(1)
                    ref_seq.description = sequence_info.group(2)
                elif header_db == "silva":
                    ref_seq.accession = sequence_info.group(1)
                    ref_seq.locus = str(sequence_info.group(2)) + '-' + str(sequence_info.group(3))
                    ref_seq.organism = sequence_info.group(4)
                    ref_seq.description = sequence_info.group(4)
                elif header_db == "fungene":
                    ref_seq.accession = sequence_info.group(1)
                    ref_seq.locus = sequence_info.group(2)
                    ref_seq.organism = re.sub(pattern="_", repl=" ", string=sequence_info.group(3))
                    ref_seq.description = sequence_info.group(3)
            else:
                sys.stdout.write("Unable to handle header: " + header + "\n")
                sys.exit()

            ref_seq.short_id = mltree_id + '_' + code_name
            fasta_replace_dict[mltree_id] = ref_seq

            mltree_id_accumulator += 1
        if swappers and len(swapped_headers) != len(swappers):
            sys.stderr.write("\nERROR: Some headers that were meant to be replaced could not be compared!\n")
            for header in swappers.keys():
                if header not in swapped_headers:
                    sys.stdout.write(header + "\n")
            sys.exit()

    sys.stdout.write("done.\n")
    sys.stdout.flush()

    return fasta_replace_dict


def query_entrez_taxonomy(search_term):
    handle = Entrez.esearch(db="Taxonomy",
                            term=search_term,
                            retmode="xml")
    record = Entrez.read(handle)
    try:
        org_id = record["IdList"][0]
        handle = Entrez.efetch(db="Taxonomy", id=org_id, retmode="xml")
        records = Entrez.read(handle)
        lineage = str(records[0]["Lineage"])
    except IndexError:
        lineage = dict()
        lineage['QueryTranslation'] = record['QueryTranslation']

    return lineage


def get_lineage(search_term, molecule_type):
    """
    Used to return the NCBI taxonomic lineage of the sequence
    :param: search_term: The NCBI search_term
    :param: molecule_type: "dna", "rrna", "prot", or "tax - parsed from command line arguments
    :return: string representing the taxonomic lineage
    """
    # TODO: fix potential error PermissionError:
    # [Errno 13] Permission denied: '/home/connor/.config/biopython/Bio/Entrez/XSDs'
    # Fixed with `sudo chmod 777 .config/biopython/Bio/Entrez/`
    if float(Bio.__version__) < 1.68:
        # This is required due to a bug in earlier versions returning a URLError
        raise AssertionError("ERROR: version of biopython needs to be >=1.68! " +
                             str(Bio.__version__) + " is currently installed. Exiting now...")
    Entrez.email = "c.morganlang@gmail.com"
    # Test the internet connection:
    try:
        Entrez.efetch(db="Taxonomy", id="158330", retmode="xml")
    except error.URLError:
        raise AssertionError("ERROR: Unable to serve Entrez query. Are you connected to the internet?")

    # Determine which database to search using the `molecule_type`
    if molecule_type == "dna" or molecule_type == "rrna":
        database = "nucleotide"
    elif molecule_type == "prot":
        database = "protein"
    elif molecule_type == "tax":
        database = "Taxonomy"
    else:
        sys.stderr.write("Welp. We're not sure how but the molecule type is not recognized!\n")
        sys.stderr.write("Please create an issue on the GitHub page.")
        sys.exit(8)

    # Find the lineage from the search_term ID
    lineage = ""
    if database in ["nucleotide", "protein"]:
        handle = Entrez.efetch(db=database, id=str(search_term), retmode="xml")
        try:
            record = Entrez.read(handle)
        except UnboundLocalError:
            raise UnboundLocalError

        if len(record) >= 1:
            try:
                if "GBSeq_organism" in record[0]:
                    organism = record[0]["GBSeq_organism"]
                    lineage = query_entrez_taxonomy(organism)
            except IndexError:
                lineage = dict()
                lineage['QueryTranslation'] = record['QueryTranslation']
        else:
            # Lineage is already set to "". Just return and move on to the next attempt
            pass
    else:
        try:
            lineage = query_entrez_taxonomy(search_term)
        except UnboundLocalError:
            sys.stderr.write("WARNING: Unable to find Entrez taxonomy using organism name:\n\t")
            sys.stderr.write(search_term + "\n")

    return lineage


def write_tax_ids(fasta_replace_dict, tree_taxa_list, molecule):
    """
    Write the number, organism and accession ID, if possible
    :param fasta_replace_dict:
    :param tree_taxa_list: The name of the output file
    :param molecule: "dna", "rrna", or "prot" - parsed from command line arguments
    :return:
    """
    sys.stdout.write("Retrieving lineage information for each reference sequence... ")
    sys.stdout.flush()

    tree_tax_list_handle = open(tree_taxa_list, "w")
    for mltree_id_key in sorted(fasta_replace_dict.keys(), key=int):
        reference_sequence = fasta_replace_dict[mltree_id_key]
        lineage = ""
        strikes = 0
        while strikes < 3:
            if strikes == 0:
                lineage = get_lineage(reference_sequence.accession, molecule)
                if type(lineage) is str:
                    # The query was successful
                    strikes = 3
            elif strikes == 1:
                # Unable to determine lineage from the search_term provided,
                # try to parse organism name from description
                if reference_sequence.organism:
                    lineage = get_lineage(reference_sequence.organism.split('_')[-2], "tax")
                    if type(lineage) is str:
                        # The query was successful
                        lineage += '; ' + reference_sequence.organism.split('_')[-2]
                        strikes = 3
                # else:
                #     # Organism information is not available, time to bail
                #     strikes += 1
            elif strikes == 2:
                lineage = get_lineage(lineage, "tax")
            if type(lineage) is dict:
                # If 'QueryTranslation' is returned, use it for the final Entrez query
                lineage = lineage['QueryTranslation'].split(' ')[0]
                lineage = re.sub("\[All Names\]", '', lineage)
            strikes += 1
        if not lineage:
            sys.stderr.write("\nWARNING: Unable to find lineage for sequence with following data:\n")
            fasta_replace_dict[mltree_id_key].get_info()
        tree_tax_list_handle.write("%s\t%s | %s\t%s\n" % (mltree_id_key,
                                                          reference_sequence.description,
                                                          reference_sequence.accession,
                                                          lineage))
    tree_tax_list_handle.close()

    sys.stdout.write("done.\n")
    sys.stdout.flush()

    return


def read_tax_ids(tree_taxa_list):
    """
    Reads the taxonomy and accession ID affiliated with each sequence number.
    This information is used to avoid horrible manual work if the pipeline is ran multiple times
    :param tree_taxa_list: The name of the tax_ids file to read
    :return:
    """
    try:
        tree_tax_list_handle = open(tree_taxa_list, 'r')
    except IOError:
        raise IOError("Unable to open " + tree_taxa_list + " for reading! Exiting.")
    fasta_replace_dict = dict()
    line = tree_tax_list_handle.readline()
    while line:
        fields = line.strip().split("\t")
        if len(fields) == 3:
            mltree_id_key, seq_info, lineage = fields
        else:
            mltree_id_key, seq_info = fields
            lineage = ""
        ref_seq = ReferenceSequence()
        ref_seq.description = seq_info.split(" | ")[0]
        ref_seq.accession = seq_info.split(" | ")[1]
        ref_seq.lineage = lineage
        fasta_replace_dict[mltree_id_key] = ref_seq
        line = tree_tax_list_handle.readline()
    tree_tax_list_handle.close()

    return fasta_replace_dict


def swap_tree_names(tree_to_swap, final_mltree, code_name):
    original_tree = open(tree_to_swap, 'r')
    raxml_tree = open(final_mltree, 'w')

    tree = original_tree.readlines()
    original_tree.close()
    if len(tree) > 1:
        sys.stderr.write("ERROR: >1 line contained in RAxML tree " + tree_to_swap)

    new_tree = re.sub('_' + re.escape(code_name), '', str(tree[0]))
    raxml_tree.write(new_tree)

    raxml_tree.close()
    return


def annotate_partition_tree(code_name, fasta_replace_dict, bipart_tree):
    try:
        tree_txt = open(bipart_tree, 'r')
    except IOError:
        raise IOError("Unable to open " + bipart_tree + " for reading.")

    tree = tree_txt.readline()
    tree_txt.close()
    for mltree_id_key in fasta_replace_dict.keys():
        tree = re.sub('\(' + mltree_id_key + "_" + code_name, '(' + fasta_replace_dict[mltree_id_key].description, tree)
        tree = re.sub(',' + mltree_id_key + "_" + code_name, ',' + fasta_replace_dict[mltree_id_key].description, tree)

    raxml_out = os.path.dirname(bipart_tree)
    annotated_tree_name = raxml_out + os.sep + "RAxML_bipartitions_annotated." + code_name
    try:
        annotated_tree = open(annotated_tree_name, 'w')
    except IOError:
        raise IOError("Unable to open " + annotated_tree_name + " for writing!")

    annotated_tree.write(tree)
    annotated_tree.close()

    return


def find_model_used(raxml_info_file):
    model_statement_re = re.compile(r".* model: ([A-Z]+) likelihood.*")
    model = ""
    command_line = ""
    with open(raxml_info_file) as raxml_info:
        for line in raxml_info:
            if model_statement_re.search(line):
                model = model_statement_re.search(line).group(1)
                break
            elif re.match('^.*/raxml.*-m ([A-Z]+)$', line):
                command_line = line
            else:
                pass
    if model == "":
        if command_line == "":
            sys.stderr.write("WARNING: Unable to parse model used from " + raxml_info_file + "!\n")
            sys.stderr.flush()
        else:
            model = re.match('^.*/raxml.*-m ([A-Z]+)$', command_line).group(1)
    return model


def update_build_parameters(args, code_name, aa_model):
    """
    Function to update the data/tree_data/ref_build_parameters.tsv file with information on this new reference sequence
    Format of file is "code_name       denominator     aa_model        cluster_identity        last_updated"
    :param args: 
    :param code_name: 
    :param aa_model: 
    :return: 
    """
    param_file = args.mltreemap + "data" + os.sep + "tree_data" + os.sep + "ref_build_parameters.tsv"
    try:
        params = open(param_file, 'a')
    except IOError:
        raise IOError("Unable to open " + param_file + "for appending!")

    date = strftime("%d_%b_%Y", gmtime())

    build_list = [code_name, "Z1111", "PROTGAMMA" + aa_model, args.identity, date]
    params.write("\t".join(build_list))

    return


def reverse_complement(rrna_sequence):
    comp = []
    for c in rrna_sequence:
        if c == 'A' or c == 'a':
            comp.append('T')
        if c == 'G' or c == 'g':
            comp.append('C')
        if c == 'U' or c == 'u' or c == 'T' or c == 't':
            comp.append('A')
        if c == 'C' or c == 'c':
            comp.append('G')
        # In the case input FASTA is a multiple alignment file
        if c == '.' or c == '-':
            comp.append(c)
        else:
            pass
    rev_comp = ''.join(reversed(comp))
    return rev_comp


def main():
    args = get_arguments()
    args = find_executables(args)

    code_name = args.code_name
    final_output_folder = args.output
    tree_taxa_list = "tax_ids_%s.txt" % code_name

    if not os.path.exists(final_output_folder):
        os.makedirs(final_output_folder)
    else:
        sys.stderr.write("WARNING: Output directory already exists. Previous outputs will be overwritten.\n")
        sys.stderr.flush()

    if args.uc and os.path.exists(tree_taxa_list):
        if sys.version_info > (2, 9):
            use_previous_names = input(tree_taxa_list + " found from a previous attempt. "
                                                        "Should it be used for this run? [y|n] ")
            while use_previous_names != "y" and use_previous_names != "n":
                use_previous_names = input("Incorrect response. Please input either 'y' or 'n'. ")
        else:
            use_previous_names = raw_input(tree_taxa_list + " found from a previous attempt. "
                                                            "Should it be used for this run? [y|n] ")
            while use_previous_names != "y" and use_previous_names != "n":
                use_previous_names = raw_input("Incorrect response. Please input either 'y' or 'n'. ")
    else:
        use_previous_names = 'n'

    fasta_dict = format_read_fasta(args.fasta_input, args.molecule, args)

    fasta_replace_dict = dict()

    log = open("create_" + code_name + "_treesapp_data_log.txt", 'w')
    log.write("Command used:\n" + ' '.join(sys.argv) + "\n\n")

    if args.uc:
        cluster_dict = read_uc(args.uc)
        if use_previous_names == 'n':
            swappers = present_cluster_rep_options(cluster_dict)
            swappers = reformat_headers(swappers)
            fasta_replace_dict = get_sequence_info(code_name, fasta_dict, fasta_replace_dict, swappers)
            write_tax_ids(fasta_replace_dict, tree_taxa_list, args.molecule)
        if use_previous_names == 'y':
            # TODO: Debug this - not working properly with --multiple_alignment and -m dna
            fasta_replace_dict = read_tax_ids(tree_taxa_list)
            if len(fasta_replace_dict.keys()) != len(fasta_dict.keys()):
                raise AssertionError("Number of sequences in new FASTA input and " + tree_taxa_list + " are not equal!")
            fasta_replace_dict = get_sequence_info(code_name, fasta_dict, fasta_replace_dict, cluster_dict)
    else:
        # args.uc is None and use_previous_names == 'n'
        fasta_replace_dict = get_sequence_info(code_name, fasta_dict, fasta_replace_dict)
        write_tax_ids(fasta_replace_dict, tree_taxa_list, args.molecule)

    sys.stdout.write("******************** " + tree_taxa_list + " generated ********************\n")

    fasta_replaced_file = code_name + ".fc.repl.fasta"
    fasta_mltree = code_name + ".fa"

    if args.multiple_alignment:
        create_new_fasta(fasta_replaced_file, fasta_replace_dict, True)
    else:
        create_new_fasta(fasta_replaced_file, fasta_replace_dict)

    if args.molecule == 'rrna':
        aligned_fasta = generate_cm_data(args)
        # args.molecule = 'dna'
        args.multiple_alignment = True
        args.fasta_input = aligned_fasta
        fasta_dict = format_read_fasta(args.fasta_input, args.molecule, args)
        # Sequences must be reverse complemented since BLAST does not like uracil
        # for header in fasta_dict:
        #     fasta_dict[header] = reverse_complement(fasta_dict[header])

    if args.multiple_alignment is False:
        sys.stdout.write("Aligning the sequences using MUSCLE... ")
        fasta_replaced_align = code_name + ".fc.repl.aligned.fasta"

        muscle_align_command = [args.executables["muscle"]]
        muscle_align_command += ["-in", fasta_replaced_file]
        muscle_align_command += ["-out", fasta_replaced_align]

        stdout, muscle_pro_returncode = launch_write_command(muscle_align_command, False)

        if muscle_pro_returncode != 0:
            sys.stderr.write("ERROR: Multiple sequence alignment using " + args.executables["muscle"] +
                             " did not complete successfully! Command used:\n" + ' '.join(muscle_align_command) + "\n")
            sys.exit()
        sys.stdout.write("done.\n")
    else:
        fasta_replaced_align = fasta_replaced_file

    remove_dashes_from_msa(fasta_replaced_file, fasta_mltree)

    sys.stdout.write("******************** FASTA file, " + fasta_mltree + " generated ********************\n")

    makeblastdb_command = [args.executables["makeblastdb"]]
    makeblastdb_command += ["-in", fasta_mltree]
    makeblastdb_command += ["-out", fasta_mltree]
    makeblastdb_command += ["-input_type", "fasta"]
    if args.molecule == "prot":
        makeblastdb_command += ["-dbtype", "prot"]
    else:
        makeblastdb_command += ["-dbtype", "nucl"]

    stdout, makeblastdb_pro_returncode = launch_write_command(makeblastdb_command)

    if makeblastdb_pro_returncode != 0:
        sys.stderr.write("ERROR: BLAST database was unable to be made using " + args.executables["makeblastdb"] +
                         "! Command used:\n" + ' '.join(makeblastdb_command) + "\n")
        sys.exit()

    log.write("\n### MAKEBLASTDB ###" + stdout)

    sys.stdout.write("******************** BLAST DB for %s generated ********************\n" % code_name)

    os.rename(fasta_replaced_align, fasta_mltree)

    if args.molecule == "rrna":
        # A .cm file has already been generated, no need for HMM
        pass
    else:
        hmm_build_command = [args.executables["hmmbuild"]]
        hmm_build_command += ["-s", code_name + ".hmm"]
        hmm_build_command.append(fasta_mltree)

        stdout, hmmbuild_pro_returncode = launch_write_command(hmm_build_command)

        log.write("\n### HMMBUILD ###\n\n" + stdout)
        log.close()

        if hmmbuild_pro_returncode != 0:
            sys.stderr.write("ERROR: hmmbuild did not complete successfully for:\n")
            sys.stderr.write(' '.join(hmm_build_command) + "\n")
            sys.exit()

        os.rename(code_name + ".hmm", final_output_folder + os.sep + code_name + ".hmm")

        sys.stdout.write("******************** HMM file for %s generated ********************\n" % code_name)

    phylip_command = "java -cp %s/sub_binaries/readseq.jar run -a -f=12 %s" % (args.mltreemap, fasta_mltree)
    os.system(phylip_command)

    phylip_file = code_name + ".phy"
    os.rename(fasta_mltree + ".phylip", phylip_file)

    raxml_out = "%s_phy_files" % code_name

    if not os.path.exists(raxml_out):
        os.system("mkdir %s" % raxml_out)
    else:
        sys.stderr.write("ERROR: " + raxml_out + " already exists from a previous run! "
                                                 "Please delete or rename it and try again.\n")
        sys.exit()

    raxml_command = [args.executables["raxmlHPC"]]
    raxml_command += ["-f", "a"]
    raxml_command += ["-p", "12345"]
    raxml_command += ["-x", "12345"]
    raxml_command += ["-#", args.bootstraps]
    raxml_command += ["-s", phylip_file]
    raxml_command += ["-n", code_name]
    raxml_command += ["-w", args.mltreemap + raxml_out]
    raxml_command += ["-T", args.num_threads]

    if args.molecule == "prot":
        raxml_command += ["-m", "PROTGAMMAAUTO"]
    elif args.molecule == "rrna" or args.molecule == "dna":
        raxml_command += ["-m", "GTRGAMMA"]
    else:
        sys.exit("ERROR: a substitution model could not be specified with the 'molecule' argument: " + args.molecule)

    stdout, raxml_returncode = launch_write_command(raxml_command, False)

    if raxml_returncode != 0:
        sys.stderr.write("ERROR: RAxML did not complete successfully! "
                         "Look in " + args.mltreemap + raxml_out + os.sep +
                         "RAxML_info." + code_name + " for an error message.\n")
        sys.stderr.write("RAxML command used:\n")
        sys.stderr.write(' '.join(raxml_command) + "\n")
        sys.exit(3)

    tree_to_swap = "%s/RAxML_bestTree.%s" % (raxml_out, code_name)
    final_mltree = "%s_tree.txt" % code_name
    os.system("mv %s %s" % (phylip_file, raxml_out))

    if os.path.exists(fasta_replaced_file):
        os.remove(fasta_replaced_file)
    if os.path.exists(phylip_file + ".reduced"):
        os.remove(phylip_file + ".reduced")

    swap_tree_names(tree_to_swap, final_mltree, code_name)

    if args.molecule == "prot":
        os.system("mv %s.fa %s.fa.p* %s" % (code_name, code_name, final_output_folder))
    if args.molecule == "rrna" or args.molecule == "dna":
        os.system("mv %s.fa %s.fa.n* %s" % (code_name, code_name, final_output_folder))
    os.system("mv %s %s %s" % (tree_taxa_list, final_mltree, final_output_folder))

    annotate_partition_tree(code_name, fasta_replace_dict, raxml_out + os.sep + "RAxML_bipartitions." + code_name)
    aa_model = find_model_used(raxml_out + os.sep + "RAxML_info." + code_name)
    update_build_parameters(args, code_name, aa_model)

    sys.stdout.write("Data for " + code_name + " has been generated succesfully.\n\n")
    sys.stdout.write("To integrate these data for use in TreeSAPP, the following steps must be performed:\n")
    sys.stdout.write("1. Include properly formatted 'denominator' codes "
                     "in data/tree_data/cog_list.tsv and data/tree_data/ref_build_parameters.tsv\n")
    sys.stdout.write("2. $ cp " + final_output_folder + os.sep + "tax_ids_%s.txt" % code_name + " data/tree_data/\n")
    sys.stdout.write("3. $ cp " + final_output_folder + os.sep + code_name + "_tree.txt data/tree_data/\n")
    sys.stdout.write("4. $ cp " + final_output_folder + os.sep + code_name + ".hmm data/hmm_data/\n")
    sys.stdout.write("5. $ cp " + final_output_folder + os.sep + code_name + ".fa* data/alignment_data/\n")
    sys.stdout.write("6. $ cp " + final_output_folder + os.sep + code_name +
                     "_tree.txt imagemaker_2_061/tree_data/\n")
    sys.stdout.write("7. $ cp " + final_output_folder + os.sep + "tax_ids_%s.txt" % code_name +
                     " imagemaker_2_061/tree_data/\n")
    sys.stdout.write("8. Create a file called imagemaker_2_061/tree_data/domain_and_color_descriptions_" +
                     code_name + ".txt to add colours to clades in the new reference tree.\n")
    sys.stdout.write("9. Modify imagemaker_2_061/tree_data/drawing_info.txt following the obvious format\n")
    sys.stdout.flush()

main()