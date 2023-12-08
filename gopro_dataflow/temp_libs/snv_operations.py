import os

try:
    from data import LOGGER
except:
    import logging
    def initLogger():
        # Configure logging to capture warnings
        logging.captureWarnings(True)
        # Configure the logging level to handle warnings
        logging.basicConfig(level=logging.WARNING)
        # Log the warning
        return logging.getLogger("py.warnings")
    LOGGER = initLogger()
    
import shapefile
import func_timeout
import math
from shapely.geometry import Point, LineString
import numpy as np
import time

    

    
import pyproj
#from utils import exceptions
#from utils import directions, snv_surfaces
#from database.controllers.general_controller import GeneralController
#from database.controllers.settings_controller import SettingsController

import geopandas as gpd

class SnvOperations:
    """
        Encapsulates methods that involve SNV operations.
    """

    def __init__(self, bufferDistance = 15, shapeFilePath = ''):
        
        #dirpath = os.path.abspath(os.path.dirname(__file__))
        #self.path = lambda string: os.path.join(dirpath, string) 
        """ NOTE: este self.path só faz sentido no contexto do ICM,
          considerando que o cliente pode instalar a build em qualquer pasta..."""        
        self._shapefile = shapefile.Reader(shapeFilePath) #shapeFilePath ex: "shape/icm.shp"
        self._gdf = gpd.read_file(shapeFilePath, engine="pyogrio") #shapeFilePath ex: "shape/icm.shp"
        self._bufferDistance = bufferDistance/100000 #meters to decimal degree

    def getVideoDirection(self, km_i,km_f):
        """
            Calculate and return video direction
            1 - ASCENDING
            2 - DESCENDING
        """
        
        if km_i < km_f:
            return 1
        elif km_i == km_f:            
            LOGGER.warning("[WARN] exceptions.CorruptGPSData")            
        return 2

       
    def setIntersectionInPosition(self, position, intersection,km_fr):
        """
            Set intersection data in position
        """
        position["snv_code"] = intersection.record[1]
        position["highway"] = intersection.record[2]
        position["state"] = intersection.record[3]
        position["km"] = intersection.record[4]
        position["km_fr"] = km_fr
        position["km_i"] = intersection.record[5]
        position["km_f"] = intersection.record[6]
        position["snv_surface"] = self.castSnvSurface(intersection.record[7])
        position["snv_version"] =  self.snvVersion

    
    def getBuffer(self, lineString, distance, timeout=True):
        def doBuffer(lineString, distance):
            return lineString.buffer(distance)
        if timeout:
            try:
                return func_timeout.func_timeout(80, doBuffer, args=(lineString, distance))
            except func_timeout.FunctionTimedOut:
                LOGGER.warning("[WARN] exceptions.TimeoutWhileBufferingLineString")
        else:
            return doBuffer(lineString, distance)
    
  
    def getBuffer(self, lineString, distance):
        def doBuffer(lineString, distance):
            return lineString.buffer(distance)
        try:
            return func_timeout.func_timeout(80, doBuffer, args=(lineString, distance))
        except func_timeout.FunctionTimedOut:
            LOGGER.warning("[WARN] exceptions.TimeoutWhileBufferingLineString")
    
    def getFractionalKm(self,snv,point):
        """
            Get fractional quilometer based on point distance along snv linestring
            Method validated with dnit geo API https://servicos.dnit.gov.br/sgplan/apigeo/web/rotas/localizarkm

            snv: snv[closest] (shapefile)
            point: point to inference (shapely.Point)
        """
        km_i, km_f = snv.record[5],snv.record[6]
        snv_line = LineString(snv.shape.points)
        distance = snv_line.project(point,normalized=True)
        distance = (km_f-km_i)*distance

        return km_i+distance

    def getInitialAndFinalKM(self, videoPoints,lines, intersections):
        """
            Get the initial and final INT KMs            
        """        
        extremeties_points = [Point(videoPoints[0]),Point(videoPoints[-1])]
        kms = []
        for pt in extremeties_points:
            closest = np.argmin([line.distance(pt) for line in lines])
            kms.append(self.getFractionalKm(intersections[closest],pt))
        
        return tuple(kms)

    def exportToShp(self,geom,output='linestring'):
        gdr = gpd.GeoDataFrame({'feature': ['video'], 'geometry': geom}, crs='EPSG:4326')        
        gdr.to_file(self.path(f'shape/{output}.shp'))
    import geopandas as gpd  
    def highway2linestring(self, query:list=[],location:gpd.geodataframe=None):          
        if location is None:           
            return self._gdf[
                (self._gdf.STATE == query[0]) &
                (self._gdf.HIGHWAY == query[1]) &
                (self._gdf.CODE.str[3] == query[2])
            ]
        else:            
            result = gpd.sjoin(self._gdf,location, how='inner', predicate='intersects')
            result = result.drop(columns=['index_right'])  # Drop unnecessary columns       
            columns = result.columns.tolist()
            result.rename(columns={c:c.replace("_left","") for c in columns}, inplace=True)     
            return  result.reset_index(drop=True)  # Reset index
            
                    
    def mapFramesToSnv(self, distanceMap, highway, segment):
        """
            Maps video coordinates to SNV codes from shapefile.
        """

        videoPoints = [(float(p["longitude"]), float(p["latitude"])) for p in distanceMap]
        videoLine = LineString(videoPoints)
        
        if videoLine.length <= 0.0001: #em graus decimais, aproximadamente 10m
           LOGGER.warning("[WARN] GPSLowFrequency")
            
        
        videoLineBuffered = self.getBuffer(videoLine, self._bufferDistance) #em graus decimais       

        shp = self.highway2linestring(highway, segment)

        intersections = list(filter(
            lambda item: LineString(item.shape.points).intersects(videoLineBuffered),
            shp
        ))

        if len(intersections) == 0:
            LOGGER.warning("[WARN] DifferentStateOrHighway")

        lines = [LineString(item.shape.points) for item in intersections]

        km_initial, km_final = self.getInitialAndFinalKM(videoPoints,lines, intersections)
        video_direction = self.getVideoDirection(km_initial, km_final)
        
        for i in range(len(distanceMap)):
            point = Point(videoPoints[i])
            closest = 0 if len(intersections) == 1 else np.argmin([line.distance(point) for line in lines])
            km_fr = self.getFractionalKm(intersections[closest],point)
            self.setIntersectionInPosition(distanceMap[i], intersections[closest], km_fr) 

        return distanceMap, video_direction


# Depreceated methods
# def adjustKmIniAndFinal(self, distanceMap):
#     """
#         Adjusts the initial and final fractional KM.
#     """

#     km_i_trunc = distanceMap[0]["km"]
#     km_f_trunc = distanceMap[-1]["km"]
#     km_i_int = distanceMap[0]["km_i"]
#     km_f_int = distanceMap[-1]["km_f"]

#     for position in distanceMap:
#         if position["km_i"] == km_i_int:
#             position["km_i"] = km_i_trunc
#         if position["km_f"] == km_f_int:
#             position["km_f"] = km_f_trunc



# def _setIntersectionInPosition(self, position, intersection, distance, km_i, km_f):
#     """
#         Set intersection data in position
#     """
#     position["snv_code"] = intersection.record[1]
#     position["highway"] = intersection.record[2]
#     position["state"] = intersection.record[3]

#     if distance != 0:
#         position["km"] = round(float(intersection.record[4]) + (distance),2)
#     else:
#         position["km"] = intersection.record[4]
    
#     if km_i < km_f: # Ascending
#         position["km_i"] = math.trunc(position["km"])
#         position["km_f"] = math.trunc(position["km"]) + 1
#     else:           # Descending
#         position["km_i"] = math.trunc(position["km"]) + 1
#         position["km_f"] = math.trunc(position["km"])

#     position["snv_surface"] = self.castSnvSurface(intersection.record[7])
#     position["snv_version"] =  self.snvVersion
if __name__ == '__main__':
    snvop = SnvOperations(15, "./shape/icm.shp")
    line = snvop.highway2linestring("RO", "174", "B")