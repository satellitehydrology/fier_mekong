import os 
import shutil
import folium
import folium.plugins as plugins
import streamlit as st
import xarray as xr
from syn_sar import *
import numpy.ma as ma
import pandas as pd
import matplotlib.pyplot as plt
import datetime
from PIL import Image

# from osgeo import gdal

import rioxarray as rio
import geemap as gm
import geemap.foliumap as geemap
import ee

# Reset Output folder
dir = 'output'
if os.path.isdir(dir):
    for f in os.listdir(dir):
        os.remove(os.path.join(dir, f))
else:
    os.mkdir(dir)

def sheet_out(url):
    return url.replace("/edit#gid=", "/export?format=csv&gid=")

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

if 'AOI_str' not in st.session_state:
    st.session_state.AOI_str = 'LowerMekong'

@st.cache(ttl = 3600)
def get_wl(mode):
    if mode == "Hindcast":
        sheet_link = pd.read_csv('AOI/%s/wl_sheet_hindcast.txt'%(str(curr_region)), sep = '\t')
        hindcast_wl = {}
        for i in range(sheet_link.shape[0]):
            station = pd.read_csv(sheet_out(sheet_link.iloc[i,1]), index_col=0).reset_index(drop = True)
            station.iloc[:,0] = pd.to_datetime(station.iloc[:,0])
            hindcast_wl[sheet_link.iloc[i,0]] = station
        return hindcast_wl
    if mode == "Forecast":
        sheet_link = pd.read_csv('AOI/%s/wl_sheet.txt'%(str(curr_region)), sep = '\t')
        forecast_wl = {}
        for i in range(sheet_link.shape[0]):
            station = pd.read_csv(sheet_out(sheet_link.iloc[i,1]))
            station.iloc[:,0] = pd.to_datetime(station.iloc[:,0])
            forecast_wl[sheet_link.iloc[i,0]] = station
        return forecast_wl

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

flood_color = {0: (0.75, 0.75, 0.75, 0.05),
 1: (0, 0, 0.543, 0.7),
 }

# Page Configuration
st.set_page_config(layout="wide")
st.title("Forecasting Inundation Extents using REOF Analysis (FIER)-Mekong")

json_data = st.secrets["json_data"]
service_account = st.secrets["service_account"]
credentials = ee.ServiceAccountCredentials(service_account, key_data=json_data)
ee.Initialize(credentials)

row1_col1, row1_col2 = st.columns([2, 1])
# Set up Geemap
with row1_col1:
    m = geemap.Map(
    zoom=7,
    center=(12.02 , 104.81),
    tiles=None,
    basemap = None
    )
    basemaps['Google Terrain'].add_to(m)
    basemaps['Google Satellite Hybrid'].add_to(m)
    basemaps['Esri Ocean'].add_to(m)
    m.addLayerControl()

with row1_col2:
    curr_region = st.session_state.AOI_str
    st.header('Select Date')
    st.subheader('**AOI: %s**'%(curr_region))
    run_type = st.radio('**Run type**:', ('Hindcast', 'Forecast'))

    if run_type == 'Hindcast':
        with st.form("Run Hindcasted FIER"):
            sheet_link = pd.read_csv('AOI/%s/wl_sheet_hindcast.txt'%(str(curr_region)), sep = '\t')
            hindcast_wl = get_wl("Hindcast")

            test = hindcast_wl[sheet_link.iloc[1,0]]
            min_date = test.iloc[0,0]
            max_date = test.iloc[-1,0]
            date = st.date_input(
                 label = "Select Hindcasted Date: **:red[(2008-01-01 to %s)]**"%(str(max_date)[:10]),
                 value = datetime.date(2018, 10, 17),
                 min_value = min_date,
                 max_value = max_date,
                 )

            depth = st.checkbox('Flood Depth Estimation')
            submitted = st.form_submit_button("Submit")

            if submitted:
                hydrosite = pd.read_csv('AOI/%s/hydrosite.csv'%(str(curr_region)))
                water_level = {}
                for i in range(hydrosite.shape[0]):
                    site = hydrosite.loc[i,'ID']
                    df = hindcast_wl[site]
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
                with xr.open_dataset(image_folder +'/output.nc', engine="h5netcdf") as output:
                    bounds = [[output.lat.values.min(), output.lon.values.min()], [output.lat.values.max(), output.lon.values.max()]]
                    sar_image, z_score_image, water_map_image = output['Synthesized SAR Image'].values, output['Z-score Image'].values, output['Inundation Map'].values
                
                innudation_img = gm.netcdf_to_ee(image_folder +'/output.nc',  var_names = 'Inundation Map')
                innudation_img = innudation_img.clip(ee.Image('users/sondo/output_test').geometry())
                innudation_img = innudation_img.updateMask(innudation_img.gte(1));

                if depth:
                    #innudation_img = gm.netcdf_to_ee(image_folder +'/output.nc',  var_names = 'Inundation Map')
                    innudation_img = innudation_img.clip(ee.Image('users/sondo/output_test').geometry())
                    innudation_img = innudation_img.updateMask(innudation_img.gte(1));

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
                    m.add_legend(title = 'Flood Depth Estimation', labels=legend_keys_flood, colors=legend_colors_flood)

                    water_map_image[np.isnan(water_map_image)] = 0
                    folium.raster_layers.ImageOverlay(
                        image = water_map_image,
                        bounds = bounds,
                        name = 'Inundation Map_' + curr_region ,
                        colormap = lambda x: flood_color[x],
                        show = False
                    ).add_to(m)

                else:
                    water_map_image[np.isnan(water_map_image)] = 0
                    folium.raster_layers.ImageOverlay(
                        image = water_map_image,
                        bounds = bounds,
                        name = 'Inundation Map_' + curr_region ,
                        colormap = lambda x: flood_color[x],
                        show = True
                    ).add_to(m)

                # st.write('Region:\n', curr_region)
                # st.write('Date: \n', date)
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
            forecast_wl = get_wl("Forecast")

            test = forecast_wl[sheet_link.iloc[0,0]]
            min_date = test.iloc[0,0]
            max_date = test.iloc[-1,0]
            date = st.date_input(
                 "Select Forecasted Date: **:red[(%s to %s)]**"%(min_date.strftime("%Y/%m/%d"), max_date.strftime("%Y/%m/%d")),
                 value = min_date,
                 min_value = min_date,
                 max_value = max_date,
                 )
            depth = st.checkbox('Flood Depth Estimation')

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
                with xr.open_dataset(image_folder +'/output.nc', engine="h5netcdf") as output:
                    bounds = [[output.lat.values.min(), output.lon.values.min()], [output.lat.values.max(), output.lon.values.max()]]
                    sar_image, z_score_image, water_map_image = output['Synthesized SAR Image'].values, output['Z-score Image'].values, output['Inundation Map'].values

                innudation_img = gm.netcdf_to_ee(image_folder +'/output.nc',  var_names = 'Inundation Map')
                innudation_img = innudation_img.clip(ee.Image('users/sondo/output_test').geometry())
                innudation_img = innudation_img.updateMask(innudation_img.gte(1));

                if depth:
                    innudation_img = gm.netcdf_to_ee(image_folder +'/output.nc',  var_names = 'Inundation Map')
                    innudation_img = innudation_img.clip(ee.Image('users/sondo/output_test').geometry())
                    innudation_img = innudation_img.updateMask(innudation_img.gte(1));

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
                    m.add_legend(title = 'Flood Depth Estimation', labels=legend_keys_flood, colors=legend_colors_flood)

                    water_map_image[np.isnan(water_map_image)] = 0
                    folium.raster_layers.ImageOverlay(
                        image = water_map_image,
                        bounds = bounds,
                        name = 'Inundation Map_' + curr_region ,
                        colormap = lambda x: flood_color[x],
                        show = False
                    ).add_to(m)

                else:
                    water_map_image[np.isnan(water_map_image)] = 0
                    folium.raster_layers.ImageOverlay(
                        image = water_map_image,
                        bounds = bounds,
                        name = 'Inundation Map_' + curr_region ,
                        colormap = lambda x: flood_color[x],
                        show = True
                    ).add_to(m)

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
    url = "https://www.sciencedirect.com/science/article/pii/S0034425720301024?casa_token=kOYlVMMWkBUAAAAA:fiFM4l6BUzJ8xTCksYUe7X4CcojddbO8ybzOSMe36f2cFWEXDa_aFHaGeEFlN8SuPGnDy7Ir8w"
    url_2 = "https://www.sciencedirect.com/science/article/abs/pii/S1364815218306194"
    url_3 = "https://www.sciencedirect.com/science/article/abs/pii/S1364815223000294"
    url_4 = "https://ieeexplore.ieee.org/abstract/document/9242297?casa_token=N4ao38AI93gAAAAA:XpEdirsJfsPByzd3no7JLEcrYxXcBVKd3Eu7M65dtg0iLE3XF-zgw65J4mN26QOt-C62jl6zeg"

    st.caption("This app has been developed by Chi-Hung Chang  & Son Do at University of Houston with supports from NASA SERVIR and GEOGloWS.")
    st.caption("Kel Markert at SERVIR Coordination Office is also acknowledged for the development of this FIER-Mekong App.")
    st.caption("Reference: [Chang et al., 2019](%s), [Chang et al., 2020](%s), [Chang et al., 2023](%s), [Peter et al., 2020](%s)" %(url_2, url, url_3, url_4))
