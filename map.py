import numpy as np
import pandas as pd
from h3 import h3
import folium
from AreaTree import AreaTree

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

# def visualize_hexagons(hexagons, color="red", folium_map=None):
    # """
    # hexagons is a list of hexcluster. Each hexcluster is a list of hexagons.
    # eg. [[hex1, hex2], [hex3, hex4]]
    # """
    # polylines = []
    # lat = []
    # lng = []
    # for hex in hexagons:
        # polygons = h3.h3_set_to_multi_polygon([hex], geo_json=False)
        # # flatten polygons into loops.
        # outlines = [loop for polygon in polygons for loop in polygon]
        # polyline = [outline + [outline[0]] for outline in outlines][0]
        # lat.extend(map(lambda v:v[0],polyline))
        # lng.extend(map(lambda v:v[1],polyline))
        # polylines.append(polyline)

    # if folium_map is None:
        # m = folium.Map(location=[sum(lat)/len(lat), sum(lng)/len(lng)], zoom_start=4, tiles='cartodbpositron')
    # else:
        # m = folium_map
    # for polyline in polylines:
        # my_PolyLine=folium.PolyLine(locations=polyline,weight=2,color=color)
        # m.add_child(my_PolyLine)
    # return m

# add h3 cells to data

def get_h3_fn(resolution):
    def get_h3(row):
        return h3.geo_to_h3(row['latitude'], row['longitude'], resolution)
    return get_h3

resolution = 6
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

# data = data.groupby('h3').agg({
            # 'location' : common_location,
            # 'stars' : np.sum,
         # }).reset_index()
# data = data.loc[data['stars'] >= 350]
# print(data)

# build area tree
# data = data.loc[data['location'].str.contains('Kentucky')] # for testing purposes
# areas = AreaTree(data, progress=True)
# areas.prune_by_hex()
# areas.prune_by_stars(min_stars=20_000)
# areas.to_df().to_json('areas.json', index=False)
# print(areas)
# hexes = areas.hexlist()

# stars = data.groupby('h3')['stars'].sum().reset_index()
# hexes = stars.loc[stars['stars'] > 300]

import pydeck as pdk
data['h3_list'] = data['h3'].apply(lambda x: [x])
area_df = pd.read_json('areas.json')
print(area_df[['name', 'stars']].sort_values('stars', ascending=False).head(50))
layer = pdk.Layer(
        'H3ClusterLayer',
        area_df,
        pickable=True,
        stroked=False,
        filled=True,
        extruded=False,
        opacity=0.25,
        get_hexagons="hexes",
        get_fill_color="[255,155,0]",
        get_line_color=[255, 255, 255],
        line_width_min_pixels=2,
)

# Set the viewport location
view_state = pdk.ViewState(latitude=38.2, longitude=-96.9, zoom=4, bearing=0, pitch=0)

# Render
r = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "{name}:  \u2606{stars}"}
)
r.to_html("example.html")

# m = folium.Map(location=[39.742043, -104.991531], zoom_start=4, tiles='cartodbpositron')
# visualize_hexagons(hexes, folium_map=m)
# m.save('example.html')
