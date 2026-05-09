"use client";

// LiveMap v3 — pure black tactical map.
//   - CARTO dark-matter tiles
//   - controls hidden until hover (CSS in map-styles.css)
//   - fitBounds the actual highway-aligned route on first paint, then locks
//   - clickable head marker → live telemetry popup
//   - panic ring overlay when shipment is COMPROMISED
//   - optional headOverride: when scrubber is dragged into the past, the
//     marker jumps to the historical lat/lng/index without moving the camera

import { useEffect, useMemo, useRef } from "react";
import maplibregl, { type Map as MlMap, type LngLatLike } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { ShipmentDetail, Telemetry } from "@/lib/api";

const STYLE_URL =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const SRC_FULL = "vt-route-full";
const SRC_TRAVELED = "vt-route-traveled";
const LYR_FULL = "vt-route-full-line";
const LYR_TRAVELED_GLOW = "vt-route-traveled-glow";
const LYR_TRAVELED = "vt-route-traveled-line";

interface Props {
  shipment: ShipmentDetail;
  /** When set, marker + traveled segment use this telemetry instead of live. */
  scrubTelemetry?: Telemetry | null;
}

function endpointEl(color: string, label: string) {
  const el = document.createElement("div");
  el.className = "vt-pin";
  el.style.setProperty("--c", color);
  el.innerHTML = `
    <span class="vt-pin__ring"></span>
    <span class="vt-pin__dot"></span>
    <span class="vt-pin__label">${label}</span>
  `;
  return el;
}

function haversine(a: [number, number], b: [number, number]) {
  const R = 6371_000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b[1] - a[1]);
  const dLng = toRad(b[0] - a[0]);
  const lat1 = toRad(a[1]);
  const lat2 = toRad(b[1]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function totalKm(path: [number, number][], from = 0, to = path.length - 1) {
  let m = 0;
  for (let i = from + 1; i <= to; i++) m += haversine(path[i - 1], path[i]);
  return m / 1000;
}

function nearestRouteIndex(
  path: [number, number][],
  lng: number,
  lat: number
): number {
  let best = 0;
  let bestD = Infinity;
  for (let i = 0; i < path.length; i++) {
    const dl = path[i][0] - lng;
    const da = path[i][1] - lat;
    const d = dl * dl + da * da;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

function popupHTML(
  s: ShipmentDetail,
  telemetry: Telemetry | undefined,
  traveledKm: number,
  totalRouteKm: number
) {
  const remain = Math.max(0, totalRouteKm - traveledKm);
  const eta = s.etaAt ? new Date(s.etaAt) : null;
  const fmt = (v?: number | null, d = 1) => (v == null ? "—" : v.toFixed(d));
  return `
    <div>
      <div class="vt-pop__head">
        <span class="vt-pop__chip">LIVE</span>
        <span class="vt-pop__code">${s.trackingCode}</span>
      </div>
      <div class="vt-pop__title">${s.asset}</div>
      <div class="vt-pop__grid">
        <div class="vt-pop__cell"><div class="vt-pop__k">Temp</div><div class="vt-pop__v">${fmt(telemetry?.tempC,1)}<span>°C</span></div></div>
        <div class="vt-pop__cell"><div class="vt-pop__k">Shock</div><div class="vt-pop__v">${fmt(telemetry?.shockG,2)}<span>G</span></div></div>
        <div class="vt-pop__cell"><div class="vt-pop__k">Speed</div><div class="vt-pop__v">${fmt(telemetry?.speedKph,0)}<span>km/h</span></div></div>
        <div class="vt-pop__cell"><div class="vt-pop__k">Battery</div><div class="vt-pop__v">${fmt(telemetry?.battery,0)}<span>%</span></div></div>
        <div class="vt-pop__cell"><div class="vt-pop__k">Humidity</div><div class="vt-pop__v">${fmt(telemetry?.humidity,0)}<span>%</span></div></div>
        <div class="vt-pop__cell"><div class="vt-pop__k">Tilt</div><div class="vt-pop__v">${fmt(telemetry?.tilt,1)}<span>°</span></div></div>
      </div>
      <div class="vt-pop__route">
        <span>${traveledKm.toFixed(0)} km · traveled</span>
        <span>${remain.toFixed(0)} km · left</span>
      </div>
      ${eta ? `<div class="vt-pop__eta">ETA · ${eta.toLocaleString(undefined,{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"})}</div>` : ""}
    </div>
  `;
}

export function LiveMap({ shipment, scrubTelemetry }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MlMap | null>(null);
  const headMarkerRef = useRef<maplibregl.Marker | null>(null);
  const originMarkerRef = useRef<maplibregl.Marker | null>(null);
  const destMarkerRef = useRef<maplibregl.Marker | null>(null);
  const headElRef = useRef<HTMLDivElement | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const shipmentRef = useRef<ShipmentDetail>(shipment);
  shipmentRef.current = shipment;

  const route = shipment.routePath ?? [];

  // Effective head: scrubbed telemetry's lat/lng (if present), otherwise live.
  const headData = useMemo(() => {
    if (
      scrubTelemetry &&
      scrubTelemetry.lng != null &&
      scrubTelemetry.lat != null &&
      route.length > 0
    ) {
      const idx = nearestRouteIndex(route, scrubTelemetry.lng, scrubTelemetry.lat);
      return { idx, coord: route[idx] as [number, number], telemetry: scrubTelemetry };
    }
    const idx = Math.min(shipment.routeIndex, Math.max(0, route.length - 1));
    return {
      idx,
      coord: route.length > 0 ? (route[idx] as [number, number]) : ([0, 30] as [number, number]),
      telemetry: shipment.telemetries.at(-1),
    };
  }, [route, scrubTelemetry, shipment.routeIndex, shipment.telemetries]);

  const compromised = shipment.status === "COMPROMISED";
  const accent = compromised ? "#FB923C" : "#22D3EE";

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: headData.coord as LngLatLike,
      zoom: 5,
      attributionControl: { compact: true },
      pitch: 0,
      dragRotate: false,
    });
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false, visualizePitch: false }),
      "top-right"
    );
    mapRef.current = map;
    return () => {
      popupRef.current?.remove();
      popupRef.current = null;
      map.remove();
      mapRef.current = null;
      headMarkerRef.current = null;
      originMarkerRef.current = null;
      destMarkerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || route.length < 2) return;

    const apply = () => {
      const traveled = route.slice(0, headData.idx + 1);
      const fullGeo = {
        type: "Feature" as const,
        properties: {},
        geometry: { type: "LineString" as const, coordinates: route },
      };
      const traveledGeo = {
        type: "Feature" as const,
        properties: {},
        geometry: { type: "LineString" as const, coordinates: traveled },
      };

      const fullSrc = map.getSource(SRC_FULL) as maplibregl.GeoJSONSource | undefined;
      if (fullSrc) fullSrc.setData(fullGeo);
      else {
        map.addSource(SRC_FULL, { type: "geojson", data: fullGeo });
        map.addLayer({
          id: LYR_FULL,
          type: "line",
          source: SRC_FULL,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": "#3A4452",
            "line-width": 1.6,
            "line-opacity": 0.45,
            "line-dasharray": [1.2, 1.6],
          },
        });
      }

      const tSrc = map.getSource(SRC_TRAVELED) as maplibregl.GeoJSONSource | undefined;
      if (tSrc) tSrc.setData(traveledGeo);
      else {
        map.addSource(SRC_TRAVELED, { type: "geojson", data: traveledGeo });
        map.addLayer({
          id: LYR_TRAVELED_GLOW,
          type: "line",
          source: SRC_TRAVELED,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": accent,
            "line-width": 12,
            "line-opacity": 0.18,
            "line-blur": 10,
          },
        });
        map.addLayer({
          id: LYR_TRAVELED,
          type: "line",
          source: SRC_TRAVELED,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": accent,
            "line-width": 2.4,
            "line-opacity": 0.95,
          },
        });
      }
      if (map.getLayer(LYR_TRAVELED)) {
        map.setPaintProperty(LYR_TRAVELED, "line-color", accent);
        map.setPaintProperty(LYR_TRAVELED_GLOW, "line-color", accent);
      }

      const origin = route[0];
      const dest = route[route.length - 1];
      if (!originMarkerRef.current) {
        originMarkerRef.current = new maplibregl.Marker({
          element: endpointEl("#5B6776", "PRAGUE"),
          anchor: "bottom",
        }).setLngLat(origin).addTo(map);
      }
      if (!destMarkerRef.current) {
        destMarkerRef.current = new maplibregl.Marker({
          element: endpointEl("#22D3EE", "MÁLAGA"),
          anchor: "bottom",
        }).setLngLat(dest).addTo(map);
      }

      if (!headMarkerRef.current) {
        const el = document.createElement("div");
        el.className = "vt-head";
        el.innerHTML = `<span class="vt-head__pulse"></span><span class="vt-head__core"></span>`;
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          openPopup();
        });
        headElRef.current = el;
        headMarkerRef.current = new maplibregl.Marker({ element: el }).setLngLat(headData.coord).addTo(map);
      } else {
        headMarkerRef.current.setLngLat(headData.coord);
      }
      if (headElRef.current) {
        headElRef.current.style.setProperty("--vt-accent", accent);
      }

      if (popupRef.current) {
        const s = shipmentRef.current;
        const tKm = totalKm(s.routePath ?? [], 0, headData.idx);
        const totalR = totalKm(s.routePath ?? []);
        popupRef.current
          .setLngLat(headData.coord)
          .setHTML(popupHTML(s, headData.telemetry, tKm, totalR));
      }

      type FitFlag = MlMap & { __vtFit?: boolean };
      if (!(map as FitFlag).__vtFit) {
        const bounds = route.reduce(
          (b, c) => b.extend(c as LngLatLike),
          new maplibregl.LngLatBounds(route[0] as LngLatLike, route[0] as LngLatLike)
        );
        map.fitBounds(bounds, {
          padding: { top: 80, bottom: 70, left: 70, right: 70 },
          duration: 1100,
          maxZoom: 6.5,
        });
        (map as FitFlag).__vtFit = true;
      }
    };

    const openPopup = () => {
      const map = mapRef.current;
      if (!map) return;
      const s = shipmentRef.current;
      const tKm = totalKm(s.routePath ?? [], 0, headData.idx);
      const totalR = totalKm(s.routePath ?? []);
      if (popupRef.current) {
        popupRef.current.remove();
        popupRef.current = null;
        return;
      }
      popupRef.current = new maplibregl.Popup({
        offset: 18,
        closeButton: true,
        closeOnClick: false,
        anchor: "bottom",
        className: "vt-popup",
        maxWidth: "280px",
      })
        .setLngLat(headData.coord)
        .setHTML(popupHTML(s, headData.telemetry, tKm, totalR))
        .addTo(map);
      popupRef.current.on("close", () => { popupRef.current = null; });
    };

    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headData.idx, shipment.status, route.length, accent]);

  return (
    <div className="vt-mapwrap relative overflow-hidden rounded-2xl border border-white/[0.06] bg-black">
      <div ref={containerRef} className="h-[460px] w-full" />
      {compromised && <div className="vt-panic" aria-hidden />}

      <div className="pointer-events-none absolute bottom-3 left-3 z-10 rounded-full border border-white/10 bg-black/70 px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-white/50 backdrop-blur">
        {Math.round((headData.idx / Math.max(1, route.length - 1)) * 100)}% · click marker
      </div>
    </div>
  );
}
