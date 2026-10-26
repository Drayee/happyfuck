#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
坐标系转换 —— WGS84 / GCJ-02 / BD-09

为什么必须搞清这个
------------------
乐健的整条链路是 GCJ-02（火星坐标），不是 WGS84：

  AMapLocationClientOption.isOffset()  →  返回 this.s
  构造函数 this.s = true                →  高德默认开启坐标偏移
  LocationService.java:1063
      new LatLng(aMapLocation.getLatitude(), aMapLocation.getLongitude())
      →  直接拿 AMapLocation 的经纬度，零转换
  UniLatLngRespBean.toLatLng():121
      new LatLng(latitude, longitude)   →  服务端打卡点也是零转换

所以：
  - routineLine / signPoint 必须是 GCJ-02
  - 服务端下发的 signPoint / rangeRunningRegion 也是 GCJ-02
  - 两者在同一坐标系里直接比较距离（AMapUtils.calculateLineDistance）

如果你从 Google Earth / 手机 GPS 原始读数（WGS84）取坐标，
在中国境内会偏移 300~700 米，轨迹直接落到围栏外。

偏移量参考（中国境内）
----------------------
  WGS84 → GCJ-02 : 约 +100~700m，随经纬度变化，无解析解，只能用多项式逼近
  GCJ-02 → BD-09  : 约 +200~300m，有解析公式
"""
import math

__all__ = [
    'wgs84_to_gcj02', 'gcj02_to_wgs84',
    'gcj02_to_bd09', 'bd09_to_gcj02',
    'out_of_china', 'detect_system',
]

_A = 6378245.0                  # 克拉索夫斯基椭球长半轴
_EE = 0.00669342162296594323    # 偏心率平方
_X_PI = math.pi * 3000.0 / 180.0


def out_of_china(lat, lon):
    """粗略判断是否在中国境外（境外不做偏移）。"""
    return not (73.66 < lon < 135.05 and 3.86 < lat < 53.55)


def _transform_lat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lat, lon):
    """WGS84（GPS 原始）-> GCJ-02（高德/腾讯/乐健）。"""
    if out_of_china(lat, lon):
        return lat, lon
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (_A / sqrtmagic * math.cos(radlat) * math.pi)
    return lat + dlat, lon + dlon


def gcj02_to_wgs84(lat, lon):
    """GCJ-02 -> WGS84（迭代逼近，精度 < 1m）。"""
    if out_of_china(lat, lon):
        return lat, lon
    # 先用一次近似，再迭代修正
    wlat, wlon = lat, lon
    for _ in range(3):
        glat, glon = wgs84_to_gcj02(wlat, wlon)
        wlat += lat - glat
        wlon += lon - glon
    return wlat, wlon


def gcj02_to_bd09(lat, lon):
    """GCJ-02 -> BD-09（百度）。

    标准公式里 x=经度, y=纬度：
        z     = sqrt(x^2 + y^2) + 0.00002 * sin(y * PI)
        theta = atan2(y, x) + 0.000003 * cos(y * PI)
        bd_lon = z * cos(theta) + 0.0065
        bd_lat = z * sin(theta) + 0.006
    """
    x, y = lon, lat
    z = math.sqrt(x * x + y * y) + 0.00002 * math.sin(y * _X_PI)
    theta = math.atan2(y, x) + 0.000003 * math.cos(y * _X_PI)
    bd_lon = z * math.cos(theta) + 0.0065
    bd_lat = z * math.sin(theta) + 0.006
    return bd_lat, bd_lon


def bd09_to_gcj02(lat, lon):
    """BD-09 -> GCJ-02（百度逆变换）。"""
    x, y = lon - 0.0065, lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * _X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(y * _X_PI)
    gcj_lon = z * math.cos(theta)
    gcj_lat = z * math.sin(theta)
    return gcj_lat, gcj_lon


def detect_system(lat, lon):
    """
    粗判一对坐标可能属于哪套系统（仅启发式，不能保证）。
    在中国境内，GCJ-02 与 WGS84 差异 100~700m，无法凭单点判断。
    这里只给出"是否在境内"和"偏移量"参考。
    """
    if out_of_china(lat, lon):
        return {'in_china': False, 'note': '境外，三套坐标系基本重合'}
    glat, glon = wgs84_to_gcj02(lat, lon)
    dlat = (glat - lat) * 111320
    dlon = (glon - lon) * 111320 * math.cos(math.radians(lat))
    dist = math.hypot(dlat, dlon)
    return {
        'in_china': True,
        'if_wgs84_then_gcj_offset_m': round(dist, 1),
        'note': '若此点实际是 WGS84，转 GCJ-02 会移动约 %.0f 米' % dist,
    }
