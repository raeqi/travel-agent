"""Official AMap facts adapter and a small, attributed public-experience sample.

No platform review scraping, key exposure, provider-data persistence or arbitrary
URL fetching. Provider coordinates are GCJ-02 and never overwrite WGS84 points.
"""
import json
import math
import os
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

PUBLIC_EXPERIENCES = {
    '复兴公园': [{
        'source_type': 'public_ugc', 'platform': 'Trip.com 游记',
        'author': 'Travelwithfei', 'published': '2025-06-19',
        'checked_on': '2026-11-01', 'sample_count': 1,
        'url': 'https://www.trip.com/moments/detail/shanghai-2-133118715/',
        'summary': '一位作者记录了早晨看到太极、舞蹈和打牌的体验，并建议早晨到访。',
        'limitation': '单篇历史游记，不能证明今天安静、开放或人少。',
    }],
}

def provider_status():
    return {'amap': {'configured': bool(os.environ.get('AMAP_WEB_SERVICE_KEY')), 'reviews_supported': False},
            'google': {'configured': False, 'reason': '当前底图未接入 Google Maps，不混入其 Places 内容'},
            'dianping': {'configured': False, 'reason': '尚未取得评论接口合作权限'},
            'live_crowd': {'configured': False, 'reason': '动画与热度均为演示'}}

def public_experiences(place):
    # Curated item is bound to our known Shanghai POI, not every namesake.
    if place.get('origin') != 'nearby':
        return []
    return PUBLIC_EXPERIENCES.get(place['name'], [])

def validate_experience(d):
    result = {}
    for field, limit in [('summary',500),('author',120),('platform',80),('url',1000),('published',10)]:
        value=d.get(field)
        if not isinstance(value,str) or not value.strip() or len(value.strip())>limit:
            raise ValueError(field+' 为空或过长')
        result[field]=value.strip()
    u=urlparse(result['url'])
    if u.scheme != 'https' or not u.hostname or u.username or u.password:
        raise ValueError('来源必须是有效的 HTTPS 网页链接')
    try:
        published=date.fromisoformat(result['published'])
    except ValueError:
        raise ValueError('发布日期需要 YYYY-MM-DD')
    if published > datetime.now(ZoneInfo('Asia/Shanghai')).date():
        raise ValueError('发布日期不能在未来')
    result['source_type']='user_supplied'
    result['limitation']='用户提供的来源摘要，系统未核实原文；不代表整体口碑或实时人流。'
    return result

def fetch_amap_facts(place):
    key=os.environ.get('AMAP_WEB_SERVICE_KEY')
    if not key:
        return {'status':'not_configured','provider':'高德地图','message':'高德地图尚未连接，暂时没有平台评分或营业信息。'}
    if not (30.7<float(place['lat'])<31.9 and 120.8<float(place['lon'])<122.1):
        return {'status':'unsupported_region','provider':'高德地图','message':'当前适配器只匹配上海地点，避免跨城市同名误配。'}
    query=urlencode({'key':key,'keywords':place['name'],'region':'310100','city_limit':'true','page_size':10,'show_fields':'business,navi,photos'})
    req=Request('https://restapi.amap.com/v5/place/text?'+query,headers={'User-Agent':'WanderLocal/0.1'})
    try:
        with urlopen(req,timeout=10) as r:
            data=json.loads(r.read(1_000_000))
    except Exception:
        # Never expose exception URLs containing the API key.
        return {'status':'error','provider':'高德地图','message':'高德请求失败，请检查网络及密钥权限。'}
    if not isinstance(data,dict) or str(data.get('status'))!='1':
        return {'status':'error','provider':'高德地图','message':'高德未返回成功结果，请检查接口权限或配额。'}
    pois=data.get('pois')
    if not isinstance(pois,list):
        return {'status':'error','provider':'高德地图','message':'高德返回的数据格式异常。'}
    matches=[p for p in pois if isinstance(p,dict) and p.get('name')==place['name']]
    if len(matches)!=1:
        return {'status':'ambiguous' if matches else 'not_found','provider':'高德地图','message':'地点无法唯一匹配，暂不展示评分，避免同名误配。'}
    poi=matches[0]
    raw=poi.get('location','').split(',')
    try:
        lon,lat=map(float,raw)
        # GCJ-02 offset is deliberately not treated as exact WGS84; allow a
        # conservative ~1.5 km bound, rejecting unrelated distant namesakes.
        meters=math.hypot((lat-float(place['lat']))*111000,(lon-float(place['lon']))*95000)
        if not math.isfinite(meters) or meters>1500:
            raise ValueError()
    except (ValueError,TypeError):
        return {'status':'ambiguous','provider':'高德地图','message':'地点坐标与现有记录不一致，需要人工确认。'}
    business=poi.get('business') or {}
    if not isinstance(business,dict):
        business={}
    return {'status':'ok','provider':'高德地图','retrieved_at':time.time(), 'poi_id':poi.get('id'),
            'name':poi.get('name'),'address':poi.get('address'),
            'rating':business.get('rating') or None,'cost':business.get('cost') or None,
            'opening_description':business.get('opentime_today') or business.get('opentime_week') or None,
            'source_url':'https://www.amap.com/place/'+str(poi.get('id','')),
            'coordinate_system':'GCJ-02','coordinate_used_for_map':False,
            'live_crowd':None,'reviews':[],
            'limitation':'评分为平台汇总，营业描述不等于已确认当前开放；未获取评论正文或实时客流。'}
