import Link from "next/link";
import { Radio } from "lucide-react";
import ShipmentDashboard from "@/components/ShipmentDashboard";

export default function Page() {
  return (
    <>
      <div className="fixed right-4 top-4 z-40 md:right-6 md:top-6">
        <Link
          href="/devices"
          className="group inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/60 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.28em] text-white/65 backdrop-blur-xl transition hover:border-cyan/40 hover:text-cyan"
        >
          <Radio className="h-3 w-3" />
          Live devices
        </Link>
      </div>
      <ShipmentDashboard trackingCode="VBT-0001" />
    </>
  );
}
