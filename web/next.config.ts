import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const isGithubPages = process.env.GITHUB_PAGES === "true";

const nextConfig: NextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  ...(isGithubPages
    ? {
        output: "export",
        basePath: "/PokeDeals",
        assetPrefix: "/PokeDeals/",
        images: { unoptimized: true },
        trailingSlash: true,
      }
    : {}),
};

export default withNextIntl(nextConfig);
