'''Reference and utilities common to all RDKit objects'''

__author__ = 'Timotej Bernat'
__email__ = 'timotej.bernat@colorado.edu'

from typing import Any, TypeAlias, Union
from rdkit.Chem.rdchem import Atom, Bond, Mol, RWMol

from ...genutils.attrs import compile_argfree_getable_attrs
from ...genutils.decorators.functional import optional_in_place
from ...genutils.typetools.categorical import _union_member_factory

RDObj : TypeAlias = Union[Atom, Bond, Mol, RWMol]
isrdobj = _union_member_factory(RDObj, 'RDObj')


# REFERENCE FOR "MAGIC" MOL PROP KEYS (https://www.rdkit.org/docs/RDKit_Book.html#romol-mol-in-python)
RDMOL_MAGIC_PROPS = {
    'MolFileComments'        : 'Read from/written to the comment line of CTABs.',
    'MolFileInfo'            : 'Read from/written to the info line of CTABs.',
    '_MolFileChiralFlag'     : 'Read from/written to the chiral flag of CTABs.',
    '_Name'                  : 'Read from/written to the name line of CTABs.',
    '_smilesAtomOutputOrder' : 'The order in which atoms were written to SMILES',
    '_smilesBondOutputOrder' : 'The order in which bonds were written to SMILES',
}
# REFERENCE FOR "MAGIC" ATOM PROP KEYS (https://www.rdkit.org/docs/RDKit_Book.html#atom)
RDATOM_MAGIC_PROPS = {
    '_CIPCode'               : 'the CIP code (R or S) of the atom',
    '_CIPRank'               : 'the integer CIP rank of the atom',
    '_ChiralityPossible'     : 'set if an atom is a possible chiral center',
    '_MolFileRLabel'         : 'integer R group label for an atom, read from/written to CTABs.',
    '_ReactionDegreeChanged' : 'set on an atom in a product template of a reaction if its degree changes in the reaction',
    '_protected'             : 'atoms with this property set will not be considered as matching reactant queries in reactions',
    'dummyLabel'             : '(on dummy atoms) read from/written to CTABs as the atom symbol',
    'molAtomMapNumber'       : 'the atom map number for an atom, read from/written to SMILES and CTABs',
    'molfileAlias'           : 'the mol file alias for an atom (follows A tags), read from/written to CTABs',
    'molFileValue'           : 'the mol file value for an atom (follows V tags), read from/written to CTABs',
    'molFileInversionFlag'   : 'used to flag whether stereochemistry at an atom changes in a reaction, read from/written to CTABs, determined automatically from SMILES',
    'molRxnComponent'        : 'which component of a reaction an atom belongs to, read from/written to CTABs',
    'molRxnRole'             : 'which role an atom plays in a reaction (1=Reactant, 2=Product, 3=Agent), read from/written to CTABs',
    'smilesSymbol'           : 'determines the symbol that will be written to a SMILES for the atom',
}

# REFERENCE TABLES FOR ENFORCING C++ TYPING THAT RDKit ENFORCES
RDPROP_GETTERS = {
    str   : 'GetProp',
    bool  : 'GetBoolProp',
    int   : 'GetIntProp',
    float : 'GetDoubleProp'
}
RDPROP_SETTERS = {
    str   : 'SetProp',
    bool  : 'SetBoolProp',
    int   : 'SetIntProp',
    float : 'SetDoubleProp'
}

# PROPERTY INSPECTION AND TRANSFER FUNCTIONS
def detailed_rdobj_info(rdobj : RDObj) -> dict[str, Any]:
    '''Extract all get-able info about a particular RDKit atom. Does NOT include any non-default Prop values (e.g. atomMapNumber)'''
    return compile_argfree_getable_attrs(rdobj, getter_re='Get', repl_str='')

def copy_rdobj_props(from_rdobj : RDObj, to_rdobj : RDObj) -> None: # NOTE : no need to incorporate typing info, as RDKit objects can correctly interpret typed strings
    '''For copying properties between a pair of RDKit Atoms or Mols'''
    # NOTE : avoid use of GetPropsAsDict() to avoid errors from restrictive C++ typing
    assert isrdobj(from_rdobj) and isrdobj(to_rdobj) # verify that both objects passed are RDKit objects...
    assert type(from_rdobj) == type(to_rdobj)        # ...AND that both objects are the same type of RDKit object

    for prop in from_rdobj.GetPropNames():
        to_rdobj.SetProp(prop, from_rdobj.GetProp(prop))

@optional_in_place
def assign_props_from_dict(prop_dict : dict[str, Any], rdobj : RDObj, preserve_type : bool=True) -> None:
    '''Copies all attributes from a strng-keyed dictionary of properties as Props of an RDKit object'''
    for key, value in prop_dict.items():
        if (type(value) not in RDPROP_SETTERS) or (not preserve_type): # set as string if type is unspecified or if explicitly requested to
            rdobj.SetProp(key, str(value))
        else:
            setter = getattr(rdobj, RDPROP_SETTERS[type(value)]) # use the atom's setter for the appropriate type
            setter(key, value) # pass key and value to setter method
