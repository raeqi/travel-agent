"""Small curated Shanghai discovery catalog; not a live map search service.

Coordinates are approximate WGS84 display points, not surveyed entrances.
Public sources establish identity/address, not current opening status.
"""
PLACES = [
    dict(name='复兴公园', lat=31.2153, lon=121.4670, category='公园 · 城市散步',
         source='https://english.shanghai.gov.cn/en-Parks/20250220/636b3df5761e4055b731a92d2abddcb3.html',
         note='想从街区切换到绿意，可以把这段散步留给复兴公园。园内有法式园林景观。'),
    dict(name='思南书局', lat=31.2129, lon=121.4647, category='书店 · 老建筑',
         source='https://english.shanghai.gov.cn/en-BookstoresLibraries/20231221/8576791e48014165a74d8be2d17640b6.html',
         note='往复兴中路走走，在 517 号的思南书局翻几页书。第一次推荐先按附近发现，不假设你喜欢书店。'),
    dict(name='思南公馆', lat=31.2134, lon=121.4640, category='街区 · 建筑漫步',
         source='https://english.shanghai.gov.cn/en-SpecialtyShoppingAreas/20231217/2df63b2e96954fa093384679eaba9b49.html',
         note='如果想继续逛街区，可以看看思南公馆的花园洋房与里弄建筑。'),
]
