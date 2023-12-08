# **Welcome to gdflow**
GoPro DataFlow, fondly referred to as **gdflow**, is a Python library designed to extract frames and sensor information from GoPro MP4 videos. Moreover, this library validates potentially corrupted measurements and offers functions to address these issues.

## **Install**

Create env

```sh
$ conda create -n gdflow python=3.8
```

Install requirements with conda env activated

```sh
$(gdflow) pip install -r requirements.txt`
```

## **Running as lib**

Import like that and be happy :)

```python
from gopro_dataflow import gopro_dataflow as gdflow
```


## **Sample as lib**

```python
from gopro_dataflow import gopro_dataflow as gdflow
import geopandas as gpd

# Consider GNSS measurement as outlier if it is more than this distance apart from last measure in meters.
last_meas_limit = 10 
# Limit distance in meters, after GNSS interpolating, to aceptc GNSS failures along video. DOP limit influences on failures length.
dist_w0_gnss = 50 
# Buffer distance in meters, to perform filter_gnns_by
buffer = 40
# Line reference to perform gdflow.filter_gnns_by(method ='location')  
line = gpd.read_file("path/to/shapefile.shp", engine="pyogrio") #shapeFilePath ex: "shape/icm.shp"

videos = gdflow.listVideos("../example_folder/")    
    for v in videos:
        print(f"Processing {v['videoName']}")

        raw_data, raw_outliers = gdflow.raw_extract(v['path'],last_meas_limit)   
             
        raw_data, gnss_outliers = gdflow.filter_gnns_by(raw_data,method ='location',line=line)  

        outliers = gdflow.adjust_outliers(raw_outliers,gnss_outliers)     

        # interpolate data to use in other apps such as icm/935
        data = gdflow.interpDataBy(raw_data,'GNSS') 
        
        #The 'data' is ready for use on ICM/935 

        #verify gaps after removed imprecise gnss measure and return 
        # if video should be accept (True) or reject (False) based on 
        verified1 = gdflow.verifyGnssGaps(data,dist_w0_gnss)         
        #Verify if the video is of good quality based on a percentage threshold
        verified2,acc_percentage,_ = gdflow.verifyQualityPercentage(data,outliers,percentage_limit = 20)  

        #save data as csv if you need
        gdflow.data2csv(data, 
                 os.path.join(opt['output'],
                              f"{v['videoName']}.csv"))
        #save data and outliers as shapefile if you need
        gdflow.points2gdf(gdflow.data2Points(data),
                   data, 
                   os.path.join(opt['output'],
                              f"{v['videoName']}.shp"))
        
        gdflow.points2gdf(gdflow.data2Points(_outliers),
                   outliers, 
                   os.path.join(opt['output'],
                              f"out_{v['videoName']}.shp"))

```

