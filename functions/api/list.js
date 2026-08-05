// Route: GET /api/list -> Tankerkoenig list.php (radius search).
import { proxy } from "./_proxy.js";

export const onRequestGet = (context) =>
  proxy(context, "list.php", ["lat", "lng", "rad", "sort", "type"]);
