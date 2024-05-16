'''Utilities for building new polymer structures; currently limited to linear polymers and PDB save format'''

import logging
LOGGER = logging.getLogger(__name__)

import warnings
with warnings.catch_warnings(record=True): # suppress numerous and irritating mbuild deprecation warnings
    warnings.filterwarnings('ignore',  category=DeprecationWarning)
    import mbuild as mb
    from mbuild import Compound
    from mbuild.lib.recipes.polymer import Polymer as MBPolymer

from pathlib import Path
from rdkit import Chem

from .exceptions import MorphologyError
from .estimation import estimate_chain_len_linear
from ..monomers.repr import MonomerGroup
from ..monomers.specification import SANITIZE_AS_KEKULE

from ..genutils.decorators.functional import allow_string_paths
from ..rdutils.bonding.portlib import get_linker_ids
from ..rdutils.bonding.substitution import saturate_ports, hydrogenate_rdmol_ports
from ..openmmtools.serialization import serialize_openmm_pdb


# CONVERSION
def mbmol_from_mono_rdmol(rdmol : Chem.Mol) -> tuple[Compound, list[int]]:
    '''Accepts a monomer-spec-compliant SMARTS string and returns an mbuild Compound and a list of the indices of atom ports'''
    linker_ids = [i for i in get_linker_ids(rdmol)] # record indices of ports - MUST unpack generator for mbuild compatibility
    
    # create port-free version of molecule which RDKit can embed without errors
    prot_mol = hydrogenate_rdmol_ports(rdmol, in_place=False)
    # prot_mol = saturate_ports(rdmol) # TOSELF : custom, port-based saturation methods are not yet ready for deployment - yield issues in RDKit representation under-the-hood 
    Chem.SanitizeMol(prot_mol, sanitizeOps=SANITIZE_AS_KEKULE) # ensure Mol is valid (avoids implicitValence issues)
    mb_compound = mb.conversion.from_rdkit(prot_mol) # native from_rdkit() method actually appears to preserve atom ordering

    return mb_compound, linker_ids

@allow_string_paths
def mbmol_to_openmm_pdb(pdb_path : Path, mbmol : Compound, num_atom_digits : int=2, res_repl : dict[str, str]=None) -> None:
    '''Save an MBuild Compound into an OpenMM-compatible PDB file'''
    if res_repl is None: # avoid mutable default
        res_repl = {'RES' : 'Pol'} 

    traj = mbmol.to_trajectory() # first convert to MDTraj representation (much more infor-rich format)
    omm_top, omm_pos = traj.top.to_openmm(), traj.openmm_positions(0) # extract OpenMM representations of trajectory

    serialize_openmm_pdb(
        pdb_path,
        topology=omm_top,
        positions=omm_pos,
        uniquify_atom_ids=True,
        num_atom_id_digits=num_atom_digits,
        resname_repl=res_repl
    )


# LINEAR POLYMER BUILDING
def build_linear_polymer(monomers : MonomerGroup, DOP : int, sequence : str='A', add_Hs : bool=False, energy_minimize : bool=False) -> MBPolymer:
    '''Accepts a dict of monomer residue names and SMARTS (as one might find in a monomer JSON)
    and a degree of polymerization (i.e. chain length in number of monomers)) and returns an mbuild Polymer object'''
    # 0) VERIFY THAT CHAIN ACTUAL CAN DEFINE LINEAR POLYMER
    if not monomers.is_linear:
        raise MorphologyError('Linear polymer building does not support non-linear monomer input')
    
    if monomers.has_valid_linear_term_orient:
        term_orient = monomers.term_orient
        LOGGER.info(f'Using pre-defined terminal group orientation {term_orient}')
    else:
        term_orient = {
            resname : orient
                for (resname, rdmol), orient in zip(monomers.iter_rdmols(term_only=True), ['head', 'tail']) # will raise StopIteration if fewer
        }
        LOGGER.warning(f'No valid terminal monomer orientations defined; autogenerated orientations "{term_orient}"; USER SHOULD VERIFY THIS YIELDS A CHEMICALLY-VALID POLYMER!')

    # 1) ADD MIDDLE MONOMERS TO CHAIN
    chain = MBPolymer() 
    for (resname, middle_monomer), sequence_key in zip(monomers.iter_rdmols(term_only=False), sequence): # zip with sequence limits number of middle monomers to length of block sequence
        LOGGER.info(f'Registering middle monomer {resname} (block identifier "{sequence_key}")')
        mb_monomer, linker_ids = mbmol_from_mono_rdmol(middle_monomer)
        chain.add_monomer(compound=mb_monomer, indices=linker_ids)

    # 2) ADD TERMINAL MONOMERS TO CHAIN
    term_iters = { # need to convert to iterators to allow for generator-like advancement (required for term group selection to behave as expected)
        resname : iter(rdmol_list)   # made necessary by annoying list-bound structure of current substructure spec
            for resname, rdmol_list in monomers.rdmols(term_only=True).items() 
    }
    for resname, head_or_tail in term_orient.items():
        LOGGER.info(f'Registering terminal monomer {resname} (orientation "{head_or_tail}")')
        term_monomer = next(term_iters[resname])
        mb_monomer, linker_ids = mbmol_from_mono_rdmol(term_monomer)
        chain.add_end_groups(compound=mb_monomer, index=linker_ids.pop(), label=head_or_tail, duplicate=False) # use single linker ID and provided head-tail orientation

    # 3) ASSEMBLE AND RETURN CHAIN
    n_atoms = estimate_chain_len_linear(monomers, DOP)
    LOGGER.info(f'Assembling linear polymer chain with {DOP} monomers ({n_atoms} atoms)')
    chain.build(DOP - 2, sequence=sequence, add_hydrogens=add_Hs) # "-2" is to account for term groups (in mbuild, "n" is the number of times to replicate just the middle monomers)
    for atom in chain.particles():
        atom.charge = 0.0 # initialize all atoms as being uncharged (gets rid of pesky blocks of warnings)
    LOGGER.info(f'Successfully assembled linear polymer chain with {DOP} monomers ({n_atoms} atoms)')
    
    if energy_minimize:
        LOGGER.info('Energy-minimizing chain to find more stabile conformer')
        chain.energy_minimize()
        LOGGER.info('Energy minimization completed')

    return chain