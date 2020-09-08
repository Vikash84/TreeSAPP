__author__ = 'Connor Morgan-Lang'

import logging
import sys
import re
from pygtrie import StringTrie

from treesapp.phylo_seq import TreeLeafReference


class Taxon:
    """
    The Taxon class represents an individual component from which the TaxonomicHierarchy is based on.
    These instances essentially form a unidirectional linked-list data structure linking the "child" taxa to their
    respective taxonomic "parents" deeper ranks (i.e. closer to the root).

    The coverage attribute is necessarily modified when adding to the TaxonomicHierarchy to control which taxa are
    present/absent (a Taxon is removed from TaxonomicHierarchy.hierarchy if coverage <= 0) and in cases where a child
    has two different parents the Taxon with greater coverage is replaces the other and forms a single path.
    """
    def __init__(self, name, rank):
        self.name = name
        self.rank = rank
        self.parent = None
        self.prefix = ""
        self.taxid = ""
        self.coverage = 1

    def prefix_taxon(self, taxon_sep="__"):
        return self.prefix + taxon_sep + self.name

    def lineage(self) -> list:
        """
        Recursively retrieve the Taxon instances in a Taxon's lineage of parent instances

        :return: List of Taxon instances in order from Root to Species
        """
        if not self.parent:
            return [self]
        lineage = self.parent.lineage()
        lineage.append(self)
        return lineage

    def absorb(self, taxon) -> None:
        """
        Merge the values from one Taxon instance into the current Taxon instance.
        Coverages are summed. Other attributes may be merged here in the future.

        :param taxon: A Taxon instance that will be folded into the current instance
        :return: None
        """
        self.coverage += taxon.coverage
        return

    def tax_dist(self, taxon) -> int:
        if self.name == taxon.name:
            return 0
        if not self.parent and not taxon.parent:
            return 1
        if taxon.name not in [t.name for t in self.lineage()]:
            return taxon.tax_dist(self)
        return self.parent.tax_dist(taxon) + 1

    def valid(self, tax_hierarchy_map: dict) -> bool:
        if self.name == "unclassified":
            return False
        if self.prefix_taxon() not in tax_hierarchy_map:
            logging.debug("Unable to find {} in hierarchy map.\n".format(self.prefix_taxon()))
            return False
        return True

    @staticmethod
    def lca(left_taxon, right_taxon):
        l1 = left_taxon.lineage()
        l2 = right_taxon.lineage()

        while len(l1) > len(l2):
            l1.pop()
        while len(l2) > len(l1):
            l2.pop()

        while l1 and l2:
            t1 = l1.pop()
            t2 = l2.pop()
            if t1 == t2:
                return t1
        return

    @staticmethod
    def lineage_slice(start_taxon, stop_taxon) -> list:
        """
        Does not include the stop_taxon, includes the start_taxon.

        :param start_taxon: A Taxon instance that is more resolved (further from root)
        :param stop_taxon: A Taxon instance whose taxon is closer to the root
        :return: A list of all Taxon instances between the start_taxon and stop_taxon, start inclusive
        """
        lineage = start_taxon.lineage()
        while lineage:
            taxon = lineage.pop(0)
            if taxon == stop_taxon:
                break
        return lineage


class TaxonomicHierarchy:
    """
    Used for storing and querying the taxonomic hierarchy of a reference package.
    """
    def __init__(self, sep="; "):
        # Private variables - should not be changed after instantiation
        self.rank_name_map = {'superkingdom': 'domain', "strain": "type_strain"}
        self.accepted_ranks_depths = {"root": 0, "domain": 1, "phylum": 2, "class": 3, "order": 4,
                                      "family": 5, "genus": 6, "species": 7}
        self.no_rank_name = "no rank"  # Name of rank for non-canonical taxonomic ranks
        self.lin_sep = sep
        self.taxon_sep = "__"  # Separator between the rank prefix and the taxon name
        self.bad_taxa = ["cellular organisms", "unclassified"]  # Optional list that can be used to remove some taxa
        self.canonical_prefix = re.compile(r"^[nrdpcofgs]" + re.escape(self.taxon_sep))
        self.proper_species_re = re.compile("^(s__)?[A-Z][a-z]+ [a-z]+$")
        self.no_rank_re = re.compile(r"^" + re.escape(self.no_rank_name[0] + self.taxon_sep) + r".*")
        self.conflicts = set()  # A tuple to store Taxon instances that create conflicting paths in the hierarchy
        # Main data structures
        self.trie = StringTrie(separator=sep)  # Trie used for more efficient searches of taxa and whole lineages
        self.hierarchy = dict()  # Dict of prefix_taxon (e.g. p__Proteobacteria) name to Taxon instances
        self.rank_prefix_map = {self.no_rank_name[0]: {self.no_rank_name},  # Tracks prefixes representing ranks
                                'r': {"root"}}
        # The following are used for tracking the state of the instance's data structures
        self.trie_key_prefix = True  # Keeps track of the trie's prefix for automated updates
        self.trie_value_prefix = False  # Keeps track of the trie's prefix for automated updates
        self.clean_trie = True  # To track whether taxa of "no rank" are included in the trie
        self.rank_prefix_map_values = set
        self.lineages_fed = 0
        self.lineages_into_trie = 0

    def get_state(self) -> dict:
        instance_state = {"clean_trie": self.clean_trie,
                          "trie_key_prefix": self.trie_key_prefix,
                          "trie_value_prefix": self.trie_value_prefix,
                          "rank_prefix_map_values": str(self.rank_prefix_map_values),
                          "accepted_ranks_depths": self.accepted_ranks_depths,
                          "lineages_fed": str(self.lineages_fed),
                          "lineages_into_tree": str(self.lineages_into_trie),
                          "rank_prefix_map": str(self.rank_prefix_map),
                          "taxon_sep": "'" + self.taxon_sep + "'",
                          "lin_sep": "'" + self.lin_sep + "'"}
        return instance_state

    def so_long_and_thanks_for_all_the_fish(self, error_str="") -> None:
        summary_string = error_str + "Summary of TaxonomicHierarchy instance state:\n"
        for key, value in self.get_state().items():
            summary_string += "\t" + key + " = " + str(value) + "\n"
        logging.error(summary_string)
        raise RuntimeError(17)

    def get_taxon_names(self, with_prefix=False):
        if with_prefix:
            return set([self.hierarchy[taxon].prefix_taxon() for taxon in self.hierarchy])
        else:
            return set([self.hierarchy[taxon].name for taxon in self.hierarchy])

    def get_taxon(self, prefix_taxon) -> Taxon:
        """
        Retrieve the Taxon instance mapped to prefix_taxon in self.hierarchy.
        If prefix_taxon isn't in self.hierarchy, a warning is issued and None returned

        :param prefix_taxon: A string formatted such that the first letter of the taxonomic rank is a prefix, separated
         from the taxon's name by two underscores, like 'd__Bacteria'
        :return: Taxon instance mapped to the prefix_taxon in self.hierarchy
        """
        try:
            return self.hierarchy[prefix_taxon]  # type: Taxon
        except KeyError:
            logging.debug("Taxon name '{}' not present in taxonomic hierarchy.\n".format(prefix_taxon))
            return

    def resolved_as(self, lineage, rank_name="species") -> bool:
        """
        This determines whether a lineage is resolved to at least the rank provided,
        within the existing TaxonomicHierarchy instance.

        :param lineage: A taxonomic lineage *with prefixed ranks* separated by self.lin_sep
        :param rank_name: Name of the rank being compared to
        :return: Boolean indicating whether a lineage is as resolved as a rank
        """
        self.validate_rank_prefixes()

        if rank_name not in self.accepted_ranks_depths:
            self.so_long_and_thanks_for_all_the_fish("Rank name '{0}' is not valid in taxonomic hierarchy.\n")

        taxon = lineage.split(self.lin_sep)[-1]
        taxon_rank = self.rank_prefix_map[taxon[0]]
        if self.accepted_ranks_depths[taxon_rank] >= self.accepted_ranks_depths[rank_name]:
            return True
        else:
            return False

    def resolved_to(self, lineage) -> str:
        """
        Determine the most resolved taxonomic rank in a lineage

        :param lineage: A taxonomic lineage *with prefixed ranks* separated by self.lin_sep
        :return: The name of the taxonomic rank a lineage was resolved to
        """
        self.validate_rank_prefixes()

        taxon = lineage.split(self.lin_sep)[-1]
        try:
            return self.rank_prefix_map[taxon[0]]
        except IndexError:
            self.so_long_and_thanks_for_all_the_fish("Empty taxon in lineage '{}'\n".format(lineage))

    def rm_taxon_from_hierarchy(self, taxon: Taxon, decrement=1) -> None:
        # Decrease Taxon.coverage for every Taxon instance in the lineage
        taxon.coverage -= decrement
        # Remove a Taxon from self.hierarchy dictionary if its coverage equals zero
        if taxon.coverage <= 0:
            try:
                self.hierarchy.pop(taxon.prefix_taxon())
            except KeyError:
                pass
                # logging.error("Unable to pop taxon '{}' from taxonomic hierarchy.\n".format(taxon.prefix_taxon()))
                # raise KeyError
        return

    def redirect_hierarchy_paths(self, rep: Taxon, old: Taxon):
        # Do not add values to rep since old is likely in its lineage so double counting
        if rep not in old.lineage():  # Just to make sure though...
            rep.absorb(old)
        for taxon in self.hierarchy.values():  # type: Taxon
            if taxon.parent == old:
                if taxon == rep:
                    pass
                else:
                    taxon.parent = rep
        # Remove all taxa between the old taxon and the LCA(rep, old)
        lca = Taxon.lca(old, rep)
        for taxon in Taxon.lineage_slice(old, lca):
            self.rm_taxon_from_hierarchy(taxon)
        return

    def resolve_conflicts(self) -> dict:
        """

        :return: A dictionary mapping the obsolete Taxon instance to the new representative Taxon instance
        """
        replaced_nodes = {}
        if len(self.conflicts) == 0:
            return replaced_nodes

        conflict_resolution_summary = "Taxonomic hierarchy conflicts were resolved by merging the left taxon into the right:\n"
        while self.conflicts:
            node_one, node_two = self.conflicts.pop()  # type: (Taxon, Taxon)

            if not node_one.valid(self.hierarchy) or not node_two.valid(self.hierarchy):
                continue

            if node_one.rank == self.no_rank_name and node_two.rank == self.no_rank_name:
                # Which one has higher coverage?
                if node_one.coverage > node_two.coverage:
                    rep = node_one
                    obsolete = node_two
                else:
                    rep = node_two
                    obsolete = node_one
            elif node_one.rank == self.no_rank_name:
                obsolete = node_one
                rep = node_two
            elif node_two.rank == self.no_rank_name:
                obsolete = node_two
                rep = node_one
            else:
                logging.debug("Conflicting nodes both had valid ranks and were therefore skipped. "
                              "These should not have been flagged as conflicting nodes.\n")
                continue
            self.redirect_hierarchy_paths(rep=rep, old=obsolete)  # obsolete Taxon is removed from self.hierarchy
            replaced_nodes[obsolete] = rep
            conflict_resolution_summary += "\t'{}' ({}) -> '{}' ({})\n".format(obsolete.name, obsolete.rank,
                                                                               rep.name, rep.rank)

        logging.debug(conflict_resolution_summary)
        return replaced_nodes

    def validate_rank_prefixes(self) -> None:
        """
        Ensures that there is only a single rank name mapped to a rank prefix (in self.rank_prefix_map) and changes
        the format of the values in self.rank_prefix_map to str from set.

        :return: None
        """
        if self.rank_prefix_map_values is set:  # Work here is already done
            for prefix in self.rank_prefix_map:
                rank_names = self.rank_prefix_map[prefix]  # type: set
                if type(rank_names) is set:
                    if len(rank_names) == 1:
                        self.rank_prefix_map[prefix] = rank_names.pop()
                    elif len(rank_names) > 1:
                        logging.error("Conflicting rank names detected for rank prefix '{0}': "
                                      "'{1}'\n".format(prefix, ','.join(rank_names)))
                        sys.exit(5)
                    else:
                        logging.warning("Prefix exists for missing rank name...? This isn't going to be good.\n")
            self.rank_prefix_map_values = str
        return

    def whet(self) -> None:
        # Ensure the rank_prefix_map values are sets that can be added to, in case self.validate_rank_prefixes was run
        if self.rank_prefix_map_values is not set:
            for k, v in self.rank_prefix_map.items():
                if type(v) is not set:
                    self.rank_prefix_map[k] = {v}
            self.rank_prefix_map_values = set
        return

    def trie_check(self):
        """
        Ensure the trie is contemporary with all lineages that have been fed into the hierarchy.
        This is accomplished by comparing the lineages_fed and lineages_into_trie properties.
        If they differ, trie rebuilds.

        :return: None
        """
        if self.lineages_fed != self.lineages_into_trie:
            self.build_multifurcating_trie(key_prefix=self.trie_key_prefix, value_prefix=self.trie_value_prefix)
        return

    def hierarchy_key_chain(self, child: Taxon, parent: Taxon) -> Taxon:
        """

        :param child:
        :param parent:
        :return:
        """
        i = 1
        alias = "{}{}{}_{}".format(child.prefix, self.taxon_sep, child.name, i)
        # Has this new taxon already been added?
        while alias in self.hierarchy:
            # This taxon's alias has been added before
            if self.hierarchy[alias].parent == parent:
                return self.hierarchy[alias]
            i += 1
            alias = "{}{}{}_{}".format(child.prefix, self.taxon_sep, child.name, i)
        # This is a taxon representing a new conflict. It's alias must be added to the hierarchy
        if alias not in self.hierarchy:
            logging.debug("Taxon '{}' with diverging lineage ({}) renamed '{}'\n"
                          "".format(child.name, self.lin_sep.join([t.name for t in parent.lineage()]), alias))
            twin = Taxon(alias.split(self.taxon_sep)[-1], child.rank)
            twin.parent = parent
            twin.prefix = child.prefix
            self.hierarchy[twin.prefix_taxon()] = twin
            return twin

    def evaluate_hierarchy_clash(self, child: Taxon, p1: Taxon, p2: Taxon) -> Taxon:
        """
        Determines whether parents of a taxon being added to self.hierarchy are the same (no clash) or unique (clash).
        If they are the same, there is nothing to do - this is the ideal situation!
        Otherwise, there may be a conflict in the taxonomic lineages of multiple taxa. For example:

        1. "d__Bacteria; p__Proteobacteria; n__environmental samples"
        2. "d__Bacteria; p__Firmicutes; c__Fake; n__environmental samples"

        Clashes are common when either the parent or the taxon (child) has no rank,
        and can show up in a taxonomic lineage at multiple different ranks.

        Prevents a hash clash by renaming the child uniquely by appending an incrementing number.

        :param child: The Taxon instance which has both p1 and p2 as potential parents
        :param p1: One parent of child, specifically the new one encountered (adoptive or in-law?)
        :param p2: A second parent of child, specifically the original one (direct descendent?)
        :return: A taxon instance representing the child with a unique, correct parent
        """
        if not p1 or p1 == p2:
            child.coverage += 1
            return child
        # Ensure they are both not valid ranks, or the same rank
        parent_lca = Taxon.lca(p1, p2)
        if parent_lca is None:
            return self.hierarchy_key_chain(child, p1)
        p1_ranks = {t.rank for t in Taxon.lineage_slice(p1, parent_lca)}
        p2_ranks = {t.rank for t in Taxon.lineage_slice(p2, parent_lca)}
        p1_lca_dist = p1.tax_dist(parent_lca)
        p2_lca_dist = p2.tax_dist(parent_lca)
        # TODO: What if the taxonomic distance between a parent and the LCA is 0 i.e. the parent is the LCA?
        # If all of the ranks are 'no rank' between a parent and the lca of the parents, add it to conflicts
        if (p1_ranks and not p1_ranks.difference({self.no_rank_name})) or \
                (p2_ranks and not p2_ranks.difference({self.no_rank_name})):
            child.coverage += 1
            self.conflicts.add((p1, p2))
            return child
        elif max(p1_lca_dist, p2_lca_dist) > 1:  # The hierarchy path between the parent and LCA is too long to pop
            # These are both taxa with a valid rank - the job gets a bit harder now. Time to prevent a clash!
            return self.hierarchy_key_chain(child, p1)
        else:
            child.coverage += 1
            self.conflicts.add((p1, p2))
            return child

    def digest_taxon(self, taxon: str, rank: str, rank_prefix: str, previous: Taxon) -> Taxon:
        """
        Digest taxon adds a new taxon to the TaxonomicHierarchy.hierarchy dictionary if it isn't already in the keys,
        or will increment the coverage attribute of a Taxon if it is already in the hierarchy dictionary.

        :param taxon: A string representing a taxon
        :param rank: A string representing the taxonomic rank for which taxon is a member
        :param rank_prefix: The one character prefix for taxon's rank e.g. 'd' for Domain
        :param previous: The Taxon instance representing the parent of taxon
        :return: The Taxon instance representing taxon
        """
        # taxon can come with the rank_prefix included and we don't want to prepend it again
        if taxon.startswith(rank_prefix + self.taxon_sep):
            taxon = taxon.lstrip(rank_prefix + self.taxon_sep)
        prefix_name = rank_prefix + self.taxon_sep + taxon

        if taxon in self.bad_taxa:
            return None

        try:
            ti = self.hierarchy[prefix_name]  # type: Taxon
            ti = self.evaluate_hierarchy_clash(ti, previous, ti.parent)
        except KeyError:
            ti = Taxon(taxon, rank)
            ti.parent = previous
            ti.prefix = rank_prefix
            self.hierarchy[prefix_name] = ti

        return ti

    def feed(self, lineage: str, lineage_ex: list) -> Taxon:
        """
        Takes lineage string, where each taxon is separated by self.lin_sep and, guided by the lineage_ex
        which is a list of extra lineage information, it adds each taxon to the dictionary self.hierarchy.
        Each taxon's name and rank is used to either find an existing Taxon object in self.hierarchy or create new ones.
        The lineage string is used to ensure the order of the taxon-parent relationships (linked-list) are correct.

        :param lineage: A taxonomic lineage string. Example:
         "cellular organisms; Bacteria"
        :param lineage_ex: A dictionary with taxon names as keys and taxonomic rank as values. Example:
         [{'TaxId': '131567', 'ScientificName': 'cellular organisms', 'Rank': 'no rank'},
                          {'TaxId': '2', 'ScientificName': 'Bacteria', 'Rank': 'superkingdom'}]
        :return: None
        """
        previous = None

        self.whet()  # Convert the values in self.rank_prefix_map to set

        taxa = lineage.split(self.lin_sep)
        while taxa and lineage_ex:
            taxon_info = lineage_ex.pop(0)
            taxon_name = taxa.pop(0)
            if taxon_name != taxon_info["ScientificName"]:
                if previous:
                    self.remove_leaf_nodes(previous.prefix_taxon())
                logging.error("Lineage and Entrez lineage extra information list don't match. Current state:\n"
                              "taxon = {0}\n"
                              "taxon_info = {1}\n".format(taxon_name, str(taxon_info)))
                sys.exit(11)
            rank = taxon_info["Rank"]
            # Decide what the prefix will be
            if rank in self.accepted_ranks_depths:
                pass
            elif rank in self.rank_name_map:
                rank = self.rank_name_map[rank]
            else:
                rank = self.no_rank_name
            rank_prefix = rank[0]
            # Record the rank's prefix in rank_prefix_map
            try:
                self.rank_prefix_map[rank_prefix].add(rank)
            except KeyError:
                self.rank_prefix_map[rank_prefix] = {rank}
            except AttributeError:
                self.so_long_and_thanks_for_all_the_fish("TaxonomicHierarchy.rank_prefix_map values are not all sets.\n")

            taxon = self.digest_taxon(taxon_name, rank, rank_prefix, previous)  # type: Taxon
            if not taxon and previous:
                break
            else:
                previous = taxon

        if len(taxa) > 0 or len(lineage_ex) > 0:
            if previous:
                self.remove_leaf_nodes(previous.prefix_taxon())
            logging.error("Not all elements popped from paired lineage and lineage_ex information.\n"
                          "lineage list = {0}\n"
                          "lineage information dictionary = {1}\n".format(taxa, lineage_ex))
            sys.exit(11)

        # Update the number of lineages provided to TaxonomicHierarchy
        self.lineages_fed += 1

        return previous

    def append_to_hierarchy_dict(self, child: str, parent: str, rank: str, rank_prefix: str) -> None:
        """
        This can be used for including a new taxon in self.hierarchy, connecting it to a pre-existing lineage.
        The child must be more-resolved (i.e. a species name) than the parent (i.e. a genus name).
        The taxonomic hierarchy rank of child must be the subsequent rank following that of parent.
        Skipping ranks (e.g. parent is Class and child is Species) is forbidden.

        :param child: Unlabelled taxon that is a more-resolved label than parent.
        :param parent: A labelled taxon that is a less-resolved label (is deeper in the taxonomic hierarchy) than child.
        :param rank: The taxonomic rank name that the child represents.
        :param rank_prefix:  The prefix of the rank. Typically this is the first character (lowercase) of rank.
        :return: None
        """
        try:
            parent_taxon = self.hierarchy[parent]
        except KeyError:
            if not self.canonical_prefix.search(parent):
                self.so_long_and_thanks_for_all_the_fish("Rank prefix expected on parent taxon '{}'\n".format(parent))
            else:
                self.so_long_and_thanks_for_all_the_fish("Parent taxon '{}' not in hierarchy.\n".format(parent))
            sys.exit()

        self.whet()
        self.validate_rank_prefixes()
        self.digest_taxon(taxon=child, previous=parent_taxon, rank=rank, rank_prefix=rank_prefix)
        return

    def feed_leaf_nodes(self, ref_leaves: list, rank_prefix_name_map=None) -> None:
        """
        Loads TreeLeafReference instances (objects with 'lineage', 'accession' and 'number' variables among others) into
        the TaxonomicHierarchy.hierarchy property.

        Since the lineages are composed of taxa with rank-prefixes, opposed to full-length rank names,
        a rank-prefix name map is required to infer the taxonomic rank of each prefix. One is loaded by default if none
        are provided.

        :param ref_leaves: A list of TreeLeafReference instances to be loaded into the hierarchy
        :param rank_prefix_name_map: A dictionary mapping rank-prefixes (str) to a set of potential rank names
        :return: None
        """
        if rank_prefix_name_map is None:
            self.rank_prefix_map.update({'d': {"domain"}, 'p': {"phylum"}, 'c': {"class"}, 'o': {"order"},
                                         'f': {"family"}, 'g': {"genus"}, 's': {"species"}, 't': {"type_strain"}})
        else:
            self.rank_prefix_map.update(rank_prefix_name_map)
        self.whet()
        self.validate_rank_prefixes()

        previous = None
        for ref_leaf in ref_leaves:  # type: TreeLeafReference
            if not ref_leaf.lineage:
                continue
            taxa = ref_leaf.lineage.split(self.lin_sep)
            while taxa:
                taxon_name = taxa.pop(0)  # type: str
                rank_prefix = taxon_name.split(self.taxon_sep)[0]
                try:
                    rank = self.rank_prefix_map[rank_prefix]
                except KeyError:
                    logging.debug("Unexpected format of taxon '{}' in lineage {} - no rank prefix separated by '{}'?\n"
                                  "".format(taxon_name, ref_leaf.lineage, self.taxon_sep))
                    taxa.clear()
                    continue
                taxon = self.digest_taxon(taxon_name, rank, rank_prefix, previous)  # type: Taxon
                if not taxon and previous:
                    ref_leaf.lineage = self.lin_sep.join([taxon.prefix_taxon() for taxon in previous.lineage()])
                    break
                else:
                    previous = taxon

            # Update the number of lineages provided to TaxonomicHierarchy
            self.lineages_fed += 1
            previous = None
        return

    def emit(self, prefix_taxon: str, with_prefix=False) -> str:
        """
        Taking a prefixed-taxon (e.g. g__Actinomyces) as input it
        retrieves the corresponding Taxon instance from self.hierarchy.
        The parents of the taxon are traversed while a parent exists to recreate the original taxonomic lineage.

        :param prefix_taxon: A string formatted such that the first letter of the taxonomic rank is a prefix, separated
         from the taxon's name by two underscores, like 'd__Bacteria'
        :param with_prefix: Boolean controlling whether each taxon's prefix is included in the lineage string
        :return: A string of the taxon's lineage where each rank is separated by self.lin_sep
        """
        taxon = self.get_taxon(prefix_taxon)
        if not taxon:
            return ""

        anno_lineage = taxon.lineage()
        if with_prefix:
            return self.lin_sep.join([taxon.prefix_taxon() for taxon in anno_lineage])
        else:
            return self.lin_sep.join([taxon.name for taxon in anno_lineage])

    def build_multifurcating_trie(self, key_prefix=True, value_prefix=False) -> None:
        """
        The initial TaxonomicHierarchy is just made from a dictionary of String (e.g. d__Bacteria): Taxon pairs.
        After finding the correct key, a lineage can be formed by traversing upwards through the linked-list of 'parent's.

        However, finding the Keys across a set of taxa names is inefficient coming in at O(n^2).
        This function builds a prefix trie that could be leveraged for more efficiently determining whether
        all taxa in a lineage are present.
        Using self.trie (pygtrie.StringTrie object), it is populated by the lineage of each taxon in self.hierarchy.
        Nodes in the tree follow the format (lineage: taxon) where taxon lacks its rank-prefix. An example:

        StringTrie(n__cellular organisms: cellular organisms,
        n__cellular organisms; d__Bacteria: Bacteria,
        n__cellular organisms; d__Bacteria; n__Terrabacteria group: Terrabacteria group,
        n__cellular organisms; d__Bacteria; n__Terrabacteria group; p__Actinobacteria: Actinobacteria, separator=; )

        :type key_prefix: bool
        :param key_prefix: Flag indicating whether the lineages (node keys) have their rank-prefix
        :param value_prefix: Flag indicating whether the taxon (node values) have their rank-prefix
        :return: None
        """
        lineages = {"r__Root"}

        if key_prefix != self.trie_key_prefix:
            self.trie_key_prefix = key_prefix
        if value_prefix != self.trie_value_prefix:
            self.trie_value_prefix = value_prefix

        # Collect all lineages in self.hierarchy, retaining the rank-prefix in case they are needed later
        for taxon_name in self.hierarchy:  # type: str
            lineages.add(self.emit(taxon_name, True))

        self.trie.clear()
        # Populate the trie using lineages, with rank-prefixes where desired (keys/values)
        for lin in sorted(lineages):
            taxon = self.clean_lineage_string(lin, with_prefix=value_prefix).split("; ")[-1]
            if not value_prefix:
                taxon = self.canonical_prefix.sub('', taxon)
            if self.clean_trie:
                lin = self.clean_lineage_string(lin, with_prefix=key_prefix)
            elif key_prefix is False:
                lin = self.strip_rank_prefix(lin)
            # Only add the entry to the trie if both lineage (key) and taxon (value) are non-empty
            if lin and taxon:
                self.trie[lin] = taxon

        self.lineages_into_trie = self.lineages_fed
        return

    def query_trie(self, lineage: str) -> str:
        """
        Determine whether a lineage is present in the TaxonomicHierarchy.trie
        If the lineage is present, return the corresponding trie value. Otherwise, return an empty string

        :return: The value corresponding to the query lineage in the trie
        """
        taxon = ""
        try:
            taxon = self.trie[lineage]
        except KeyError:
            logging.debug("Lineage '{}' isn't present in TaxonomicHierarchy.trie.\n".format(lineage))
            pass
        return taxon

    def get_prefixed_lineage_from_bare(self, bare_lineage: str) -> str:
        """

        :param bare_lineage: A lineage lacking rank prefixes e.g. "Bacteria; Actinobacteria; Actinobacteria"
        :return: Empty string if lineage or a prefix of the full lineage isn't found, or a lineage with the correct
        rank-prefixes prepended if it was found.
        """
        # Ensure the TaxonomicHierarchy.trie is formatted correctly for the queries
        if self.trie_key_prefix is True or self.trie_value_prefix is False:
            self.build_multifurcating_trie(key_prefix=False, value_prefix=True)

        # Clean up the taxonomic lineage query by removing bad taxa (e.g. 'cellular organisms').
        lineage_split = bare_lineage.split(self.lin_sep)
        if self.clean_trie:
            lineage_split = self.rm_bad_taxa_from_lineage(lineage_split)  # Not guided by rank prefix
            lineage_split = self.rm_absent_taxa_from_lineage(lineage_split)  # Not guided by rank prefix

        ref_lineage = ""
        # Iteratively climb the taxonomic lineage until a hit is found or there are no further ranks
        while not ref_lineage and lineage_split:
            taxon = self.query_trie(self.lin_sep.join(lineage_split))
            if taxon:
                ref_lineage = self.clean_lineage_string(lineage=self.emit(taxon, with_prefix=True),
                                                        with_prefix=True)
            lineage_split = lineage_split[:-1]
        return ref_lineage

    def project_lineage(self, lineage_str):
        """
        Function for checking whether all taxa in a lineage exist within TaxonomicHierarchy

        :param lineage_str: A lineage string where taxa are separated by self.lin_sep. Can be prefixed (e.g. d__Archaea)
         or not, but it must match the state of self.trie. This is not checked!
        :return: Boolean indicating whether the entire lineage is present in the multifurcating taxonomic trie
        """
        self.trie_check()
        return lineage_str in self.trie

    def rank_representatives(self, rank_name: str, with_prefix=False) -> set:
        """
        Retrieves all taxa in the hierarchy of a specified rank

        :param rank_name: Name of the rank to search for taxa
        :param with_prefix: Flag indicating whether the taxa names should include the rank prefix (True) or not
        :return: Set containing all taxa in the hierarchy that represent a specific rank
        """
        # Check rank name to see if its present in the hierarchy
        if rank_name not in self.accepted_ranks_depths:
            self.so_long_and_thanks_for_all_the_fish("Rank '{0}' "
                                                     "is not in hierarchy's accepted names.\n".format(rank_name))

        taxa = set()
        for prefix_name in self.hierarchy:
            taxon = self.hierarchy[prefix_name]
            if taxon.rank == rank_name:
                if with_prefix:
                    taxa.add(prefix_name)
                else:
                    taxa.add(taxon.name)
        return taxa

    def rm_bad_taxa_from_lineage(self, split_lineage: list) -> list:
        """
        For removing bad taxa from a lineage. Useful when the lineage lacks rank-prefixes

        :param split_lineage: A taxonomic lineage that has been split into a list of taxonomic ranks. For example:
         ["cellular organisms", "Bacteria", "Proteobacteria"]
        :return: Lineage with the taxa in self.bad_taxa (if any) removed
        """
        cleaned_lineage = []
        if self.bad_taxa:
            # Potential list of bad strings: "cellular organisms", "delta/epsilon subdivisions"
            for taxon in split_lineage:
                if taxon not in self.bad_taxa:
                    cleaned_lineage.append(taxon)
        else:
            cleaned_lineage = split_lineage
        return cleaned_lineage

    def rm_absent_taxa_from_lineage(self, lineage_list: list) -> list:
        """
        Removes all taxa from the taxonomic lineage that are not present in self.hierarchy.
        This is meant to remove potentially non-canonical ranks from the unprefixed taxonomic lineage.

        :param lineage_list: A list representation of the split taxonomic lineage
        :return: A list of the taxonomic lineage with the taxa that are not present in self.hierarchy removed
        """
        _taxa = self.get_taxon_names()
        i = 0
        while i < len(lineage_list):
            if lineage_list[i] not in _taxa:
                lineage_list.pop(i)
            else:
                i += 1
        return lineage_list

    def strip_rank_prefix(self, lineage: str) -> str:
        stripped_lineage = []
        for rank in lineage.split(self.lin_sep):
            try:
                prefix, taxon = rank.split(self.taxon_sep)
            except ValueError:
                taxon = rank
            stripped_lineage.append(str(taxon))
        return self.lin_sep.join(stripped_lineage)

    def clean_lineage_string(self, lineage: str, with_prefix=True) -> str:
        """
        Removes superfluous taxonomic ranks and characters that make lineage comparisons difficult

        :type with_prefix: bool
        :param with_prefix: Flag indicating whether the lineages have their rank-prefix
        :param lineage: A taxonomic lineage string where each rank is separated by a semi-colon
        :return: String with the purified taxonomic lineage adhering to the NCBI hierarchy
        """
        reconstructed_lineage = []
        self.validate_rank_prefixes()
        for rank in lineage.split(self.lin_sep):  # type: str
            try:
                prefix, name = rank.split(self.taxon_sep)
            except ValueError:
                rank = re.sub(r'(?<!^[a-z])' + re.escape(self.taxon_sep), '_', rank)
                try:
                    prefix, name = rank.split(self.taxon_sep)
                except ValueError:
                    self.so_long_and_thanks_for_all_the_fish("Rank-prefix required for clean_lineage_string().\n"
                                                             "None was provided for taxon '{}' in lineage {}\n"
                                                             "".format(rank, lineage))
                    raise ValueError()

            if not self.no_rank_re.match(rank) and self.rank_prefix_map[prefix] in self.accepted_ranks_depths:
                if with_prefix is False:
                    rank = self.canonical_prefix.sub('', rank)
                if name:
                    reconstructed_lineage.append(str(rank))
        return self.lin_sep.join(reconstructed_lineage)

    def check_lineage(self, lineage: str, organism: str, verbosity=0) -> str:
        """
        Sometimes the NCBI lineage is incomplete or the rank prefixes are out of order.
        This function checks (and fixes) the following things:
        1. Uses organism to add Species to the lineage if it is missing
        2. Ensure the progression of rank (i.e. from domain to species) is ordered properly

        :param lineage: A taxonomic lineage *with prefixed ranks* separated by self.lin_sep
        :param organism: Name of the organism. Parsed from the sequence header (usually at the end in square brackets)
        :param verbosity: 1 prints debugging messages
        :return: A list of elements for each taxonomic rank representing the taxonomic lineage
        """
        if not self.trie_key_prefix or not self.clean_trie:
            self.clean_trie = True
            logging.debug("Switching multifurcating trie to include rank prefixes.\n")
            self.build_multifurcating_trie(key_prefix=True)

        if verbosity:
            logging.debug("check_lineage():\n\t"
                          "lineage = '{0}'\n\t"
                          "organism = '{1}'\n\t"
                          "trie_key_prefix = {2}\n\t"
                          "clean_trie = {3}\n".format(lineage, organism, self.trie_key_prefix, self.clean_trie))

        lineage = self.clean_lineage_string(lineage, with_prefix=True)

        if len(lineage) == 0:
            return ""

        if not self.project_lineage(lineage):
            self.so_long_and_thanks_for_all_the_fish("Lineage '{0}' not in taxonomic hierarchy.\n".format(lineage))

        # Handle prefix discrepancy between lineage and organism if organism doesn't have rank prefix
        if not self.canonical_prefix.search(organism):
            for child_lineage, taxon in self.trie.items(prefix=lineage):  # type: (str, str)
                if taxon == organism:
                    organism = child_lineage.split(self.lin_sep)[-1]

        lineage_list = lineage.split(self.lin_sep)
        rank_resolution = self.resolved_to(lineage)
        try:
            rank_depth = self.accepted_ranks_depths[rank_resolution]
        except KeyError:
            logging.error("'{}' not in list of accepted ranks ({}).\n"
                          "".format(rank_resolution, ", ".join(self.accepted_ranks_depths.keys())))
            raise KeyError
        if self.proper_species_re.match(lineage_list[-1]):
            if verbosity:
                logging.debug("check_lineage(): Perfect lineage.\n")
        elif len(lineage_list) == 6 and rank_depth == 6 and self.proper_species_re.match(organism):
            if not self.canonical_prefix.search(organism):
                if self.rank_prefix_map['s'] == "species":
                    organism = "s" + self.taxon_sep + organism
                else:
                    self.so_long_and_thanks_for_all_the_fish("Unexpected rank prefix for species"
                                                             " in TaxonomicHierarchy.rank_prefix_map\n")
            self.append_to_hierarchy_dict(organism, lineage_list[-1], rank="species", rank_prefix='s')
            lineage_list.append(organism)
            if verbosity:
                logging.debug("check_lineage(): Organism name added to complete the lineage.\n")
        else:
            if verbosity:
                logging.debug("check_lineage(): Truncated lineage.\n")

        self.validate_rank_prefixes()  # Ensure the rank-prefix map is formatted correctly
        # Ensure the order and progression of ranks is correct (no domain -> phylum -> species for example)
        i = 0
        for taxon in lineage_list:  # type: str
            try:
                prefix, _ = taxon.split(self.taxon_sep)
            except ValueError:
                self.so_long_and_thanks_for_all_the_fish("Rank-prefix required for check_lineage(),"
                                                         " taxon: '{}'.\n".format(taxon))
                raise ValueError

            if self.rank_prefix_map[prefix] not in self.accepted_ranks_depths:
                logging.debug("Rank '{0}' is not in the list of accepted taxonomic ranks.\n"
                              "Lineage will be truncated to '{1}'.\n".format(self.rank_prefix_map[prefix],
                                                                             self.lin_sep.join(lineage_list[0:i])))
                for prefix_taxon_name in lineage_list[i:]:
                    if self.get_taxon(prefix_taxon=prefix_taxon_name):
                        self.rm_taxon_from_hierarchy(self.get_taxon(prefix_taxon=prefix_taxon_name))  # type: Taxon
                lineage_list = lineage_list[0:i]
                break

            if self.accepted_ranks_depths[self.rank_prefix_map[taxon[0]]] > i+1:
                logging.debug("Order of taxonomic ranks in cleaned lineage '{0}' is unexpected.\n"
                              "Lineage will be truncated to '{1}'.\n".format(self.lin_sep.join(lineage_list),
                                                                             self.lin_sep.join(lineage_list[0:i])))
                for prefix_taxon_name in lineage_list[i:]:
                    if self.get_taxon(prefix_taxon=prefix_taxon_name):
                        self.rm_taxon_from_hierarchy(self.get_taxon(prefix_taxon=prefix_taxon_name))  # type: Taxon
                lineage_list = lineage_list[0:i]
                break
            i += 1
        if len(lineage_list) == 0:
            lineage_list = ["r__Root"]

        return self.lin_sep.join(lineage_list)

    def remove_leaf_nodes(self, taxa: list) -> None:
        """
        Decrements the coverage attribute for each taxon and all parent taxa (deeper ranks).
        If coverage reaches zero, for a taxon its key is popped from the hierarchy dictionary

        TaxonomicHierarchy.trie is rebuilt is any taxa are popped from the hierarchy.

        :param taxa: A list of taxa names that exist within TaxonomicHierarchy.hierarchy keys
        :return: None
        """
        if type(taxa) is str:
            taxa = [taxa]
        for prefix_taxon_name in sorted(taxa):
            leaf_taxon = self.get_taxon(prefix_taxon=prefix_taxon_name)  # type: Taxon
            if leaf_taxon:
                for taxon in leaf_taxon.lineage():
                    self.rm_taxon_from_hierarchy(taxon)
                # Update self.lineages_fed
                self.lineages_fed -= 1

        # Update self.trie if the number of lineages fed is not equal to number of lineages in the trie
        self.trie_check()
        return

    def jetison_taxa_from_hierarchy(self, entrez_records: list) -> None:
        """
        Used for removing taxonomic lineages from the TaxonomicHierarchy

        :param entrez_records: A list of EntrezRecord instances
        :return: None
        """
        taxa_names = []
        for e_record in entrez_records:  # type: entrez_utils.EntrezRecord
            # Find the prefixed names of the organisms to be removed
            if e_record.organism and not self.canonical_prefix.search(e_record.organism):
                try:
                    taxon = e_record.taxon_rank[0] + self.taxon_sep + e_record.organism
                    if taxon not in self.hierarchy:
                        taxon = e_record.lineage.split(self.lin_sep)[-1]
                except IndexError:
                    taxon = e_record.lineage.split(self.lin_sep)[-1]
            elif e_record.organism in self.hierarchy:
                taxon = e_record.organism
            else:
                continue
            taxa_names.append(taxon)

        logging.debug("Removing {} taxa ({} unique) from taxonomic hierarchy.\n".format(len(taxa_names),
                                                                                        len(set(taxa_names))))
        self.remove_leaf_nodes(taxa_names)
        return

    def summarize_taxa(self):
        """
        Function for enumerating the representation of each taxonomic rank within a TaxonomicHierarchy instance

        :return: A formatted, human-readable string stating the number of unique taxa at each rank
        """
        taxonomic_summary_string = ""
        taxa_counts = dict()
        self.validate_rank_prefixes()

        for taxon_name in self.hierarchy:
            taxon = self.hierarchy[taxon_name]  # type: Taxon
            try:
                taxa_counts[taxon.rank] += 1
            except KeyError:
                taxa_counts[taxon.rank] = 1
            except TypeError:
                self.so_long_and_thanks_for_all_the_fish("TypeError in summarize_taxa().\n{}, {}, {}.\n"
                                                         "".format(taxa_counts, taxon.rank, taxon))

        taxonomic_summary_string += "Number of unique lineages:\n"
        for rank in sorted(self.accepted_ranks_depths, key=lambda x: self.accepted_ranks_depths[x]):
            try:
                counts = taxa_counts[rank]
            except KeyError:  # Pass if a rank wasn't found in the lineages
                continue

            buffer = " "
            while len(rank) + len(str(counts)) + len(buffer) < 12:
                buffer += ' '
            taxonomic_summary_string += "\t" + rank + buffer + str(counts) + "\n"

        return taxonomic_summary_string

    def trim_lineages_to_rank(self, leaf_taxa_map: dict, rank: str) -> dict:
        """
        Iterates a dictionary and trims the lineage string values to a specified rank.
        Also removes lineages that are unclassified at the desired rank or higher (closer to root)

        :param leaf_taxa_map: Maps indices to lineages
        :param rank: The taxonomic rank lineages need to be trimmed to
        :return: Dictionary of keys mapped to trimmed lineages
        """
        trimmed_lineage_map = dict()
        depth = 0
        th_rank_name = ""

        try:
            depth = self.accepted_ranks_depths[rank]
        except KeyError:
            self.so_long_and_thanks_for_all_the_fish("Rank '{0}' is not in hierarchy's accepted names.\n".format(rank))
        truncated = 0

        self.validate_rank_prefixes()

        for node_name in sorted(leaf_taxa_map):
            lineage = leaf_taxa_map[node_name].split(self.lin_sep)

            # Remove lineage from testing if the rank doesn't exist (unclassified at a high rank)
            if len(lineage) == 1 or len(lineage) < depth:
                truncated += 1
                continue

            trimmed_lineage_map[node_name] = self.lin_sep.join(lineage[:depth])

            # Ensure the last taxon in the lineage has the expected rank-prefix
            taxon = lineage[:depth][-1]
            try:
                th_rank_name = self.rank_prefix_map[taxon[0]]
            except KeyError:
                self.so_long_and_thanks_for_all_the_fish("Rank prefix {}"
                                                         " not found in rank prefix map.\n".format(taxon[0]))
            if rank != th_rank_name:
                self.so_long_and_thanks_for_all_the_fish("Rank prefix '{}' doesn't match rank name '{}'"
                                                         " in trimmed lineage.\n".format(rank, th_rank_name))

        logging.debug("{0} lineages truncated before '{1}' were removed during lineage trimming.\n".format(truncated,
                                                                                                           rank))
        return trimmed_lineage_map
