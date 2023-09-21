'''Thin wrappers around mdtraj-implemented property calculations'''

from typing import Any, Callable, Iterable, Optional, TypeAlias
from dataclasses import dataclass, field

from itertools import combinations

import numpy as np
import pandas as pd
import mdtraj as mdt

from openmm.unit import Unit
from openmm.unit import nanometer, nanosecond, dimensionless

from ..genutils.unitutils import hasunits


# ENCAPSULATION FOR PROPERTY CALCULATIONS
@dataclass
class PropCalc:
    '''For encapsulating property calculation methods, labels, and units'''
    calc   : Callable
    name   : str
    abbr   : str
    unit   : Unit
    kwargs : dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f'{self.name} ({self.abbr}, {self.unit.get_symbol()})'

    def compute(self, traj : mdt.Trajectory) -> Any:
        '''Apply method to a trajectory'''
        return self.calc(traj, **self.kwargs)
    

DEFAULT_PROPS = [ # the base properties of interest for the 2023 monomer spec study
    PropCalc(calc=mdt.compute_rg                , name='Radius of Gyration'             , abbr='Rg'  , unit=nanometer),
    PropCalc(calc=mdt.shrake_rupley             , name='Solvent Accessible Surface Area', abbr='SASA', unit=nanometer**2, kwargs={'mode' : 'residue'}),
    PropCalc(calc=mdt.relative_shape_antisotropy, name='Relative Shape Anisotropy'      , abbr='K2'  , unit=dimensionless)    
]


# TRAJECTORY TOPOLOGY SELECTION
PairDict : TypeAlias = dict[str, Iterable[tuple[int, int]]] # a dictionary with key-labelled arrays of atom index pairs

def atom_pairs_by_element(mdtop : mdt.Topology) -> PairDict:
    '''Returns a pair dict of atom IDs by each possible duo of distinct elements'''
    unique_elem_types = set(atom.element.symbol for atom in mdtop.atoms)
    
    return {
        f'{elem1}-{elem2}' : mdtop.select_pairs(f'element {elem1}', f'element {elem2}')
            for (elem1, elem2) in combinations(unique_elem_types, 2) # every possible choice of 2 distinct atom types
    }


# PROPERTY CALCULATIONS TO DATAFRAMES
def acquire_rdfs(traj : mdt.Trajectory, pair_dict : Optional[PairDict]=None, min_rad : float=0.0, max_rad : float=1.0, rad_unit : Unit=nanometer) -> pd.DataFrame:
    '''Takes a Trajectory and produces a DataFrame for all possible pairwise Radial Distribution Functions,
    along with the radii sampled up to the specified maximum radius (must have units!)'''
    rad_range = np.array([min_rad, max_rad]) * rad_unit
    if pair_dict is None:
        pair_dict = atom_pairs_by_element(traj)

    out_dframe = pd.DataFrame()
    for label, atom_id_pairs in pair_dict.items():
        rad_points, rdf = mdt.compute_rdf(traj, pairs=atom_id_pairs, r_range=rad_range._value)
        out_dframe[f'Radius ({rad_unit})'] = rad_points # NOTE : radii range will be same for all pairs, so overwrite beyond first RDF is OK
        out_dframe[f'g(r) ({label})'] = rdf 

    return out_dframe

def acquire_time_props(traj : mdt.Trajectory, time_points : np.ndarray, time_unit : Unit=nanosecond, properties : list[PropCalc]=DEFAULT_PROPS) -> pd.DataFrame:
    '''Compute and plot a battery of labelled and unit-ed properties over a given trajectory'''
    out_dframe = pd.DataFrame()

    if hasunits(time_points):
        time_points = time_points.in_units_of(time_unit) # convert to chosen time units - NOTE : must be done BEFORE extracting unit string
        unit_str = f' ({time_points.unit.get_symbol()})'
    else:
        unit_str = ''
    out_dframe[f'Sample Time{unit_str}'] = time_points

    for prop in properties:
        time_series = prop.compute(traj) 
        if (time_series.ndim > 1):
            time_series = time_series.sum(axis=-1) # sum over atoms / residue if multiple series are given (particular to SASA calculation)

        out_dframe[prop.label] = time_series * prop.unit

    return out_dframe

## DataFrame splitting for plotting 
def _dframe_splitter_factory(regex : str):
    '''Factory for creating splitting methods that choose an x-data column and remianinig y-data columns from a dataframe
    based on a regular expression applied to the name of the cdata columns'''
    def dframe_to_plot_data(dframe : pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        '''Takes a DataFrame populated with RDF data and unpacks it into x and y data and labels for plotting and calculations'''
        x_data = dframe.filter(regex=regex)
        y_data = dframe[[label for label in dframe.columns if label != x_data.columns[0]]] # index props with all non-time point columns

        return x_data, y_data
    return dframe_to_plot_data

rdfs_to_plot_data   = _dframe_splitter_factory(regex='Radius')
props_to_plot_data  = _dframe_splitter_factory(regex='Time')
states_to_plot_data = _dframe_splitter_factory(regex=r'\ATime \(') # ensures that 'Elapsed Time' and 'Time Remaining' are not caught by regex as x-data (need to have only 1 column)