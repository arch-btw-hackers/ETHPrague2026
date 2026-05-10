import ShipmentDashboard from "@/components/ShipmentDashboard";

interface PageProps {
  params: { id: string };
}

export default function DeviceDashboardPage({ params }: PageProps) {
  const id = decodeURIComponent(params.id);
  return (
    <ShipmentDashboard
      trackingCode={id}
      apiBase={`/api/external/devices/${encodeURIComponent(id)}`}
      readOnly
    />
  );
}
