"use client";

import "leaflet/dist/leaflet.css";

import { useEffect, useMemo } from "react";
import L, { type LatLngBoundsExpression, type LatLngExpression } from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

export type ItineraryMapPoint = {
  latitude: number;
  longitude: number;
  label: string;
  kind: "hotel" | "activity";
  dayNumber?: number;
  detail?: string;
};

const HOTEL_COLOR = "#d76c4e";
const ACTIVITY_COLOR = "#10212b";

function createPinIcon(color: string, label: string) {
  const safeLabel = label.replace(/[<>&]/g, "");
  return L.divIcon({
    className: "tripbreeze-map-pin",
    iconSize: [26, 34],
    iconAnchor: [13, 32],
    popupAnchor: [0, -28],
    html: `
      <div style="position:relative;width:26px;height:34px;">
        <div style="
          position:absolute;inset:0;
          background:${color};
          border-radius:50% 50% 50% 0;
          transform:rotate(-45deg);
          box-shadow:0 4px 10px rgba(16,33,43,0.25);
          border:2px solid #ffffff;
        "></div>
        <div style="
          position:absolute;top:5px;left:0;right:0;
          text-align:center;
          color:#ffffff;
          font-size:11px;
          font-weight:700;
          font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
          line-height:16px;
        ">${safeLabel}</div>
      </div>
    `,
  });
}

function FitBounds({ bounds }: { bounds: LatLngBoundsExpression | null }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) {
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 });
    }
  }, [bounds, map]);
  return null;
}

export default function ItineraryMap({ points }: { points: ItineraryMapPoint[] }) {
  const validPoints = useMemo(
    () =>
      points.filter(
        (point) =>
          Number.isFinite(point.latitude) &&
          Number.isFinite(point.longitude) &&
          Math.abs(point.latitude) <= 90 &&
          Math.abs(point.longitude) <= 180,
      ),
    [points],
  );

  const bounds = useMemo<LatLngBoundsExpression | null>(() => {
    if (!validPoints.length) return null;
    return validPoints.map((point) => [point.latitude, point.longitude] as [number, number]);
  }, [validPoints]);

  const center = useMemo<LatLngExpression>(() => {
    if (validPoints.length) {
      return [validPoints[0].latitude, validPoints[0].longitude];
    }
    return [48.8566, 2.3522];
  }, [validPoints]);

  if (!validPoints.length) {
    return null;
  }

  return (
    <div className="overflow-hidden rounded-[1.3rem] border border-ink/10">
      <MapContainer
        center={center}
        zoom={12}
        scrollWheelZoom={false}
        style={{ height: "360px", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {validPoints.map((point, index) => {
          const isHotel = point.kind === "hotel";
          const label = isHotel ? "H" : String(point.dayNumber ?? index + 1);
          const icon = createPinIcon(isHotel ? HOTEL_COLOR : ACTIVITY_COLOR, label);
          return (
            <Marker
              key={`${point.kind}-${index}-${point.latitude}-${point.longitude}`}
              position={[point.latitude, point.longitude]}
              icon={icon}
            >
              <Popup>
                <div className="text-sm">
                  <div className="font-semibold">{point.label}</div>
                  {point.detail ? <div className="mt-1 text-xs text-slate">{point.detail}</div> : null}
                  {!isHotel && point.dayNumber ? (
                    <div className="mt-1 text-xs text-slate">Day {point.dayNumber}</div>
                  ) : null}
                </div>
              </Popup>
            </Marker>
          );
        })}
        <FitBounds bounds={bounds} />
      </MapContainer>
    </div>
  );
}
