from collections import OrderedDict
import numpy as np
from ocgis.api.dataset.collection.dimension.temporal import TemporalDimension
from ocgis.api.dataset.collection.dimension.dimension import LevelDimension
from ocgis.api.dataset.collection.dimension.spatial import SpatialDimension


class OcgVariable(object):
    
    def __init__(self,name,value,temporal,spatial,level=None,uri=None):
        assert(value.shape[0] == len(temporal.value))
        if level is None:
            assert(value.shape[1] == 1)
        assert(np.all(value.shape[2:] == spatial.value.shape))
        
        self.name = name
        self.value = value
        self.temporal = temporal
        self.spatial = spatial
        self.level = level
        self.uri = uri
        
        ## hold aggregated values separate from raw
        self.raw_value = None
        ## hold calculated values
        self.calc_value = OrderedDict()
        
        self._is_empty = False
        
    @classmethod
    def get_empty(cls,name,uri=None):
        temporal = TemporalDimension(np.empty(0))
        spatial = SpatialDimension(np.empty(0))
        value = np.empty(0)
        ret = cls(name,value,temporal,spatial,uri=uri)
        ret._is_empty = True

   
class OcgCollection(object):
    
    def __init__(self,ugeom=None):
        if ugeom is None:
            ugeom = {'ugid':1,'geom':None}
        self.ugeom = ugeom
        self._tid_name = 'tid'
        self._tbid_name = 'tbid'
        self._tgid_name = 'tgid'
        self._tgbid_name = 'tgbid'
        self._mode = 'raw'
        
        ## variable level identifiers
        self.tid = Identifier()
        self.tbid = Identifier()
        self.tgid = Identifier()
        self.tgbid = Identifier()
        self.lid = Identifier(dtype=object)
        self.lbid = Identifier(dtype=object) ## level bounds identifier
        self.gid = Identifier(dtype=object)
        ## collection level identifiers
        self.cid = Identifier(dtype=object) ## calculations
        self.vid = Identifier(dtype=object) ## variables
        self.did = Identifier(dtype=object) ## dataset (uri)
        ## variable storage
        self.variables = {}
        
    @property
    def is_empty(self):
        es = [var._is_empty for var in self.variables.itervalues()]
        if np.all(es):
            ret = True
            if np.any(es):
                raise(ValueError)
        else:
            ret = False
        return(ret)
    
    def add_calculation(self,var):
        self._mode = 'calc'
        for key in var.calc_value.keys():
            self.cid.add(key)
        ## update time group identifiers
        self.tgid.add(var.temporal.tgdim.value)
        self.tgbid.add(var.temporal.tgdim.bounds)

    def add_variable(self,var):
        ## add the variable to storage
        self.variables.update({var.name:var})
        
        ## update collection identifiers
        self.vid.add(np.array([var.name]))
        self.did.add(np.array([var.uri]))
        
        ## update variable identifiers #########################################
        
        ## time
        self.tid.add(var.temporal.value)
        if var.temporal.bounds is not None:
            self.tbid.add(var.temporal.bounds)
        else:
            self.tbid.add(np.array([[None,None]]))
        
        ## level
        add_lbid = True
        if var.level is None:
            self.lid.add(np.array([None]))
            add_lbid = False
        else:
            self.lid.add(var.level.value)
            if var.level.bounds is None:
                add_lbid = False
        if add_lbid:
            self.lbid.add(var.level.bounds)
        else:
            self.lbid.add(np.array([[None,None]]))
            
        ## geometry
        masked = var.spatial.get_masked()
        gid = self.gid
        for geom in masked.compressed():
            gid.add(np.array([[geom.wkb]]))


class Identifier(object):
    
    def __init__(self,init_vals=None,dtype=None):
        self.dtype = dtype
        if init_vals is None:
            self.storage = None
        else:
            self._init_storage_(init_vals)
        
    def __len__(self):
        return(self.storage.shape[0])
    
    @property
    def uid(self):
        return(self.storage[:,0].astype(int))
    
    def add(self,value):
        try:
            if value.ndim <= 1:
                value = value.reshape(-1,1)
        except AttributeError:
            value = np.array([[value]])
        if self.storage is None:
            self._init_storage_(value)
        else:
            adds = np.zeros(value.shape[0],dtype=bool)
            for idx in range(adds.shape[0]):
                cmp = self.storage[:,1:] == value[idx,:]
                cmp2 = cmp.all(axis=1)
                if not np.any(cmp2):
                    adds[idx] = True
            if adds.any():
                new_values = value[adds,:]
                shape = self.storage.shape
                self.storage.resize(shape[0]+new_values.shape[0],shape[1])
                self.storage[-new_values.shape[0]:,0] = self._get_curr_(new_values.shape[0])
                self.storage[-new_values.shape[0]:,1:] = new_values
            
    def get(self,value):
        try:
            cmp = (self.storage[:,1:] == value).all(axis=1)
        except AttributeError:
            value = np.array([[value]])
            cmp = (self.storage[:,1:] == value).all(axis=1)
        return(int(self.storage[cmp,[0]]))
    
    def _get_curr_(self,n):
        ret = np.arange(self._curr,self._curr+n,dtype=self.storage.dtype)
        self._curr = self._curr + n
        return(ret)
    
    def _init_storage_(self,init_vals):
        if len(init_vals.shape) == 1:
            init_vals = init_vals.reshape(-1,1)
        shape = list(init_vals.shape)
        shape[1] += 1
        if self.dtype is None:
            self.dtype = init_vals.dtype
        self.storage = np.empty(shape,dtype=self.dtype)
        self.storage[:,1:] = init_vals
        self._curr = self.storage.shape[0]+1
        self.storage[:,0] = np.arange(1,self._curr,dtype=self.dtype)