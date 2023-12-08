import folium 
from folium.plugins import MeasureControl
import os
import geopandas

try:
    from utils.geometry import *
except:
    from ..utils.geometry import *



def get_overall_bounds(gdfs):
    # Check if the list is not empty
    if not gdfs:
        raise ValueError("Input list of GeoDataFrames is empty.")

    # Initialize bounds with the total bounds of the first GeoDataFrame
    overall_bounds = gdfs[0].total_bounds if not gdfs[0].empty else gdfs[1].total_bounds
    

    # Iterate over the remaining GeoDataFrames
    for gdf in gdfs[1:]:
        # Calculate total bounds for the current GeoDataFrame
        bounds = gdf.total_bounds

        # Update overall bounds to include the current GeoDataFrame
        overall_bounds = (
            min(overall_bounds[0], bounds[0]),
            min(overall_bounds[1], bounds[1]),
            max(overall_bounds[2], bounds[2]),
            max(overall_bounds[3], bounds[3])
        )
    return overall_bounds
def _create_popup_msg(row,lgd_keys):
    msg = ""
    for key in lgd_keys:
        if key in row:
            msg += f"<b>{key}:</b> {row[key]} \n"
    return msg
def _add_circle_gdf(gdf,color,map,lgd_keys):
    # Add each GeoDataFrame geometry as a CircleMarker to the map
    epsg = get_epsg(gdf)
    for idx, row in gdf.iterrows():
        coordinates = [row['geometry'].y, row['geometry'].x]
        folium.CircleMarker(location=coordinates, 
                            radius=7,                             
                            color=color,                                
                            popup=_create_popup_msg(row,lgd_keys)
                            ).add_to(map)
        #folium.CircleMarker(location=coordinates, radius=7, color=color,  popup=_create_popup_msg(row,lgd_keys)).add_to(map)

def _add_line_gdf(gdf,color,map,lgd_keys):
    epsg = get_epsg(gdf)
    for index, row in gdf.iterrows():
        # Extract coordinates from LineString
        coordinates = [(lat, lon) for lon, lat in row['geometry'].coords]
        # Add PolyLine to the map
        folium.PolyLine(locations=coordinates, 
                        color=color,
                        dash_array='10',  # specify the dash pattern (5 pixels dash, 10 pixels gap)
                        #dash_offset='5',  # specify the pixel offset of the dash pattern
                        weight=3,
                        opacity=0.8,
                        popup=_create_popup_msg(row,lgd_keys)
                        ).add_to(map)

def _add_polygon_gdf(gdf,color,map,lgd_keys): 
    for _, row in gdf.iterrows():
        coordinates = [(point[1], point[0]) for point in row['geometry'].exterior.coords]
        folium.Polygon(locations=coordinates, 
                       color=color, 
                       fill=True, 
                       fill_color=get_color(10), 
                       fill_opacity=0.05,                       
                       popup=_create_popup_msg(row,lgd_keys)
                       ).add_to(map)



        
def get_color(input_value):

    # Predefined colors based on Strachnyi, K. (2022). ColorWise. O’Reilly Media, Inc. https://www.oreilly.com/library/view/colorwise/9781492097839/

    predcolors = [
        "#39fc8a",  #0 principal
        "#ff2424",  #1 complementar
        "#ff2600",  #2 complementar vibrante
        "#fff349",  #3 analoga a principal a esquerda 1
        "#38f1e8",  #4 analoga a principal a direita 1
        "#e0d040",  #5 analoga a principal a esquerda 2    
        "#40a0e0",  #6 analoga a principal a direita 2
        "#b5dae4",  #7 cor neutra (cinza com fundo azul)
        "#fa936b",  
        "#eb87be",  
        "#e6e6e6f3",#10 backgroud        
        "#0bfff3"   
    ]

    # Ensure input_value is positive
    input_value = abs(input_value)
    # Calculate index based on input_value
    index = input_value % len(predcolors)
    # Return the candy color corresponding to the index
    
    return predcolors[index]

def _add_legend_to_map(map,used_colors):
    

    # Generate a dynamic legend HTML
    legend_html = f'''
        <div style="position: fixed; 
                    padding: 10px;  /* Add padding here */ 
                    top: 50px; left: 50px; width: 250px; height: 300px; 
                    border: 2px solid white; z-index: 9999; font-size: 13px;
                    background-color:{get_color(10)}; opacity: 0.9">
        &nbsp; <h3><b>  Legenda  </b></h3> <br>
    '''
    used_colors.reverse()
    for color, category, f_type in used_colors:
        if f_type == 'point':
            legend_html += f' <svg height="15" width="15"><circle cx="7" cy="7" r="7" fill="{color}" ></circle></svg>'
        elif f_type == 'line':
            legend_html += f' <svg height="15" width="15"><rect width="15" height="3" fill="{color}" ></rect></svg>'
        elif f_type == 'poly':
            legend_html += f' <svg height="15" width="15"><rect width="15" height="15" fill="transparent" stroke="{color}" stroke-width="4"></rect></svg>'
        legend_html += f' <b>: &nbsp;{category}</b> <i>({f_type})</i><br>'

    legend_html += '</div>'

    # Add the legend as an HTML element to the map
    map.get_root().html.add_child(folium.Element(legend_html))


def plot_gdfs_on_map(gdfs:list,adt_gdf:list, output:str="map.html",legend:list=["valid","outliers"])->folium.Map:
    #TODO: remove default legend to prevent errors
    used_colors = []
    # Calculate the bounding box of the GeoDataFrame
    minx, miny, maxx, maxy = get_overall_bounds(gdfs)
 
    # Create a Folium map
    map = folium.Map()
    MeasureControl(primary_length_unit='meters').add_to(map)
   
    for gdf in adt_gdf:
        # Add GeoPandas data to the map
        folium.GeoJson(gdf).add_to(map)
        #_add_polygon_gdf(gdf,_get_candy_color(3),map,'KM')        

    for idx, gdf in enumerate(gdfs):
        color = get_color(idx)
        _add_circle_gdf(gdf, color, map, "frame")

        used_colors.append((color, legend[idx]))
        

    # Fit the map to the bounding box
    map.fit_bounds([(miny, minx), (maxy, maxx)])
    _add_legend_to_map(map,used_colors)
    # Save the map as an HTML file
    map.save(output)    
    # map.show_in_browser()
    
    return map


       
def init_map():    
    #NOTE: ref 
    # Create a Folium map
    map = folium.Map(tiles=None)
    MeasureControl(primary_length_unit='meters').add_to(map)    
    # TMS info
    tms_url = "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"
    tms_attribution = "Google Maps"
    # Add the Google Maps TMS to the map    
    folium.TileLayer(tiles='cartodbpositron',attr='Mapa Claro',name='Mapa Claro').add_to(map)
    folium.TileLayer(tiles= 'cartodbdark_matter',attr='Mapa Escuro',name='Mapa Escuro').add_to(map)   
    folium.TileLayer(tiles=tms_url, attr=tms_attribution, name=tms_attribution).add_to(map)    
    # add the layer control 
    folium.LayerControl().add_to(map)

    return map

def plot_data(features:list)->folium.Map:   
    
    used_colors = []
    map = init_map()
    points = []
    s_features = sorted(features, key=lambda x: x.z_index, reverse=True)
    for f in s_features: 
        if f.feature_type == 'poly':            
            _add_polygon_gdf(f.gdf, f.color, map,f.lgd_keys)
            used_colors.append((f.color, f.legend,'poly'))            
        elif f.feature_type == 'line':
            _add_line_gdf(f.gdf, f.color, map,f.lgd_keys)
            used_colors.append((f.color, f.legend,'line'))
        elif f.feature_type == 'point': 
            points.append(f.gdf)
            _add_circle_gdf(f.gdf, f.color, map,f.lgd_keys)
            used_colors.append((f.color, f.legend,'point'))
        
       
        else:
            raise ValueError(f"`feature_type: {f.feature_type}` is not avaiable!")
    
    # Calculate the bounding box of the GeoDataFrame
    minx, miny, maxx, maxy = get_overall_bounds(points)
    # Fit the map to the bounding box
    map.fit_bounds([(miny, minx), (maxy, maxx)])
    
    _add_legend_to_map(map,used_colors)
    #map.show_in_browser()

    return map

class FeatureLayer:
    """
    Creates a gdflow.FeatureLayer() required to plot_data()
    Args:
                         data (dict): _description_
                         feature_type (str): _description_
                         legend (str): _description_
                         lgd_keys (list): _description_
                         color (str): _description_

        
    """
    
    
    def __init__(self,
                 data: dict = None,                 
                 gdf:geopandas.geodataframe= None,
                 feature_type:str='point',
                 legend:str='',
                 lgd_keys:list=[None],
                 color:int=0,
                 z_index:int=0): 
                     
        self._feature_types = ["point", "line","poly"]   
        if feature_type not in self._feature_types:            
            raise ValueError(f"Error: '{feature_type}' is not supported! \n Avaiable types:{self._feature_types}")      
        self.data = data
        self.gdf = data2gdf(data) if gdf is None else gdf
        self.epsg = get_epsg(self.gdf)
        self.legend = legend
        self.lgd_keys = lgd_keys
        self.color = color
        self.feature_type = feature_type
        self.z_index = z_index




