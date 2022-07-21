import streamlit as st
import geemap as gm
import geemap.foliumap as geemap
import ee
import folium
import os

# Reset Output folder
dir = 'output'
for f in os.listdir(dir):
    os.remove(os.path.join(dir, f))

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
def generate_depth(flood_raster):
    flood = ee.Image(flood_raster)
    flood = flood.updateMask(flood.gte(1));
    area = flood.geometry().bounds().buffer(1000).bounds()

    dem = ee.Image('users/sondo/merit_dem_cogeo').clip(area)
    projection = dem.projection()
    resolution = projection.nominalScale().getInfo()
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

    return costDepthFilter

# Page Configuration
st.set_page_config(layout="wide")
# Title and Description
st.title("Generate Flood Depth using Floodwater Depth Estimation Tool (FwDET)")

row1_col1, row1_col2 = st.columns([2, 1])

# Set up Geemap
with row1_col1:
    m = geemap.Map(
    zoom=5,
    center=(12.02 , 104.81),
    )
    m.addLayerControl()


with row1_col2:
    # Form
    st.subheader('Flood Innudation Raster Input')
    with st.form('Input'):
        title = st.text_input('Insert Earth Engine Asset Directory of Innudation Raster:', 'users/sondo/output_test')
        st.markdown('_Example: users/sondo/output_test_')
        depth = st.checkbox('Flood Depth Estimation')
        submitted = st.form_submit_button("Submit")

        if submitted:
            flood = ee.Image(title)
            flood = flood.updateMask(flood.gte(1));

            m = geemap.Map(
            zoom=5,
            center=(12.02 , 104.81),
            basemap = None,
            tiles = None
            )
            m.centerObject(flood, 8)


            flood_params = {'min': 0,
            'max': 1,
            'palette': ['red','#000072']}


            depth_params = {'min': 1,
            'max': 4,
            'palette': ['#FEF001','#FD9A01','#FD6104','#F00505']}
            if depth:
                basemaps['Google Satellite Hybrid'].add_to(m)
                basemaps['Google Terrain'].add_to(m)
                costDepthFilter = generate_depth(title)
                gm.ee_export_image(costDepthFilter, 'output/flood_depth.tif', )
                costDepthFilter_viz = costDepthFilter.where(costDepthFilter.lt(1), 1)\
                .where(costDepthFilter.gte(1).And(costDepthFilter.lt(3)), 2)\
                .where(costDepthFilter.gte(3).And(costDepthFilter.lt(5)), 3)\
                .where(costDepthFilter.gte(5), 4)\

                m.addLayer(costDepthFilter_viz, depth_params, name = "Flood Depth")

                legend_keys_flood = ['< 1 meter', '1 - 3 meters', '3 - 5 meters', '> 5 meteres',]
                legend_colors_flood = ['#FEF001','#FD9A01','#FD6104','#F00505']
                m.add_legend(title = 'Flood Depth', labels=legend_keys_flood, colors=legend_colors_flood, control = True)

            else:
                basemaps['Google Terrain'].add_to(m)
                m.addLayer(flood, flood_params, name = 'Innudation Extent',)

            m.addLayerControl()
    try:
        with open("output/flood_depth.tif", 'rb') as f:
            st.download_button('Download Latest Run Output (.tif)',
            f,
            file_name = "flood_depth.tif",
            mime= "image/geotiff")
    except Exception as e:
        pass



with row1_col1:
    # folium_static(m.to_streamlit(scrolling = True), height = 600, width = 900)
    m.to_streamlit(height = 600, scrolling = True)
