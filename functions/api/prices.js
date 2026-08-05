// Route: GET /api/prices -> Tankerkoenig prices.php (prices for station ids).
import { proxy } from "./_proxy.js";

export const onRequestGet = (context) => proxy(context, "prices.php", ["ids"]);
