import type { Area } from "../lib/geo";
import type { AreaSeries, BBox, DatasetMeta, HotspotRow, Metric, Sensor } from "./contract";

export interface AreaQuery {
  area: Area;
  /** The area is the whole region: use every cell. */
  whole: boolean;
  metric: Metric;
  /** Leave out cells with persistent industrial / waste-burning sources. */
  excludePersistent: boolean;
}

export interface CellQuery {
  sensor: Sensor;
  metric: Metric;
  from: number; // month index, inclusive
  to: number;
  excludePersistent: boolean;
}

export type CellValues = Map<string, { lat: number; lon: number; value: number }>;

/**
 * A data source: the region's description, an area's monthly record, and per-cell values for the
 * map. Sums, bands and anomalies for an area are computed server-side. The API (fed by the pipeline) is the
 * only implementation: users cannot load their own files.
 */
export interface DataSource {
  id: string;
  label: string;
  description?: string;
  load(): Promise<DatasetMeta>;
  areaSeries(q: AreaQuery, signal?: AbortSignal): Promise<AreaSeries>;
  cellWindow(q: CellQuery, signal?: AbortSignal): Promise<CellValues>;
  /** Individual detections. The API does not serve them (it stores fire-days), so this is unset for now. */
  hotspots?(range: [number, number], bbox: BBox, limit: number): Promise<HotspotRow[]>;
}
