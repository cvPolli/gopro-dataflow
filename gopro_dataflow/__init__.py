__version__ = "development"
#import os
#os.path.dirname(os.path.abspath(__file__))
#os.path.join(self._database_folder, os.pardir)

try:
    from gopro_dataflow.core import (verifyGnssGaps,
                                    raw_extract,                                 
                                    interpDataBy,
                                    data2Points,
                                    list_videos,                                    
                                    filter_gnss_by_precision,
                                    merge_raw_data,
                                    adjust_outliers,
                                    verifyQualityPercentage
                                    )

    from gopro_dataflow.utils.geometry import (geom2gdf,
                                            points2Linestring,
                                            points2gdf,
                                            get_epsg,
                                            gpd_buffer,
                                            gnss_data_to_gdf,
                                            gdf_to_gnss_data,
                                            cross_validation,
                                            data2gdf
                                    )
    from gopro_dataflow.utils.export import (data2csv)

    from gopro_dataflow.utils.map import(plot_gdfs_on_map,get_color,plot_data,FeatureLayer)

    from gopro_dataflow.utils.frames import (export_frame_at_distance)
    

except:

    from ..gopro_dataflow.core import (verifyGnssGaps,
                                    raw_extract,                                 
                                    interpDataBy,
                                    data2Points,
                                    list_videos,
                                    filter_gnss_by_precision,
                                    merge_raw_data,
                                    adjust_outliers,
                                    verifyQualityPercentage
                                    )

    from ..gopro_dataflow.utils.geometry import (geom2gdf,
                                            points2Linestring,
                                            points2gdf,
                                            get_epsg,
                                            gpd_buffer,
                                            gnss_data_to_gdf,
                                            gdf_to_gnss_data,
                                            cross_validation,
                                            data2gdf,

                                    )
    from ..gopro_dataflow.utils.export import (data2csv)

    from ..gopro_dataflow.utils.map import(plot_gdfs_on_map,get_color,plot_data,FeatureLayer)
    from ..gopro_dataflow.utils.frames import (export_frame_at_distance)
