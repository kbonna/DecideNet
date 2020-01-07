# -----------------------------------------------------------------------------#
#                            glm_utils.py                                      #
#------------------------------------------------------------------------------#

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from itertools import combinations
from nistats.design_matrix import make_first_level_design_matrix

class Regressor():
    '''Implements representation of the single GLM regressor.
    
    Allows for conversion of regressor described as number of onsets and 
    optionally magnitude modulations into estimated BOLD timecourse through 
    make_first_level_design_matrix function from Nistats. Useful in situations
    where there are mutliple parametrically modulated regressors. Automatically
    handled both cases of unmodulated and modulated regressors.
    ''' 
    def __init__(self, name, frame_times, onset, 
                 duration=None, modulation=False):
        '''
        Args:
            name (str): Name of the regressor.
            frame_times (array of shape (n_frames,)):
                The timing of acquisition of the scans in seconds.
            onset (np.array): 
                Specifies the start time of each event in seconds.
            duration (np.array, optional): 
                Duration of each event in seconds. Defaults duration is set to 
                0 (impulse function).
            modulation (np.array, optional): 
                Parametric modulation of event amplitude. Before convolution 
                regressor is demeaned. 
        '''
        self._name = name
        self._onset = onset.copy()
        self._frame_times = frame_times.copy()
        self._n_events = len(onset)
        
        if modulation is not False:
            if modulation.shape != onset.shape:
                raise ValueError(
                    'onset and modulation have to be the same shape, but '\
                    '{} and {} were passed'.format(modulation.shape, onset.shape)
                )
        else:
            self._modulation = False
        self._modulation = modulation
        
        if duration is None:
            self._duration = np.zeros(onset.shape)
        else:
            if duration.shape != onset.shape:
                raise ValueError(
                    'onset and duration have to be the same shape, but '\
                    '{} and {} were passed'.format(duration.shape, onset.shape)
                )
            self._duration = duration
            
        self._dm_column = self._create_dm_column()
        
    @property
    def is_empty(self):
        return (self._onset.size == 0)
            
    @property
    def name(self):
        return self._name
                
    @property
    def dm_column(self):
        return self._dm_column
    
    def _create_dm_column(self):
        '''Create column of design matrix corresponding to regressor modulation.
        
        Args:

                
        Returns: (pd.DataFrarme)
            Regressor time-course convolved with HRF.        
        '''
        events_dict = {
            'onset': self._onset,
            'duration': self._duration,
            'trial_type': np.ones(self._n_events)
        } 

        if self._modulation is not False:
            events_dict['modulation'] = self._modulation

        events = pd.DataFrame(events_dict        )
        events.loc[:, "trial_type"] = self.name
        
        if self._modulation is not False:
            events['modulation'] -= events['modulation'].mean()
        
        dm = make_first_level_design_matrix(self._frame_times, events, drift_model=None)
        dm = dm.drop('constant', axis=1)

        return dm
    
    def plot_regressor(self, color='r') -> None:
        '''Plots BOLD timecourse for regressors:
        
        Args:
            color: Plot line color.
        '''
        fig, ax = plt.subplots(facecolor='w', figsize=(25, 3))

        ax.plot(self._dm_column, color)
        ax.set_xlim(0, np.max(self._frame_times))
        ax.set_xlabel('Time [s]')
        ax.set_ylabel('est. BOLD')
        ax.grid()
        
    @classmethod
    def corrcoef(cls, reg1, reg2):
        '''Return correlation between two regressors'''
        
        rval = np.corrcoef(
            reg1.dm_column.values.T, 
            reg2.dm_column.values.T
        )
        
        return rval[0,1]

def my_make_first_level_design_matrix(regressors: list, confounds):
    '''Turn arbitrary number of regressors and confound table int design matrix.

    Args:
        regressors: list of Regressor objects
        confounds: pd.DataFrame with confounds

    Note:
        Index of confounds should reflect frame times in secods and should match
        regressors _frame_times.

    Returns (2-tuple):
        Final GLM design matrix as DataFrame and dictionary with condition
        contrast vectors for all specifified regressors.
    '''
    regressors = [r for r in regressors if r.is_empty == False]
    
    add_regs = pd.concat(
        [r.dm_column for r in regressors] + [confounds], axis=1, sort=False
    )
    add_reg_names = [r.name for r in regressors] + list(confounds.columns)

    for ft1, ft2 in combinations([r._frame_times for r in regressors] +
                                 [np.array(confounds.index)], 2):
        if not np.array_equal(ft1, ft2):
            raise ValueError(f'regressors frame_times not matching')

    # Create design matrix
    dm = make_first_level_design_matrix(
        frame_times=regressors[0]._frame_times,
        add_regs=add_regs,
        add_reg_names=add_reg_names
        )

    # Create condition vectors for all regressors of interest
    conditions = {r.name: np.zeros(dm.shape[1]) for r in regressors}
    for condition_name in conditions:
        conditions[condition_name][list(dm.columns).index(condition_name)] = 1

    return (dm, conditions)    
