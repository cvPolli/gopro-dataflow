import geopandas as gpd
import datetime

from geopy.distance import distance
from shapely.geometry import LineString, Point
import pyproj
import os
import copy
from .common import *

try:
    from ..temp_libs.snv_operations import SnvOperations
except:
    from temp_libs.snv_operations import SnvOperations

#TODO: rename this method to geom2shp
def geom2gdf(geom,output=None,data=None):
    #TODO: adjust geom2gdf() to export shp Z
    att = {}
    for item in data:
        for key, value in item.items():
            if isinstance(value,datetime.datetime):
                continue
            att.setdefault(key, []).append(int(value) if isinstance(value, bool) else value)
    att['geometry'] = geom
    gdf = gpd.GeoDataFrame(att, crs='EPSG:4326') 
    if output:
        gdf.to_file(output)
    return gdf

def points2Linestring(videoPoints,att,output):
    geom = LineString(videoPoints)
    geom2gdf(geom,output,att)       
    
def points2gdf(videoPoints,att,output=None):
    geom = [Point(p) for p in videoPoints]
    return geom2gdf(geom,output,att) 
    
def get_epsg(gdf):
    # Get the CRS information
    crs = gdf.crs
    # Extract the EPSG code from the CRS
    return int(pyproj.CRS(crs).to_epsg())

def data2gdf(data):
    return points2gdf(data2Points(data),data)

def gpd_buffer(gdf:gpd.geodataframe,distance:int,output:str = None)-> gpd.geodataframe:
    """
    Apply a buffer to a GeoDataFrame using Web Mercator projection.

    Args:
        gdf (geopandas.GeoDataFrame): The GeoDataFrame to which the buffer will be applied.
        distance (int): The buffer distance in meters.
        output (str, optional): The file path to save the resulting GeoDataFrame as a shapefile.

    Returns:
        geopandas.GeoDataFrame: A new GeoDataFrame with the buffer applied.  
   
    """
    
    _gdf = gdf.copy(deep=True)

    cur_epsg = get_epsg(_gdf)
    _gdf = _gdf.to_crs(3857) #reproject to webmercator
    _gdf['geometry'] = _gdf.geometry.buffer(distance) #apply distance in meters
    _gdf = _gdf.to_crs(cur_epsg) #back to origin epsg   
     
    if output is not None:
        _gdf.to_file( os.path.join(output,"gdf_buffer.shp"))       

    return _gdf

def gnss_data_to_gdf(data,key_name='tsmp'):
    geom = [Point(value['lng'], value['lat']) for value in data.values()]    
    att = {}
    
    for key, value in data.items():
        att.setdefault(key_name, []).append(int(key) if isinstance(key, bool) else key)
        for key1, value1 in value.items():
            if isinstance(value1,datetime.datetime):
                continue
            att.setdefault(key1, []).append(int(value1) if isinstance(value1, bool) else value1)
    att['geometry'] = geom
    
    return gpd.GeoDataFrame(att, crs='EPSG:4326') 

def gdf_to_gnss_data(gdf:gpd.GeoDataFrame)->dict:
    """_summary_

    Args:
        gdf (gpd.GeoDataFrame): _description_

    Returns:
        dict: _description_
    """
    gnss_data = {}
    available_columns = [col for col in gdf.columns if col not in ['tsmp']]
   
    _gdf = gdf.copy(deep=True)
    _gdf = _gdf.sort_values(by='tsmp')
        
    for index, row in _gdf.iterrows():        
        tsmp = row['tsmp']
        point_data = {col: row[col] for col in available_columns}
        point_data['lat'] = row['lat']
        point_data['lng'] = row['lng']
        
        gnss_data[tsmp] = point_data
    
    return gnss_data

#TODO: move this to utils\time.py
def get_current_datetime_formatted():
    current_datetime = datetime.datetime.now()
    formatted_datetime = current_datetime.strftime("%y%m%d_%H%M")
    return formatted_datetime

def cross_validation(data:dict,location:gpd.GeoDataFrame,buffer:float=40, output:str=None)->tuple: 
    """Filter GNSS data based on location and subsequently conduct cross-validation between the data and specific geographic locations.
    
    Args:
        data (dict): A dictionary containing raw GNSS data or a data interpoled by gdflow.interpDataBy()        
        location (gpd.GeoDataFrame): A GeoDataFrame representing a geographic location used in location-based filtering./
            
        buffer (float, optional): The 'buffer' distance (in meters) used in location-based filtering.
            Defaults to 40.
        output (str, optional): If 'output' is not None save cross_validation results at output dir

    Returns:
        Tuple[dict, dict, gpd.GeoDataFrame]: A tuple containing 3 GeoDataFrames. 
            The first dict contains valid geospatial data points clipped by the location buffer.
            The second dict contains outliers, which are geospatial data points outside the clipped area.
            The third **GeoDataFrame** contain the area (buffer result) used to perform clip.

    Notes:
    This function performs cross-validation by clipping geospatial data with a location_buffer (i.e. polygon) and identifying outliers.

    Example:
        valid_data, outliers = gdflow.crossValidation(raw_data, line, buffer=20, output="validation_results")
    """   
    
    
    if 'gnss' in data.keys():
        filter_data = copy.deepcopy(data)   
        out_data = copy.deepcopy(data)
        filter_data['gnss'], out_data['gnss'], buff_area = _cross_validation(filter_data['gnss'], 
                                                            location=location, 
                                                            buffer=buffer,
                                                            output=output)   
        
    else:
        filter_data, out_data,buff_area = _cross_validation(data, 
                                                            location=location, 
                                                            buffer=buffer,
                                                            output=output) 
        pass   
     
    return filter_data, out_data,buff_area

def _cross_validation(raw_gnss_data:dict,location:gpd.GeoDataFrame=None,buffer:int=40,output:str = None)-> tuple:
    #TODO: Consider alias_map in geometry functions that uses lat, lng, tsmp, etc

           
    #perform buffer
    location_buff = gpd_buffer(location,buffer)    

    gnss_gdf = gnss_data_to_gdf(raw_gnss_data)
        
    #perform clip
    valid_gnss = gnss_gdf.clip(location_buff) 

    #get outliers
    outliers = gpd.overlay(gnss_gdf, valid_gnss, how='difference')
    
    if output is not None:
        #TODO: create a method to export geodataframes to KML or KMZ file
        #TODO: dont export gdf if has no len, implement LOGGER.warning()

        now_str = get_current_datetime_formatted()
        gnss_gdf.to_file(os.path.join(output,f"{now_str}_all_gnss.shp"))
        #XXX this code bellow dosent works
        #gnss_gdf.to_file(os.path.join(output,f"{now_str}_all_gnss.kmz"), driver='KML')

        valid_gnss.to_file(os.path.join(output,f"{now_str}_valid_gnss.shp"))
        #XXX this code bellow dosent works
        #valid_gnss.to_file(os.path.join(output,f"{now_str}_valid_gnss.kmz"), driver='KML')

        outliers.to_file(os.path.join(output,f"{now_str}_gnss_outliers.shp"))
        #XXX this code bellow dosent works
        #outliers.to_file(os.path.join(output,f"{now_str}_gnss_outliers.kmz"), driver='KML')        

        location_buff.to_file(os.path.join(output,f"{now_str}_location_buffer.shp"))
        #XXX this code bellow dosent works
        #highway_gdf_buff.to_file(os.path.join(output,f"{now_str}_highway_buffer.kmz"), driver='KML')
    
    return gdf_to_gnss_data(valid_gnss),gdf_to_gnss_data(outliers),location_buff
 

def data2Points(data:dict, aliasMap:dict = {},z_value:bool=False)->list:
    """Convert data to points format

    Args:
        data (dict): data returned by interpDataBy
        aliasMap (dict, optional): _description_. Defaults to {}.
        z_value (bool, optional): If true creates a 3D point. Defaults to False.

    Returns:
        list: A list of tuple (lat,lng) or (lat,lng,alt)  
    """
    aliasMap = checkAliasMap(aliasMap)
    lng = aliasMap['longitude']
    lat = aliasMap['latitude']
    alt = aliasMap['altitude']
    points = []
    
    for d in data:
        if z_value:
            points.append((float(d[lng]), float(d[lat]), float(d[alt])))            
        else:
            points.append((float(d[lng]), float(d[lat])))
            
    return points