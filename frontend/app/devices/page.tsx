"use client";

// External device hub — lists every tracker registered upstream at
// `/api/v1/dashboard/devices` and links each one into the full
// ShipmentDashboard view (read-only, AI-augmented).

import Link from "next/link";
import useSWR from "swr";
import { motion } from "framer-motion";
import { ArrowUpRight, ShieldCheck, ShieldAlert, Radio } from "lucide-react";
import { fetcher } from "@/lib/api";

interface ExternalLatestReading {
  temp_c: number | null;
  acceleration_overload: number | null;
  lat: number | null;
  lon: number | null;
}

interface ExternalDeviceSummary {
  device_id: string;
  conditions_hash: string | null;
  latest_telemetry_hash: string | null;
  latest_reading: ExternalLatestReading | null;
  is_valid: boolean | null;
  reason: string | null;
  timestamp: string | null;
}

export default function DevicesPage() {
  const { data, error, isLoading } = useSWR<ExternalDeviceSummary[]>(
    "/api/external/devices",
    fetcher,
    { refreshInterval: 10_000 }
  );

  return (
    <main className="relative z-10 mx-auto max-w-7xl px-6 py-10 md:px-10 md:py-12">
      <header className="mb-8 flex items-end justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.32em] text-white/50">
            External Hub
          </div>
          <h1 className="mt-2 font-mono text-2xl text-white">Live Devices</h1>
          <p className="mt-1 text-[12px] text-white/50">
            GigaService telemetry · sourced from{" "}
            <span className="font-mono text-white/65">/api/v1/dashboard/devices</span>
          </p>
        </div>
        <Link
          href="/"
          className="rounded-full border border-white/10 bg-white/[0.02] px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.28em] text-white/65 transition hover:border-cyan/40 hover:text-cyan"
        >
          ← Hub home
        </Link>
      </header>

      {error && (
        <div className="rounded-2xl border border-warn/30 bg-warn/[0.04] p-5 text-warn">
          Could not reach the external hub. Check that the GigaService is up.
        </div>
      )}

      {isLoading && !data && (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-2xl border border-white/[0.06] bg-white/[0.02]"
            />
          ))}
        </div>
      )}

      {data && data.length === 0 && (
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-6 text-[13px] text-white/55">
          No devices registered upstream yet.
        </div>
      )}

      {data && data.length > 0 && (
        <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data.map((d, i) => (
            <DeviceCard key={d.device_id} device={d} delay={i * 0.04} />
          ))}
        </ul>
      )}
    </main>
  );
}

function DeviceCard({
  device,
  delay,
}: {
  device: ExternalDeviceSummary;
  delay: number;
}) {
  const valid = device.is_valid !== false;
  const fmt = (v: number | null | undefined, d = 1) =>
    v == null ? "—" : v.toFixed(d);
  const ts = device.timestamp ? new Date(device.timestamp) : null;

  return (
    <motion.li
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay }}
    >
      <Link
        href={`/devices/${encodeURIComponent(device.device_id)}`}
        className={`group block rounded-2xl border bg-white/[0.015] p-5 transition hover:bg-white/[0.04] ${
          valid ? "border-white/[0.06] hover:border-cyan/40" : "border-warn/30 bg-warn/[0.03] hover:border-warn/60"
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[9px] uppercase tracking-[0.32em] text-white/45">
              <Radio className="h-3 w-3" />
              Device
            </div>
            <div className="mt-1 truncate font-mono text-[13px] text-white">
              {device.device_id}
            </div>
          </div>
          <ArrowUpRight
            className={`h-4 w-4 transition ${
              valid ? "text-white/35 group-hover:text-cyan" : "text-warn"
            }`}
          />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 font-mono text-[11px]">
          <Cell label="Temp" value={`${fmt(device.latest_reading?.temp_c, 1)}°C`} />
          <Cell
            label="Shock"
            value={`${fmt(device.latest_reading?.acceleration_overload, 2)}G`}
          />
          <Cell
            label="Lat"
            value={fmt(device.latest_reading?.lat, 3)}
          />
          <Cell
            label="Lon"
            value={fmt(device.latest_reading?.lon, 3)}
          />
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-white/[0.05] pt-3 text-[10px] uppercase tracking-[0.24em]">
          <span
            className={`inline-flex items-center gap-1.5 ${
              valid ? "text-emerald-400" : "text-warn"
            }`}
          >
            {valid ? (
              <ShieldCheck className="h-3 w-3" />
            ) : (
              <ShieldAlert className="h-3 w-3" />
            )}
            {valid ? "valid" : device.reason ?? "violation"}
          </span>
          <span className="font-mono text-white/45">
            {ts
              ? ts.toLocaleString(undefined, {
                  day: "2-digit",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : "—"}
          </span>
        </div>
      </Link>
    </motion.li>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-[0.28em] text-white/35">
        {label}
      </div>
      <div className="mt-0.5 text-white/85">{value}</div>
    </div>
  );
}
