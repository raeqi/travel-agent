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

# Published store listings, checked 2026-11-01. Approximate neighborhood pins;
# addresses identify the actual stores. No live availability or price claims.
PLACES += [
    dict(name='COVA（新天地店）',lat=31.2202,lon=121.4704,category='咖啡 · 甜点',
         source='https://www.pasticceriacova.com/zh-hans/pages/xintiandi',
         note='太仓路181弄17号01C-2。品牌门店页列有咖啡、糕点和下午茶，可作为走累后的停靠点；请出发前确认营业。'),
    dict(name='半岛精品店与咖啡厅（新天地）',lat=31.2200,lon=121.4708,category='咖啡 · 下午茶',
         source='https://english.shanghai.gov.cn/en-TrendyStoresinShanghai/20240126/026b320bac27403ebf56c435ae782e8c.html',
         note='太仓路181弄16号1单元。公开介绍列有咖啡、烘焙和户外座位；不是外滩半岛酒店内的门店，营业待确认。'),
    dict(name='Polux（新天地）',lat=31.2196,lon=121.4704,category='餐厅 · 法式小馆',
         source='https://english.shanghai.gov.cn/en-Restaurants/20250303/9abcc0d313724a1f9735332e08f28892.html',
         note='太仓路181弄新天地北里5号。公开介绍为法式休闲餐厅，有户外座位；菜单、价格和营业以店铺确认为准。'),
    dict(name='Gaga Coast（新天地）',lat=31.2204,lon=121.4706,category='餐厅 · 早午餐',
         source='https://english.shanghai.gov.cn/en-Restaurants/20250303/9abcc0d313724a1f9735332e08f28892.html',
         note='太仓路181弄18号02单元。公开介绍列有三明治、意面等早午餐选择；当前菜单与营业待确认。'),
    dict(name='复兴面包房（INS Park）',lat=31.2165,lon=121.4667,category='餐厅 · 烘焙轻食',
         source='https://english.shanghai.gov.cn/en-Restaurants/20250303/9abcc0d313724a1f9735332e08f28892.html',
         note='雁荡路109号INS Park F102。公开介绍兼有烘焙与轻食、户外座位；不是仅售面包的店，营业待确认。'),
]
