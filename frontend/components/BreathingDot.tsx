"use client";
import { motion } from "framer-motion";
import type { ShipmentStatus } from "@/lib/api";

// "Breathing" dot — pulses while the shipment is live, locks solid when delivered,
// and pulses orange when compromised.
export function BreathingDot({ status }: { status: ShipmentStatus }) {
  const color =
    status === "COMPROMISED"
      ? "#FF7A1A"
      : status === "DELIVERED"
      ? "#7A8493"
      : "#22E3FF";

  const animate =
    status === "DELIVERED"
      ? { scale: 1, opacity: 1 }
      : { scale: [1, 1.4, 1], opacity: [0.9, 0.4, 0.9] };

  return (
    <span className="relative inline-flex h-2.5 w-2.5 items-center justify-center">
      <motion.span
        className="absolute inline-flex h-full w-full rounded-full"
        style={{ background: color }}
        animate={animate}
        transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
      />
      <span
        className="relative inline-flex h-1.5 w-1.5 rounded-full"
        style={{ background: color }}
      />
    </span>
  );
}
