import csv
from ocgis.conv.base import OcgConverter
from csv import excel
from ocgis.util.shp_cabinet import ShpCabinet
import os
from ocgis import env
from collections import OrderedDict
import logging
from ocgis.util.logging_ocgis import ocgis_lh
import fiona
from shapely.geometry.geo import mapping


class OcgDialect(excel):
    lineterminator = '\n'


class CsvConverter(OcgConverter):
    _ext = 'csv'

    def _get_fileobject_(self,coll):
        f = open(self.path,'w')
        writer = csv.writer(f,dialect=OcgDialect)
        return(f,writer)
                    
    def _build_(self,f,coll):
        headers = [h.upper() for h in coll.headers]
        f[1].writerow(headers)
        
    def _write_coll_(self,f,coll):
        f,writer = f
        for geom,row in coll.get_iter():
            writer.writerow(row)
            
    def _finalize_(self,f):
        f[0].close()


class CsvPlusConverter(CsvConverter):
    _add_ugeom = True

    def _build_(self,f,coll):
        headers = [h.upper() for h in coll.headers]
        f[1].writerow(headers)
        self._ugid_gid_store = {}
    
    def _get_fileobject_(self,coll):
        '''
        :returns: (CSV file object,CSV writer object,Fiona shapefile object)
        '''
        ret = CsvConverter._get_fileobject_(self,coll)
        
        if not self.ops.aggregate:
            fiona_path = os.path.join(self._get_or_create_shp_folder_(),self.prefix+'_gid.shp')
            archetype_field = coll._archetype_field
            fiona_crs = archetype_field.spatial.crs.value
            fiona_schema = {'geometry':archetype_field.spatial.abstraction_geometry._geom_type,
                            'properties':OrderedDict([['DID','int'],['UGID','int'],['GID','int']])}
            fiona_object = fiona.open(fiona_path,'w',driver='ESRI Shapefile',crs=fiona_crs,schema=fiona_schema)
        else:
            ocgis_lh('creating a UGID-GID shapefile is not necessary for aggregated data. use UGID shapefile.',
                     'conv.csv+',
                     logging.WARN)
            fiona_object = None
        
        return(list(ret)+[fiona_object])
    
    def _write_coll_(self,f,coll):
        file_csv,file_writer,file_fiona = f
        rstore = self._ugid_gid_store
        is_aggregated = self.ops.aggregate
        for geom,row in coll.get_iter():
            file_writer.writerow(row)
            if not is_aggregated:
                did,gid,ugid = row[0],row[5],row[2]
                try:
                    if gid in rstore[did][ugid]:
                        continue
                    else:
                        raise(KeyError)
                except KeyError:
                    if did not in rstore:
                        rstore[did] = {}
                    if ugid not in rstore[did]:
                        rstore[did][ugid] = []
                    if gid not in rstore[did][ugid]:
                        rstore[did][ugid].append(gid)
                    feature = {'properties':{'GID':gid,'UGID':ugid,'DID':did},
                               'geometry':mapping(geom)}
                    file_fiona.write(feature)
            
    def _finalize_(self,f):
        for fobj in f:
            try:
                fobj.close()
            except:
                pass
    
    def _OLD_write_(self):
        gid_file = OrderedDict()
        build = True
        is_aggregated = self.ops.aggregate
        with open(self.path,'w') as f:
            ocgis_lh(msg='opened csv file: {0}'.format(self.path),level=logging.DEBUG,
                     logger='conv.csv+')
            writer = csv.writer(f,dialect=OcgDialect)
            for coll in self:
                ocgis_lh('writing collection','conv.csv+',level=logging.DEBUG)
                if build:
                    ocgis_lh('starting build','conv.csv+',level=logging.DEBUG)
                    headers = coll.get_headers(upper=True)
                    if env.WRITE_TO_REFERENCE_PROJECTION:
                        projection = env.REFERENCE_PROJECTION
                    else:
                        projection = coll._archetype.spatial.projection
                    writer.writerow(headers)
                    build = False
                    ocgis_lh(msg='build finished'.format(self.path),level=logging.DEBUG,
                     logger='conv.csv+')
                for geom,row,geom_ids in coll.get_iter(with_geometry_ids=True):
                    if not is_aggregated:
                        ugid = geom_ids['ugid']
                        did = geom_ids['did']
                        gid = geom_ids['gid']
                        if ugid not in gid_file:
                            gid_file[ugid] = OrderedDict()
                        if did not in gid_file[ugid]:
                            gid_file[ugid][did] = OrderedDict()
                        gid_file[ugid][did][gid] = geom
                    writer.writerow(row)
                ocgis_lh('finished writing collection','conv.csv+',level=logging.DEBUG)
        
        if is_aggregated is True:
            ocgis_lh('creating a UGID-GID shapefile is not necessary for aggregated data. use UGID shapefile.',
                     'conv.csv+',
                     logging.WARN)
        else:
            ocgis_lh('writing UGID-GID shapefile','conv.csv+',logging.DEBUG)
            sc = ShpCabinet()
            shp_dir = os.path.join(self.outdir,'shp')
            try:
                os.mkdir(shp_dir)
            ## catch if the directory exists
            except OSError:
                if os.path.exists(shp_dir):
                    pass
                else:
                    raise
            shp_path = os.path.join(shp_dir,self.prefix+'_gid.shp')
            
            def iter_gid_file():
                for ugid,did_gid in gid_file.iteritems():
                    for did,gid_geom in did_gid.iteritems():
                        for gid,geom in gid_geom.iteritems():
                            yield({'geom':geom,'DID':did,
                                   'UGID':ugid,'GID':gid})
            
            sc.write(iter_gid_file(),shp_path,sr=projection.sr)
