import numpy as np
import pandas as pd
from h3 import h3
import json
import pydeck as pdk

import streamlit as st

areas_path = 'data/areas.json'
distances_path = 'data/distances.json'

rng = np.random.default_rng()

@st.cache_data
def load(smth):
    if smth == 'areas':
        areas = pd.read_json(areas_path)
        def deserialize(dic):
            """Turn JSON-serialized multi-index pd.Series back into pd.Series"""

            multi = pd.MultiIndex.from_product(
                    [['both', 'sport', 'trad'], range(10)],
                    names=['style', 'grade_idx']
                    )
            return pd.Series(dic.values(), index=multi)
        stars_col = areas['stars'].apply(deserialize)
        areas_dict = areas.to_dict()
        areas_dict['stars'] = {name: stars_col.loc[name] for name in stars_col.index}
        areas = pd.DataFrame(areas_dict)
        # add colors
        def color(x):
            big1 = rng.integers(150,256)
            big2 = rng.integers(150,256)
            lil1 = rng.integers(100)
            lil2 = rng.integers(100)
            colors = rng.choice([big1, big1, lil1, lil2], size=(3), replace=False).tolist()
            if colors[1] > colors[0] + colors[2]: # no green-forward
                colors[1] = 0
            if colors[2] > colors[0] + colors[1]: # no purple-forward
                colors[2] = colors[2] // 2
            return colors
        areas['color'] = areas.apply(color, axis=1)
        return areas
    elif smth == 'usa_hexes':
        with open(usa_hexes_path, 'r') as f:
            return set(json.load(f))
    elif smth == 'distances, star_power':
        distances = pd.read_json(distances_path)
        star_power = distances.copy()
        return distances, star_power

areas = load('areas')
distances, star_power = load('distances, star_power')

st.write("What style you looking for?")
sport, trad = st.checkbox('Sport', True), st.checkbox('Trad', True)

st.write('What grades you looking for?')
grade_min, grade_max = st.slider('What grades you looking for?', 6, 15, (6, 15), format='5.%d', label_visibility='collapsed')
grade_idx_min, grade_idx_max = grade_min - 6, grade_max - 5 # offset by 1 for inclusive slicing

st.write('How much you like driving?')
inv_power = st.slider('How much do you like driving?', 0.1, 1.0, 0.25, format='', label_visibility='collapsed')
power_law = 1 / inv_power

# define function to extract star count depending on style
if sport and trad:
    def stars_by_style_grade(stars):
        sport = stars['sport'][grade_idx_min : grade_idx_max].sum()
        trad = stars['trad'][grade_idx_min : grade_idx_max].sum()
        both = stars['both'][grade_idx_min : grade_idx_max].sum()
        return sport + trad + both
elif sport:
    def stars_by_style_grade(stars):
        sport = stars['sport'][grade_idx_min : grade_idx_max].sum()
        both = stars['both'][grade_idx_min : grade_idx_max].sum()
        return sport + both
elif trad:
    def stars_by_style_grade(stars):
        trad = stars['trad'][grade_idx_min : grade_idx_max].sum()
        both = stars['both'][grade_idx_min : grade_idx_max].sum()
        return trad + both
else:
    #TODO: how to handle this?
    raise SystemExit

areas['style_grade_stars'] = areas['stars'].apply(stars_by_style_grade)

for name in star_power.columns:
    stars = areas.loc[name, 'style_grade_stars']
    star_power[name] = stars / (distances[name] ** power_law)
destinations = star_power.idxmax(axis=1)

def make_hex_layer(hexes, tooltip, opacity=0.25, color=[0,150,150]):
    """convenience function for creating pydeck H3ClusterLayer from set of hexes"""

    df = pd.DataFrame({'tooltip' : [tooltip], 'hexes' : [list(hexes)]})
    l = pdk.Layer(
            'H3ClusterLayer',
            df,
            pickable=True,
            stroked=False,
            filled=True,
            extruded=False,
            opacity=0.25,
            get_hexagons='hexes',
            get_fill_color=color,
    )
    return l

names = pd.unique(destinations.values)
layers = []
for name in names:
    # get hexes for this destination, choose a random color, and create a layer
    hexes = destinations.loc[destinations == name].index
    color = areas.loc[name, 'color']
    layers.append(make_hex_layer(hexes, name, color=color))

    # # same for the hexes that make up the destination itself, but with higher opacity
    # area_hexes = areas.loc[name, 'hexes']
    # stars = areas.loc[name, 'stars']
    # layers.append(make_hex_layer(area_hexes, f'{name}:  \u2606{stars}', opacity=1, color=color))

st.subheader("Your Gumby Road Map")
# Render
view_state = pdk.ViewState(latitude=38.2, longitude=-96.9, zoom=3, bearing=0, pitch=0)
st.pydeck_chart(
        pdk.Deck(
            layers=layers,
            map_style='light',
            initial_view_state=view_state,
            tooltip={"text": "{tooltip}"}
            )
        )
