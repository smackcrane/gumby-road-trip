import numpy as np
import pandas as pd
from h3 import h3
from tqdm import tqdm
import json
import os
import re
import pydeck as pdk
from AreaTree import AreaTree

#
#   Settings
#

resolution = 5 # resolution for h3
power_law = 2 # exponent of power law
mp_data_path = 'data/mp_routes.csv'
countries_geojson_path = 'data/countries.geojson'

areas_path = 'data/areas.json'
usa_hexes_path = 'data/usa_hexes.json'
distances_path = 'data/distances.json'
RECOMPUTE_AREA_TREE = True
RECOMPUTE_DISTANCES = True

#
#
#

rng = np.random.default_rng()

# load and clean up dataset
data = pd.read_csv(mp_data_path, index_col=0).rename(columns={
            'Route' : 'name',
            'Location' : 'location',
            'URL' : 'url',
            'Avg Stars' : 'avg_stars',
            'Route Type' : 'type',
            'Rating' : 'grade',
            'Pitches' : 'pitches',
            'Length' : 'length',
            'Area Latitude' : 'latitude',
            'Area Longitude' : 'longitude',
            ' desc' : 'description',
            ' protection' : 'protection',
            ' num_votes' : 'num_votes',
            })
data = data.drop(columns=['url', 'pitches', 'length', 'description', 'protection'])
data = data.loc[~data['location'].str.endswith('International')] # only US lower 48
data = data.loc[~data['location'].str.endswith('Alaska')] # only US lower 48
data = data.loc[~data['location'].str.endswith('Hawaii')] # only US lower 48
data = data.loc[data['grade'].str.startswith('5.')] # drop "Easy 5th AI1-2 Mod. Snow" etc. etc.
data['stars'] = data['avg_stars'] * data['num_votes'] # compute total stars
# extract grade as index: upto 5.6 -> 0; 5.7 -> 1; 5.8 -> 2; ...; 5.15 -> 9
regex = re.compile(r'5\.(\d+)')
def grade_to_idx(grade):
    m = regex.match(grade)
    grade_idx = int(m.group(1)) - 6
    return max(grade_idx, 0)
data['grade_idx'] = data['grade'].apply(grade_to_idx)
# extract syle as 'sport', 'trad', or 'both' (e.g. 'Trad, Mixed, Ice, Alpine' -> 'trad')
def base_style(style):
    if 'Sport' in style and 'Trad' not in style:
        return 'sport'
    elif 'Trad' in style and 'Sport' not in style:
        return 'trad'
    elif 'Sport' in style and 'Trad' in style:
        return 'both'
data['style'] = data['type'].apply(base_style)

# fix some bad data
data.loc[data['location'].str.contains('Cody Night Rodeo'), 'latitude'] = 44.13111
data.loc[data['location'].str.contains('Cody Night Rodeo'), 'longitude'] = -107.25702 
data.loc[data['location'].str.contains('Dihedrals > X Rock'), 'latitude'] = 37.31105
data.loc[data['location'].str.contains('Dihedrals > X Rock'), 'longitude'] = -107.86121

# add h3 cells to data
get_h3 = lambda row: h3.geo_to_h3(row['latitude'], row['longitude'], resolution)
data['hex'] = data.apply(get_h3, axis=1)

if RECOMPUTE_AREA_TREE or not os.path.isfile(areas_path):
    print('Growing area tree ...')
    areas = AreaTree(data, progress=True)
    # # prune to headline areas
    # areas.prune_by_hex()
    # areas.prune_by_stars(min_stars=20_000)
    areas.prune_by_diameter(miles=70)
    areas = areas.to_df()
    areas = areas.loc[areas['stars'].apply(np.sum) > 10_000]
    areas = areas.set_index('name')
    areas.to_json(areas_path)
else:
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

if RECOMPUTE_DISTANCES or not os.path.isfile(distances_path):
    if not os.path.isfile(usa_hexes_path):
        print('Computing USA lower 48 hex set ...')
        with open(countries_geojson_path, 'r') as f:
            countries = json.load(f)
        usa_polygons = countries['features'][238]['geometry']
        # convert MultiPolygon to multiple Polygons
        usa_hexes = set()
        for coords in usa_polygons['coordinates']:
            if coords[0][0][0] < -125: # only lower 48, exclude Alaska & Hawaii
                continue
            coords = [[[lat, lng] for [lng, lat] in coords[0]]] # reverse order of lat/lng
            geojson = {'type' : 'Polygon', 'coordinates' : coords}
            hexes = h3.polyfill(geojson, resolution)
            usa_hexes.update(hexes)
        with open(usa_hexes_path, 'w') as f:
            json.dump(list(usa_hexes), f)
    else:
        with open(usa_hexes_path, 'r') as f:
            usa_hexes = set(json.load(f))

    # update usa hexes with climbing area hexes in case there's any disagreement
    all_area_hexes = [h for hexes in areas['hexes'] for h in hexes]
    usa_hexes.update(all_area_hexes)

    def gen_distance(hexes):
        frontier = set(hexes)
        interior = set()
        i = 0
        while frontier: # loop until we run out of frontier
            yield i, frontier
            interior.update(frontier) # add frontier to interior
            frontier = set([nbr for h in frontier for nbr in h3.hex_ring(h, 1)]) # new frontier
            frontier = frontier.difference(interior) # subtract points already in interior
            frontier = frontier.intersection(usa_hexes) # subtract points outside the us
            i += 1

    print('Computing distance dataframe ...')
    distances = pd.DataFrame(index=list(usa_hexes), columns=areas.index)
    for name in tqdm(areas.index):
        for dist, hexes in gen_distance(areas.loc[name, 'hexes']): # hexs at fixed dist to destination
            distances.loc[list(hexes), name] = dist + 1
    #TODO: fix this? i.e. expand flood to reach disconnected hexes
    distances.dropna(inplace=True) # drop nan distances (disconneced hexes)
    distances.to_json(distances_path)
else:
    distances = pd.read_json(distances_path)

# compute best destination for each hex
star_power = distances # note this will modify distance df, new name to match new contents
for name in star_power.columns:
    stars = areas.loc[name, 'stars'].sum()
    star_power[name] = stars / (distances[name] ** power_law)
destinations = star_power.idxmax(axis=1)

#TODO: if a hex is occupied by a climbing area, make that the destination? or allow coups?
#       (also if multiple areas share a hex, give it to the bigger one---or should there only be one per hex?)
#       (also if an area doesn't pull its own hex, just remove it?)

# build pydeck layers

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

print('Building pydeck layers ...')
names = pd.unique(destinations.values)
layers = []
for name in names:
    # get hexes for this destination, choose a random color, and create a layer
    hexes = destinations.loc[destinations == name].index
    rng_color = rng.integers(256, size=(3))
    color = json.loads(f'[{rng_color[0]}, {rng_color[1]}, {rng_color[2]}]') # dunno, pydeck is picky
    layers.append(make_hex_layer(hexes, name, color=color))

    # same for the hexes that make up the destination itself, but with higher opacity
    area_hexes = areas.loc[name, 'hexes']
    stars = areas.loc[name, 'stars'].sum()
    layers.append(make_hex_layer(area_hexes, f'{name}:  \u2606{stars}', opacity=1, color=color))

# Render
view_state = pdk.ViewState(latitude=38.2, longitude=-96.9, zoom=4, bearing=0, pitch=0)
r = pdk.Deck(
        layers=layers,
        map_style='light',
        initial_view_state=view_state,
        tooltip={"text": "{tooltip}"}
)
r.to_html("example.html")



