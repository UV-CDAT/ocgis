import numpy as np
import itertools
from ocgis.calc.wrap.base import OcgFunctionTree
from ocgis.calc.wrap import library
from ocgis.calc.wrap.library import SampleSize


class OcgCalculationEngine(object):
    '''
    wrapf : object : this is the wrapped function object
    grouping_idx : int[] : quickly split the data into groups
    ugrouping_idx : int[] : unique representation of grouping_idx for iteration
    weights : float[] : areal weights (not normalized)
    values : float[] : value vector corresponding to dim of grouping_idx. if
        it is a multivariate function, this should be a dictionary mapping
        variables to values that the base function will know how to interpret
    '''
    
    def __init__(self,grouping,timevec,funcs,raw=False,agg=False,
                 time_range=None,mode='raw'):
        self.raw = raw
        self.agg = agg
        self.time_range = time_range
        ## subset timevec if time_range is passed
        if self.time_range is not None:
            self.timevec = timevec[(timevec>=time_range[0])*
                                   (timevec<=time_range[1])]
        else:
            self.timevec = timevec
        ## convert solitary grouping arguments to list
        if type(grouping) == str: grouping = [grouping]
        self.grouping = grouping or ['day']
        ## always calculate the sample size. do a copy so functions list cannot
        ## grow in memory. only a problem when testing.
#        funcs_copy = copy(funcs)
#        funcs_copy.insert(0,{'func':'n'})
        self.funcs = self.set_funcs(funcs)
        self.funcs = funcs
        ## set flag for multivariate calculations. univariate and multivariate
        ## requests are not allowed at this point.
        if mode == 'multi':
            self.has_multi = True
        else:
            self.has_multi = False
        ## get the time groups
        self.dgroups,self.dtime = self.get_distinct_groups()
        ## select which value data to pull based on raw and agg arguments
        if self.raw:
            self.use_agg = False
        elif self.raw is False and self.agg is True:
            self.use_agg = True
        else:
            self.use_agg = False
        
    def set_funcs(self,funcs):
        potentials = OcgFunctionTree.get_potentials()
        for f in funcs:
            for p in potentials:
                if p[0] == f['func']:
                    f['ref'] = getattr(library,p[1])
                    break
            if 'name' not in f:
                f['name'] = f['func']
            if 'kwds' not in f:
                f['kwds'] = {}
        return(funcs)
        
    def get_distinct_groups(self):
        ## holds date components
        dparts = {'year':[],'month':[],'day':[],'idx':[]}
        ## pull date parts from date objects and append to date part dictionary
        for ii,dt in enumerate(self.timevec):
            for grp in self.grouping:
                dparts[grp].append(getattr(dt,grp))
            dparts['idx'].append(ii)
        ## convert to numpy arrays
        for key in dparts.keys(): dparts[key] = np.array(dparts[key],dtype=int)
        ## replace empty list with a list containing NoneType for nested
        ## iterator and find unique combinations.
        duni = {}
        for key in dparts.keys():
            if key is 'idx':
                continue
            elif len(dparts[key]) is 0:
                duni[key] = np.array([None])
            else:
                duni[key] = np.unique(dparts[key]).astype(int)
                
        ## make the unique group combinations
        
        ## will hold idx to groups
        dgroups = []
        dtime = {'tgid':[],'month':[],'day':[],'year':[]}
        ## the default select all array
        bidx = np.ones(len(dparts['idx']),dtype=bool)
        ## loop for combinations
        tgid = 1
        for year,month,day in itertools.product(duni['year'],duni['month'],duni['day']):
            ## idx arrays that when combined provide a group set
            check = dict(zip(['year','month','day'],[year,month,day]))
            for key,value in check.iteritems():
                dtime[key].append(value)
            yidx,midx,didx = [self._get_date_idx_(bidx,dparts,part,value) 
                              for part,value in check.iteritems()]
            idx = yidx*midx*didx
#            dgroups.append((dparts['idx'][idx]).astype(bool))
            dgroups.append(idx)
            dtime['tgid'].append(tgid)
            tgid += 1
        return(dgroups,dtime)
            
    def _get_date_idx_(self,bidx,dparts,part,value):
        if part in self.grouping:
            idx = dparts[part] == value
        else:
            idx = bidx
        return(idx)
    
    def execute(self,coll):
        ## TODO: potential speed-up with vectorization
        
        ## hold calculated data
        if self.has_multi:
#            coll['attr'] = OrderedDict()
            ## put the mulivariate calculation presence in the output collection
            ## for reference by future iterators.
#            coll['has_multi'] = True
            coll.has_multi = True
        else:
#            coll['attr'] = OrderedDict.fromkeys(coll['value'].keys(),value={})
#            coll['has_multi'] = False
            coll.has_multi = False
            
        ## store array shapes
        coll._use_agg = self.use_agg
        shapes = coll._get_shape_dict_(len(self.dgroups),raw=self.raw)
#        shapes = {}
#        for var_name,value in coll.iter_values(agg=self.iter_agg):
#            import ipdb;ipdb.set_trace()
#            ## shape of the output calculation array
#            calc_shape = (len(self.dgroups),
#                          value['lid'].shape[0],
#                          coll['geom'].shape[0],
#                          coll['geom'].shape[1])
#            calc_mask = np.empty(calc_shape,dtype=bool)
#            calc_mask[:,:,:,:] = coll['geom_mask']
#            ## this is the shape for each temporally grouped calculation
#            out_shape = (1,
#                         value['lid'].shape[0],
#                         coll['geom'].shape[0],
#                         coll['geom'].shape[1])
#            ## set up the weights reshaping to account for levels
#            wshape = (value['lid'].shape[0],
#                      coll['weights'].shape[0],
#                      coll['weights'].shape[1])
#            fweights = np.ma.array(np.empty(wshape,dtype=float),
#                                   mask=np.zeros(wshape,
#                                                 dtype=bool))
#            fweights[:] = coll['weights']
#            fweights.mask[:] = coll['geom_mask']
#            shapes.update({var_name:{'calc_shape':calc_shape,
#                                     'calc_mask':calc_mask,
#                                     'out_shape':out_shape,
#                                     'fweights':fweights}})
        ## loop through functions and make calculations
        for ii,f in enumerate(self.funcs,start=1):
            ## for multivariate calculations, the structure is different and
            ## functions are not applied to individual variables.
            if self.has_multi:
                raise(NotImplementedError)
                archetype = coll.variables.keys()[0]
                ref = f['ref'](agg=self.agg,
                               raw=self.raw,
                               weights=shapes[archetype]['fweights'])
                calc = np.ma.array(np.empty(shapes[archetype]['calc_shape'],
                                       dtype=ref.dtype),
                                       mask=shapes[archetype]['calc_mask'])
                for grp_idx,grp in zip(range(len(self.dgroups)),self.dgroups):
                    ## for sample size, we just need the count from one variable.
                    if isinstance(ref,SampleSize):
                        dref = coll._get_value_(archetype)
                        data = dref[grp,:,:,:]
                        calc[grp_idx,:,:,:] = ref.calculate(
                                            data,shapes[archetype]['out_shape'])
                    else:
                        ## cv-controlled multivariate functions require collecting
                        ## data arrays before passing to function.
                        kwds = f['kwds'].copy()
                        for key in ref.keys:
                            dref = coll._get_value_(key)
                            data = dref[grp,:,:,:]
                            kwds.update({key:data})
                        calc[grp_idx,:,:,:] = ref.calculate(
                                                shapes[key]['out_shape'],**kwds)
                coll.calc_multi[f['name']] = calc
            else:
                for var_name,value in coll._iter_items_():
                    ref = f['ref'](agg=self.agg,
                                   raw=self.raw,
                                   weights=shapes[var_name]['fweights'])
                    calc = np.ma.array(np.empty(shapes[var_name]['calc_shape'],
                                                dtype=ref.dtype),
                                       mask=shapes[var_name]['calc_mask'])
                    for grp_idx,grp in zip(range(len(self.dgroups)),
                                           self.dgroups):
                        data = value[grp,:,:,:]
                        try:
                            calc[grp_idx,:,:,:] = ref.calculate(
                                                data,
                                                shapes[var_name]['out_shape'],
                                                **f['kwds'])
                        except:
                            import ipdb;ipdb.set_trace()
                    coll.variables[var_name].calc_value.\
                      update({f['name']:calc})
                    coll.variables[var_name].cid = np.append(
                                            coll.variables[var_name].cid,ii)
                    
#        coll['attr'] = attr
        return(coll)
    
#    def execute(self,coll):
#        ## TODO: potential speed-up with vectorization
#        ## hold calculated data
#        if self.has_multi:
#            coll['attr'] = OrderedDict()
#            ## put the mulivariate calculation presence in the output collection
#            ## for reference by future iterators.
#            coll['has_multi'] = True
#        else:
#            coll['attr'] = OrderedDict.fromkeys(coll['value'].keys(),value={})
#            coll['has_multi'] = False
#        ## shape of the output calculation array
#        calc_shape = (len(self.dgroups),
#                      coll['lid'].shape[0],
#                      coll['geom'].shape[0],
#                      coll['geom'].shape[1])
#        calc_mask = np.empty(calc_shape,dtype=bool)
#        calc_mask[:,:,:,:] = coll['geom_mask']
#        ## loop through functions and make calculations
#        for f in self.funcs:
#            ref = f['ref']()
#            calc = np.ma.array(np.empty(calc_shape,dtype=ref.dtype),
#                               mask=calc_mask)
#            ## arguments for iterator
#            iter_args = [zip(range(len(self.dgroups)),self.dgroups),
#                         iter_array(coll['gid']),
#                         range(coll['lid'].shape[0])]
#            ## for multivariate calculations, the structure is different and
#            ## functions are not applied to individual variables.
#            if self.has_multi:
#                for grp,gidx,lidx in itertools.product(*iter_args):
#                    ## for sample size, we just need the count from one variable.
#                    if isinstance(ref,SampleSize):
#                        key = coll[self.vkey].keys()[0]
#                        dref = coll[self.vkey][key]
#                        if not self.raw:
#                            data = (dref[grp[1],lidx,gidx[0],gidx[1]]).reshape(-1,1,1,1)
#                        else:
#                            data = (dref[grp[1],lidx,:,:]).reshape(-1,1,dref.shape[2],dref.shape[3])
#                        calc[grp[0]][lidx][gidx] = ref.calculate(data)
#                    else:
#                        ## cv-controlled multivariate functions require collecting
#                        ## data arrays before passing to function.
#                        kwds = f['kwds'].copy()
#                        for key in ref.keys:
#                            dref = coll[self.vkey][key]
#                            if not self.raw:
#                                data = (dref[grp[1],lidx,gidx[0],gidx[1]]).reshape(-1,1,1,1)
#                            else:
#                                data = (dref[grp[1],lidx,:,:]).reshape(-1,1,dref.shape[2],dref.shape[3])
#                            kwds.update({key:data})
#                        calc[grp[0]][lidx][gidx] = ref.calculate(**kwds)
#                coll['attr'][f['name']] = calc
#            else:
#                for var,value in coll[self.vkey].iteritems():
#                    for grp,gidx,lidx in itertools.product(*iter_args):
#                        if not self.raw:
#                            data = (value[grp[1],lidx,gidx[0],gidx[1]]).reshape(-1,1,1,1)
#                        else:
#                            data = (value[grp[1],lidx,:,:]).reshape(-1,1,value.shape[2],value.shape[3])
#                        calc[grp[0],lidx,gidx[0],gidx[1]] = ref.calculate(data,**f['kwds'])
#                    coll['attr'][var].update({f['name']:calc})
##        coll['attr'] = attr
#        return(coll)