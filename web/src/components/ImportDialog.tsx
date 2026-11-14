import { useRef, useState } from "react";
import { COLUMN_ALIASES } from "../config";
import type { DatasetMeta } from "../data/contract";
import { isFirmsHeader } from "../data/firms";
import { type DataSource, describeColumnMapping, uploadSource } from "../data/sources";
import { parseCsv, toCsv } from "../lib/csv";
import { downloadText } from "../lib/exporters";

interface Props {
  open: boolean;
  onClose: () => void;
  onLoad: (src: DataSource) => void;
}

const REQUIRED = new Set(["lat", "lon"]);

/** Load any contract-shaped CSV/JSON (optionally with meta.json) without touching code. */
export function ImportDialog({ open, onClose, onLoad }: Props) {
  const [file, setFile] = useState<{ name: string; records: Record<string, unknown>[]; header: string[] } | null>(null);
  const [meta, setMeta] = useState<Partial<DatasetMeta> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const metaInput = useRef<HTMLInputElement>(null);

  if (!open) return null;

  const readData = async (f: File) => {
    setError(null);
    try {
      const text = await f.text();
      if (f.name.endsWith(".json")) {
        const data = JSON.parse(text);
        const records = Array.isArray(data) ? data : data.rows;
        if (!Array.isArray(records)) throw new Error("JSON must be an array of rows or { rows: [...] }.");
        if (!Array.isArray(data) && data.meta) setMeta(data.meta);
        setFile({ name: f.name, records, header: Object.keys(records[0] ?? {}) });
      } else {
        const { header, records } = parseCsv(text);
        setFile({ name: f.name, records, header });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const firms = file ? isFirmsHeader(file.header) : false;
  const mapping = file && !firms ? describeColumnMapping(file.header) : [];
  const missing = mapping.filter((m) => REQUIRED.has(m.field) && !m.column).map((m) => m.field);

  const load = () => {
    if (!file) return;
    try {
      onLoad(uploadSource(file.name.replace(/\.(csv|json)$/i, ""), file.records, meta ?? {}));
      setFile(null);
      setMeta(null);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const template = () =>
    downloadText(
      "cells_monthly_template.csv",
      toCsv([
        { cell_id: "33.85_35.95", lat: 33.85, lon: 35.95, year: 2019, month: 10, sensor: "modis_raw", cell_days: 4, fire_count: 6, sum_frp: 152.3 },
        { cell_id: "33.85_35.95", lat: 33.85, lon: 35.95, year: 2019, month: 10, sensor: "viirs_raw", cell_days: 9, fire_count: 27, sum_frp: 240.1 },
        { cell_id: "33.85_35.95", lat: 33.85, lon: 35.95, year: 2019, month: 10, sensor: "harmonized", cell_days: 4.1, fire_count: 6.4, sum_frp: 158 },
      ]),
    );

  return (
    <div className="modal-scrim" role="dialog" aria-modal aria-labelledby="import-title" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="drawer-head">
          <div>
            <span className="eyebrow">Data source</span>
            <h2 id="import-title">Load your own data</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="modal-body">
          <p className="muted small">
            Drop a <code>cells_monthly</code> file (one row per cell × month × sensor) or a raw <b>NASA FIRMS</b> hotspot CSV, which is filtered and gridded here. Column names are matched loosely, so
            <code> latitude</code>, <code>lat</code> and <code>cell_lat</code> all work. Everything stays in your browser.
          </p>

          <div
            className={`dropzone${drag ? " is-drag" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              const f = e.dataTransfer.files[0];
              if (f) readData(f);
            }}
            onClick={() => input.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
          >
            <input ref={input} type="file" accept=".csv,.json" hidden onChange={(e) => e.target.files?.[0] && readData(e.target.files[0])} />
            {file ? (
              <>
                <b>{file.name}</b>
                <span>{file.records.length.toLocaleString()} rows · {file.header.length} columns</span>
              </>
            ) : (
              <>
                <b>Drop CSV / JSON here</b>
                <span>or click to choose a file</span>
              </>
            )}
          </div>

          <div className="meta-row">
            <input
              ref={metaInput}
              type="file"
              accept=".json"
              hidden
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                try {
                  setMeta(JSON.parse(await f.text()));
                } catch {
                  setError("meta.json is not valid JSON.");
                }
              }}
            />
            <button className="btn btn-ghost" onClick={() => metaInput.current?.click()}>
              {meta ? "meta.json loaded ✓" : "Add meta.json (optional)"}
            </button>
            <button className="btn btn-ghost" onClick={template}>
              Download template
            </button>
          </div>

          {firms && (
            <div className="callout">
              <b>Raw FIRMS hotspots detected.</b> Rows are cleaned (type 0, MODIS confidence ≥ 30, VIIRS nominal/high), snapped to a 0.1° grid and counted as
              active cell-days per sensor. No harmonized series is produced from a raw file.
            </div>
          )}
          {file && !firms && (
            <table className="mapping">
              <thead>
                <tr>
                  <th>Contract field</th>
                  <th>Matched column</th>
                </tr>
              </thead>
              <tbody>
                {mapping.map((m) => (
                  <tr key={m.field} className={m.column ? "" : REQUIRED.has(m.field) ? "is-missing" : "is-optional"}>
                    <td>
                      <code>{m.field}</code>
                    </td>
                    <td>{m.column ?? <span className="muted">{REQUIRED.has(m.field) ? "missing" : "not found"}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {file && missing.length > 0 && (
            <div className="warn">
              Missing {missing.join(", ")}. Rename the column or add an alias in <code>config.ts → COLUMN_ALIASES</code> (accepted:{" "}
              {missing.map((f) => COLUMN_ALIASES[f].join(" / ")).join("; ")}).
            </div>
          )}
          {error && <div className="warn">{error}</div>}
        </div>
        <footer className="modal-foot">
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={!file || missing.length > 0} onClick={load}>
            Load dataset
          </button>
        </footer>
      </div>
    </div>
  );
}
