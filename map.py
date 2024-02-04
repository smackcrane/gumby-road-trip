
import numpy as np
import pandas as pd

data = pd.read_csv('mp_routes.csv', index_col=0).rename(columns={
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


