// VibeTrack Intelligence Hub — HTTP entrypoint.
import "dotenv/config";
import express from "express";
import cors from "cors";
import morgan from "morgan";
import { telemetryRouter } from "./routes/telemetry";
import { shipmentsRouter } from "./routes/shipments";
import { startSimulator } from "./services/simulator";

const app = express();

app.use(cors());
app.use(express.json({ limit: "256kb" }));
app.use(morgan("tiny"));

app.get("/healthz", (_req, res) => res.json({ ok: true, service: "vibetrack-hub" }));

app.use("/api/telemetry", telemetryRouter);
app.use("/api/shipments", shipmentsRouter);

// Centralised error handler — keeps responses minimal and JSON-shaped.
app.use(
  (
    err: Error,
    _req: express.Request,
    res: express.Response,
    _next: express.NextFunction
  ) => {
    console.error("[hub:error]", err);
    res.status(500).json({ error: "INTERNAL", message: err.message });
  }
);

const port = Number(process.env.PORT ?? 4000);
app.listen(port, () => {
  console.log(`▲ VibeTrack hub listening on :${port}`);
  startSimulator();
});
