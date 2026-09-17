/**
 * Payee independent step (no agent key):
 *   POST https://api.xaps.network/receipts/clear
 *   { "receipt_id": "<from X-XAPS-Receipt>", "require_use_case": "value_move",
 *     "amount": 1.25, "pay_to": "0x...", "resource": "https://..." }
 * Refuse settlement unless body.clear === true.
 *
 * Payer helper: wrapFetchWithXaps in xaps-mcp-edge src/xaps_x402.ts
 */
export const XAPS_RECEIPT_HEADER = "X-XAPS-Receipt";
