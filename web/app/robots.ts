import type { MetadataRoute } from "next";
import { SITE } from "@/lib/seo";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      // JSON endpoints and the MCP transport are not pages; everything else is.
      { userAgent: "*", allow: "/", disallow: ["/api/", "/mcp", "/openapi.json"] },
    ],
    sitemap: `${SITE.url}/sitemap.xml`,
    host: SITE.url,
  };
}
