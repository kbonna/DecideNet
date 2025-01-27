# -----------------------------------------------------------------------------#
#                            glm_utils.py                                      #
#------------------------------------------------------------------------------#

import matplotlib.pyplot as plt
import nibabel as nib
import pandas as pd
import numpy as np
import numbers
import os

from itertools import combinations
from nistats import design_matrix
from nistats import hemodynamic_models
from nistats.reporting import plot_design_matrix
from nilearn import image

class Regressor:
    '''Implements representation of the single GLM regressor.
    
    Allows for conversion of regressor described as number of onsets and 
    optionally magnitude modulations into estimated BOLD timecourse through 
    make_first_level_design_matrix function from Nistats. Useful in situations
    where there are mutliple parametrically modulated regressors. Automatically
    handled both cases of unmodulated and modulated regressors.
    '''
    
    def __init__(self, name, frame_times, onset, *, duration=None, 
                 modulation=None):
        '''
        Args:
            name (str): Name of the regressor.
            frame_times (np.ndarray of shape (n_frames,)):
                The timing of acquisition of the scans in seconds.
            onset (array-like): 
                Specifies the start time of each event in seconds.
            duration (array-like, optional): 
                Duration of each event in seconds. Defaults duration is set to 0 
                (impulse function).
            modulation (array-like, optional): 
                Parametric modulation of event amplitude. Before convolution 
                regressor is demeaned. 
        '''
        if not isinstance(frame_times, np.ndarray) or frame_times.ndim != 1:
            msg = 'frame_times should be np.ndarray of shape (n_frames, )'
            raise TypeError(msg)

        self._name = name
        self._frame_times = frame_times
            
        n_events = len(onset)
        
        if duration is None:
            duration = np.zeros(n_events)
            
        if modulation is None or (len(modulation) > 1 
                                  and np.all(np.array(modulation) == modulation[0])):
            modulation = np.ones(n_events)
        elif len(modulation) > 1:
            modulation = np.array(modulation)
            modulation = modulation - np.mean(modulation)
        
        self._values, _ = hemodynamic_models.compute_regressor(
            exp_condition=np.vstack((onset, duration, modulation)),
            hrf_model='spm',
            frame_times=frame_times
        )
     
    @classmethod
    def from_values(cls, name, frame_times, values):
        '''Alternative constructor bypassing compute_regressor function.
        
        Args:
            name (str): Name of the regressor.
            frame_times (np.ndarray of shape (n_frames,)):
                The timing of acquisition of the scans in seconds.
            values (array-like): 
                Regressor values for each frame time.         
        '''
        if not isinstance(frame_times, np.ndarray) or frame_times.ndim != 1:
            msg = 'frame_times should be np.ndarray of shape (n_frames, )'
            raise TypeError(msg)
        if len(values) != len(frame_times):
            msg = 'length mismatch between values and frame_times ' + \
                 f'{len(values)} != {len(frame_times)}'
            raise ValueError(msg)
        
        obj = cls.__new__(cls)
        super(Regressor, obj).__init__()
        obj._name = name
        obj._frame_times = frame_times
        obj._values = np.array(values)[:, np.newaxis]
        
        return obj
        
    @property
    def name(self):
        return self._name
        
    @property
    def frame_times(self):
        return self._frame_times
        
    @property
    def values(self):
        return self._values
    
    @property
    def is_empty(self):
        return (self.values == 0).all()
    
    def __repr__(self):
        return f"{self.__class__.__name__}(name='{self.name}')"
    
    def __len__(self):
        return len(self.frame_times)
    
    def plot(self, color='r') -> None:
        '''Plots BOLD timecourse for regressors:
        
        Args:
            color: Plot line color.
        '''
        fig, ax = plt.subplots(facecolor='w', figsize=(25, 3))

        ax.plot(self._frame_times, self.values, color)
        ax.set_xlim(0, np.max(self._frame_times))
        ax.set_xlabel('Time [s]')
        ax.set_ylabel('est. BOLD')
        ax.grid()
    
    def corr(self, other):
        '''Calculate correlation between two regressors.'''
        if not isinstance(other, self.__class__):
            msg = f'{other} should be of {self.__class__} type but is {type(other)}'
            raise TypeError(msg)
        return np.corrcoef(self.values.T, other.values.T)[0, 1]
    
    def __add__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError(f'cannot add regressor and {type(other)}')
        if not (self.frame_times == other.frame_times).all():
            raise ValueError('frame_times for added regressors does not match')    
        
        result = self.from_values(
            name=f'{self.name}+{other.name}',
            frame_times=self._frame_times,
            values=(self._values+other._values).flatten()
        )         
        return result
    
    def __mul__(self, other):
        if not isinstance(other, numbers.Real):
            raise TypeError(f'cannot multiply regressor and {type(other)}')

        result = self.from_values(
            name=f'{other}*{self.name}',
            frame_times=self._frame_times,
            values=(self._values*other).flatten()
        )    
        return result
        
    def __rmul__(self, other):
        return self * other
    
    def __sub__(self, other):
        new_name = f'{self.name}-{other.name}'
        result = self + (-1) * other
        result._name = new_name
        return result
    
    def __truediv__(self, other):
        return self * (1 / other)
    
    
def my_make_first_level_design_matrix(regressors: list):
    '''Turn arbitrary number of regressors into first level design matrix.
    
    This function wraps make_first_level_design_matrix function from 
    nistats.design_matrix module to create design matrix from list of Regressor
    objects. Note that this design matrix lacks confounds regressors. If you
    want to include confounds, pass it to the FirstLevelModel.fit method.

    Args:
        regressors: list of Regressor objects

    Returns (2-tuple):
        Final GLM design matrix as DataFrame and dictionary with condition
        contrast vectors for all specifified regressors.
    '''
    if not isinstance(regressors, list) or not regressors:
        raise TypeError('regressors should be a non-empty list')
    if not all(isinstance(reg, Regressor) for reg in regressors):
        raise TypeError(f'regressors should be a list of {Regressor}')
    if not all([(r.frame_times == regressors[0].frame_times).all() 
                for r in regressors]):
        raise ValueError('frame_times for all regressors should be equal')
    frame_times = regressors[0].frame_times
    
    # Filter empty regressors (i.e. miss regressor for subjects with no misses)
    regressors = [r for r in regressors if r.is_empty == False]

    # Combine regressors into dataframe
    joined_regs_names = [r.name for r in regressors]
    joined_regs = pd.DataFrame(
        data=np.hstack([r.values for r in regressors]), 
        index=frame_times,
        columns=joined_regs_names
    )

    # Compute design matrix
    dm = design_matrix.make_first_level_design_matrix(
        frame_times=frame_times,
        add_regs=joined_regs,
        add_reg_names=joined_regs_names
    )

    # Create condition vectors for all regressors of interest
    conditions = {r.name: np.zeros(dm.shape[1]) for r in regressors}
    for condition_name in conditions:
        conditions[condition_name][list(dm.columns).index(condition_name)] = 1

    return (dm, conditions)      

def convolve(signal, t_r=2, oversampling=50, hrf_model='spm'):
    '''Convolve signal with hemodynamic response function.
    
    Performs signal convolution with requested hrf model. This function wraps around nistats 
    compute_regressor function usually used for creating task-based regressors. The trick is to 
    define neural regressor as a sequence of equally spaced (with the gap of 1TR) and modulated
    'task events'. Event amplitude modulation corresponds to neural signal amplitude at a given 
    timepoint.
    
    Args:
        signal (iterable):
            Neural signal.
        t_r (float):
            Repetition time in seconds.
        oversampling (int, optional):
            Convolution upsampling rate.
        hrf_model (str, optional):
            Hemodynamic response function type. See the documentation of compute regressor function 
            from nistats.hemodynamic_models for more details.
            
    Returns:
        Convolved neural signal in BOLD space.
    '''
    n_volumes = len(signal)
    frame_times = np.arange(0, n_volumes * t_r, t_r)
    onsets = np.zeros((3, n_volumes))
    for vol, amplitude in enumerate(signal):
        onsets[:, vol] = (vol * t_r, 0, amplitude)

    signal_bold = hemodynamic_models.compute_regressor(
        onsets,
        hrf_model=hrf_model,                              
        frame_times=frame_times,
        oversampling=oversampling,     
        fir_delays=None)[0].ravel()

    return signal_bold


def load_first_level_stat_maps(path, tasks):
    '''Load statistical maps (first level GLM output).
    
    Args:
        path (str): 
            Path to directory where first level output is stored. Note that 
            files should follow BIDS-like naming convention, i.e. 
            sub-<sub>_task-<task>_statmap.nii
        tasks (list of str):
            List containing all task names.
    Returns: 
        (list): 
            List of size n_conditions x n_subjects. First index denotes task 
            condition. Conditions are coded 0 for reward and 1 for punishment.
    '''
    tmap_files = {task: sorted([os.path.join(path, file) 
                  for file in os.listdir(path) if task in file]) 
                  for task in tasks}
    tmap_imgs = {task: [nib.load(tmap_files[task][i]) 
                 for i in range(len(tmap_files[task]))] 
                 for task in tasks}
    
    return tmap_imgs


def extract_img_value_for_mni_coords(mni_coords, img):
    '''Extract image value for specific mni coordinates.
    
    Args: 
        mni_coords (tuple):
            MNI coordinates x, y, z.
        img (Nifti1Image):
            3D Nifti image. Can be atlas image, statistical map, T1, etc.
    
    Returns:
        Image value for voxel closest to specified MNI coordinates.
    '''    
    array_coords = image.coord_transform(*mni_coords, np.linalg.inv(img.affine))
    array_coords = tuple(round(array_coord) for array_coord in array_coords)
    return img.get_fdata()[array_coords]


def add_clusters_labels(clusters_table, atlas_img, atlas_label_codes, 
                        atlas_name, inplace=False):
    '''Automatic labeling of activation peaks according to provided brain atlas.
    
    Args:
        clusters_table (DataFrame):
            Output of nistats.reporting.get_clusters_table function. DataFrame
            describing peak activations. If you want to use your custom table 
            make sure that it has three columns: X, Y and Z describing peak
            coordinates in MNI space.
        atlas_img (nibabel.nifti1.Nifti1Image):
            Atlas brain image with values for each voxel corresponding to region
            index.
        atlas_label_codes (dict):
            Mapping between region index and region name. Keys should be 
            integers corresponding to region index and values should be region 
            names.    
        atlas_name (str):
            Name of the brain atlas.
        inplace (bool, optional):
            If True, clusters_table will be modified in place, otherwise new 
            DataFrame is returned. 
            
    Returns:
        Cluster table with additional column corresponding to peak label. 
    '''
    col_name = f'{atlas_name} label'
    
    if inplace:
        clusters_table_extended = clusters_table
    else:
        clusters_table_extended = clusters_table.copy(deep=True)
    clusters_table_extended[col_name] = ''
    
    for row, cluster in clusters_table.iterrows():

        peak_mni_coords = np.array(cluster.loc[['X', 'Y', 'Z']], dtype='float')
        
        # Find region index
        region_index = extract_img_value_for_mni_coords(
            mni_coords=peak_mni_coords,
            img=atlas_img
        )
        
        # Find corresponding region name
        clusters_table_extended.loc[row, col_name] = atlas_label_codes.get(
            int(region_index), '?') 

    return clusters_table_extended


def upsampled_events(t_r, n_volumes, onset, duration, modulation=None, 
                     sampling_rate=1/16):
    '''Create upsampled regressors from given events.
    
    This function is used to create upsampled psychological regressors. These 
    can be used to create interaction regressors in PPI analysis. Since 
    deconvolved neural signal is usually upsampled (sixteen times by default is 
    SPM) and interaction regressors have to be created in the neural domain, 
    psychological regressor has to be upsampled to match sample rate for the
    neural regressor. Then PPI regressor can be calculated as point-by-point 
    multiplication of psychological and physiological regressors.
    
    Args:
        t_r (float):
            Scanning repetition time (TR).
        n_volumes (int):
            Number of scans for entire task.
        onset (iterable):
            Contains all event onset (in seconds).
        duration (float):
            Duration of event. Here, we assume all events have same duration.
        modulation (iterable, optional):
            Events amplitude modulation.
        sampling_rate (float):
            Upsampling rate. For 16-fold upsampling sampling_rate is 1/16.
            
    Returns:
        Numpy 1D array of length n_volumes / sampling_rate. Note that this 
        function returns demeaned psychological regressor (omitting demeaning 
        can produce spurious PPI effects if deconvolution is imperfect).
    '''
    if modulation is None:
        modulation = np.ones((len(onset), ))
    
    if duration > 0:
        n_frames_per_event = int(duration / (t_r * sampling_rate))
    elif duration == 0:
        n_frames_per_event = 1
    else: 
        raise ValueError('duration should be non negative float')
        
    frame_times_up = np.arange(0, n_volumes*t_r, t_r*sampling_rate)
    ts_event_up = np.zeros(frame_times_up.shape)

    for event, amplitude in zip(onset, modulation):
        first_frame = np.argmax(frame_times_up >= event)
        ts_event_up[range(first_frame, 
                          first_frame + n_frames_per_event)] = amplitude
        
    return ts_event_up - ts_event_up.mean()