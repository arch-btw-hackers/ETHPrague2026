-- CreateEnum
CREATE TYPE "ShipmentStatus" AS ENUM ('IN_TRANSIT', 'COMPROMISED', 'DELIVERED');

-- CreateEnum
CREATE TYPE "ViolationKind" AS ENUM ('TEMPERATURE_HIGH', 'TEMPERATURE_LOW', 'SHOCK', 'GEOFENCE', 'OFFLINE');

-- CreateTable
CREATE TABLE "Shipment" (
    "id" TEXT NOT NULL,
    "trackingCode" TEXT NOT NULL,
    "asset" TEXT NOT NULL,
    "origin" TEXT NOT NULL,
    "destination" TEXT NOT NULL,
    "status" "ShipmentStatus" NOT NULL DEFAULT 'IN_TRANSIT',
    "contractAddress" TEXT,
    "chainId" INTEGER,
    "payerAddress" TEXT,
    "carrierAddress" TEXT,
    "maxTempC" DOUBLE PRECISION NOT NULL DEFAULT 8,
    "minTempC" DOUBLE PRECISION NOT NULL DEFAULT -20,
    "maxShockG" DOUBLE PRECISION NOT NULL DEFAULT 5,
    "geofence" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Shipment_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Device" (
    "id" TEXT NOT NULL,
    "serial" TEXT NOT NULL,
    "apiKey" TEXT NOT NULL,
    "shipmentId" TEXT NOT NULL,
    "lastSeenAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Device_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Telemetry" (
    "id" TEXT NOT NULL,
    "shipmentId" TEXT NOT NULL,
    "tempC" DOUBLE PRECISION NOT NULL,
    "shockG" DOUBLE PRECISION NOT NULL,
    "lat" DOUBLE PRECISION,
    "lng" DOUBLE PRECISION,
    "battery" DOUBLE PRECISION,
    "raw" JSONB,
    "recordedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Telemetry_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Event" (
    "id" TEXT NOT NULL,
    "shipmentId" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "violation" "ViolationKind",
    "message" TEXT NOT NULL,
    "meta" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Event_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RefundTx" (
    "id" TEXT NOT NULL,
    "shipmentId" TEXT NOT NULL,
    "contractAddress" TEXT NOT NULL,
    "chainId" INTEGER NOT NULL,
    "method" TEXT NOT NULL,
    "args" JSONB NOT NULL,
    "reason" TEXT NOT NULL,
    "judgeVerdict" TEXT,
    "judgeNotes" TEXT,
    "broadcastTxHash" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "RefundTx_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Shipment_trackingCode_key" ON "Shipment"("trackingCode");

-- CreateIndex
CREATE INDEX "Shipment_status_idx" ON "Shipment"("status");

-- CreateIndex
CREATE UNIQUE INDEX "Device_serial_key" ON "Device"("serial");

-- CreateIndex
CREATE UNIQUE INDEX "Device_apiKey_key" ON "Device"("apiKey");

-- CreateIndex
CREATE UNIQUE INDEX "Device_shipmentId_key" ON "Device"("shipmentId");

-- CreateIndex
CREATE INDEX "Telemetry_shipmentId_recordedAt_idx" ON "Telemetry"("shipmentId", "recordedAt");

-- CreateIndex
CREATE INDEX "Event_shipmentId_createdAt_idx" ON "Event"("shipmentId", "createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "RefundTx_shipmentId_key" ON "RefundTx"("shipmentId");

-- AddForeignKey
ALTER TABLE "Device" ADD CONSTRAINT "Device_shipmentId_fkey" FOREIGN KEY ("shipmentId") REFERENCES "Shipment"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Telemetry" ADD CONSTRAINT "Telemetry_shipmentId_fkey" FOREIGN KEY ("shipmentId") REFERENCES "Shipment"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Event" ADD CONSTRAINT "Event_shipmentId_fkey" FOREIGN KEY ("shipmentId") REFERENCES "Shipment"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RefundTx" ADD CONSTRAINT "RefundTx_shipmentId_fkey" FOREIGN KEY ("shipmentId") REFERENCES "Shipment"("id") ON DELETE CASCADE ON UPDATE CASCADE;
