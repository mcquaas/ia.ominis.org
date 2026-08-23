"use client";

import { useEffect, useMemo } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

export type AllCanMapOrg = {
  id: number;
  name: string;
  address?: string | null;
  url?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  state?: string | null;
  city?: string | null;
  type?: string | null;
  specialty?: string | null;
};

const MEXICO_CENTER: [number, number] = [23.6345, -102.5528];
const DEFAULT_ZOOM = 5;

function parseCoord(o: AllCanMapOrg): { lat: number; lng: number } | null {
  const lat = o.latitude?.trim();
  const lng = o.longitude?.trim();
  if (!lat || !lng) return null;
  const la = Number(lat);
  const ln = Number(lng);
  if (Number.isNaN(la) || Number.isNaN(ln)) return null;
  if (la < -90 || la > 90 || ln < -180 || ln > 180) return null;
  return { lat: la, lng: ln };
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) {
      map.setView(MEXICO_CENTER, DEFAULT_ZOOM);
      return;
    }
    if (points.length === 1) {
      map.setView(points[0], 12);
      return;
    }
    const b = L.latLngBounds(points);
    map.fitBounds(b, { padding: [40, 40], maxZoom: 14 });
  }, [map, points]);
  return null;
}

type MarkerRow = { key: number; pos: [number, number]; org: AllCanMapOrg };

function FocusOnId({ focusId, markers }: { focusId?: number | null; markers: MarkerRow[] }) {
  const map = useMap();
  useEffect(() => {
    if (focusId == null || markers.length === 0) return;
    const m = markers.find((x) => x.key === focusId);
    if (!m) return;
    map.setView(m.pos, Math.max(map.getZoom(), 13), { animate: true });
  }, [focusId, map, markers]);
  return null;
}

/** Fix default marker assets when bundled (Leaflet + Next). */
function useFixLeafletIcons() {
  useEffect(() => {
    const iconUrl = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png";
    const iconRetinaUrl = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png";
    const shadowUrl = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png";
    const DefaultIcon = L.icon({ iconUrl, iconRetinaUrl, shadowUrl, iconSize: [25, 41], iconAnchor: [12, 41] });
    L.Marker.prototype.options.icon = DefaultIcon;
  }, []);
}

export default function AllCanLeafletMap({
  organizations,
  focusId,
}: {
  organizations: AllCanMapOrg[];
  focusId?: number | null;
}) {
  useFixLeafletIcons();

  const markers = useMemo(() => {
    const out: MarkerRow[] = [];
    for (const o of organizations) {
      const c = parseCoord(o);
      if (!c) continue;
      out.push({ key: o.id, pos: [c.lat, c.lng], org: o });
    }
    return out;
  }, [organizations]);

  const points = useMemo(() => markers.map((m) => m.pos), [markers]);

  if (markers.length === 0) {
    return (
      <div className="flex h-[min(360px,40vh)] w-full items-center justify-center rounded-lg border border-white/10 bg-[#0a1628]/80 text-sm text-gray-400">
        Ninguna entrada en esta vista tiene latitud/longitud para el mapa.
      </div>
    );
  }

  return (
    <div className="relative h-[min(360px,40vh)] w-full overflow-hidden rounded-lg border border-white/10 z-0">
      <MapContainer
        center={points[0] ?? MEXICO_CENTER}
        zoom={DEFAULT_ZOOM}
        className="h-full w-full [&_.leaflet-tile-pane]:brightness-[0.85] [&_.leaflet-tile-pane]:contrast-[1.05]"
        scrollWheelZoom
        aria-label="Mapa de organizaciones All.Can"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds points={points} />
        <FocusOnId focusId={focusId} markers={markers} />
        {markers.map(({ key, pos, org }) => (
          <Marker key={key} position={pos}>
            <Popup>
              <div className="min-w-[200px] text-gray-900">
                <p className="font-semibold leading-snug">{org.name}</p>
                <p className="text-xs text-gray-600 mt-1">
                  {[org.type, org.specialty].filter(Boolean).join(" · ")}
                </p>
                {(org.city || org.state) && (
                  <p className="text-xs text-gray-600">{[org.city, org.state].filter(Boolean).join(", ")}</p>
                )}
                {org.address && <p className="text-xs text-gray-500 mt-1">{org.address}</p>}
                {org.url && (
                  <a
                    href={org.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-orange-700 underline mt-2 inline-block"
                  >
                    Sitio web
                  </a>
                )}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
