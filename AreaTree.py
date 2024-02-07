import numpy as np
import pandas as pd
from copy import deepcopy
import time
from tqdm import tqdm
from h3 import h3

"""
Mountain Project (MP) data processing
"""

class Area:
    """Class to store climbing area as a node in AreaTree"""

    def __init__(self, df, pbar=None):
        """takes df of MP data with a common top-level location"""
        
        df = deepcopy(df)
        try: # extract common top-level location
            name = df['location'].str[-1].unique().item()
        except ValueError as e:
            raise ValueError('Dataframe must have a common top-level location') from e

        self.name = name.strip()
        df['location'].apply(lambda x: x.pop()) # delete this area from end of each list

        # if there are sub-areas, recurse; if not, extract data
        subnames = df['location'].str[-1].unique()
        # exclude nan, which happens if `.str[-1]` sees empty list
        subnames = [s for s in subnames if s == s]
        if subnames:
            self.subs = [Area(df.loc[df['location'].str[-1]==subname], pbar) for subname in subnames]
            self.stars = np.sum([sub.stars for sub in self.subs])
            self.hexes = set([h for sub in self.subs for h in sub.hexes])
        else:
            self.subs = []
            self.stars = df['stars'].sum()
            self.hexes = df['h3'].unique()
            assert len(self.hexes)==1, f"{self.name=} {self.hexes=}"
            if pbar is not None:
                pbar.update(len(df))

    def propogate_hexes(self):
        """propogate hexes up from leaves to all parents"""

        if self.subs: # if there are children, recurse and get hexes from them
            for sub in self.subs:
                sub.propogate_hexes()
            self.hexes = set([h for sub in self.subs for h in sub.hexes])
        # if no children, just leave hexes alone

    def prune_by_hex(self):
        """prune branches to highest level lying in a single hex"""
        
        if len(self.hexes) > 1: # if children comprise multiple hexes, recurse
            for sub in self.subs:
                sub.prune_by_hex()
        elif self.subs: # if all children lie in a single hex, prune at this node
            self.subs = []

    def prune_by_stars(self, min_stars):
        """prune branches to lowest level with at least min_stars"""

        self.subs = [sub for sub in self.subs if sub.stars >= min_stars]
        for sub in self.subs:
            sub.prune_by_stars(min_stars)

    def leaves(self):
        """Return list of leaves as dicts containing 'name', 'stars', 'hexes'"""

        if self.subs:
            return [leaf for sub in self.subs for leaf in sub.leaves()]
        else:
            return [{
                'name' : self.name,
                'stars' : int(self.stars),
                'hexes' : list(self.hexes),
                }]

    def __repr__(self):
        s = self.name
        if self.subs:
            for sub in sorted(self.subs, key=lambda s: s.name):
                s += '\n  '
                s += '\n  '.join(repr(sub).splitlines())
        else:
            s += f'  {self.stars:.0f} stars'#, hex {self.hexes}'
        return s

class AreaTree:
    """Class to work with MP climbing areas in tree structure"""

    def __init__(self, df, progress=False):
        """takes df of MP data and builds tree of climbing areas

        df needs preprocessing to add columns 'stars' and 'h3'
        """

        df = deepcopy(df) # copy df so we can modify it safely
        df.loc[:, 'location'] = df['location'].str.split('>')

        # check if there's a common top-level location already; insert one if not
        top_level = df['location'].str[-1].unique()
        if len(top_level) != 1:
            df['location'].apply(lambda x: x.append('_all_locations'))

        if progress: # progress bar
            print('Building tree ...')
            pbar = tqdm(total=len(df))
        else:
            pbar = None
        # build tree recursively
        self.root = Area(df, pbar)
        if pbar is not None: pbar.close()

    def hexlist(self):
        return list(self.root.hexes)

    def prune_by_hex(self):
        """prune branches to highest level lying in a single hex"""

        self.root.prune_by_hex()

    def prune_by_stars(self, min_stars):
        """prune branches to lowest level with at least min_stars per hex"""

        self.root.prune_by_stars(min_stars)
        self.root.propogate_hexes()

    def to_df(self):
        """Convert to DataFrame

        Each row is a leaf node, and contains the name, total stars, and list of hexes
        """

        leaves = self.root.leaves()
        return pd.DataFrame(leaves)

    def __repr__(self):
        return repr(self.root)
