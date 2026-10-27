/**
 * Generates robots.txt and sitemap.xml at build time from VITE_SITE_URL.
 *
 * These files used to be static in public/ with a hard-coded
 * "https://your-domain.com". Shipping that is not cosmetic: the <link
 * rel="canonical"> and og:url tags tell search engines that the canonical
 * version of every page lives on a domain you do not own, and the sitemap
 * points crawlers there too. The result is a site that either does not get
 * indexed or passes its ranking signals to someone else's domain.
 *
 * Generating them means the domain is set once, in one place, at deploy time.
 */
import { writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const raw = process.env.VITE_SITE_URL || "http://localhost:8080";
const site = raw.replace(/\/+$/, "");
const dist = resolve(process.cwd(), "dist");
const today = new Date().toISOString().slice(0, 10);

mkdirSync(dist, { recursive: true });

writeFileSync(resolve(dist, "robots.txt"), `User-agent: *
Allow: /

# Nothing behind authentication should ever be crawled.
Disallow: /admin
Disallow: /api/

Sitemap: ${site}/sitemap.xml
`);

writeFileSync(resolve(dist, "sitemap.xml"), `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${site}/</loc>
    <lastmod>${today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
`);

console.log(`[seo] robots.txt + sitemap.xml generated for ${site}`);
if (site.includes("localhost")) {
  console.warn("[seo] WARNING: VITE_SITE_URL is not set — using localhost. " +
               "Set it to your real domain before a public deploy.");
}
