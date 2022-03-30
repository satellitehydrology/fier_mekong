import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
from tensorflow.keras import models
import tensorflow as tf
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)
import xarray as xr
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.colors

root_output_folder = 'AOI/'

def tpc_predict(region, site, mode, value):
    tpc_mode = '%s/TF_model/500m/site-%s_tpc%s'%(str(region), str(site), str(mode).zfill(2))

    in_model = models.load_model(root_output_folder + tpc_mode)

    return in_model.predict([value])[0][0]

def synthesize_sar(region, water_level,):

    sm_mode = '%s/RSM/500m/RSM_hydro.nc'%(region)
    RSM = xr.open_dataset(root_output_folder + sm_mode)

    for ct_mode in range(len(RSM.mode.values)):

        sm = RSM.spatial_modes.values[:,:,ct_mode]

        site = str(RSM.hydro_site.sel(mode = ct_mode + 1).values)
        mode = ct_mode + 1
        value = float(water_level[site])

        est_tpc = tpc_predict(region, site, ct_mode + 1, value)
        if ct_mode == 0:
            syn_sar = sm*est_tpc
        else:
            syn_sar = syn_sar + sm*est_tpc

    all_meanVV_dir = '%s/stats_img/500m/all_meanVV.nc'%(region)
    all_meanVV = xr.open_dataset(root_output_folder + all_meanVV_dir)
    all_meanVV = all_meanVV.to_array().values[0,:,:]

    syn_sar = syn_sar + all_meanVV

    # Z-score
    zscore_threshold = -3

    dry_meanVV_dir = '%s/stats_img/500m/dry_meanVV.nc'%(region)
    dry_meanVV = xr.open_dataset(root_output_folder + dry_meanVV_dir)
    dry_meanVV = dry_meanVV.to_array().values[0,:,:]


    dry_stdVV_dir = '%s/stats_img/500m/dry_stdVV.nc'%(region)
    dry_stdVV = xr.open_dataset(root_output_folder + dry_stdVV_dir)
    dry_stdVV = dry_stdVV.to_array().values[0,:,:]

    z_score_img = (syn_sar-dry_meanVV)/dry_stdVV

    # Inundation Map

    aoi_indx = np.argwhere(~np.isnan(dry_meanVV))
    water_indx = np.argwhere( z_score_img < zscore_threshold )
    water_map = np.empty((syn_sar.shape[0], syn_sar.shape[1]))
    water_map[:] = np.nan
    water_map[aoi_indx[:,0], aoi_indx[:,1]] = 0
    water_map[water_indx[:,0], water_indx[:,1]] = 1
    # water_map[water_map == 2] = np.nan

    # water_map = z_score_img.copy()
    # water_map[z_score_img < zscore_threshold] = 1
    # water_map[z_score_img >= zscore_threshold] = 0

    RSM.close()

    return syn_sar, z_score_img, water_map

def image_output(region, water_level):

    folder_name = 'output'
    sar_image, z_score_image, water_map_image = synthesize_sar(region, water_level)

    fig = plt.figure()
    plt.imshow(sar_image, cmap='gray')
    plt.axis('off')
    plt.savefig(folder_name +'/syn_sar.png', bbox_inches='tight', dpi=300, pad_inches = 0)
    plt.close()

    fig = plt.imshow(z_score_image, cmap='jet', vmin=-3, vmax=3, interpolation='None')
    plt.axis('off')
    plt.savefig(folder_name +'/z_score.png', bbox_inches='tight', dpi=300, pad_inches = 0)
    plt.close()

    water_cmap =  matplotlib.colors.ListedColormap(["silver","darkblue"])
    # water_cmap.set_bad('w', 0.001)
    fig = plt.imshow(water_map_image, cmap = water_cmap)
    #plt.clim(vmin=0, vmax=1)
    plt.axis('off')
    plt.savefig(folder_name +'/water_map.png', bbox_inches='tight', dpi=300, interpolation='None', pad_inches = 0)
    plt.close()
    #plt.show()

    # Make nc file:
    all_meanVV_dir = '%s/stats_img/500m/all_meanVV.nc'%(region)
    all_meanVV = xr.open_dataset(root_output_folder + all_meanVV_dir)
    out_file = xr.Dataset(
        {
            "Synthesized SAR Image": (
                all_meanVV.dims,
                sar_image
                            ),
            "Z-score Image": (
                all_meanVV.dims,
                z_score_image,
                             ),
            "Inundation Map": (
                all_meanVV.dims,
                water_map_image,
                     ),
        },
        coords = all_meanVV.coords,
    )
    all_meanVV.close()
    out_file.to_netcdf(folder_name +'/output.nc')

    return folder_name
