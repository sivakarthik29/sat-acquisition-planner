import { useEffect, useRef } from "react";
import L from "leaflet";

// Leaflet is used directly (no wrapper library) to keep the dependency list short.
export default function MapView({ points, onPick, focus, fitSignal }) {
  const el = useRef(null);
  const map = useRef(null);
  const layer = useRef(null);
  const pick = useRef(onPick);
  pick.current = onPick;

  useEffect(() => {
    const m = L.map(el.current, {
      zoomControl: true,
      worldCopyJump: true,
    }).setView([21.5, 78.5], 5);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
    }).addTo(m);
    m.on("click", (e) => pick.current(e.latlng.lat, e.latlng.lng));
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => m.remove();
  }, []);

  useEffect(() => {
    layer.current.clearLayers();
    points.forEach((p) => {
      // The footprint circle has the same area as the requested AOI, so its size is honest.
      L.circle([p.lat, p.lon], {
        radius: Math.sqrt(p.area_km2 / Math.PI) * 1000,
        color: "#0E2233",
        weight: 1,
        fillOpacity: 0.12,
      }).addTo(layer.current);
      L.marker([p.lat, p.lon], {
        icon: L.divIcon({
          className: "",
          html: `<span class="pin${p.muted ? " muted" : ""}"></span>`,
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        }),
        interactive: !!p.label,
      })
        .bindTooltip(p.label || "", { direction: "top", offset: [0, -8] })
        .addTo(layer.current);
    });
  }, [points]);

  useEffect(() => {
    if (focus && map.current)
      map.current.setView(
        [focus.lat, focus.lon],
        Math.max(map.current.getZoom(), 7),
      );
  }, [focus]);

  // Zoom to show every target when the set changes in bulk (example set, tab switch).
  const latest = useRef(points);
  latest.current = points;
  useEffect(() => {
    const pts = latest.current;
    if (!map.current || pts.length === 0) return;
    map.current.fitBounds(L.latLngBounds(pts.map((q) => [q.lat, q.lon])), {
      padding: [60, 60],
      maxZoom: 8,
    });
  }, [fitSignal]);

  return (
    <div
      ref={el}
      className="map"
      role="application"
      aria-label="Map. Click to choose a target."
    />
  );
}
