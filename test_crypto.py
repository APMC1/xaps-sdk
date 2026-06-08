import os
import hmac
import hashlib
import json
from xaps import verify_xaps_receipt

# 1. Simulate the Central Bank Node generating a receipt
mock_receipt = {
    "status": "approved",
    "toll": 0.01,
    "target_wallet": "5EDYPKTcwRNyXupXhL4adVkr1rhvxsSPEnoRGzYqrLRB5xoU"
}

# The Node signs the receipt using its private secret
secret = os.getenv("XAPS_RECEIPT_SECRET")
data_string = json.dumps(mock_receipt, sort_keys=True, separators=(',', ':')).encode('utf-8')
node_signature = hmac.new(secret.encode('utf-8'), data_string, hashlib.sha256).hexdigest()

print("\n🏦 --- XAPS CENTRAL BANK ---")
print(f"Minted Receipt: {mock_receipt}")
print(f"Cryptographic Signature: {node_signature}\n")

# 2. The SDK intercepts the receipt and verifies the math
print("🤖 --- AI AGENT SDK ---")
print("Verifying mathematical proof...")

try:
    is_valid = verify_xaps_receipt(mock_receipt, node_signature)
    if is_valid:
        print("✅ SUCCESS: The SDK mathematically verified the Node's signature!")
        print("The AI agent is cleared to execute the Web3 transaction.\n")
    else:
        print("❌ FAILED: Signatures do not match. Execution blocked.\n")
except Exception as e:
    print(f"❌ ERROR: {e}\n")
