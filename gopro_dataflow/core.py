# coding=utf-8

"""Lê e exporta para CVS os dados de GoPro contidos no stream GPMF de um container MP4.

Referências
-----------


* https://github.com/gopro/gpmf-parser
* https://github.com/gopro/gpmf-parser/issues/90#issuecomment-615874494
* https://github.com/gopro/gpmf-parser/issues/90#issuecomment-719787568
* https://github.com/gopro/gpmf-parser/issues/160
* https://sno.phy.queensu.ca/~phil/exiftool/TagNames/GoPro.html
* https://github.com/juanmcasillas/gopro2gpx
* https://github.com/stilldavid/gopro-utils

"""

# - *- coding: utf- 8 - *
#external libs
import sys
import os
import numpy as np
import struct
import datetime
from construct import GreedyRange
from geopy.distance import distance
from contextlib import contextmanager
import copy
import geopandas as gpd

# internal modules
try: 
    from .utils.gpmf import extract, parse    
    from .utils.exceptions import GnssGapExceedsLimit,QualityPercentageExceedsLimit
    from .utils.geometry import *
    from .utils.map import *
    from .utils.common import *
except:
    from utils.gpmf import extract, parse    
    from utils.exceptions import GnssGapExceedsLimit,QualityPercentageExceedsLimit
    from utils.geometry import *
    from utils.map import *
    from utils.common import *

#internal variables
_avgPayDur = 1.04 #avarage payload duration in seconds, acordding to https://github.com/gopro/gpmf-parser/issues/90#issuecomment-615874494

#TODO: transform _gpmfGnssDataKey into a lambda function based on hero model (HERO5,HERO6,...HERO11) 'GPS5' if model < '11' else 'GPS9
_gpmfGnssDataKey = 'GPS5'
_gpmfAccDataKey = 'ACCL'
_gpmfGyroDataKey = 'GYRO'

_sensorsMap = {'gnss':{},'acc':{},'gyr':{},'cam':{}}



LOGGER = initLogger()
#TODO: method relate to byte, stream or gpmf, reorganize later
def _tryUnpackByte(element): 
    try:
        if isinstance(element,bytes):
            try:
                _element = element.decode()
                return _element
            except:
                try:
                    number = struct.unpack('d', element) 
                    return number
                except:
                    return element
    except:
        return element
#TODO: method relate to byte, stream or gpmf, reorganize later        
def _gpmfDataAsKeyValueList(data):
    """Converte os dados GPMF crus em uma lista de tuplas (chave, valor), onde o valor pode ser ou um literal de tipo
    básico ou uma outra lista de tuplas chave-valor recursivamente.

    São usadas listas de tuplas com chave-valor em lugar de um dicionario, devido a que é comum existirem mais de um
    valor com a mesma chave, como é o caso dos sub-streams de dados de sensores, todos com dados diferente mas usando
    a mesma chave ``STRM``.
    """
    result = []
    elements = GreedyRange(parse.FOURCC).parse(data)
    for element in elements:
        if element.type == 0:  # elemento do tipo zero indica uma sub-lista
            elementValue = _gpmfDataAsKeyValueList(element.data)
        else:
            try:
                elementValue = parse.parse_value(element)
            except ValueError:
                elementValue = _tryUnpackByte(element.data)
        result.append((_tryUnpackByte(element.key), elementValue))
    return result
#TODO: method relate to byte, stream or gpmf, reorganize later
def _getFirstOrDefault(collection, default=None):
    """Função auxiliar que retona o primeiro elemento de uma coleção ou, caso a coleção esteja vazia, um valor
    default será retornado"""
    return next(iter(collection), default)
#TODO: method relate to byte, stream or gpmf, reorganize later
def _getValues(keyValuePairs, key):
    """Retorna todos os valores das tuplas com chave ``key``."""
    for (k, v) in keyValuePairs:
        if key == k:
            yield v
#TODO: method relate to byte, stream or gpmf, reorganize later
def _getValue(keyValuePairs, key):
    """Retorna o primeiro valor da tupla com chave ``key``."""
    return next(iter(_getValues(keyValuePairs, key)), None)
#TODO: method relate to byte, stream or gpmf, reorganize later
def _list_devices(gpmfData):
    """Enumera as tuplas (id, nome) dos dispositivos presentes nos dados GPMF."""
    for (k, v) in gpmfData:
        if k == 'DEVC':
            yield (_getValue(v, 'DVID'), _getValue(v, 'DVNM'))
#TODO: method relate to byte, stream or gpmf, reorganize later
def _getDeviceStreams(gpmfData, deviceId):
    """Enumera os sub-streams de dados de sensores contidos nos dados GPMF para o dispositivo ``deviceId``, retornando
    os dados do sensor como um dicionário."""
    for device_data in _getValues(gpmfData, 'DEVC'):
        if _getValue(device_data, 'DVID') == deviceId:
            for stream in _getValues(device_data, 'STRM'):
                yield {i: j for i, j in stream}  # converte os dados do sub-stream de lista de tuplas para um dicionário
#TODO: method relate to byte, stream or gpmf, reorganize later
def _getStreamData(stream, scaling):
    """Obtem os valores de um sub-stream de dados de sensor, aplicando scaling e fazendo a média dos mesmos, se for
    necessário."""
    data = np.array(stream)
    return data * scaling
#TODO: method relate to byte, stream or gpmf, reorganize later
def _getStreamByKey(streams,key):    
    for stream in streams:
        if not stream:
            continue                
        if key in stream.keys():
            return stream    
#TODO: move _findClosestTsmp() to time.py, but need to rewrite
def _findClosestTsmp(target_timestamp, timestamp_dict):    
    closest_timestamp = None
    min_time_difference = float('inf')

    for timestamp in timestamp_dict:
        time_difference = abs(timestamp - target_timestamp)
        if time_difference < min_time_difference:
            min_time_difference = time_difference
            closest_timestamp = timestamp
        else:
            # If time_difference starts to increase, break out of the loop
            break

    return closest_timestamp
#TODO: move _getStartTsmp() to time.py, but need to rewrite
def _getStartTsmp(payloads):
    for payload, timestamps in payloads:
            gpmfData = _gpmfDataAsKeyValueList(payload)
            firstDevice = _getFirstOrDefault(_list_devices(gpmfData))
            streams = list(_getDeviceStreams(gpmfData, firstDevice[0])) 
            gnssStream = _getStreamByKey(streams,'GPSF')
            #XXX gnssStream['GPSF'] is None
            if gnssStream is not None and gnssStream['GPSF'] > 0: #indicate that payload measures are fixed
                gnss_s_dt = gnssStream.get('GPSU', -1) - datetime.timedelta(seconds=timestamps[0] / 1000) 
                return datetime.datetime.timestamp(gnss_s_dt)
       
def _interpMeasByTsmp(strm,_tsmp, onlyIndex = False): 
    
    _tsmpMeas = {}    
    _meas = strm.get(strm['MEASK'])  

    if not _meas or len(_meas)==0:
        return _tsmpMeas
    _interval = _avgPayDur/len(_meas)

    for idx in range(len(_meas)):            
        _meaTsmp = _tsmp+(idx*_interval)            
        _tsmpMeas[_meaTsmp] = _meas[idx] if not onlyIndex else idx
    
    return _tsmpMeas

def _process_sensor(sensor_stream, sensor_type, tsmp):
    #TODO: Create a statement and handle the case when `_interpMeasByTsmp` is equal to {}.
    if not sensor_stream:
        return sensor_stream
    
    meas = _interpMeasByTsmp(sensor_stream, tsmp)
    freq = len(meas) / _avgPayDur

    if sensor_type == 'gnss':
        dop = sensor_stream['GPSP'] / 100
        fix = sensor_stream['GPSF'] > 0
        return {           
                tsmp: {
                    'lat': lat,
                    'lng': lng,
                    'alt': alt,
                    'speed2D': speed2D,
                    'speed3D': speed3D,
                    'DOP': dop,
                    'fix': fix,
                    'freq': freq,
                }
                for tsmp, (lat, lng, alt, speed2D, speed3D) in meas.items()           
                }
    elif sensor_type == 'acc':
        return {            
                tsmp: {
                    'z': z,
                    'x': x,
                    'y': y,
                    'freq': freq,
                }
                for tsmp, (z, x, y) in meas.items()           
                }
    elif sensor_type == 'gyr':
       common_data = {
        tsmp: {
            'z': z,
            'x': x,
            'y': y,
            'freq': freq,
        }
        for tsmp, (z, x, y) in meas.items()
        }    
       if 'TMPC' in sensor_stream:
            for tsmp in meas.keys():
                common_data[tsmp]['tempC'] = sensor_stream['TMPC']    
       return common_data

    elif sensor_type == 'cam':        
        return {           
                tsmp: {
                    'frameIdx': idx,
                    'FPS': freq,
                }
                for idx, (tsmp, item) in enumerate(meas.items())
                }                    
    else:
        return None

def _stream2Data(strm, _tsmp):
    sensor_data = {}
    sensor_data['gnss'] = _process_sensor(strm['gnss'], 'gnss', _tsmp)
    sensor_data['acc'] = _process_sensor(strm['acc'], 'acc', _tsmp)
    sensor_data['gyr'] = _process_sensor(strm['gyr'], 'gyr', _tsmp)
    sensor_data['cam'] = _process_sensor(strm['cam'], 'cam',  _tsmp)
    
    return sensor_data

def _createStream(payload):
    """_summary_
    consider that sensors are synced
    Args:
        payload (_type_): _description_        

    Returns:
        object: {'gnss(dict)': gnss informations and measures,
                'acc(dict)': acc informations and measures,
                'gyr(dict)': gyr informations and measures,
                'cam(dict)': cam informations and measures}                
    """
       
    strms = copy.deepcopy(_sensorsMap)

    #get gmpf
    gpmfData = _gpmfDataAsKeyValueList(payload)
    firstDevice = _getFirstOrDefault(_list_devices(gpmfData))
    raw_streams = list(_getDeviceStreams(gpmfData, firstDevice[0])) 
    
    #get streams    
    _gnss_stream = _getStreamByKey(raw_streams,_gpmfGnssDataKey)
    _acc_stream = _getStreamByKey(raw_streams,_gpmfAccDataKey)
    _gyr_stream = _getStreamByKey(raw_streams,_gpmfGyroDataKey)   
    
    #TODO: implement GPP9 if available (> hero10)
    #TODO: add more information, such as STNM and UNIT
 
    strms['gnss'] = {**_gnss_stream,'MEASK':'GPS5'} if _gnss_stream else {}
    strms['acc'] = {**_acc_stream,'MEASK':'GPS5'} if _acc_stream else {}
    strms['gyr'] = {**_gyr_stream,'MEASK':'GPS5'} if _gyr_stream else {}
    
    if _getStreamByKey(raw_streams,'CORI') is not None:
        _camStream = _getStreamByKey(raw_streams,'CORI')   
        strms['cam'] = {**_camStream,'MEASK':'CORI'} if _camStream else {}           
    else:
        _camStream = _getStreamByKey(raw_streams,'SHUT')
        strms['cam'] = {**_camStream,'MEASK':'SHUT'} if _camStream else {}           
       
    #rescalling measures
    for sensor in strms.keys():
        _strm = strms[sensor] 
        if not _strm:
            continue    
        _measures = _strm.get(_strm['MEASK'])
        if not _measures:
            continue
        _scal = 1.0 / np.array(_strm.get('SCAL', 1.0))
        for idx, m in enumerate(_measures):        
            strms[sensor][_strm['MEASK']][idx] = _getStreamData(m,_scal)       
  
    return strms

#TODO:move _disableWarnings() to general.py, but need to test idk if it works importing from another file
@contextmanager
def _disableWarnings():
    # Disable warnings temporarily
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")
    try:
        yield
    finally:
        # Enable warnings again when the block of code is done
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

#TODO: move _adjustFrameIdx() to frame.py, but need to rewrite to return value
def _adjustFrameIdx(last_idx, data_cam):
    if last_idx > 0:   
        for key, item in data_cam.items():
            item['frameIdx'] += last_idx   



def _getDirname(path):
    return os.path.dirname(path) if path.lower().endswith('mp4') else path


def _calculateDistanceMap(data,dist_limit): 
    _data = copy.deepcopy(data)
    _outliers = copy.deepcopy(data)
    _outliers['gnss'] = {}
    for idx, (key,item) in enumerate(data['gnss'].items()):
        if idx == 0:
            _data['gnss'][key]['dist_last_meas'] = 0.001 #default value for the first meas            
            lastPosition = (item['lat'],item['lng'])
        else:    
            curPosition = (item['lat'],item['lng'])
            dst = abs(distance(lastPosition,curPosition).meters)

            if dist_limit is None:
                _data['gnss'][key]['dist_last_meas'] = dst            
                lastPosition = curPosition
                continue

            if dst > dist_limit or dst == 0:
                msg = f"GNSS measure [{idx}] is null or has distance from the last position ({dst}m) greater than the specified limit ({dist_limit}m) and has been considered an outlier and removed."
                LOGGER.warning(msg)
                outlier_data = {**_data['gnss'].pop(key),'dop_filter': False, 'dist_filter': True}
                _outliers['gnss'][key] = outlier_data
                continue              

            _data['gnss'][key]['dist_last_meas'] = dst            
            lastPosition = curPosition

    return _data, _outliers
           


def _checkAliasMap(aliasMap: dict)->dict:               
    """
    This function checks if all keys were passed through the aliasMap. 
    If that doesn't happen, it fills that key with the default value.
    Args:
        aliasMap (dict): {'tsmp':'timestamp',
                        'datetime': 'data',
                        'latitude': 'lat',
                        'longitude': 'long',
                        'altitude': 'alt'} #only the keys you wish to include

    Returns:
        dict: aliasMap with all available keys
    """
    default_keys = ['tsmp','datetime','latitude','longitude','altitude',
                    'speed','speed2D','speed3D','dist_last_meas','distance','freq_gnss',
                    'gnss_DOP','gnss_fix','FPS','frame_idx', 'frame_time', 'frame_time_sec']    
    
    for key in default_keys:
        if not key in aliasMap.keys():
            aliasMap[key]=key
    
    return aliasMap

#external methods 
def filter_gnss_by_precision(data:dict, dop_limit:float=5):             
    outliers = copy.deepcopy(data)
    outliers['gnss'] = {}
    filter_data = copy.deepcopy(data)
    for tsmp, gnss_data in data['gnss'].items():
        # filter GNSS by DOP and FIX            
        if gnss_data['DOP'] > dop_limit or not gnss_data['fix']:
            # warning_message = (
            #     f"Timestamp[{tsmp}] has DOP ({gnss_data['DOP']}) greater than the specified limit ({dop_limit}). "
            #     if gnss_data['DOP'] > dop_limit else ""
            # ) + (
            #     f"\nTimestamp [{tsmp}] measure was not fixed. " if not gnss_data['fix'] else ""
            # )    
            LOGGER.warning(f"Timestamp[{tsmp}] | DOP ({gnss_data['DOP']}) | FIX: {gnss_data['fix']}")        

            
            outlier_data = {**filter_data['gnss'].pop(tsmp),'dop_filter': False, 'dist_filter': True}
            outliers['gnss'][tsmp] = outlier_data
            
    if len(outliers):
        LOGGER.warning(f"{len(outliers)} GNSS measurements have been removed!")
    return filter_data, outliers

# #TODO: create a docstring 
def verifyGnssGaps(data_interp,dist_limit, aliasMap = {},_raise=True):
    
    if len(data_interp)==0:
        return False
    aliasMap = checkAliasMap(aliasMap)
    aliasMap = checkAliasMap(aliasMap)
    verified = True
    for idx, data in enumerate(data_interp):      
        if idx == 0:
             lastPosition = (data[aliasMap['latitude']],data[aliasMap['longitude']])
             continue        
        curPosition = (data[aliasMap['latitude']],data[aliasMap['longitude']])
        dst = abs(distance(lastPosition,curPosition).meters)
        data_interp[idx]['dist_last_meas'] = dst
        if dst > dist_limit:
            if _raise:
                raise  GnssGapExceedsLimit(dst,dist_limit)                         
            print(f"data[{idx}] | GNSS gap ({dst} meters) exceeds distance without GNSS limit ({dist_limit} metrs)")
            verified = False        
        lastPosition = curPosition
    return verified

def raw_extract(video_path:str, last_meas_limit:float = 10)-> tuple:   
    """Extracts GNSS, Accelerometer, and Gyroscope data from the GPMF stream of an MP4 file and checks
       for the presence of outliers based on the distance between a GNSS measurement and its predecessor.

    Args:
        video_path (str): path/to/gopro_video.MP4
        last_meas_limit (float, optional): Distance used for outlier detection. Defaults to 10.

    Returns:
        tuple: A tuple containing raw_data and raw_outliers
    """
    try:
        data = copy.deepcopy(_sensorsMap)            
        with _disableWarnings():
            payloads, parser, x64 = extract.get_gpmf_payloads_from_file(video_path) #extract payloads using hachoir
                  
        
        start_tsmp = _getStartTsmp(payloads) #consider gnss clock    
        data['start_tsmp'] = start_tsmp        
        last_idx = 0 #frame idx counter

        for idx, (payload, _) in enumerate(payloads):
            
            #creates a strem object
            _tsmp = start_tsmp+(_avgPayDur*idx)
            _strm = _createStream(payload)                     
            
            #convert stream to data format
            _data = _stream2Data(_strm,_tsmp)                         
            
            #adjust frame index sequence accordirg last frame idx (from last payload) and automatically upadate data['cam']            
            _adjustFrameIdx(last_idx,_data['cam'])
            #update last_idx
            last_key, last_item = list(_data['cam'].items())[-1]
            last_idx = last_item['frameIdx']           

            data['gnss'].update(_data['gnss'])           
            data['acc'].update(_data['acc'])    
            data['gyr'].update(_data['gyr'])    
            data['cam'].update(_data['cam'])               

        return _calculateDistanceMap(data, last_meas_limit)

    except Exception as ex:
        raise ex
    
def get_tsmp_sec(tsmp_min, tsmp_sec_total):    
    """Return the parsed seconds of the actual video frame, considering the frame minute.

    Args:
        tsmp_min (int): tsmp_sec_total in minutes
        tsmp_sec_total (int): total seconds of the timestamp, related with the actual video frame

    Returns:
        tsmp_sec: the seconds related to the actual frame of the video. 
    """
    return f"{(tsmp_sec_total - (tsmp_min*60)):.2f}"
    
def interpDataBy(data:dict,sens_freq:str, imu:bool= False, aliasMap:dict = {})->list:
    """interpolate data according to sens_freq (currently is only 'GNSS' avaiable)

    Args:
        data (dict): data with sensors and frames
        sens_freq (str): Senor frequence name EX: 'GNSS' 
        imu (bool): Inertial measurement unit condition
        aliasMap (dixt): do not recomend it uses
    Returns:
        data_interp(list): [{'tsmp', 'lat', 'lng', 'speed', 'speed2D', 'speed3D', 'distance',...}] 
        
    """

    assert sens_freq == 'GNSS', f"""Error: '{sens_freq}' is not supported yet!
    Supported frequencies: GNSS
    Implemented to next version supported frequencies: CAM
    Frequency without version implementation deadline: IMU"""      
   
    aliasMap = _checkAliasMap(aliasMap)
    tsmp_sec = 0
    data_interp = []
    start_tsmp = data['start_tsmp']
    if sens_freq == 'GNSS':
        for idx, (tsmp, gnss_meas) in enumerate(data['gnss'].items()):            
            closest_cam = data['cam'][_findClosestTsmp(tsmp,data['cam'])]                                    
            acc_distance = gnss_meas['dist_last_meas'] if idx == 0 else acc_distance + gnss_meas['dist_last_meas']     

            tsmp_sec = tsmp - start_tsmp
            if tsmp_sec >= 60:
                tsmp_min = tsmp_sec // 60
                
                tsmp_sec_formated = get_tsmp_sec(tsmp_min, tsmp_sec)
                
                tsmp_f = f"{tsmp_min:.0f}m {tsmp_sec_formated}s"
            else:
                tsmp_f = f'{tsmp_sec:.2f}s'
                    
   
            
            _data ={aliasMap['tsmp']:tsmp,
                    aliasMap['datetime']: datetime.datetime.fromtimestamp(tsmp),
                    aliasMap['latitude']:gnss_meas['lat'],
                    aliasMap['longitude']:gnss_meas['lng'], 
                    aliasMap['altitude']:gnss_meas['alt'],
                    aliasMap['speed']:round(gnss_meas['speed2D']*3.6,2), 
                    aliasMap['speed2D']:gnss_meas['speed2D'], 
                    aliasMap['speed3D']:gnss_meas['speed3D'], 
                    aliasMap['dist_last_meas']:gnss_meas['dist_last_meas'],
                    aliasMap['distance']: acc_distance,
                    aliasMap['freq_gnss']: gnss_meas['freq'],
                    aliasMap['gnss_DOP']: gnss_meas['DOP'],
                    aliasMap['gnss_fix']: gnss_meas['fix'],
                    aliasMap['FPS']: closest_cam['FPS'],
                    aliasMap['frame_idx']: closest_cam['frameIdx'],
                    aliasMap['frame_time']: tsmp_f,
                    aliasMap['frame_time_sec']: round(tsmp_sec,2)}
           
            if imu:
                #TODO: get all window of IMU measures  consider opt imu-meas   
                #TODO: rewrite imu-instant mode (default), takes long time             
                #interpolate closest tsmp to get instant measure of imu
                closest_gyr = data['gyr'][_findClosestTsmp(tsmp,data['gyr'])]  

                _data['zGyr'] = closest_gyr['z'] 
                _data['xGyrX'] = closest_gyr['x']
                _data['yGyr'] = closest_gyr['y']
                _data['freq_gyr'] = closest_gyr['freq']
                _data['tempC'] = closest_gyr['tempC']
                
                closest_acc = data['acc'][_findClosestTsmp(tsmp,data['acc'])]                  
                _data['zAcc'] = closest_acc['z']                   
                _data['xAacc'] = closest_acc['x']                    
                _data['xAcc'] = closest_acc['y']
                _data['freq_acc'] = closest_acc['freq']
        
            data_interp.append(_data)  

    elif sens_freq == 'CAM':
    #TODO: transform GNSS to XYZ geodetic to interpolate at cam frquency
    #TODO: interpolate data at cam frequency 
        pass
    elif sens_freq == 'IMU':    
        pass
    
    return data_interp


#TODO: create a docstring and move this function to common.py
def list_videos(path):
    videos = []        
    if path.endswith('.MP4'): 
        videos.append({
            'path':path,
            'videoName':path.split('/')[-1].split('.')[0]
            })
        
    else:            
        files = os.listdir(path)
        for f in files:
            if f.endswith('.MP4'): 
                videos.append({
                    'path':os.path.join(path,f),
                    'videoName':f.split('.')[0]
                    })
    return videos

          
def filter_gnns_by(raw_data:dict,method:str,dop_limit:float=5,
                   line:gpd.GeoDataFrame=None,location:gpd.GeoDataFrame=None, buffer:float=40, output:str=None)->tuple:
    """Filter GNSS data based on specified method.

    This function filters GNSS data from a dictionary based on the chosen method.
    
    Args:
        raw_data (dict): A dictionary containing raw GNSS data.
        method (str): The method to use for filtering. Choose from "precision" or "location".
        dop_limit (float, optional): The Dilution of Precision (DOP) threshold used in precision-based filtering.
            Defaults to 5.
        line (gpd.GeoDataFrame, optional): Depreceated.
            Defaults to None.
        location (gpd.GeoDataFrame, optional): A GeoDataFrame representing a geographic location used in location-based filtering.
            Defaults to None.
        buffer (float, optional): The buffer distance (in meters) used in location-based filtering.
            Defaults to 40.

    Returns:
        tuple: A tuple containing the filtered GNSS data and any detected outliers.

    Raises:
        ValueError: If the 'method' argument is not one of the allowed choices.
    """
    LOGGER.warning("`filter_gnns_by()` wiil be deprecite, use `cross_validation()` instead!")
    if line is not None:
        location = line        
        LOGGER.warning("`line` wiil be deprecite, consider use `location` instead!")
    if location is None:
        raise ValueError("[ERROR] line == location == None")
        
        

    choices = ["precision", "location"]  # Allowed choices
    if method not in choices:
        buff_area = None
        raise ValueError(f"[ERROR]: `{method}` is not supported!")

    if method == choices[0]:
        raise ValueError(f"Temp Error: '{method}' is temporarily deactivated! Sorry for the inconvenience. :S")
        #TODO: adjust out_data as _filter_gnss_by_precision return
        filter_data, out_data = _filter_gnss_by_precision(raw_data, dop_limit)
    elif method == choices[1]:
        filter_data = copy.deepcopy(raw_data)
        out_data = copy.deepcopy(raw_data)
        filter_data['gnss'], out_data['gnss'], buff_area = cross_validation(filter_data['gnss'], 
                                                              location=location, 
                                                              buffer=buffer,
                                                              output=output)          
    return filter_data, out_data,buff_area

def merge_raw_data(raw_data_1: dict, raw_data_2: dict={}) -> dict:
    
    """
    Merge 2 raw data dictionaries into a single dictionary.

    Args:
        raw_data_1 (dict): A list containing individual raw data dictionaries.
        raw_data_2 (dict): A list containing individual raw data dictionaries.

    Returns:
        dict: A dictionary resulting from merging all raw data dictionaries in the input list.

    """
    if not len(raw_data_2):
        raw_data_1["gnss"] = dict(sorted(raw_data_1["gnss"].items()))
        return raw_data_1
    # Convert non-string keys to strings and merge dictionaries
    merged_gnss = {str(key): value for key, value in raw_data_1['gnss'].items()}
    merged_gnss.update({str(key): value for key, value in raw_data_2['gnss'].items()})
    merged_gnss = {float(key): value for key, value in merged_gnss.items()}
    merged_data = raw_data_1.copy()
    merged_data['gnss'] = dict(sorted(merged_gnss.items()))

    return merged_data

def adjust_outliers(gnss_out:dict,disord_out:dict={},method:str='GNSS')->dict:
    """Merge outliers a interpolate it to get a same format as data after interpDataBy()

    Args:
        disord_out (dict): outliers from raw_extract()
        gnss_out (dict): outliers from cross_validation()
        method (str, optional): method to interpDataBy(merged_outliers). Defaults to 'GNSS'.

    Returns:
        (list): [{'tsmp', 'lat', 'lng', 'speed','speed2D', 'speed3D', 'distance',...}] 
    """
    raw_outliers, _ = _calculateDistanceMap(merge_raw_data(gnss_out,disord_out),None)
    outliers = interpDataBy(raw_outliers, method) #GNSS

    return outliers

def verifyQualityPercentage(valid_data,out_data,bad_track_limit,_raise=False):
    """
    Verify that the percentage of outliers in relation to the data is greater than
    the limit specified in the parameter.

    Args:
        valid_data (dict): Is the total GNSS data intercepted
        out_data (dict): Is the outliers tracked by the rawExtract function
        bad_track_limit (float): Is the max acceptable percentage of bad tracks in the data.
        _raise (dict): Indicates that we want to raise a exception if the quality percentage exceeds the limit.
    Returns:
        (tuple): A tuple containing three values - isValidVideo (bool), quality_percentage (float), and limit (float).
        The value of 'limit' is complementary to 'bad_track_limit' (the sum of both limits is 100%).

    Example:
        ```python
        from gopro import data as gpdf
        raw_data, _outliers = gpdf.rawExtract(v['path'],opt)    
        data = interpDataBy(raw_data,opt) #GNSS              
        verifyQualityPercentage(valid_data,out_data,bad_track_limit = 20, _raise = False)  
           
        ```

        ```sh
            $ True, 81.11, 80.00
        ``` 
    """
    limit = 100-bad_track_limit        
    isValidVideo = True        
    #calculating the percentage of bad tracks of total tracks.
    quality_percentage = round(100 if len(out_data) == 0 else len(valid_data)/(len(valid_data)+len(out_data)) * 100, 2)

    if quality_percentage <= limit: 
        isValidVideo = False                   
        LOGGER.warning(f"This video was reproved the test with {quality_percentage}% of bad track, consider limit ({limit}%).")       
        if _raise:                        
            raise  QualityPercentageExceedsLimit(quality_percentage, limit)
    else:
        print(f"This video was aproved the test with {quality_percentage}% of good track, consider limit ({limit}%).")
    return isValidVideo, quality_percentage, limit

def parse_args():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('-v', '--video', help='path to video', required=True)
    opt = ap.add_argument_group('Optional arguments')

    opt.add_argument('-o','--output', help='path to destiny folder for the video', default=None)

    opt.add_argument('--imu', help='flag to export imu measures (default: False)', action="store_true", default=False)
    #TODO: add imu-meas as choices ['istant','window']
    opt.add_argument('--sens-freq', 
        help='Frequency of sensor measurements to output. Choose from: GNSS, CAM, IMU. (default: GNSS)',
        type=str, 
        choices=['GNSS', 'CAM', 'IMU'], 
        default='GNSS')

    opt.add_argument('--dop-limit', 
        help='Discard GNSS measurements with Dilution of Precision (DOP) greater than this limit. (default: 5)',
        type=float, 
        default=5)
    
    ap.add_argument('--out-perc-limit', 
        help='Limit bad tracks percentage, after GNSS interpolating. (default: 20)',
        type=float, 
        default=20)

    opt.add_argument('--last-meas-limit', 
        help='Consider GNSS measurement as outlier if it is more than this distance apart from last measure. (default: 10 meters)',
        type=float, 
        default=10)

    opt.add_argument('--dist-w0-gnss', 
        help='Limit distance in meters, after GNSS interpolating, to aceptc GNSS failures along video. DOP limit influences on failures length. (default: 50 meters)',
        type=float, 
        default=50)

    p_args = ap.parse_args()
    
    p_args.output = _getDirname(p_args.video) if p_args.output == None else p_args.output

    return {'video': p_args.video,            
            'opt': {'output' : p_args.output,
                    'imu': p_args.imu, 
                    'sens_freq': p_args.sens_freq,
                    'last_meas_limit':p_args.last_meas_limit, 
                    'dop_limit': p_args.dop_limit, 'dist_w0_gnss': p_args.dist_w0_gnss, 
                    'out_perc_limit': p_args.out_perc_limit}
                    }

if __name__ == '__main__':    
    import time 
    from temp_libs.snv_operations import SnvOperations
    import time 
    from temp_libs.snv_operations import SnvOperations

    args = parse_args()
    
    dop_limit = args['opt'].pop('dop_limit')
    last_meas_limit = args['opt'].pop('last_meas_limit')

    start_time = time.time()
    videos = list_videos(args.pop('video')) 
    opt =  args['opt']     

    buffer_dst = 40  
    by_location_dst = 10000 #10km

    snvop = SnvOperations(15, "./gopro_dataflow/data/shp/icm.shp")
    line = snvop.highway2linestring(query=["RJ","393","A"]) 
    #NOTE:creates a line string based on by_location_dst   
    line_loc = snvop.highway2linestring(location=gpd_buffer(line,by_location_dst))  

    #NOTE:If you want to view the result, export to shape by uncommenting the line below!
    #line_loc.to_file(os.path.join(opt['output'],f"by_location_{buffer_dst}m.shp"))
   
    for v in videos:
        print(f"Processing {v['videoName']}")       

        #returns raw_data and removed measures basead on last_meas_limit (disord_out)
        raw_data, disord_out = raw_extract(v['path'],last_meas_limit)              
        
        #NOTE: Old method `filter_gnns_by` still works and produces the same result, but it will be deprecated.
        #filter_data, cross_out, buff_area = filter_gnns_by(raw_data,method='location',location=line,buffer=buffer_dst)          
        filter_data, cross_out, buff_area = cross_validation(raw_data,line,buffer_dst)    

        filter_data2, true_cross_out, buff_area2 = cross_validation(cross_out,line_loc,buffer_dst)      

        #adjust_outliers is needed to plot_gdfs_on_map( )
        outliers = adjust_outliers(disord_out,cross_out, 'GNSS') 
        true_outliers = adjust_outliers(true_cross_out,{}, 'GNSS') 
        
        data = interpDataBy(filter_data, 'GNSS') #GNSS
        #TODO: ajust frame_time to data2
        data2 = interpDataBy(filter_data2, 'GNSS') #GNSS 
        
        # verifyQualityPercentage(data,outliers,20)
        
        # #verify gaps after removed corrupt gnss measures
        # verified = verifyGnssGaps(data,50, _raise = False)   

        map = plot_data(features=[FeatureLayer(gdf = data2gdf(data),
                                            feature_type = "point",
                                            legend = "Traj. aceita",
                                            lgd_keys = ["frame_idx","frame_time","speed"],
                                            color = get_color(0),
                                            z_index = 0),                                                                           
                                FeatureLayer(gdf = data2gdf(data2),
                                            feature_type = "point",
                                            legend = "Traj. em SNVs próximos",
                                            lgd_keys = ["frame_idx","frame_time","speed"],
                                            color = get_color(3),
                                            z_index = 1), 
                                FeatureLayer(gdf = data2gdf(true_outliers),
                                            feature_type = "point",
                                            legend = "Traj. recusada",
                                            lgd_keys = ["frame_idx","frame_time","speed"],
                                            color = get_color(1),
                                            z_index = 2),                                  
                                FeatureLayer(gdf = line_loc,
                                            feature_type = "line",
                                            legend = "SNVs próximos",
                                            lgd_keys = ['KM','CODE'],
                                            color = get_color(5),
                                            z_index = 4),   
                                FeatureLayer(gdf = line,
                                            feature_type = "line",
                                            legend = "SNV",
                                            lgd_keys = ['KM','CODE'],
                                            color = get_color(6),
                                            z_index = 3),                                 
                                FeatureLayer(gdf = buff_area,
                                            feature_type = "poly",
                                            legend = f"SNV with {buffer_dst}m of buffer",
                                            lgd_keys = ['KM','CODE'],
                                            color = get_color(6),
                                            z_index = 10),
                                FeatureLayer(gdf = buff_area2,
                                            feature_type = "poly",
                                            legend = f"SNV próximos buff",
                                            lgd_keys = ['KM','CODE'],
                                            color = get_color(5),
                                            z_index = 11)])           
                       
        #Save the map as an HTML file
        map.save(os.path.join(opt['output'],f"{v['videoName']}buff_{buffer_dst}m.html"))    
        # map.show_in_browser()

        # if verified:
        #     print(f"{v['videoName']} was processed successfully!")
        # else:
        #     print(f"{v['videoName']} was processed but not accepted!")
        #filter gnss data by location see utils.geometry.cross_validation()         

     
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Elapsed time: {elapsed_time} seconds")
