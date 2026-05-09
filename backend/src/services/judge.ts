// "Supreme Judge" — placeholder for the future agentic verifier.
//
// The Arbitrator is deterministic and fast; the Judge is an LLM agent
// (Claude / GPT) that double-checks borderline violations and can pull
// independent attestations via Apify x402 before a refund is broadcast.
//
// This module is intentionally side-effect-free and dependency-light so it
// can be swapped to a real provider (Anthropic SDK / OpenAI SDK) without
// touching the rest of the hub.

import { prisma } from "../db";

export type JudgeVerdict = "APPROVE" | "REJECT";

export interface JudgeResult {
  verdict: JudgeVerdict;
  notes: string;
}

// Plug-in surface. Replace `runLLM` with a real call to Claude / GPT.
async function runLLM(_prompt: string): Promise<JudgeResult> {
  // Stub verdict — keeps the pipeline functional in dev.
  return {
    verdict: "APPROVE",
    notes:
      "Stub Judge: deterministic Arbitrator verdict accepted. Wire JUDGE_API_KEY to enable LLM review.",
  };
}

export async function reviewRefund(shipmentId: string): Promise<JudgeResult | null> {
  const refund = await prisma.refundTx.findUnique({ where: { shipmentId } });
  if (!refund) return null;

  const events = await prisma.event.findMany({
    where: { shipmentId, kind: "VIOLATION" },
    orderBy: { createdAt: "asc" },
    take: 50,
  });

  const prompt = [
    "You are the Supreme Judge for an RWA logistics escrow.",
    "Decide APPROVE or REJECT for the prepared refund based on these violations:",
    JSON.stringify(events, null, 2),
    `Reason summary: ${refund.reason}`,
  ].join("\n");

  const result = await runLLM(prompt);

  await prisma.refundTx.update({
    where: { shipmentId },
    data: { judgeVerdict: result.verdict, judgeNotes: result.notes },
  });
  await prisma.event.create({
    data: {
      shipmentId,
      kind: "JUDGE_VERDICT",
      message: `Supreme Judge: ${result.verdict}`,
      meta: { notes: result.notes },
    },
  });

  return result;
}
