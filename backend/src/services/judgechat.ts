// AI chat + PDF report — bound to a specific shipment for context.
//
// chatWithJudge() reuses the OpenAI configuration from insights.ts but with a
// different system prompt so the model speaks in the operator's voice instead
// of returning JSON. If the API key is missing or the call fails, we fall
// back to a deterministic answer drawn from the live telemetry.
//
// renderReport() produces a styled PDF (pdfkit) summarising the shipment for
// the judges, including a vector Ethereum logo, key metrics, and the latest
// AI risk assessment.

import PDFDocument from "pdfkit";
import { prisma } from "../db";
import { getInsight } from "./insights";

interface ChatTurn { role: "user" | "assistant"; content: string }

const CHAT_SYSTEM = `You are the VibeTrack Supreme Judge — a forensic AI for
an RWA logistics platform.

Voice:
  • 1–2 sentences, max 40 words, decisive and grounded in numbers.
  • No filler, no preamble, no emojis, no markdown headings.
  • Lead with a number (with units) when the user asks for one.
  • Always give the operator something useful: cite a telemetry signal,
    threshold, ETA, or route fact from the live context. Do NOT reply
    with "insufficient telemetry" if any context is provided — instead
    summarise what is known and call out the missing field by name.`;

export interface ChatResult {
  answer: string;
  model: string;
}

export async function chatWithJudge(
  shipmentId: string,
  question: string,
  history: ChatTurn[] = []
): Promise<ChatResult> {
  const shipment = await prisma.shipment.findUniqueOrThrow({
    where: { id: shipmentId },
    include: {
      telemetries: { orderBy: { recordedAt: "desc" }, take: 12 },
      events: { orderBy: { createdAt: "desc" }, take: 6 },
    },
  });

  const last = shipment.telemetries[0];
  const facts =
    `Tracking ${shipment.trackingCode} · ${shipment.asset}\n` +
    `Route ${shipment.origin} → ${shipment.destination} · status ${shipment.status}\n` +
    `Thresholds: maxTemp ${shipment.maxTempC}°C · maxShock ${shipment.maxShockG}G\n` +
    (last
      ? `Latest sample: T=${last.tempC.toFixed(1)}°C · G=${last.shockG.toFixed(2)} · ` +
        `V=${last.speedKph?.toFixed(0) ?? "-"} kph · battery ${last.battery?.toFixed(0) ?? "-"}%\n`
      : "No telemetry yet.\n") +
    `Recent events:\n${shipment.events
      .map((e) => `  · ${e.kind}: ${e.message}`)
      .join("\n") || "  · none"}`;

  return runJudgeChat(facts, question, history);
}

/**
 * Same OpenAI call path as `chatWithJudge`, but the caller supplies the
 * forensic context as plain text (used by the external-device proxy where
 * there's no Prisma row to read).
 */
export async function runJudgeChat(
  facts: string,
  question: string,
  history: ChatTurn[] = []
): Promise<ChatResult> {
  const key = process.env.OPENAI_API_KEY;
  if (!key) return { answer: localAnswer(question, facts), model: "heuristic" };

  const model = process.env.OPENAI_MODEL ?? "gpt-4o-mini";
  try {
    const r = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${key}`,
      },
      body: JSON.stringify({
        model,
        temperature: 0.2,
        max_tokens: 90,
        messages: [
          { role: "system", content: CHAT_SYSTEM },
          { role: "system", content: `Live shipment context:\n${facts}` },
          ...history.slice(-6),
          { role: "user", content: question },
        ],
      }),
    });
    if (!r.ok) return { answer: localAnswer(question, facts), model: "heuristic" };
    const data = await r.json();
    const content = data.choices?.[0]?.message?.content?.trim();
    if (!content) return { answer: localAnswer(question, facts), model: "heuristic" };
    return { answer: content.slice(0, 280), model };
  } catch {
    return { answer: localAnswer(question, facts), model: "heuristic" };
  }
}

function localAnswer(_q: string, facts: string): string {
  return `Operating offline. Snapshot:\n${facts}`;
}

// ---------------------------------------------------------------------------
// PDF report
// ---------------------------------------------------------------------------

const ETH_PATH_TOP =
  // Ethereum diamond — top half (filled), drawn relative to (0,0).
  "M 32 0 L 0 52 L 32 38 L 64 52 Z";
const ETH_PATH_BOTTOM = "M 32 96 L 0 60 L 32 78 L 64 60 Z";

/**
 * Generic shipment-like input the report renderer needs. Decoupled from
 * Prisma so external (proxied) devices can produce the same PDF.
 */
export interface ReportShipment {
  trackingCode: string;
  asset: string;
  origin: string;
  destination: string;
  status: string;
  maxTempC: number;
  maxShockG: number;
  contractAddress: string | null;
  chainId: number | null;
  payerAddress: string | null;
  carrierAddress: string | null;
  /** Newest-first list of recent samples (~last 120). */
  telemetries: Array<{
    tempC: number;
    shockG: number;
    lat: number | null;
    lng: number | null;
    recordedAt: Date | string;
  }>;
}

export async function renderReport(shipmentId: string): Promise<Buffer> {
  const shipment = await prisma.shipment.findUniqueOrThrow({
    where: { id: shipmentId },
    include: {
      telemetries: { orderBy: { recordedAt: "desc" }, take: 120 },
    },
  });
  const insight = await getInsight(shipmentId, false);
  return renderReportFromData(
    {
      trackingCode: shipment.trackingCode,
      asset: shipment.asset,
      origin: shipment.origin,
      destination: shipment.destination,
      status: shipment.status,
      maxTempC: shipment.maxTempC,
      maxShockG: shipment.maxShockG,
      contractAddress: shipment.contractAddress,
      chainId: shipment.chainId,
      payerAddress: shipment.payerAddress,
      carrierAddress: shipment.carrierAddress,
      telemetries: shipment.telemetries.map((t) => ({
        tempC: t.tempC,
        shockG: t.shockG,
        lat: t.lat,
        lng: t.lng,
        recordedAt: t.recordedAt,
      })),
    },
    insight
  );
}

export async function renderReportFromData(
  shipment: ReportShipment,
  insight: import("./insights").Insight
): Promise<Buffer> {
  const doc = new PDFDocument({ size: "A4", margin: 56 });
  const chunks: Buffer[] = [];
  doc.on("data", (c) => chunks.push(c as Buffer));
  const done = new Promise<Buffer>((resolve) => {
    doc.on("end", () => resolve(Buffer.concat(chunks)));
  });

  const PAGE_W = doc.page.width;
  const MARGIN = 56;
  const CONTENT_W = PAGE_W - MARGIN * 2;
  // Helvetica's WinAnsi cannot render U+2192. Use a plain ASCII arrow.
  const ARROW = "  >  ";

  // ---------- Header band ----------
  const HEADER_H = 110;
  doc.rect(0, 0, PAGE_W, HEADER_H).fill("#050708");

  // Ethereum mark — drawn at fixed pixel coords inside the band.
  doc.save().translate(MARGIN, 26).scale(0.55);
  doc.fillColor("#7B8CFF").path(ETH_PATH_TOP).fill();
  doc.fillColor("#A4B0FF").path(ETH_PATH_BOTTOM).fill();
  doc.restore();

  doc.fillColor("#E6E9EF").font("Helvetica-Bold").fontSize(13)
    .text("VIBETRACK", MARGIN + 60, 36, { characterSpacing: 4 });
  doc.fillColor("#7A8190").font("Helvetica").fontSize(8)
    .text("INTELLIGENCE HUB . FORENSIC LOGISTICS REPORT", MARGIN + 60, 56, {
      characterSpacing: 2,
    });
  doc.fillColor("#5C6373").font("Helvetica").fontSize(7.5)
    .text(`Generated ${new Date().toUTCString()}`, MARGIN + 60, 72, {
      characterSpacing: 1,
    });

  // ---------- Title ----------
  let y = HEADER_H + 36;
  doc.font("Helvetica").fontSize(8).fillColor("#9099AA")
    .text("CASE", MARGIN, y, { characterSpacing: 3 });
  y += 14;
  doc.font("Helvetica-Bold").fontSize(20).fillColor("#0B0D10")
    .text(`${shipment.trackingCode}  ${shipment.asset}`, MARGIN, y, {
      width: CONTENT_W,
    });
  y = doc.y + 6;
  doc.font("Helvetica").fontSize(10).fillColor("#4A5160")
    .text(`${shipment.origin}${ARROW}${shipment.destination}`, MARGIN, y);
  y = doc.y + 24;

  // ---------- Verdict box ----------
  const verdictColor =
    insight.riskLabel === "CRITICAL"
      ? "#D9480F"
      : insight.riskLabel === "ELEVATED"
      ? "#C58B00"
      : insight.riskLabel === "MODERATE"
      ? "#0E7C7B"
      : "#1F8A4C";
  const VERDICT_H = 88;
  doc.roundedRect(MARGIN, y, CONTENT_W, VERDICT_H, 10)
    .lineWidth(0.5).strokeColor("#D7DBE2").fillAndStroke("#FAFBFC", "#D7DBE2");

  // Three columns: Score | Status | Headline
  const col1 = MARGIN + 20;
  const col2 = MARGIN + 140;
  const col3 = MARGIN + 260;
  const labelY = y + 16;
  const valueY = y + 32;

  doc.fillColor("#9099AA").font("Helvetica").fontSize(7.5)
    .text("RISK SCORE", col1, labelY, { characterSpacing: 3 });
  doc.fillColor(verdictColor).font("Helvetica-Bold").fontSize(34)
    .text(`${insight.riskScore.toFixed(0)}`, col1, valueY);

  doc.fillColor("#9099AA").font("Helvetica").fontSize(7.5)
    .text("STATUS", col2, labelY, { characterSpacing: 3 });
  doc.fillColor(verdictColor).font("Helvetica-Bold").fontSize(15)
    .text(insight.riskLabel, col2, valueY + 8);

  doc.fillColor("#9099AA").font("Helvetica").fontSize(7.5)
    .text("HEADLINE", col3, labelY, { characterSpacing: 3 });
  doc.fillColor("#0B0D10").font("Helvetica-Bold").fontSize(11)
    .text(insight.headline, col3, valueY + 4, {
      width: PAGE_W - MARGIN - col3,
      ellipsis: true,
      height: 44,
    });

  y += VERDICT_H + 28;

  // ---------- Telemetry envelope ----------
  const last = shipment.telemetries[0]; // already DESC ordered by query
  const tempVals = shipment.telemetries.map((t) => t.tempC);
  const shockVals = shipment.telemetries.map((t) => t.shockG);
  const stat = (vals: number[]) => ({
    avg: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0,
    max: vals.length ? Math.max(...vals) : 0,
    min: vals.length ? Math.min(...vals) : 0,
  });
  const tStat = stat(tempVals);
  const gStat = stat(shockVals);

  y = drawSectionLabel(doc, "TELEMETRY ENVELOPE", MARGIN, y) + 12;

  // Two-column grid, generous row height
  const ROW = 30;
  const colA = MARGIN;
  const colB = MARGIN + CONTENT_W / 2;

  drawKV(doc, "Samples", `${shipment.telemetries.length}`, colA, y);
  drawKV(
    doc,
    "Temperature",
    `min ${tStat.min.toFixed(1)} . avg ${tStat.avg.toFixed(1)} . max ${tStat.max.toFixed(1)} C`,
    colB,
    y
  );
  y += ROW;

  drawKV(doc, "Threshold", `${shipment.maxTempC} C max  /  ${shipment.maxShockG} G max`, colA, y);
  drawKV(
    doc,
    "Shock",
    `min ${gStat.min.toFixed(2)} . avg ${gStat.avg.toFixed(2)} . max ${gStat.max.toFixed(2)} G`,
    colB,
    y
  );
  y += ROW;

  if (last) {
    drawKV(
      doc,
      "Last sample",
      `${new Date(last.recordedAt).toUTCString()}   ${last.lat?.toFixed(4)}, ${last.lng?.toFixed(4)}`,
      colA,
      y,
      CONTENT_W
    );
    y += ROW;
  }

  y += 6;

  // ---------- Sparkline charts (Temp & Shock, oldest → newest) ----------
  if (shipment.telemetries.length >= 2) {
    const oldFirst = [...shipment.telemetries].reverse();
    const tempsLine = oldFirst.map((t) => t.tempC);
    const shocksLine = oldFirst.map((t) => t.shockG);
    const chartW = (CONTENT_W - 20) / 2;
    const chartH = 70;
    drawSparkChart(
      doc,
      tempsLine,
      MARGIN,
      y,
      chartW,
      chartH,
      "TEMPERATURE  C",
      shipment.maxTempC,
      "#0E7C7B"
    );
    drawSparkChart(
      doc,
      shocksLine,
      MARGIN + chartW + 20,
      y,
      chartW,
      chartH,
      "SHOCK  G",
      shipment.maxShockG,
      "#7B8CFF"
    );
    y += chartH + 24;
  }

  // ---------- AI Executive Summary ----------
  y = drawSectionLabel(doc, "EXECUTIVE SUMMARY", MARGIN, y) + 12;
  doc.fillColor("#0B0D10").font("Helvetica").fontSize(11)
    .text(insight.summary || "No summary generated.", MARGIN, y, {
      width: CONTENT_W,
      lineGap: 3,
    });
  y = doc.y + 18;

  // ---------- Anomalies / Recommendations ----------
  if (insight.anomalies.length) {
    y = drawSectionLabel(doc, "ANOMALIES", MARGIN, y) + 10;
    for (const a of insight.anomalies) {
      doc.fillColor("#0B0D10").font("Helvetica").fontSize(10)
        .text(`-  ${a}`, MARGIN + 6, y, { width: CONTENT_W - 6 });
      y = doc.y + 4;
    }
    y += 12;
  }

  if (insight.recommendations.length) {
    y = drawSectionLabel(doc, "RECOMMENDED ACTIONS", MARGIN, y) + 10;
    for (const a of insight.recommendations) {
      doc.fillColor("#0B0D10").font("Helvetica").fontSize(10)
        .text(`-  ${a}`, MARGIN + 6, y, { width: CONTENT_W - 6 });
      y = doc.y + 4;
    }
    y += 12;
  }

  // Page break if needed before identity section
  if (y > doc.page.height - 220) {
    doc.addPage();
    y = MARGIN;
  }

  // ---------- On-chain identity ----------
  y = drawSectionLabel(doc, "ON-CHAIN IDENTITY", MARGIN, y) + 12;
  drawKV(doc, "Contract", shipment.contractAddress ?? "-", colA, y, CONTENT_W); y += ROW;
  drawKV(doc, "Chain ID", String(shipment.chainId ?? "-"), colA, y); y += ROW;
  drawKV(doc, "Payer", shipment.payerAddress ?? "-", colA, y, CONTENT_W); y += ROW;
  drawKV(doc, "Carrier", shipment.carrierAddress ?? "-", colA, y, CONTENT_W);

  // ---------- Footer ----------
  const footY = doc.page.height - 56;
  doc.moveTo(MARGIN, footY).lineTo(PAGE_W - MARGIN, footY)
    .lineWidth(0.5).strokeColor("#E1E4EA").stroke();
  doc.fillColor("#9099AA").font("Helvetica").fontSize(7.5)
    .text(
      `Model ${insight.model}   .   Forecast horizon ${insight.forecast.length} steps   .   vibetrack.eth`,
      MARGIN,
      footY + 10,
      { width: CONTENT_W, align: "center", characterSpacing: 2 }
    );

  doc.end();
  return done;
}

function drawSectionLabel(
  doc: PDFKit.PDFDocument,
  label: string,
  x: number,
  y: number
): number {
  doc.fillColor("#9099AA").font("Helvetica-Bold").fontSize(8)
    .text(label, x, y, { characterSpacing: 3 });
  doc.moveTo(x, y + 14).lineTo(x + 56, y + 14)
    .lineWidth(1).strokeColor("#0B0D10").stroke();
  return y + 14;
}

function drawKV(
  doc: PDFKit.PDFDocument,
  k: string,
  v: string,
  x: number,
  y: number,
  width = 240
) {
  doc.fillColor("#9099AA").font("Helvetica").fontSize(7.5)
    .text(k.toUpperCase(), x, y, { characterSpacing: 2 });
  doc.fillColor("#0B0D10").font("Helvetica").fontSize(10)
    .text(v, x, y + 12, { width, ellipsis: true, height: 14 });
}

/**
 * Mini sparkline-style line chart: framed box with axis-implied scale,
 * threshold line, and filled area under the curve. Used for the report's
 * temperature & shock visual envelope.
 */
function drawSparkChart(
  doc: PDFKit.PDFDocument,
  values: number[],
  x: number,
  y: number,
  w: number,
  h: number,
  label: string,
  threshold: number | null,
  stroke: string
) {
  // Frame
  doc.roundedRect(x, y, w, h, 6)
    .lineWidth(0.5).strokeColor("#D7DBE2").fillAndStroke("#FAFBFC", "#D7DBE2");

  // Title
  doc.fillColor("#9099AA").font("Helvetica").fontSize(7.5)
    .text(label, x + 10, y + 8, { characterSpacing: 2, width: w - 80 });

  if (values.length < 2) return;

  const padL = 30, padR = 10, padT = 22, padB = 14;
  const innerX = x + padL;
  const innerY = y + padT;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (threshold != null && Number.isFinite(threshold)) hi = Math.max(hi, threshold);
  if (hi - lo < 1e-6) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.08;
  lo -= pad; hi += pad;

  const yFor = (v: number) => innerY + innerH - ((v - lo) / (hi - lo)) * innerH;
  const xFor = (i: number) => innerX + (i / (values.length - 1)) * innerW;

  // Min/max ticks (left axis)
  doc.fillColor("#9099AA").font("Helvetica").fontSize(6.5)
    .text(hi.toFixed(1), x + 4, innerY - 2, { width: padL - 6, align: "right" })
    .text(lo.toFixed(1), x + 4, innerY + innerH - 6, { width: padL - 6, align: "right" });

  // Threshold line
  if (threshold != null && Number.isFinite(threshold) && threshold <= hi && threshold >= lo) {
    const ty = yFor(threshold);
    doc.save();
    doc.lineWidth(0.6).strokeColor("#D9480F").dash(3, { space: 2 });
    doc.moveTo(innerX, ty).lineTo(innerX + innerW, ty).stroke();
    doc.restore();
    doc.fillColor("#D9480F").font("Helvetica").fontSize(6)
      .text(`max ${threshold}`, innerX + innerW - 40, ty - 8, { width: 40, align: "right" });
  }

  // Filled area under curve
  doc.save();
  doc.moveTo(xFor(0), innerY + innerH);
  for (let i = 0; i < values.length; i++) doc.lineTo(xFor(i), yFor(values[i]));
  doc.lineTo(xFor(values.length - 1), innerY + innerH).closePath();
  doc.fillOpacity(0.12).fillColor(stroke).fill();
  doc.restore();

  // Stroke line
  doc.save();
  doc.lineWidth(1.2).strokeColor(stroke);
  doc.moveTo(xFor(0), yFor(values[0]));
  for (let i = 1; i < values.length; i++) doc.lineTo(xFor(i), yFor(values[i]));
  doc.stroke();
  doc.restore();

  // Last value dot
  const lx = xFor(values.length - 1);
  const ly = yFor(values[values.length - 1]);
  doc.circle(lx, ly, 2).fillColor(stroke).fill();
}
