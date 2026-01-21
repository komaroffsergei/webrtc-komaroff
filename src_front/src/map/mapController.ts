import maplibregl, { type LngLatBoundsLike, type Map, type GeoJSONSource } from "maplibre-gl";

export type Airport = {
  id?: string;
  code?: string;
  name?: string;
  lat: number;
  lon: number;
  status?: string;
};

export type RouteArtifact = {
  from?: Record<string, unknown>;
  to?: Record<string, unknown>;
  geometry: [number, number][];
  distance_km?: number;
};

export class MapController {
  private map: Map | null = null;
  private ready = false;
  private pendingAirports: Airport[] | null = null;
  private pendingPos: { lat: number; lon: number } | null = null;
  private pendingRoute: RouteArtifact | null = null;

  init(containerId: string): void {
    if (this.map) return;

    this.map = new maplibregl.Map({
      container: containerId,
      style: "https://demotiles.maplibre.org/style.json",
      center: [37.6173, 55.7558],
      zoom: 6,
    });

    this.map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-left");

    this.map.on("load", () => {
      if (!this.map) return;

      this.map.addSource("airports", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      this.map.addLayer({
        id: "airports",
        type: "circle",
        source: "airports",
        paint: {
          "circle-radius": 5,
          "circle-color": "#ffb020",
          "circle-stroke-color": "#1d1d1f",
          "circle-stroke-width": 1,
        },
      });

      this.map.addSource("position", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      this.map.addLayer({
        id: "position",
        type: "circle",
        source: "position",
        paint: {
          "circle-radius": 7,
          "circle-color": "#007aff",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
        },
      });

      this.map.addSource("route", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      this.map.addLayer({
        id: "route",
        type: "line",
        source: "route",
        paint: {
          "line-color": "#007aff",
          "line-width": 4,
        },
      });

      this.ready = true;
      if (this.pendingAirports) this.setAirports(this.pendingAirports);
      if (this.pendingPos) this.setCurrentPosition(this.pendingPos.lat, this.pendingPos.lon);
      if (this.pendingRoute) this.drawRoute(this.pendingRoute);
    });
  }

  setAirports(airports: Airport[]): void {
    if (!this.map || !this.ready) {
      this.pendingAirports = airports;
      return;
    }
    const source = this.map.getSource("airports") as GeoJSONSource;
    source.setData({
      type: "FeatureCollection",
      features: airports.map((a) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [a.lon, a.lat] },
        properties: {
          id: a.id ?? "",
          code: a.code ?? "",
          name: a.name ?? "",
          status: a.status ?? "",
        },
      })),
    });
  }

  setCurrentPosition(lat: number, lon: number): void {
    if (!this.map || !this.ready) {
      this.pendingPos = { lat, lon };
      return;
    }
    const source = this.map.getSource("position") as GeoJSONSource;
    source.setData({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [lon, lat] },
          properties: {},
        },
      ],
    });
  }

  drawRoute(route: RouteArtifact): void {
    if (!this.map || !this.ready) {
      this.pendingRoute = route;
      return;
    }
    const source = this.map.getSource("route") as GeoJSONSource;
    source.setData({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "LineString", coordinates: route.geometry },
          properties: { distance_km: route.distance_km ?? null },
        },
      ],
    });

    const bounds = this.boundsForCoords(route.geometry);
    if (bounds) {
      this.map.fitBounds(bounds, { padding: 60, duration: 800 });
    }
  }

  private boundsForCoords(coords: [number, number][]): LngLatBoundsLike | null {
    if (!coords.length) return null;
    let minLon = coords[0][0];
    let maxLon = coords[0][0];
    let minLat = coords[0][1];
    let maxLat = coords[0][1];
    for (const [lon, lat] of coords) {
      minLon = Math.min(minLon, lon);
      maxLon = Math.max(maxLon, lon);
      minLat = Math.min(minLat, lat);
      maxLat = Math.max(maxLat, lat);
    }
    return [
      [minLon, minLat],
      [maxLon, maxLat],
    ];
  }
}
