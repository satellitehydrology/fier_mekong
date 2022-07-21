

import streamlit as st
# Page Configuration
st.set_page_config(layout="wide")

import fier_mekong, fwdet



page_names_to_funcs = {
    "FIER-Mekong": fier_mekong.app,
    "FwDET-Flood Depth": fwdet.app,
}

selected_page = st.sidebar.selectbox("Select an application", page_names_to_funcs.keys())
page_names_to_funcs[selected_page]()
