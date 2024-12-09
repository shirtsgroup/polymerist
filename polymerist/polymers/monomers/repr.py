'''For representing monomer information'''

__author__ = 'Timotej Bernat'
__email__ = 'timotej.bernat@colorado.edu'

import logging
LOGGER = logging.getLogger(__name__)

from typing import Generator, Optional, Union
from dataclasses import dataclass, field

from itertools import cycle
from collections import defaultdict

from rdkit import Chem

from ...genutils.iteration import iter_len
from ...genutils.fileutils.jsonio.jsonify import make_jsonifiable

from ...smileslib.primitives import Smarts, is_valid_SMARTS
from ...rdutils.bonding.portlib import get_num_ports


# MAIN REPRESENTATION CLASS
@make_jsonifiable
@dataclass
class MonomerGroup:
    '''Stores collections of residue-labelled monomer SMARTS'''
    monomers : dict[str, Union[Smarts, list[Smarts]]] = field(default_factory=dict)
    term_orient : dict[str, str] = field(default_factory=dict) # keys are either "head" or "tail", values are the names of residues in "monomers"

    def __post_init__(self) -> None:
        # Encase bare SMARTS into lists and check that all monomer SMARTS are valid
        for resname, smarts_seq in self.monomers.items():
            if isinstance(smarts_seq, list):
                if not smarts_seq:
                    raise IndexError(f'Empty monomer declaration for "{resname}"') # catch case where empty list if provided (would slip through subsequent checks otherwise)
                smarts_list = smarts_seq # no modification needed
            elif isinstance(smarts_seq, str):
                LOGGER.warning(f'Wrapping bare monomer SMARTS in list to comply with spec (storing as ["{smarts_seq}"])')
                smarts_list = [smarts_seq] # wrap lone SMARTS string in list
                self.monomers[resname] = smarts_list # update value internally (doesn't change size of dict)
            else:
                raise TypeError(f'Values of monomers must be either SMARTS strings or lists of SMARTS strings, not "{type(smarts_seq).__name__}"')
            
            # check that all SMARTS are valid
            for i, smarts in enumerate(smarts_list): # we can now be sure that this is a list of SMARTS strings
                if not is_valid_SMARTS(smarts):
                    raise ValueError(f'Provided invalid monomer SMARTS string for {resname}[{i}]: "{smarts}"')      
                # DEV: decide whether or not SMILES expansion and spec-compliance should be enforced here or shunted off to the user 
        # DEV: opted to forgo term_orient check for now, as modifying this violates the read-only data model aimed for here
                
    @staticmethod
    def is_terminal(monomer : Chem.Mol) -> bool:
        '''Determine whether or not a monomer is terminal'''
        return get_num_ports(monomer) == 1

    # ATTRIBUTE PROPERTIES AND ALIASES
    @property
    def SMARTS(self) -> dict[str, list[Smarts]]:
        '''Alias of legacy "monomers" attribute'''
        return self.monomers # alias of legacy name for convenience
    
    def iter_rdmols(self, term_only : Optional[bool]=None) -> Generator[tuple[str, Chem.Mol], None, None]:
        '''
        Generate (residue name, RDKit Mol) pairs of all monomers present
        Simplifies iteration over internal lists of monomer Mols

        Can optionally filter by monomer termination:
            term_only=True  -> only terminal monomers
            term_only=False -> only middle monomers
            term_only=None  -> all monomers
        '''
        for resname, SMARTS_list in self.monomers.items():
            for SMARTS in SMARTS_list:
                monomer = Chem.MolFromSmarts(SMARTS)
                if (term_only is None) or (MonomerGroup.is_terminal(monomer) == term_only):
                    yield (resname, monomer)

    def rdmols(self, term_only : Optional[bool]=None) -> dict[str, list[Chem.Mol]]:
        '''
        Returns dict of RDKit Mol lists keyed by residue name

        Can optionally filter by monomer termination:
            term_only=True  -> only terminal monomers
            term_only=False -> only middle monomers
            term_only=None  -> all monomers
        '''
        rdmol_dict = defaultdict(list)
        for resname, rdmol in self.iter_rdmols(term_only=term_only):
            rdmol_dict[resname].append(rdmol)

        return rdmol_dict
    
    @property
    def n_monomers(self) -> int:
        '''Returns number of present monomers; multiple monomers under the same residue name are considered distinct'''
        return iter_len(self.iter_rdmols(term_only=None))
    
    # END GROUP DETERMINATION 
    def linear_end_groups(self) -> dict[str, tuple[str, Chem.Mol]]:
        '''
        Returns head-and-tail end group residue names and Mol objects as defined by term_orient
        
        If term orient is undefined, will automatically take then first 
        <= 2 terminal groups available to be the end groups
        
        Returns
        -------
        end_groups : dict[str, tuple[str, Chem.Mol]]
            A dict whose keys are any of {'head', 'tail'} and whose
            values are 2-tuples of residue names and Mols for the corresponding monomer
        '''
        if self.term_orient and set(self.term_orient.keys()) == {'head', 'tail'}:
            LOGGER.info(f'Using user-defined terminal group orientation {self.term_orient}')
            monomer_iters = {
                resname : cycle(smarts_list) 
                    for resname, smarts_list in self.rdmols(term_only=True).items()
            } # cycle handles degenerate end group case correctly
            
            return {
                head_or_tail : (resname, next(monomer_iters[resname])) # will raise KeyError if any of the resnames are not present
                    for head_or_tail, resname in self.term_orient.items()
            }
        else:
            term_orient_auto : dict[str, Smarts] = {}
            end_groups_auto  : dict[str, Chem.Mol] = {}
            for head_or_tail, (resname, rdmol) in zip(['head', 'tail'], self.iter_rdmols(term_only=True)): # zip will bottom out early if fewer than 2 terminal monomers are present
                term_orient_auto[head_or_tail] = resname # populate purely for logging
                end_groups_auto[head_or_tail]  = (resname, rdmol)
            LOGGER.warning(f'No valid terminal monomer orientations defined; auto-assigned orientations "{term_orient_auto}"; USER SHOULD VERIFY THIS YIELDS A CHEMICALLY-VALID POLYMER!')
                
            return end_groups_auto
    
    # COMPOSITION METHODS
    def __add__(self, other : 'MonomerGroup') -> 'MonomerGroup':
        '''Content-aware method of merging multiple sets of monomer info via the addition operator'''
        cls = self.__class__
        if not isinstance(other, cls):
            raise NotImplementedError(f'Can only merge {cls.__name__} with another {cls.__name__}, not object of type {type(other)}')
        # TODO: figure out how to handle combination of term group orientation gracefully (ignoring for now)
        return MonomerGroup(monomers={**self.monomers, **other.monomers})

    __radd__ = __add__ # support reverse addition

    # CHEMICAL INFORMATION
    def unique(self, cap_group : Union[Smarts, Chem.Mol]=Chem.MolFromSmarts('[H]-[*]')) -> 'MonomerGroup':
        '''Return a MonomerGroup containing only the unique monomers present, given a particular port saturating group (by default just a hydrogen)'''
        raise NotImplementedError
        # unique_mono = set()
        # for SMARTS in monomer_smarts.values():
        #     monomer = Chem.MolFromSmarts(SMARTS)
        #     clear_atom_map_nums(monomer, in_place=True) 
        #     hydrogenate_monomer_ports(monomer, in_place=True) 
        #     unique_mono.add(Chem.MolToSmiles(monomer)) # TODO : eventually make this SMARTS-based (or even better RDKit Mol-based); can't for now since hydrogenated fragments don't equate

        # return unique_mono

    def is_homopolymer(self) -> bool:
        '''Identify if a polymer is a homopolymer (i.e. only 1 type of middle monomer)'''
        # n_mid, n_term = count_middle_and_term_mono(monomer_smarts) # TODO : reimplement with comparison of port-hydrogenated monomers
        # return (n_mid == 1)
        return (len(self.unique()) == 1) # by definition, a homopolymer only has 1 unique class of monomer

    # GRAPH INFORMATION
    @property
    def is_branchable(self) -> bool:
        '''Whether it is possible to generate a branched polymer from this set of monomers'''
        return any(
            get_num_ports(monomer) > 2
                for (resname, monomer) in self.iter_rdmols(term_only=None)
        )
    
    @property
    def is_linear(self) -> bool:
        '''Whether a group of monomers can ONLY be assembled into a linear chain'''
        return not self.is_branchable

    @property
    def is_linear_homopolymer(self) -> bool:
        '''Identify if a polymer is a linear homopolymer'''
        return self.is_linear and self.is_homopolymer

    @property
    def num_mid_and_term(self) -> tuple[int, int]:
        '''Counts of how many of the monomers are middle vs terminal, respectively'''
        group_counts = [0, 0]
        for (resname, monomer) in self.iter_rdmols(term_only=None): # TODO : consider reimplementing using new term group filtering option
            group_counts[self.is_terminal(monomer)] += 1 # index by bool
        
        return tuple(group_counts) # convert to tuple