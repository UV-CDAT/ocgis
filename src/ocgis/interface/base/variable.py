from ocgis.util.logging_ocgis import ocgis_lh
import abc
from collections import OrderedDict
from ocgis.util.helpers import get_iter
import numpy as np
from ocgis import constants


class AbstractValueVariable(object):
    __metaclass__ = abc.ABCMeta
    
    def __init__(self,value=None):
        self._value = value
    
    @property
    def value(self):
        if self._value is None:
            self._value = self._get_value_()
        return(self._value)
    def _get_value_(self):
        return(self._value)
    
    @property
    def _value(self):
        return(self.__value)
    @_value.setter
    def _value(self,value):
        self.__value = self._format_private_value_(value)
    @abc.abstractmethod
    def _format_private_value_(self,value):
        return(value)


class AbstractSourcedVariable(AbstractValueVariable):
    __metaclass__ = abc.ABCMeta
    
    def __init__(self,data,src_idx=None,value=None,debug=False):
        if not debug and value is None and data is None:
            ocgis_lh(exc=ValueError('Sourced variables require a data source if no value is passed.'))
        self._data = data
        self._src_idx = src_idx
        self._debug = debug
        
        super(AbstractSourcedVariable,self).__init__(value=value)
        
    @property
    def _src_idx(self):
        return(self.__src_idx)
    @_src_idx.setter
    def _src_idx(self,value):
        self.__src_idx = self._format_src_idx_(value)
    
    def _format_src_idx_(self,value):
        if value is None:
            ret = value
        else:
            ret = value
        return(ret)
    
    def _get_value_(self):
        if self._data is None and self._value is None:
            ocgis_lh(exc=ValueError('Values were requested from data source, but no data source is available.'))
        elif self._src_idx is None and self._value is None:
            ocgis_lh(exc=ValueError('Values were requested from data source, but no source index source is available.'))
        else:
            self._set_value_from_source_()
        return(self._value)
            
    @abc.abstractmethod
    def _set_value_from_source_(self): pass


class Variable(AbstractSourcedVariable):
    
    def __init__(self,name=None,alias=None,units=None,meta=None,uid=None,
                 value=None,data=None,debug=False):
        self.name = name
        self.alias = alias or name
        self.units = units
        self.meta = meta or {}
        self.uid = uid
        
        super(Variable,self).__init__(value=value,data=data,debug=debug)
        
    def __getitem__(self,slc):
        if self._value is None:
            value = None
        else:
            value = self._value[slc]
        ret = Variable(name=self.name,alias=self.alias,units=self.units,meta=self.meta,
                       uid=self.uid,value=value,data=self._data,debug=self._debug)
        return(ret)
                
    def __repr__(self):
        ret = '{0}(alias="{1}",name="{2}",units="{3}")'.format(self.__class__.__name__,self.alias,self.name,self.units)
        return(ret)
    
    def _format_private_value_(self,value):
        if value is None:
            ret = None
        else:
            assert(isinstance(value,np.ndarray))
            if not isinstance(value,np.ma.MaskedArray):
                ret = np.ma.array(value,mask=False,fill_value=constants.fill_value)
            else:
                ret = value
        return(ret)
    
    def _get_value_(self):
        raise(NotImplementedError)
    
    def _set_value_from_source_(self):
        raise(NotImplementedError)
    
    
class VariableCollection(OrderedDict):
    
    def __init__(self,**kwds):
        variables = kwds.pop('variables',None)
        
        super(VariableCollection,self).__init__()
        
        if variables is not None:
            for variable in get_iter(variables,dtype=Variable):
                self.add_variable(variable)
                
    def add_variable(self,variable):
        assert(isinstance(variable,Variable))
        assert(variable.alias not in self)
        self.update({variable.alias:variable})
        
    def _get_sliced_variables_(self,slc):
        variables = [v.__getitem__(slc) for v in self.itervalues()]
        ret = VariableCollection(variables=variables)
        return(ret)
        
        
class DerivedVariable(Variable):
    
    def __init__(self,**kwds):
        self.function = kwds.pop('function')
        
        super(DerivedVariable,self).__init__(**kwds)