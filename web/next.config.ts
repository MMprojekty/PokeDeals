import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const isGithubPages = process.env.GITHUB_PAGES === "true";

const nextConfig: NextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: isGithubPages,
  },
  ...(isGithubPages
    ? {
        output: "export",
        basePath: "/PokeDeals",
        images: { unoptimized: true },
      }
    : {}),
};

export default withNextIntl(nextConfig);
