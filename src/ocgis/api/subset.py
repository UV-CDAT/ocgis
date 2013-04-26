import itertools
from multiprocessing import Pool
from ocgis.calc.engine import OcgCalculationEngine
from ocgis import env
from ocgis.interface.shp import ShpDataset
from ocgis.api.collection import RawCollection
from ocgis.exc import EmptyData, ExtentError, MaskedDataError
from ocgis.interface.projection import WGS84
from ocgis.util.spatial.wrap import Wrapper
from copy import deepcopy


class SubsetOperation(object):
    
    def __init__(self,ops,serial=True,nprocs=1,validate=True):
        self.ops = ops
        self.serial = serial
        self.nprocs = nprocs
        
        if validate:
            ops.dataset.validate()
        
#        ## construct OcgDataset objects
#        for request_dataset in env.ops.dataset:
#            import ipdb;ipdb.set_trace()
#            iface = request_dataset.interface.copy()
#            iface.update({'s_abstraction':self.ops.abstraction})
#            ods = OcgDataset(request_dataset,
#                             interface_overload=iface)
#            
#            request_dataset.ocg_dataset = ods
        
        ## move to operations ##################################################
        
        
#        ## determine if dimensions are equivalent.
#        mappers = [EqualSpatialDimensionMapper,EqualTemporalDimensionMapper,EqualLevelDimensionMapper]
#        for mapper in mappers:
#            mapper(self.ops.dataset)
#            
#        ## ensure they are all the same type of spatial interfaces. raise an error
#        ## otherwise.
#        types = [type(ods['ocg_dataset'].i.spatial) for ods in self.ops.dataset]
#        if all([t == SpatialInterfacePolygon for t in types]):
#            self.itype = SpatialInterfacePolygon
#        elif all([t == SpatialInterfacePoint for t in types]):
#            self.itype = SpatialInterfacePoint
#        else:
#            raise(ValueError('Input datasets must have same geometry types. Perhaps overload "s_abstraction"?'))
#        
#        ## ensure all data has the same projection
#        projections = [ods.ocg_dataset.i.spatial.projection.sr.ExportToProj4() for ods in self.ops.dataset]
#        projection_test = [projections[0] == ii for ii in projections]
#        if not all(projection_test):
#            raise(ValueError('Input datasets must share a common projection.'))
#        
        ## if the target dataset(s) has a different projection than WGS84, the
        ## selection geometries will need to be projected.
        if ops.geom is not None and not isinstance(ops.dataset[0].ds.spatial.projection,WGS84):
            ops.geom.project(ops.dataset[0].ds.spatial.projection)
#        if not self.ops._get_object_('geom').is_empty:
#            if self.ops.dataset[0].ocg_dataset.i.spatial.projection != self.ops.geom.ocgis.sr.ExportToProj4():
#                new_geom = self.ops.geom.ocgis.get_projected(self.ops.dataset[0].ocg_dataset.i.spatial.projection.sr)
#                self.ops.geom = new_geom

        ## create the calculation engine
        if self.ops.calc is None:
            self.cengine = None
        else:
            self.cengine = OcgCalculationEngine(self.ops.calc_grouping,
                                           self.ops.calc,
                                           raw=self.ops.calc_raw,
                                           agg=self.ops.aggregate)
            
        ## check for snippet request in the operations dictionary. if there is
        ## on, the time range should be set in the operations dictionary.
        if self.ops.snippet is True:
            for rd in self.ops.dataset:
                rd.level_range = [1,1]
                ods = rd.ds
                ref = ods.temporal
                if self.cengine is None or (self.cengine is not None and self.cengine.grouping is None):
                    rd.time_range = [ref.value[0],ref.value[0]]
                else:
                    ods.temporal.set_grouping(self.cengine.grouping)
                    tgdim = ods.temporal.group
                    times = ref.value[tgdim.dgroups[0]]
                    rd.time_range = [times.min(),times.max()]
        
    def __iter__(self):
        '''Return OcgCollection objects from the cache or directly from
        source data.
        
        yields
        
        OcgCollection'''
        
        ## simple iterator for serial operations
        if self.serial:
            it = itertools.imap(get_collection,self._iter_proc_args_())
        ## use a multiprocessing pool returning unordered geometries
        ## for the parallel case
        else:
            raise(NotImplementedError)
            pool = Pool(processes=self.nprocs)
            it = pool.imap_unordered(get_collection,
                                     self._iter_proc_args_())
        ## the iterator return from the Pool requires calling its 'next'
        ## method and catching the StopIteration exception
        while True:
            try:
                yld = it.next()
                yield(yld)
            except StopIteration:
                break
        
    def _iter_proc_args_(self):
        '''Generate arguments for the extraction function.
        
        yields
        
        SubsetOperation
        geom_dict :: dict
        '''
        
#        ## copy for the iterator to avoid pickling the cache
#        so_copy = copy.copy(self)
        if self.ops.geom is None:
            yield(self,None)
        elif isinstance(self.ops.geom,ShpDataset):
            for geom in self.ops.geom:
                yield(self,geom)
        else:
            yield(self,self.ops.geom)
            
def get_collection((so,geom)):
    '''Execute requested operations.
    
    so :: SubsetOperation
    geom_dict :: GeometryDataset'''
    
    ## using the OcgDataset objects built in the SubsetOperation constructor
    ## do the spatial and temporal subsetting.
    coll = RawCollection(ugeom=geom)
    ## perform the operations on each request dataset
    for request_dataset in so.ops.dataset:
        ## reference the dataset object
        ods = request_dataset.ds
        ## return a slice or do the other operations
        if so.ops.slice is not None:
            ods = ods.__getitem__(so.ops.slice)
        ## other subsetting operations
        else:
            ## if a geometry is passed and the target dataset is 360 longitude,
            ## unwrap the passed geometry to match the spatial domain of the target
            ## dataset.
            if geom is None:
                igeom = None
            else:
                if ods.spatial.is_360:
                    w = Wrapper(axis=ods.spatial.pm)
                    geom.spatial.geom[0] = w.unwrap(deepcopy(geom.spatial.geom[0]))
                igeom = geom.spatial.geom[0]
            ## perform the data subset
            try:
                ods = ods.get_subset(spatial_operation=so.ops.spatial_operation,
                                     polygon=igeom,
                                     temporal=request_dataset.time_range,
                                     level=request_dataset.level_range)
                if so.ops.aggregate:
                    try:
                        new_geom_id = geom.uid
                    except AttributeError:
                        new_geom_id = 1
                    ods.aggregate(new_geom_id=new_geom_id)
                if not env.OPTIMIZE_FOR_CALC:
                    if ods.spatial.is_360 and so.ops.output_format != 'nc' and so.ops.vector_wrap:
                        ods.spatial.vector.wrap()
                if not so.ops.file_only and ods.value.mask.all():
                    if so.ops.allow_empty:
                        pass
                    else:
                        raise(MaskedDataError)
            except EmptyData:
                if so.ops.allow_empty:
                    ods = None
                else:
                    raise(ExtentError(request_dataset))
        coll.variables.update({request_dataset.alias:ods})
        
    ## if there are calculations, do those now and return a new type of collection
    if so.cengine is not None:
        coll = so.cengine.execute(coll,file_only=so.ops.file_only)
        
    ## conversion of groups.
    if so.ops.output_grouping is not None:
        raise(NotImplementedError)
    else:
        return(coll)
