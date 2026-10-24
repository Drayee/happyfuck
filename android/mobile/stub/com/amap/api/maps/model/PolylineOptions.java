package com.amap.api.maps.model;

public final class PolylineOptions {
    public PolylineOptions add(LatLng p) { return this; }
    public PolylineOptions addAll(Iterable<LatLng> pts) { return this; }
    public PolylineOptions color(int color) { return this; }
    public PolylineOptions width(float width) { return this; }
}
