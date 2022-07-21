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

# Reset Output folder
dir = 'output'
for f in os.listdir(dir):
    os.remove(os.path.join(dir, f))

def sheet_out(url):
    return url.replace("/edit#gid=", "/export?format=csv&gid=")

def colorize(data, cmap='viridis'):
    array = ma.masked_invalid(data)
    normed_data = (array - array.min()) / (array.max() - array.min())
    cm = plt.cm.get_cmap(cmap)
    return cm(array)

# Page Configuration
st.set_page_config(layout="wide")

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
}

# Title and Description
st.title("Forecasting Inundation Extents using REOF Analysis (FIER)-Mekong")

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
                    basemaps['Google Terrain'].add_to(m)
                    basemaps['Google Satellite Hybrid'].add_to(m)

                    image_folder = image_output(curr_region, water_level)
                    with xr.open_dataset(image_folder +'/output.nc',) as output:
                        bounds = [[output.lat.values.min(), output.lon.values.min()], [output.lat.values.max(), output.lon.values.max()]]
                        sar_image, z_score_image, water_map_image = output['Synthesized SAR Image'].values, output['Z-score Image'].values, output['Inundation Map'].values

                    water_cmap =  matplotlib.colors.ListedColormap(["silver","darkblue"])
                    water_map_image =  colorize(water_map_image, water_cmap)

                    # folium.raster_layers.ImageOverlay(
                    #     image= image_folder +'/syn_sar.png',
                    #     # image = sar_image,
                    #     bounds = bounds,
                    #     opacity = 0.5,
                    #     name = 'Synthesized Sar Image_' + curr_region,
                    #     show = False,
                    # ).add_to(m)
                    #
                    # # Add Z_SCORE
                    # folium.raster_layers.ImageOverlay(
                    #     image= image_folder +'/z_score.png',
                    #     # image = z_score_image,
                    #     bounds = bounds,
                    #     opacity = 0.5,
                    #     name = 'Z-score Image_' + curr_region ,
                    #     show = False
                    # ).add_to(m)

                    # Add Inundation
                    folium.raster_layers.ImageOverlay(
                        # image= image_folder +'/water_map.png',
                        image = water_map_image,
                        bounds = bounds,
                        opacity = 0.5,
                        name = 'Inundation Map_' + curr_region ,
                        show = True
                    ).add_to(m)

                    m.addLayerControl()
                    st.write('Region:\n', curr_region)
                    st.write('Date: \n', date)

            try:
                with open("output/output.tiff", 'rb') as f:
                    st.download_button('Download Latest Run Output (.tiff)',
                    f,
                    file_name = "output.tiff",
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
                    basemaps['Google Terrain'].add_to(m)
                    basemaps['Google Satellite Hybrid'].add_to(m)

                    image_folder = image_output(curr_region, water_level)
                    with xr.open_dataset(image_folder +'/output.nc',) as output:
                        bounds = [[output.lat.values.min(), output.lon.values.min()], [output.lat.values.max(), output.lon.values.max()]]
                        sar_image, z_score_image, water_map_image = output['Synthesized SAR Image'].values, output['Z-score Image'].values, output['Inundation Map'].values

                    water_cmap =  matplotlib.colors.ListedColormap(["silver","darkblue"])
                    water_map_image =  colorize(water_map_image, water_cmap)

                    # folium.raster_layers.ImageOverlay(
                    #     image= image_folder +'/syn_sar.png',
                    #     # image = sar_image,
                    #     bounds = bounds,
                    #     opacity = 0.5,
                    #     name = 'Synthesized Sar Image_' + curr_region,
                    #     show = False,
                    # ).add_to(m)
                    #
                    # # Add Z_SCORE
                    # folium.raster_layers.ImageOverlay(
                    #     image= image_folder +'/z_score.png',
                    #     # image = z_score_image,
                    #     bounds = bounds,
                    #     opacity = 0.5,
                    #     name = 'Z-score Image_' + curr_region ,
                    #     show = False
                    # ).add_to(m)

                    # Add Inundation
                    folium.raster_layers.ImageOverlay(
                        # image= image_folder +'/water_map.png',
                        image = water_map_image,
                        bounds = bounds,
                        opacity = 0.5,
                        name = 'Inundation Map_' + curr_region ,
                        show = True
                    ).add_to(m)

                    m.addLayerControl()
                    st.write('Region:\n', curr_region)
                    st.write('Date: \n', date)

            try:
                with open("output/output.tiff", 'rb') as f:
                    st.download_button('Download Latest Run Output (.tiff)',
                    f,
                    file_name = "output.tiff",
                    mime= "image/geotiff")
            except:
                pass

    first = Image.open("logo/first.PNG")
    second = Image.open("logo/second_row.PNG")
    st.image([first], width=450,)
    st.image([second], width=350,)


with row1_col1:
    m.to_streamlit(height = 600, scrolling = True)
    st.write('Disclaimer: This is a test version of FIER method for Mekong Region')
    url = "https://www.sciencedirect.com/science/article/pii/S0034425720301024?casa_token=kOYlVMMWkBUAAAAA:fiFM4l6BUzJ8xTCksYUe7X4CcojddbO8ybzOSMe36f2cFWEXDa_aFHaGeEFlN8SuPGnDy7Ir8w"
    st.write("Reference: [Chang, C. H., Lee, H., Kim, D., Hwang, E., Hossain, F., Chishtie, F., ... & Basnayake, S. (2020). Hindcast and forecast of daily inundation extents using satellite SAR and altimetry data with rotated empirical orthogonal function analysis: Case study in Tonle Sap Lake Floodplain. Remote Sensing of Environment, 241, 111732.](%s)" % url)
    url_2 = "https://www.sciencedirect.com/science/article/abs/pii/S1364815218306194"
    st.write("[Chang, C. H., Lee, H., Hossain, F., Basnayake, S., Jayasinghe, S., Chishtie, F., ... & Du Bui, D. (2019). A model-aided satellite-altimetry-based flood forecasting system for the Mekong River. Environmental modelling & software, 112, 112-127.](%s)" % url_2)
    st.write("This app has been developed by Chi-Hung Chang  & Son Do at University of Houston with supports from NASA SERVIR and GEOGloWS.")
    st.write("Kel Markert at SERVIR Coordination Office is also acknowledged for the development of this FIER-Mekong App.")
