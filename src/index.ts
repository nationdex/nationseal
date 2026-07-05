import { Client, type ParseClient } from "seyfert";
import { closeDatabase, connectDatabase } from "./lib/db";

declare module "seyfert" {
	interface UsingClient extends ParseClient<Client<true>> {}
	// Tell Seyfert where to auto-discover ComponentCommand classes from.
	interface ExtendedRCLocations {
		components?: string;
	}
}

console.log("[nationseal] Starting...");

const client = new Client();

console.log("[nationseal] Connecting to database...");
await connectDatabase();
console.log("[nationseal] Database connected, starting bot...");

// Graceful shutdown: drop the Discord gateway first (so no new
// interactions come in mid-shutdown), then flush the JSON database so
// writes are persisted cleanly and in-flight API calls have a chance to
// settle.
let shuttingDown = false;
async function shutdown(signal: NodeJS.Signals): Promise<void> {
	if (shuttingDown) return;
	shuttingDown = true;
	console.log(`[nationseal] Caught ${signal}, shutting down…`);
	try {
		client.gateway?.disconnectAll();
	} catch (error) {
		console.error("[nationseal] Error disconnecting gateway:", error);
	}
	try {
		await closeDatabase();
	} catch (error) {
		console.error("[nationseal] Error closing database:", error);
	}
	process.exit(0);
}

process.on("SIGINT", () => void shutdown("SIGINT"));
process.on("SIGTERM", () => void shutdown("SIGTERM"));

try {
	await client.start();
	// Auto-discover ComponentCommand classes from src/components.
	const path = await import("node:path");
	const componentsDir = path.join(process.cwd(), "src", "components");
	await client.loadComponents(componentsDir);
	console.log("[nationseal] Component handlers loaded");
	console.log("[nationseal] Bot started, uploading commands...");
	await client.uploadCommands({ cachePath: "./commands.json" });
	console.log("[nationseal] Commands uploaded successfully!");
} catch (error) {
	console.error("[nationseal] Fatal error:", error);
	await shutdown("SIGTERM");
}
