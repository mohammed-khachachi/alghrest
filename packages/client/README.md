# @mohammed-khachachi/alghrest-client

Official TypeScript and JavaScript Client SDK for the **ALGHREST Autonomous Algorithmic Trading & Quantitative Research Platform**.

Provides full type safety, authenticated REST endpoints, and resilient real-time WebSocket subscriptions for market data, agent topology, portfolio state, and OpenBB multi-provider intelligence.

---

## 📦 Installation

```bash
# npm
npm install @mohammed-khachachi/alghrest-client

# yarn
yarn add @mohammed-khachachi/alghrest-client

# pnpm
pnpm add @mohammed-khachachi/alghrest-client
```

---

## 🚀 Quick Start

```typescript
import { AlghrestClient } from "@mohammed-khachachi/alghrest-client";

// Initialize client
const client = new AlghrestClient({
  baseUrl: "http://127.0.0.1:8000",
  accessToken: process.env.ALGHREST_API_TOKEN,
  timeoutMs: 8000,
});

// 1. Check system health
const health = await client.getHealth();
console.log(`Backend status: ${health.status} (${health.environment})`);

// 2. Fetch live quotes (backed by OpenBB / mock provider)
const quotes = await client.getQuotes(["BTC", "AAPL", "EUR/USD"]);
for (const q of quotes) {
  console.log(`${q.symbol}: $${q.price} (bid: $${q.bid}, ask: $${q.ask})`);
}

// 3. Inspect active trading agents
const { agents, running } = await client.getAgents();
console.log(`Active agents: ${running}/${agents.length}`);
```

---

## 📡 Real-Time WebSocket Streaming

Connect to the live feed for instant order fills, risk alerts, and market ticks:

```typescript
const sub = client.subscribeDashboard({
  onOpen: () => console.log("Connected to ALGHREST streaming feed"),
  onMessage: (message) => {
    console.log(`[${message.type}]`, message.payload);
  },
  onError: (err) => console.error("Stream error:", err),
  onClose: () => console.log("Stream closed"),
  reconnectIntervalMs: 3000,
  maxReconnectAttempts: 10,
});

// To disconnect:
// sub.close();
```

---

## 📊 OpenBB Historical Data

Access cross-asset financial data through ALGHREST's unified OpenBB adapter:

```typescript
// Query OpenBB historical bars
const history = await client.getOpenBBHistorical({
  symbol: "AAPL",
  assetClass: "equity",
  timeframe: "1d",
  startDate: "2026-10-01",
  endDate: "2026-11-01",
  provider: "yfinance",
});

console.log(`Retrieved ${history.bars.length} bars for ${history.symbol}`);
```

---

## 🛡️ Error Handling

The SDK provides explicit typed errors for robust handling:

```typescript
import {
  AlghrestAuthError,
  AlghrestNotFoundError,
  AlghrestTimeoutError,
  AlghrestValidationError,
} from "@mohammed-khachachi/alghrest-client";

try {
  const quote = await client.getQuotes(["UNKNOWN_SYM"]);
} catch (error) {
  if (error instanceof AlghrestAuthError) {
    console.error("Authentication failed. Check your access token.");
  } else if (error instanceof AlghrestTimeoutError) {
    console.error("Request timed out.");
  } else if (error instanceof AlghrestValidationError) {
    console.error("Invalid parameters:", error.responseBody);
  }
}
```

---

## 🚢 Publishing to the npm Registry

To publish new versions of this SDK to npm or GitHub Packages:

### Option A: Public npm Registry (`npmjs.com`)
1. Ensure you are logged into your npm account:
   ```bash
   npm login
   npm whoami
   ```
2. Build and verify the package:
   ```bash
   npm run build
   npm pack --dry-run
   ```
3. Publish to npm:
   ```bash
   npm publish --access public
   ```

### Option B: GitHub Packages (`npm.pkg.github.com`)
1. Create a GitHub Personal Access Token (PAT) with `write:packages` permission.
2. In `packages/client/.npmrc`:
   ```ini
   @mohammed-khachachi:registry=https://npm.pkg.github.com/
   //npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
   ```
3. Publish:
   ```bash
   npm publish
   ```

---

## 📄 License

MIT © [Mohammed Khachachi](https://github.com/mohammed-khachachi)
