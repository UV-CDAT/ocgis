from ocgis.calc import base
import numpy as np


class FrequencyPercentile(base.AbstractUnivariateSetFunction,base.AbstractParameterizedFunction):
    key = 'freq_perc'
    parms_definition = {'percentile':float}
    description = 'The percentile value along the time axis. See: http://docs.scipy.org/doc/numpy-dev/reference/generated/numpy.percentile.html.'
    
    def calculate(self,values,percentile=None):
        '''
        :param percentile: Percentile to compute.
        :type percentile: float on the interval [0,100]
        '''
        ret = np.percentile(values,percentile,axis=0)
        return(ret)
    
    
class Mean(base.AbstractUnivariateSetFunction):
    description = 'Compute mean value of the set.'
    key = 'mean'
    
    def calculate(self,values):
        return(np.ma.mean(values,axis=0))
    
    
class StandardDeviation(base.AbstractUnivariateSetFunction):
    description = 'Compute standard deviation of the set.'
    key = 'std'
    
    def calculate(self,values):
        return(np.ma.std(values,axis=0))