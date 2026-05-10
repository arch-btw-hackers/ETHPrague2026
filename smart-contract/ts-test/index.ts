import { createPublicClient, createWalletClient, http, parseGwei } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { sepolia } from "viem/chains";

const CONTRACT = (process.env.CONTRACT_ADDRESS ?? "0x26B93158005c29a4597235c5bF0457Ee3eDE6fdb") as `0x${string}`;

const ABI = [
  {
    type: "function",
    name: "nextShipmentId",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "createShipment",
    inputs: [
      { name: "receiverWallet", type: "address" },
      { name: "trackerServiceWallet", type: "address" },
      { name: "packageRef", type: "string" },
    ],
    outputs: [{ name: "shipmentId", type: "uint256" }],
    stateMutability: "nonpayable",
  },
  {
    type: "function",
    name: "getShipment",
    inputs: [{ name: "shipmentId", type: "uint256" }],
    outputs: [
      { name: "sender", type: "address" },
      { name: "receiver", type: "address" },
      { name: "trackerService", type: "address" },
      { name: "packageRef", type: "string" },
      { name: "telemetryProof", type: "string" },
      { name: "trackerState", type: "uint8" },
      { name: "status", type: "uint8" },
      { name: "receiverConfirmed", type: "bool" },
      { name: "createdAt", type: "uint256" },
      { name: "deliveredAt", type: "uint256" },
    ],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "startShipment",
    inputs: [{ name: "shipmentId", type: "uint256" }],
    outputs: [],
    stateMutability: "nonpayable",
  },
  {
    type: "function",
    name: "submitTrackerState",
    inputs: [
      { name: "shipmentId", type: "uint256" },
      { name: "isGood", type: "bool" },
      { name: "telemetryProof", type: "string" },
    ],
    outputs: [],
    stateMutability: "nonpayable",
  },
  {
    type: "function",
    name: "confirmReceived",
    inputs: [{ name: "shipmentId", type: "uint256" }],
    outputs: [],
    stateMutability: "nonpayable",
  },
] as const;

const TRACKER_STATE = ["UNKNOWN", "GOOD", "BAD"] as const;
const SHIPMENT_STATUS = ["CREATED", "IN_TRANSIT", "DELIVERED", "BREACHED", "CANCELLED"] as const;

function ok(msg: string) { console.log(`  ✓ ${msg}`); }
function fail(msg: string) { console.error(`  ✗ ${msg}`); process.exit(1); }
function section(msg: string) { console.log(`\n[${msg}]`); }

async function main() {
  const rpcUrl = process.env.SEPOLIA_RPC_URL;
  const privateKey = process.env.PRIVATE_KEY;

  if (!rpcUrl) fail("SEPOLIA_RPC_URL not set");
  if (!privateKey) fail("PRIVATE_KEY not set");

  const account = privateKeyToAccount(`0x${privateKey!.replace(/^0x/, "")}`);

  const publicClient = createPublicClient({ chain: sepolia, transport: http(rpcUrl) });
  const walletClient = createWalletClient({ chain: sepolia, transport: http(rpcUrl), account });

  console.log("=== ColdChainShipment TypeScript network test ===");
  console.log("Contract:", CONTRACT);
  console.log("Wallet:  ", account.address);

  // ── 1. RPC connectivity ────────────────────────────────────────────────────
  section("1. RPC connectivity");
  const block = await publicClient.getBlockNumber();
  ok(`Connected to Sepolia — latest block: ${block}`);

  // ── 2. Contract read ───────────────────────────────────────────────────────
  section("2. Contract read");
  const nextId = await publicClient.readContract({ address: CONTRACT, abi: ABI, functionName: "nextShipmentId" });
  ok(`nextShipmentId = ${nextId}`);

  if (nextId > 0n) {
    const s = await publicClient.readContract({ address: CONTRACT, abi: ABI, functionName: "getShipment", args: [0n] });
    const [sender, receiver, trackerService, packageRef, telemetryProof, trackerState, status, receiverConfirmed, createdAt, deliveredAt] = s as [string, string, string, string, string, number, number, boolean, bigint, bigint];
    ok(`Shipment #0: status=${SHIPMENT_STATUS[status]}, trackerState=${TRACKER_STATE[trackerState]}, receiverConfirmed=${receiverConfirmed}`);
    ok(`  packageRef:     ${packageRef}`);
    ok(`  telemetryProof: ${telemetryProof}`);
    ok(`  createdAt:      ${new Date(Number(createdAt) * 1000).toISOString()}`);
    if (deliveredAt > 0n) ok(`  deliveredAt:    ${new Date(Number(deliveredAt) * 1000).toISOString()}`);
  }

  // ── 3. Full happy-path flow ────────────────────────────────────────────────
  section("3. Full happy-path flow (create → start → tracker GOOD → confirm → DELIVERED)");

  const createHash = await walletClient.writeContract({
    address: CONTRACT, abi: ABI, functionName: "createShipment",
    args: [account.address, account.address, "ipfs://ts-test-package-ref"],
  });
  const createReceipt = await publicClient.waitForTransactionReceipt({ hash: createHash });
  if (createReceipt.status !== "success") fail("createShipment tx failed");

  const shipmentId = await publicClient.readContract({ address: CONTRACT, abi: ABI, functionName: "nextShipmentId" }) as bigint - 1n;
  ok(`createShipment -> id=${shipmentId}  tx=${createHash}`);

  const startHash = await walletClient.writeContract({ address: CONTRACT, abi: ABI, functionName: "startShipment", args: [shipmentId] });
  await publicClient.waitForTransactionReceipt({ hash: startHash }).then(r => { if (r.status !== "success") fail("startShipment tx failed"); });
  ok(`startShipment  tx=${startHash}`);

  const trackerHash = await walletClient.writeContract({
    address: CONTRACT, abi: ABI, functionName: "submitTrackerState",
    args: [shipmentId, true, "swarm://ts-telemetry-proof"],
  });
  await publicClient.waitForTransactionReceipt({ hash: trackerHash }).then(r => { if (r.status !== "success") fail("submitTrackerState tx failed"); });
  ok(`submitTrackerState(good)  tx=${trackerHash}`);

  const confirmHash = await walletClient.writeContract({ address: CONTRACT, abi: ABI, functionName: "confirmReceived", args: [shipmentId] });
  await publicClient.waitForTransactionReceipt({ hash: confirmHash }).then(r => { if (r.status !== "success") fail("confirmReceived tx failed"); });
  ok(`confirmReceived  tx=${confirmHash}`);

  // ── 4. Verify final state ──────────────────────────────────────────────────
  section("4. Verify final state");
  const final = await publicClient.readContract({ address: CONTRACT, abi: ABI, functionName: "getShipment", args: [shipmentId] });
  const [,,, , , finalTrackerState, finalStatus, finalReceiverConfirmed,, finalDeliveredAt] = final as [string, string, string, string, string, number, number, boolean, bigint, bigint];

  if (finalStatus !== 2) fail(`Expected DELIVERED (2), got ${SHIPMENT_STATUS[finalStatus]}`);
  ok(`status = ${SHIPMENT_STATUS[finalStatus]}`);

  if (finalTrackerState !== 1) fail(`Expected GOOD (1), got ${TRACKER_STATE[finalTrackerState]}`);
  ok(`trackerState = ${TRACKER_STATE[finalTrackerState]}`);

  if (!finalReceiverConfirmed) fail("receiverConfirmed should be true");
  ok(`receiverConfirmed = ${finalReceiverConfirmed}`);

  if (finalDeliveredAt === 0n) fail("deliveredAt should be set");
  ok(`deliveredAt = ${new Date(Number(finalDeliveredAt) * 1000).toISOString()}`);

  console.log("\n=== ALL CHECKS PASSED ===\n");
}

main().catch((err) => { console.error(err); process.exit(1); });
