import logging

def initLogger():
    # Configure logging to capture warnings
    logging.captureWarnings(True)
    # Configure the logging level to handle warnings
    
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
    # Log the warning
    return logging

def checkAliasMap(aliasMap: dict)->dict:               
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
                    'speed','speed3D','dist_last_meas','distance','freq_gnss',
                    'gnss_DOP','gnss_fix','FPS','frame_idx']    
    
    for key in default_keys:
        if not key in aliasMap.keys():
            aliasMap[key]=key
    
    return aliasMap