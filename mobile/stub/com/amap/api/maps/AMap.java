package com.amap.api.maps;

import com.amap.api.maps.model.LatLng;
import com.amap.api.maps.model.Marker;
import com.amap.api.maps.model.MarkerOptions;
import com.amap.api.maps.model.Polygon;
import com.amap.api.maps.model.PolygonOptions;
import com.amap.api.maps.model.Polyline;
import com.amap.api.maps.model.PolylineOptions;

public final class AMap {

    public interface OnMapClickListener {
        void onMapClick(LatLng latLng);
    }

    public UiSettings getUiSettings() { return null; }
    public void setOnMapClickListener(OnMapClickListener l) { }
    public Marker addMarker(MarkerOptions o) { return null; }
    public Polyline addPolyline(PolylineOptions o) { return null; }
    public Polygon addPolygon(PolygonOptions o) { return null; }
    public void moveCamera(CameraUpdate u) { }
}
