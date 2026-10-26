package com.amap.api.maps;

import android.content.Context;

/**
 * 高德地图 SDK 隐私合规入口（编译期 stub）。
 *
 * 不调用 updatePrivacyShow / updatePrivacyAgree 就开始用地图，
 * SDK 会直接拒绝渲染并报 errorCode 555570（隐私合规校验失败）。
 */
public final class MapsInitializer {

    public static synchronized void updatePrivacyShow(Context ctx,
                                                      boolean hasShow,
                                                      boolean hasAgree) { }

    public static synchronized void updatePrivacyAgree(Context ctx, boolean agree) { }
}
