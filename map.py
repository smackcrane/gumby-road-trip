import numpy as np
import pandas as pd
from h3 import h3
from tqdm import tqdm
import json
import folium
import pydeck as pdk
from AreaTree import AreaTree

rng = np.random.default_rng()

data = pd.read_csv('data/mp_routes.csv', index_col=0).rename(columns={
            'Route' : 'name',
            'Location' : 'location',
            'URL' : 'url',
            'Avg Stars' : 'avg_stars',
            'Route Type' : 'type',
            'Rating' : 'rating',
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
data['stars'] = data['avg_stars'] * data['num_votes'] # compute total stars

RECOMPUTE_AREA_TREE = False
RECOMPUTE_USA_HEXES = False
resolution = 5

# add h3 cells to data

def get_h3_fn(resolution):
    def get_h3(row):
        return h3.geo_to_h3(row['latitude'], row['longitude'], resolution)
    return get_h3

data['h3'] = data.apply(get_h3_fn(resolution), axis=1)

def common_location(locations):
    """Take series of locations and return greatest common location"""

    locations = zip(*locations.str.split('>').str[::-1]) # split by '>', reverse, zip
    common = [] # common location found so far
    for names in locations: # loop through sublocation levels
        for i in range(1, len(names)): # loop through zip of names at that level
            if names[0] != names[i]: # if any names don't match then return
                return ' > '.join(common)
        common.append(names[0].strip()) # if all the names matched then add it to the common location
    return ' > '.join(common)

if RECOMPUTE_AREA_TREE:
    # data = data.groupby('h3').agg({
                # 'location' : common_location,
                # 'stars' : np.sum,
             # }).reset_index()
    #data = data.loc[data['stars'] >= 350]
    print(data)

    # build area tree
    areas = AreaTree(data, progress=True)
    areas.prune_by_hex()
    areas.prune_by_stars(min_stars=20_000)
    areas.to_df().to_json('data/areas.json')
    print(areas)
# hexes = areas.hexlist()

# stars = data.groupby('h3')['stars'].sum().reset_index()
# hexes = stars.loc[stars['stars'] > 300]

# data['h3_list'] = data['h3'].apply(lambda x: [x])
area_df = pd.read_json('data/areas.json')
layer0 = pdk.Layer(
        'H3ClusterLayer',
        area_df,
        pickable=True,
        stroked=False,
        filled=True,
        extruded=False,
        # opacity=0.25,
        get_hexagons="hexes",
        get_fill_color="[225,125,0]",
)

if RECOMPUTE_USA_HEXES:
    with open('data/countries.geojson', 'r') as f:
        countries = json.load(f)
    usa = countries['features'][238]['geometry']
    # convert MultiPolygon to multiple Polygons
    hexes = set()
    for coords in tqdm(usa['coordinates']):
        if coords[0][0][0] < -125: # only lower 48, exclude Alaska & Hawaii
            continue
        coords = [[[lat, lng] for [lng, lat] in coords[0]]] # reverse order of lat/lng
        geojson = {'type' : 'Polygon', 'coordinates' : coords,}
        h = h3.polyfill(geojson, resolution)
        hexes.update(h)

    hex_df = pd.DataFrame({'name' : ['USA'], 'stars' : [5], 'hexes' : [list(hexes)], 'r' : [50], 'g' : [250], 'b' : [230]})
    hex_df.to_json('data/usa_hex.json')
    # print(hex_df)

hex_df = pd.read_json('data/usa_hex.json')

layer_usa = pdk.Layer(
        'H3ClusterLayer',
        hex_df,
        pickable=True,
        stroked=False,
        filled=True,
        extruded=False,
        opacity=0.10,
        get_hexagons="hexes",
        get_fill_color=[0,255,255],
)

def make_hex_layer(hexes, name, stars, color=[0,150,150]):
    df = pd.DataFrame({'name' : [name], 'stars' : [stars], 'hexes' : [list(hexes)]})
    l = pdk.Layer(
            'H3ClusterLayer',
            df,
            pickable=True,
            stroked=False,
            filled=True,
            extruded=False,
            opacity=0.25,
            get_hexagons='hexes',
            get_fill_color=list(color),
    )
    return l

all_area_hexes = [h for hexes in area_df['hexes'] for h in hexes]

usa_hexes = set(hex_df.loc[0, 'hexes'])
usa_hexes.update(all_area_hexes) # in case there are hexes outside the border
usa = pd.DataFrame(index=list(usa_hexes))
usa['star_power'] = 0.0
usa['destination'] = ''


def enum_frontier(hexes):
    frontier = set(hexes)
    interior = set()
    i = 0
    while frontier: # loop until we run out of frontier
        yield i, frontier
        interior.update(frontier) # add frontier to interior
        frontier = set([nbr for h in frontier for nbr in h3.hex_ring(h, 1)]) # compute new frontier
        frontier = frontier.difference(interior) # subtract points already in interior
        frontier = frontier.intersection(usa_hexes) # subtract points outside the us
        i += 1

# area_hexes = area_df.loc[area_df['name'].str.contains('Joshua Tree'), 'hexes'].item()
# layers = []
# for i, hexes in tqdm(enum_frontier(area_hexes)):
    # rng_color = rng.integers(256, size=(3))
    # color = json.loads(f'[{rng_color[0]}, {rng_color[1]}, {rng_color[2]}]')
    # layers.append(make_hex_layer(hexes, 'frontier', i, color=color))

for _, row in tqdm(area_df.iterrows(), total=len(area_df)):
    destination, stars, area_hexes = row['name'], row['stars'], row['hexes']
    for i, hexes in enum_frontier(area_hexes): # hexes at distnace i from destination
        star_power = stars / (i+1) # stars discounted by distance
        for h in hexes: # check if this destination is best for this hex
            if star_power > usa.loc[h, 'star_power']:
                usa.loc[h, 'star_power'] = star_power
                usa.loc[h, 'destination'] = destination


layers = []
dests = usa['destination'].unique()
for dest in dests:
    hexes = usa.loc[usa['destination']==dest].index
    rng_color = rng.integers(256, size=(3))
    color = json.loads(f'[{rng_color[0]}, {rng_color[1]}, {rng_color[2]}]')
    layers.append(make_hex_layer(hexes, dest, "stars", color))




# Set the viewport location
view_state = pdk.ViewState(latitude=38.2, longitude=-96.9, zoom=4, bearing=0, pitch=0)

# Render
r = pdk.Deck(
        layers=[layer_usa, *layers, layer0],
        map_style='light',
        initial_view_state=view_state,
        tooltip={"text": "{name}:  \u2606{stars}"}
)
r.to_html("example.html")

# m = folium.Map(location=[39.742043, -104.991531], zoom_start=4, tiles='cartodbpositron')
# visualize_hexagons(hexes, folium_map=m)
# m.save('example.html')
