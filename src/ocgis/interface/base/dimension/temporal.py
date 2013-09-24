import base
import numpy as np
from collections import deque
import itertools
import datetime
from ocgis import constants
from ocgis.util.logging_ocgis import ocgis_lh
from ocgis.exc import EmptySubsetError


class TemporalDimension(base.VectorDimension):
    _date_parts = ('year','month','day','hour','minute','second','microsecond')
    _axis = 'T'
    
    def get_grouping(self,grouping):
        group_map = dict(zip(range(0,7),self._date_parts,))
        group_map_rev = dict(zip(self._date_parts,range(0,7),))

        value = np.empty((self.value.shape[0],3),dtype=object)
        
        value_datetime = self._get_datetime_value_()
        value_datetime_bounds = self._get_datetime_bounds_()
        
        if self.bounds is None:
            value[:,:] = value_datetime.reshape(-1,1)
        else:
            value[:,0] = value_datetime_bounds[:,0]
            value[:,1] = value_datetime
            value[:,2] = value_datetime_bounds[:,1]
        
        def _get_attrs_(dt):
            return([dt.year,dt.month,dt.day,dt.hour,dt.minute,dt.second,dt.microsecond])
        
        parts = np.empty((len(self.value),len(self._date_parts)),dtype=int)
        for row in range(parts.shape[0]):
            parts[row,:] = _get_attrs_(value[row,1])
        
        unique = deque()
        for idx in range(parts.shape[1]):
            if group_map[idx] in grouping:
                fill = np.unique(parts[:,idx])
            else:
#                fill = np.array([0])
                fill = [None]
            unique.append(fill)

        select = deque()
        idx2_seq = range(len(self._date_parts))
        for idx in itertools.product(*[range(len(u)) for u in unique]):
            select.append([unique[idx2][idx[idx2]] for idx2 in idx2_seq])
        select = np.array(select)
        dgroups = deque()
        idx_cmp = [group_map_rev[group] for group in grouping]
        keep_select = []
        for idx in range(select.shape[0]):
            match = select[idx,idx_cmp] == parts[:,idx_cmp]
            dgrp = match.all(axis=1)
            if dgrp.any():
                keep_select.append(idx)
                dgroups.append(dgrp)
        select = select[keep_select,:]
        assert(len(dgroups) == select.shape[0])
        
        dtype = [(dp,object) for dp in self._date_parts]
        new_value = np.empty((len(dgroups),),dtype=dtype)
        new_bounds = np.empty((len(dgroups),2),dtype=object)

        for idx,dgrp in enumerate(dgroups):
            ## tuple conversion is required for structure arrays: http://docs.scipy.org/doc/numpy/user/basics.rec.html#filling-structured-arrays
            new_value[idx] = tuple(select[idx])
            sel = value[dgrp][:,(0,2)]
            new_bounds[idx,:] = [sel.min(),sel.max()]
        
        new_bounds = np.atleast_2d(new_bounds).reshape(-1,2)
        new_value = np.atleast_1d(new_value)

        return(TemporalGroupDimension(grouping=grouping,value=new_value,bounds=new_bounds,
                                      dgroups=dgroups))
        
    def get_time_region(self,time_region,return_indices=False):
        assert(isinstance(time_region,dict))
        
        ## return the values to use for the temporal region subsetting.
        value = self._get_datetime_value_()
        
        ## remove any none values in the time_region dictionary. this will save
        ## time in iteration.
        time_region = time_region.copy()
        time_region = {k:v for k,v in time_region.iteritems() if v is not None}
        assert(len(time_region) > 0)
        
        ## this is the boolean selection array.
        select = np.zeros(self.shape[0],dtype=bool)
        
        ## for each row, determine if the date criterion are met updating the
        ## select matrix accordingly.
        row_check = np.zeros(len(time_region),dtype=bool)
        
        for idx_row in range(select.shape[0]):
            ## do the comparison for each time_region element.
            row = value[idx_row]
            for ii,(k,v) in enumerate(time_region.iteritems()):
                part = getattr(row,k)
                if part in v:
                    row_check[ii] = True
                else:
                    row_check[ii] = False
            if row_check.all():
                select[idx_row] = True
        
        if not select.any():
            ocgis_lh(logger='nc.temporal',exc=EmptySubsetError(origin='temporal'))
        
        ret = self[select]
        
        if return_indices:
            raw_idx = np.arange(0,self.shape[0])[select]
            ret = (ret,raw_idx)
        
        return(ret)
    
    def _get_datetime_bounds_(self):
        '''Intended for subclasses to overload the method for accessing the datetime
        value. For example, netCDF times are floats that must be converted.'''
        return(self.bounds)
    
    def _get_datetime_value_(self):
        '''Intended for subclasses to overload the method for accessing the datetime
        value. For example, netCDF times are floats that must be converted.'''
        return(self.value)
        
        
class TemporalGroupDimension(base.VectorDimension):
    
    def __init__(self,*args,**kwds):
        self.grouping = kwds.pop('grouping',None)
        self.dgroups = kwds.pop('dgroups',None)
        self._representative_datetime = None
        
        super(TemporalGroupDimension,self).__init__(*args,**kwds)
    
    @property
    def representative_datetime(self):
        if self._representative_datetime is None:
            ref_value = self.value
            ref_bounds = self.bounds
            ret = np.empty((ref_value.shape[0],),dtype=object)
            set_grouping = set(self.grouping)
            if set_grouping == set(['month']):
                ref_calc_month_centroid = constants.calc_month_centroid
                for idx in range(ret.shape[0]):
                    month = ref_value[idx]['month']
                    ## get the start year from the bounds data
                    start_year = ref_bounds[idx][0].year
                    ## create the datetime object
                    ret[idx] = datetime.datetime(start_year,month,ref_calc_month_centroid)
            elif set_grouping == set(['year']):
                ref_calc_year_centroid_month = constants.calc_year_centroid_month
                ref_calc_year_centroid_day = constants.calc_year_centroid_day
                for idx in range(ret.shape[0]):
                    year = ref_value[idx]['year']
                    ## create the datetime object
                    ret[idx] = datetime.datetime(year,ref_calc_year_centroid_month,ref_calc_year_centroid_day)
            elif set_grouping == set(['month','year']):
                ref_calc_month_centroid = constants.calc_month_centroid
                for idx in range(ret.shape[0]):
                    year,month = ref_value[idx]['year'],ref_value[idx]['month']
                    ret[idx] = datetime.datetime(year,month,ref_calc_month_centroid)
            elif set_grouping == set(['day']):
                for idx in range(ret.shape[0]):
                    start_year,start_month = ref_bounds[idx][0].year,ref_bounds[idx][0].month
                    ret[idx] = datetime.datetime(start_year,start_month,ref_value[idx]['day'],12)
            elif set_grouping == set(['day','month']):
                for idx in range(ret.shape[0]):
                    start_year = ref_bounds[idx][0].year
                    day,month = ref_value[idx]['day'],ref_value[idx]['month']
                    ret[idx] = datetime.datetime(start_year,month,day,12)
            elif set_grouping == set(['day','year']):
                for idx in range(ret.shape[0]):
                    day,year = ref_value[idx]['day'],ref_value[idx]['year']
                    ret[idx] = datetime.datetime(year,1,day,12)
            elif set_grouping == set(['day','year','month']):
                for idx in range(ret.shape[0]):
                    day,year,month = ref_value[idx]['day'],ref_value[idx]['year'],ref_value[idx]['month']
                    ret[idx] = datetime.datetime(year,month,day,12)
            else:
                ocgis_lh(logger='interface.temporal',exc=NotImplementedError('grouping: {0}'.format(self.grouping)))
            return(ret)
            
    def _validate_bounds_(self,value):
        try:
            assert(value.shape[0] == self._value.shape[0])
        except AssertionError:
            ocgis_lh(exc=ValueError('Value and bounds data types do not match.'))