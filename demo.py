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
# from osgeo import gdal
import rioxarray as rio

def sheet_out(url):
    return url.replace("/edit#gid=", "/export?format=csv&gid=")

def colorize(data, cmap='viridis'):
    array = ma.masked_invalid(data)
    normed_data = (array - array.min()) / (array.max() - array.min())
    cm = plt.cm.get_cmap(cmap)
    return cm(array)

# Page Configuration
st.set_page_config(layout="wide")

# Title and Description
st.title("Forecasting Inundation Extents using REOF Analysis (FIER)-Mekong")


row1_col1, row1_col2 = st.columns([2, 1])
# Set up Geemap
with row1_col1:
    m = folium.Map(
        zoom_start=5,
        location =(12.02 , 104.81),
        control_scale=True,
    )
    plugins.Fullscreen(position='topright').add_to(m)
    folium.TileLayer('Stamen Terrain').add_to(m)
    m.add_child(folium.LatLngPopup())
    folium.LayerControl().add_to(m)




with row1_col2:
    # Form
    st.subheader('Determine Region of Interest')
    with st.form('Select Region'):

        region = st.selectbox(
     'Determine region:',
     ('LowerMekong','New Region' ),
     )


        submitted = st.form_submit_button("Submit")

        if submitted:
            try:
                location = [12.23, 104.79] # NEED FIX!!!!!!!!!!!
                m = folium.Map(
                    zoom_start = 7,
                    location = location,
                    control_scale=True,
                )
                plugins.Fullscreen(position='topright').add_to(m)
                folium.TileLayer('Stamen Terrain').add_to(m)
                m.add_child(folium.LatLngPopup())
                folium.LayerControl().add_to(m)

                folium.LayerControl().add_to(m)

                hydrosite = pd.read_csv('AOI/%s/hydrosite.csv'%(str(region)))
                hydrosite = hydrosite.sort_values(by='Lat', ascending=False)
                st.write('Water Level Gauge')
                st.dataframe(hydrosite)

                for i in range(0,len(hydrosite)):
                   folium.Marker(
                      location=[hydrosite.iloc[i]['Lat'], hydrosite.iloc[i]['Long']],
                      popup=hydrosite.iloc[i]['Name'],
                   ).add_to(m)

            except:
                st.write('Region not ready')

    st.subheader('Select Date')
    run_type = st.radio('Run type:', ('Hindcast', 'Forecast'))
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
                hydrosite = pd.read_csv('AOI/%s/hydrosite.csv'%(str(region)))
                water_level = {}
                for i in range(hydrosite.shape[0]):
                    site = hydrosite.loc[i,'ID']
                    df = pd.read_excel('AOI/%s/water_level/historical/500m/%s.xlsx'%(region, site))
                    d = pd.Timestamp(date)
                    water_level[site] = round(df[df['time'] == d].water_level.values[0], 3)


                location = [12.23, 104.79] # NEED FIX!!!!!!!!!!!
                m = folium.Map(
                    zoom_start = 7,
                    location = location,
                    control_scale=True,
                )

                image_folder = image_output(region, water_level)
                with xr.open_dataset(image_folder +'/output.nc',) as output:
                    bounds = [[output.lat.values.min(), output.lon.values.min()], [output.lat.values.max(), output.lon.values.max()]]
                    sar_image, z_score_image, water_map_image = output['Synthesized SAR Image'].values, output['Z-score Image'].values, output['Inundation Map'].values

                water_cmap =  matplotlib.colors.ListedColormap(["silver","darkblue"])
                water_map_image =  colorize(water_map_image, water_cmap)

                folium.raster_layers.ImageOverlay(
                    image= image_folder +'/syn_sar.png',
                    # image = sar_image,
                    bounds = bounds,
                    opacity = 0.5,
                    name = 'Synthesized Sar Image_' + region,
                    show = False,
                ).add_to(m)

                # Add Z_SCORE
                folium.raster_layers.ImageOverlay(
                    image= image_folder +'/z_score.png',
                    # image = z_score_image,
                    bounds = bounds,
                    opacity = 0.5,
                    name = 'Z-score Image_' + region ,
                    show = False
                ).add_to(m)

                # Add Inundation
                folium.raster_layers.ImageOverlay(
                    # image= image_folder +'/water_map.png',
                    image = water_map_image,
                    bounds = bounds,
                    opacity = 0.5,
                    name = 'Inundation Map_' + region ,
                    show = True
                ).add_to(m)

                plugins.Fullscreen(position='topright').add_to(m)
                folium.TileLayer('Stamen Terrain').add_to(m)
                m.add_child(folium.LatLngPopup())
                folium.LayerControl().add_to(m)
                st.write('Region:\n', region)
                st.write('Date: \n', date)

        try:
            nc_file = xr.open_dataset('output/output.nc')
            innudation_map = nc_file['Inundation Map']
            innudation_map = innudation_map.rio.set_spatial_dims('lon', 'lat')
            innudation_map.rio.set_crs("epsg:4326")
            innudation_map.rio.to_raster("output/output.tiff")
            nc_file.close()

            with open("output/output.tiff", 'rb') as f:
                st.download_button('Download Latest Run Output (.tiff)',
                f,
                file_name = "output.tiff",
                mime= "image/geotiff")


        except:
            pass

    else:
        with st.form("Run Forecast FIER"):
            sheet_link = pd.read_csv('AOI/%s/wl_sheet.txt'%(str(region)), sep = '\t')
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

                hydrosite = pd.read_csv('AOI/%s/hydrosite.csv'%(str(region)))
                water_level = {}
                for i in range(hydrosite.shape[0]):
                    site = hydrosite.loc[i,'ID']
                    df = forecast_wl[site]
                    d = pd.Timestamp(date)
                    water_level[site] = round(df[df['time'] == d].water_level.values[0], 3)

                location = [12.23, 104.79] # NEED FIX!!!!!!!!!!!
                m = folium.Map(
                    zoom_start = 7,
                    location = location,
                    control_scale=True,
                )

                image_folder = image_output(region, water_level)
                with xr.open_dataset(image_folder +'/output.nc',) as output:
                    bounds = [[output.lat.values.min(), output.lon.values.min()], [output.lat.values.max(), output.lon.values.max()]]
                    sar_image, z_score_image, water_map_image = output['Synthesized SAR Image'].values, output['Z-score Image'].values, output['Inundation Map'].values

                water_cmap =  matplotlib.colors.ListedColormap(["silver","darkblue"])
                water_map_image =  colorize(water_map_image, water_cmap)

                folium.raster_layers.ImageOverlay(
                    image= image_folder +'/syn_sar.png',
                    # image = sar_image,
                    bounds = bounds,
                    opacity = 0.5,
                    name = 'Synthesized Sar Image_' + region,
                    show = False,
                ).add_to(m)

                # Add Z_SCORE
                folium.raster_layers.ImageOverlay(
                    image= image_folder +'/z_score.png',
                    # image = z_score_image,
                    bounds = bounds,
                    opacity = 0.5,
                    name = 'Z-score Image_' + region ,
                    show = False
                ).add_to(m)

                # Add Inundation
                folium.raster_layers.ImageOverlay(
                    # image= image_folder +'/water_map.png',
                    image = water_map_image,
                    bounds = bounds,
                    opacity = 0.5,
                    name = 'Inundation Map_' + region ,
                    show = True
                ).add_to(m)

                plugins.Fullscreen(position='topright').add_to(m)
                folium.TileLayer('Stamen Terrain').add_to(m)
                m.add_child(folium.LatLngPopup())
                folium.LayerControl().add_to(m)

                st.write('Region:\n', region)
                st.write('Date: \n', date)

        try:
            nc_file = xr.open_dataset('output/output.nc')
            innudation_map = nc_file['Inundation Map']
            innudation_map = innudation_map.rio.set_spatial_dims('lon', 'lat')
            innudation_map.rio.set_crs("epsg:4326")
            innudation_map.rio.to_raster("output/output.tiff")
            nc_file.close()

            with open("output/output.tiff", 'rb') as f:
                st.download_button('Download Latest Run Output (.tiff)',
                f,
                file_name = "output.tiff",
                mime= "image/geotiff")


        except:
            pass




with row1_col1:
    folium_static(m, height = 600, width = 900)
    st.write('Disclaimer: This is a test version of FIER method for Mekong Region')
    url = "https://www.sciencedirect.com/science/article/pii/S0034425720301024?casa_token=kOYlVMMWkBUAAAAA:fiFM4l6BUzJ8xTCksYUe7X4CcojddbO8ybzOSMe36f2cFWEXDa_aFHaGeEFlN8SuPGnDy7Ir8w"
    st.write("Reference: [Chang, C. H., Lee, H., Kim, D., Hwang, E., Hossain, F., Chishtie, F., ... & Basnayake, S. (2020). Hindcast and forecast of daily inundation extents using satellite SAR and altimetry data with rotated empirical orthogonal function analysis: Case study in Tonle Sap Lake Floodplain. Remote Sensing of Environment, 241, 111732.](%s)" % url)
    st.write("This app has been developed by Chi-Hung Chang  & Son Do at University of Houston with supports from NASA SERVIR and GEOGloWS.")
    st.write("Kel Markert at SERVIR Coordination Office is also acknowledged for the development of this FIER-Mekong App.")

    uh = Image.open("logo/uh_logo_2.PNG")
    uw = Image.open("logo/uwashington.png")
    servir = Image.open("logo/servirmekong.png")
    nasa = Image.open("logo/nasa.png")
    geoglows = Image.open("logo/geoglows.jpg")
    st.image([uh, uw, servir, nasa,], width=150,)
    st.image([geoglows], width=200,)
