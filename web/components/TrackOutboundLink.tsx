"use client";

import type { ReactNode } from "react";

type TrackOutboundLinkProps = {
  href: string;
  productSlug: string;
  shopSlug: string;
  priceHuf: number;
  className?: string;
  children: ReactNode;
};

export function TrackOutboundLink({
  href,
  productSlug,
  shopSlug,
  priceHuf,
  className,
  children,
}: TrackOutboundLinkProps) {
  function trackClick() {
    const body = JSON.stringify({
      productSlug,
      shopSlug,
      priceHuf,
      destinationUrl: href,
    });

    try {
      if (typeof navigator !== "undefined" && "sendBeacon" in navigator) {
        const blob = new Blob([body], { type: "application/json" });
        navigator.sendBeacon("/api/clicks", blob);
        return;
      }
    } catch {
      // Fall through to fetch.
    }

    void fetch("/api/clicks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {
      // Best-effort analytics — never block navigation.
    });
  }

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
      onClick={trackClick}
    >
      {children}
    </a>
  );
}
