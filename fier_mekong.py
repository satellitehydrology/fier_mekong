import folium
import folium.plugins as plugins
import streamlit as st
from streamlit_folium import folium_static
import xarray as xr
from syn_sar import *
import numpy.ma as ma
import pandas as pd
import matplotlib.pyplot as plt
import datetime
from PIL import Image

from osgeo import gdal

import rioxarray as rio
import geemap as gm
import geemap.foliumap as geemap
import ee


def sheet_out(url):
    return url.replace("/edit#gid=", "/export?format=csv&gid=")

def colorize(data, cmap='viridis'):
    array = ma.masked_invalid(data)
    normed_data = (array - array.min()) / (array.max() - array.min())
    cm = plt.cm.get_cmap(cmap)
    return cm(array)

def generate_depth(flood):
    area = flood.geometry().bounds().buffer(1000).bounds()

    dem = ee.Image('users/sondo/merit_dem_cogeo').clip(area)
    projection = dem.projection()
    dem = dem.updateMask(dem.gte(0))

    jrc = ee.Image('JRC/GSW1_3/GlobalSurfaceWater').select('transition').clip(area)
    water_image = jrc

    flood_image = flood.multiply(0)
    flood_image = flood_image.reproject(projection)

    w = water_image.reproject(projection)
    waterFill = flood_image.mask().where(w.eq(1),1)
    flood_image = waterFill.updateMask(waterFill.eq(1)).multiply(0)

    kernel = ee.Kernel.fixed(3,3,[[1,1,1],[1,1,1],[1,1,1]])
    kernel_weighted = ee.Kernel.fixed(3,3,[[1,1,1],[1,0,1],[1,1,1]])
    median = dem.focal_median(kernel = kernel).reproject(projection)
    median_weighted = dem.focal_median(kernel = kernel_weighted).reproject(projection)
    diff = dem.subtract(median)
    mzscore = diff.multiply(0.6745).divide(diff.abs().focal_median(kernel = kernel).reproject(projection))
    fillDEM = dem.where(mzscore.gt(3.5),median_weighted)
    expand = flood_image.focal_max(kernel = ee.Kernel.square(radius =  projection.nominalScale(), units= 'meters',)).reproject(projection)
    demMask = fillDEM.updateMask(flood_image.mask().eq(0))
    boundary = demMask.add(expand)
    medianBoundary = boundary.focal_median(kernel = kernel).reproject(projection)
    medianWeightedBoundary = boundary.focal_median(kernel = kernel_weighted).reproject(projection)
    diffBoundary = boundary.subtract(medianBoundary)
    mzscoreBoundary = diffBoundary.multiply(0.6745).divide(diffBoundary.abs().focal_median(kernel = kernel).reproject(projection))
    fill = fillDEM.where(mzscoreBoundary.gt(3.5),medianWeightedBoundary)

    mod = fill.updateMask(flood_image.mask().eq(0))
    source = mod.mask()
    val = 10000
    push = 5000
    cost0 = ee.Image(val).where(source,0).cumulativeCost(source,push)
    cost1 = ee.Image(val).where(source,1).cumulativeCost(source,push)
    cost2 = mod.unmask(val).cumulativeCost(source,push)
    costFill = cost2.subtract(cost0).divide(cost1.subtract(cost0))
    costSurface = mod.unmask(0).add(costFill)

    boxcar = ee.Kernel.square(radius = 3, units = 'pixels', normalize = True);
    costDepth = costSurface.subtract(fill).rename('FwDET_GEE').convolve(boxcar)\
    .reproject(projection).updateMask(flood_image.eq(0))

    costDepthFilter = costDepth.where(costDepth.lt(0),0)
    costDepthFilter = costDepthFilter.updateMask(flood.mask())
    # costDepthFilter = costDepthFilter.updateMask(costDepthFilter.neq(0))

    return costDepthFilter

# Page Configuration
# st.set_page_config(layout="wide")

if 'AOI_str' not in st.session_state:
    st.session_state.AOI_str = None

basemaps = {
    'Google Maps': folium.TileLayer(
        tiles = 'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
        attr = 'Google',
        name = 'Google Maps',
    ),
    'Google Satellite': folium.TileLayer(
        tiles = 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        attr = 'Google',
        name = 'Google Satellite',
    ),
    'Google Terrain': folium.TileLayer(
        tiles = 'https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}',
        attr = 'Google',
        name = 'Google Terrain',
    ),
    'Google Satellite Hybrid': folium.TileLayer(
        tiles = 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
        attr = 'Google',
        name = 'Google Satellite Hybrid',
    ),
    'Esri Ocean': folium.TileLayer(
        tiles="https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Esri Ocean",
    ),
}

def app():
    
    # Title and Description
    st.title("Forecasting Inundation Extents using REOF Analysis (FIER)-Mekong")

    if 'AOI_str' not in st.session_state:
        st.session_state.AOI_str = None

    # Reset Output folder
    dir = 'output'
    for f in os.listdir(dir):
        os.remove(os.path.join(dir, f))

    row1_col1, row1_col2 = st.columns([2, 1])
    # Set up Geemap
    with row1_col1:
        if st.session_state.AOI_str == None:
            m = geemap.Map(
            zoom=5,
            center=(12.02 , 104.81),
            tiles=None,
            basemap = None
            )
            basemaps['Google Terrain'].add_to(m)
            basemaps['Google Satellite Hybrid'].add_to(m)
            # m.add_child(folium.LatLngPopup())
            m.addLayerControl()
        else:
            curr_region = st.session_state.AOI_str
            location = (12.23, 104.79) # NEED FIX!!!!!!!!!!!

            m = geemap.Map(
            zoom=7,
            center=(12.23, 104.79),
            tiles=None,
            basemap = None
            )
            basemaps['Google Terrain'].add_to(m)
            basemaps['Google Satellite Hybrid'].add_to(m)
            hydrosite = pd.read_csv('AOI/%s/hydrosite.csv'%(str(curr_region)))
            hydrosite = hydrosite.sort_values(by='Lat', ascending=False)
            for i in range(0,len(hydrosite)):
               folium.Marker(
                  location=[hydrosite.iloc[i]['Lat'], hydrosite.iloc[i]['Long']],
                  popup=hydrosite.iloc[i]['Name'],
               ).add_to(m)
            m.addLayerControl()

    with row1_col2:
        # Form
        st.subheader('Determine Region of Interest')
        with st.form('Select Region'):

            region = st.selectbox(
         'Determine region:',
         ('LowerMekong',),
         )


            submitted = st.form_submit_button("Submit")

            if submitted:
                st.session_state.AOI_str = region
                curr_region = st.session_state.AOI_str
                location = [12.23, 104.79] # NEED FIX!!!!!!!!!!!
                m = geemap.Map(
                zoom=7,
                center=(12.23, 104.79),
                tiles=None,
                basemap = None
                )
                basemaps['Google Terrain'].add_to(m)
                basemaps['Google Satellite Hybrid'].add_to(m)


                hydrosite = pd.read_csv('AOI/%s/hydrosite.csv'%(str(curr_region)))
                hydrosite = hydrosite.sort_values(by='Lat', ascending=False)
                st.write('Water Level Gauge')
                st.dataframe(hydrosite)

                for i in range(0,len(hydrosite)):
                   folium.Marker(
                      location=[hydrosite.iloc[i]['Lat'], hydrosite.iloc[i]['Long']],
                      popup=hydrosite.iloc[i]['Name'],
                   ).add_to(m)
                m.addLayerControl()

        if st.session_state.AOI_str != None:
            st.subheader('Select Date')
            st.markdown('**AOI: %s**'%(curr_region))
            run_type = st.radio('Run type:', ('Hindcast', 'Forecast'))
            depth = st.checkbox('Flood Depth Estimation')
            curr_region = st.session_state.AOI_str

            if run_type == 'Hindcast':
                with st.form("Run Hindcasted FIER"):
                    date = st.date_input(
                         "Select Hindcasted Date (2008-01-01 to 2019-12-31):",
                         value = datetime.date(2018, 10, 17),
                         min_value = datetime.date(2008, 1, 1),
                         max_value = datetime.date(2019, 12, 31),
                         )
                    submitted = st.form_submit_button("Submit")
                    if submitted:
                        hydrosite = pd.read_csv('AOI/%s/hydrosite.csv'%(str(curr_region)))
                        water_level = {}
                        for i in range(hydrosite.shape[0]):
                            site = hydrosite.loc[i,'ID']
                            df = pd.read_excel('AOI/%s/water_level/historical/500m/%s.xlsx'%(curr_region, site))
                            d = pd.Timestamp(date)
                            water_level[site] = round(df[df['time'] == d].water_level.values[0], 3)

                        location = [12.23, 104.79] # NEED FIX!!!!!!!!!!!
                        m = geemap.Map(
                        zoom=7,
                        center=(12.23, 104.79),
                        tiles=None,
                        basemap = None
                        )
                        basemaps['Esri Ocean'].add_to(m)
                        basemaps['Google Terrain'].add_to(m)
                        basemaps['Google Satellite Hybrid'].add_to(m)

                        image_folder = image_output(curr_region, water_level)
                        # with xr.open_dataset(image_folder +'/output.nc',) as output:
                            # bounds = [[output.lat.values.min(), output.lon.values.min()], [output.lat.values.max(), output.lon.values.max()]]
                            # sar_image, z_score_image, water_map_image = output['Synthesized SAR Image'].values, output['Z-score Image'].values, output['Inundation Map'].values

                        innudation_img = gm.netcdf_to_ee(image_folder +'/output.nc',  var_names = 'Inundation Map')
                        innudation_img = innudation_img .clip(ee.Image('users/sondo/output_test').geometry())
                        innudation_img = innudation_img.updateMask(innudation_img.gte(1));

                        flood_params = {'min': 0,'max': 1,'palette': ['red','#000072']}
                        m.addLayer(innudation_img, flood_params, name = 'Innudation Extent', shown = ~depth)
                        # m.centerObject(innudation_img)

                        if depth:
                            costDepthFilter = generate_depth(innudation_img)
                            gm.ee_export_image(costDepthFilter, 'output/flood_depth.tif', )
                            costDepthFilter_viz = costDepthFilter.where(costDepthFilter.eq(0), 0)\
                            .where(costDepthFilter.gt(0).And(costDepthFilter.lt(1)), 1)\
                            .where(costDepthFilter.gte(1).And(costDepthFilter.lt(3)), 2)\
                            .where(costDepthFilter.gte(3).And(costDepthFilter.lt(5)), 3)\
                            .where(costDepthFilter.gte(5), 4)

                            depth_params = {'min': 0,
                            'max': 4,
                            'palette': ['#FEF001','#FD9A01','#FD6104','#F00505','#542061']}

                            m.addLayer(costDepthFilter_viz, depth_params, name = "Flood Depth Estimation Using FwDet")
                            legend_keys_flood = ['0 meter (Estimated)','0 - 1 meter', '1 - 3 meters', '3 - 5 meters', '> 5 meters',]
                            legend_colors_flood = ['#FEF001','#FD9A01','#FD6104','#F00505','#542061']
                            m.add_legend(title = 'Flood Depth Estimation', labels=legend_keys_flood, colors=legend_colors_flood, control = True, layer_name = 'Flood Depth Estimation Using FwDet')

                        # m.addLayerControl()
                        st.write('Region:\n', curr_region)
                        st.write('Date: \n', date)
                try:
                    with open("output/output.tiff", 'rb') as f:
                        st.download_button('Download Latest Innudation Extent Output (.tiff)',
                        f,
                        file_name = "%s_%s.tiff"%(curr_region, date),
                        mime= "image/geotiff")
                except:
                    pass
                if depth:
                    try:
                        with open("output/output.tiff", 'rb') as f:
                            st.download_button('Download Latest Flood Depth Output (.tif)',
                            f,
                            file_name = "%s_%s.tif"%(curr_region, date),
                            mime= "image/geotiff")
                    except:
                        pass

            else:
                with st.form("Run Forecast FIER"):
                    sheet_link = pd.read_csv('AOI/%s/wl_sheet.txt'%(str(curr_region)), sep = '\t')
                    forecast_wl = {}
                    for i in range(sheet_link.shape[0]):
                        station = pd.read_csv(sheet_out(sheet_link.iloc[i,1]))
                        station.iloc[:,0] = pd.to_datetime(station.iloc[:,0])
                        forecast_wl[sheet_link.iloc[i,0]] = station

                    test = forecast_wl[sheet_link.iloc[0,0]]
                    min_date = test.iloc[0,0]
                    max_date = test.iloc[-1,0]

                    date = st.date_input(
                         "Select Forecasted Date (%s to %s):"%(min_date.strftime("%Y/%m/%d"), max_date.strftime("%Y/%m/%d")),
                         value = min_date,
                         min_value = min_date,
                         max_value = max_date,
                         )




                    submitted = st.form_submit_button("Submit")

                    if submitted:

                        hydrosite = pd.read_csv('AOI/%s/hydrosite.csv'%(str(curr_region)))
                        water_level = {}
                        for i in range(hydrosite.shape[0]):
                            site = hydrosite.loc[i,'ID']
                            df = forecast_wl[site]
                            d = pd.Timestamp(date)
                            water_level[site] = round(df[df['time'] == d].water_level.values[0], 3)

                        location = [12.23, 104.79] # NEED FIX!!!!!!!!!!!
                        m = geemap.Map(
                        zoom=7,
                        center=(12.23, 104.79),
                        tiles=None,
                        basemap = None
                        )
                        basemaps['Esri Ocean'].add_to(m)
                        basemaps['Google Terrain'].add_to(m)
                        basemaps['Google Satellite Hybrid'].add_to(m)

                        image_folder = image_output(curr_region, water_level)
                        # with xr.open_dataset(image_folder +'/output.nc',) as output:
                            # bounds = [[output.lat.values.min(), output.lon.values.min()], [output.lat.values.max(), output.lon.values.max()]]
                            # sar_image, z_score_image, water_map_image = output['Synthesized SAR Image'].values, output['Z-score Image'].values, output['Inundation Map'].values

                        innudation_img = gm.netcdf_to_ee(image_folder +'/output.nc',  var_names = 'Inundation Map')
                        innudation_img = innudation_img .clip(ee.Image('users/sondo/output_test').geometry())
                        innudation_img = innudation_img.updateMask(innudation_img.gte(1));

                        flood_params = {'min': 0,'max': 1,'palette': ['red','#000072']}
                        m.addLayer(innudation_img, flood_params, name = 'Innudation Extent')
                        # m.centerObject(innudation_img)

                        if depth:
                            costDepthFilter = generate_depth(innudation_img)
                            gm.ee_export_image(costDepthFilter, 'output/flood_depth.tif', )
                            costDepthFilter_viz = costDepthFilter.where(costDepthFilter.eq(0), 0)\
                            .where(costDepthFilter.gt(0).And(costDepthFilter.lt(1)), 1)\
                            .where(costDepthFilter.gte(1).And(costDepthFilter.lt(3)), 2)\
                            .where(costDepthFilter.gte(3).And(costDepthFilter.lt(5)), 3)\
                            .where(costDepthFilter.gte(5), 4)

                            depth_params = {'min': 0,
                            'max': 4,
                            'palette': ['#FEF001','#FD9A01','#FD6104','#F00505','#542061']}

                            m.addLayer(costDepthFilter_viz, depth_params, name = "Flood Depth Estimation Using FwDet")
                            legend_keys_flood = ['0 meter (Estimated)','0 - 1 meter', '1 - 3 meters', '3 - 5 meters', '> 5 meters',]
                            legend_colors_flood = ['#FEF001','#FD9A01','#FD6104','#F00505','#542061']
                            m.add_legend(title = 'Flood Depth Estimation', labels=legend_keys_flood, colors=legend_colors_flood, control = True, layer_name = 'Flood Depth Estimation Using FwDet')

                        # m.addLayerControl()
                        st.write('Region:\n', curr_region)
                        st.write('Date: \n', date)
                try:
                    with open("output/output.tiff", 'rb') as f:
                        st.download_button('Download Latest Innudation Extent Output (.tiff)',
                        f,
                        file_name = "%s_%s.tiff"%(curr_region, date),
                        mime= "image/geotiff")
                except:
                    pass
                if depth:
                    try:
                        with open("output/output.tiff", 'rb') as f:
                            st.download_button('Download Latest Flood Depth Output (.tif)',
                            f,
                            file_name = "%s_%s.tif"%(curr_region, date),
                            mime= "image/geotiff")
                    except:
                        pass

        first = Image.open("logo/first.PNG")
        second = Image.open("logo/second_row.PNG")
        st.image([first], width=450,)
        st.image([second], width=350,)


    with row1_col1:
        m.to_streamlit(height = 700, scrolling = True)
        # folium_static(m, height = 600, width = 900)
        st.write('Disclaimer: This is a test version of FIER method for Mekong Region')
        url = "https://www.sciencedirect.com/science/article/pii/S0034425720301024?casa_token=kOYlVMMWkBUAAAAA:fiFM4l6BUzJ8xTCksYUe7X4CcojddbO8ybzOSMe36f2cFWEXDa_aFHaGeEFlN8SuPGnDy7Ir8w"
        st.write("Reference: [Chang, C. H., Lee, H., Kim, D., Hwang, E., Hossain, F., Chishtie, F., ... & Basnayake, S. (2020). Hindcast and forecast of daily inundation extents using satellite SAR and altimetry data with rotated empirical orthogonal function analysis: Case study in Tonle Sap Lake Floodplain. Remote Sensing of Environment, 241, 111732.](%s)" % url)
        url_2 = "https://www.sciencedirect.com/science/article/abs/pii/S1364815218306194"
        st.write("[Chang, C. H., Lee, H., Hossain, F., Basnayake, S., Jayasinghe, S., Chishtie, F., ... & Du Bui, D. (2019). A model-aided satellite-altimetry-based flood forecasting system for the Mekong River. Environmental modelling & software, 112, 112-127.](%s)" % url_2)
        url_3 = "https://ieeexplore.ieee.org/abstract/document/9242297?casa_token=N4ao38AI93gAAAAA:XpEdirsJfsPByzd3no7JLEcrYxXcBVKd3Eu7M65dtg0iLE3XF-zgw65J4mN26QOt-C62jl6zeg"
        st.write("[Peter, B. G., Cohen, S., Lucey, R., Munasinghe, D., Raney, A., & Brakenridge, G. R. (2020). Google Earth Engine Implementation of the Floodwater Depth Estimation Tool (FwDET-GEE) for rapid and large scale flood analysis. IEEE Geoscience and Remote Sensing Letters.](%s)" % url_3)
        st.write("This app has been developed by Chi-Hung Chang  & Son Do at University of Houston with supports from NASA SERVIR and GEOGloWS.")
        st.write("Kel Markert at SERVIR Coordination Office is also acknowledged for the development of this FIER-Mekong App.")
