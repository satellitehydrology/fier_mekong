import folium
import folium.plugins as plugins
import streamlit as st
from streamlit_folium import folium_static
import xarray as xr
from syn_sar import *
import numpy.ma as ma
import pandas as pd
import matplotlib.pyplot as plt


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
                hydrosite = pd.read_csv('AOI/%s/hydrosite.csv'%(str(region)))
                st.write('Water Level Gauge')
                st.dataframe(hydrosite)
            except:
                st.write('Region not ready')

    try:
        st.subheader('Water Level Input')
        with st.form("Run FIER"):
            hydrosite = pd.read_csv('AOI/%s/hydrosite.csv'%(str(region)))
            water_level = {}
            for i in range(hydrosite.shape[0]):
                water_level[hydrosite.loc[i,'ID']] = st.number_input("%s Station Water level:"%(hydrosite.loc[i,'Name']),
                format = '%.2f',
                min_value = float(hydrosite.loc[i,'Minimum(meters)']),
                max_value = float(hydrosite.loc[i,'Maximum(meters)']),
                value = (float(hydrosite.loc[i,'Minimum(meters)']) + float(hydrosite.loc[i,'Maximum(meters)']))/2
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

                    image_folder = image_output(region, water_level)
                    output =  xr.open_dataset(image_folder +'/output.nc',)
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
                    output.close()
                    st.write('Region:\n', region)
                    st.write('Water level:\n', water_level)

                except:
                    st.write('Error')
    except:
        pass




with row1_col1:
    folium_static(m, height = 600, width = 800)
    st.write('Disclaimer: This is a test version of FIER method for Bangladesh')
    url = "https://www.sciencedirect.com/science/article/pii/S0034425720301024?casa_token=kOYlVMMWkBUAAAAA:fiFM4l6BUzJ8xTCksYUe7X4CcojddbO8ybzOSMe36f2cFWEXDa_aFHaGeEFlN8SuPGnDy7Ir8w"
    st.write("Reference: [Chang, C. H., Lee, H., Kim, D., Hwang, E., Hossain, F., Chishtie, F., ... & Basnayake, S. (2020). Hindcast and forecast of daily inundation extents using satellite SAR and altimetry data with rotated empirical orthogonal function analysis: Case study in Tonle Sap Lake Floodplain. Remote Sensing of Environment, 241, 111732.](%s)" % url)
    st.write("This app has been developed by Son Do & Chi-Hung Chang at University of Houston.")
